import os
import uuid
from datetime import date, datetime
from flask import Blueprint, render_template, redirect, url_for, request, flash, jsonify, current_app
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from app import db
from app.models import Expense, ExpenseApproval, ApprovalRule, ApprovalStep, User
from app.utils import role_required, EXPENSE_CATEGORIES
from app.ocr import extract_receipt_data

ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp", "pdf"}

employee_bp = Blueprint("employee", __name__)


def _allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


@employee_bp.route("/dashboard")
@login_required
@role_required("employee")
def dashboard():
    expenses = (Expense.query
                .filter_by(employee_id=current_user.id)
                .order_by(Expense.created_at.desc())
                .all())
    rules = ApprovalRule.query.filter_by(company_id=current_user.company_id).all()
    company = current_user.company
    return render_template(
        "employee/dashboard.html",
        expenses=expenses,
        rules=rules,
        categories=EXPENSE_CATEGORIES,
        company=company,
    )


@employee_bp.route("/submit", methods=["POST"])
@login_required
@role_required("employee")
def submit_expense():
    title = request.form.get("title", "").strip()
    description = request.form.get("description", "").strip()
    category = request.form.get("category", "")
    amount = request.form.get("amount", "")
    currency = request.form.get("currency", current_user.company.currency_code)
    expense_date_str = request.form.get("expense_date", "")
    rule_id = request.form.get("rule_id") or None
    vendor = request.form.get("vendor", "").strip()

    if not all([title, category, amount, expense_date_str]):
        flash("Title, category, amount, and date are required.", "danger")
        return redirect(url_for("employee.dashboard"))

    try:
        amount = float(amount)
        expense_date = datetime.strptime(expense_date_str, "%Y-%m-%d").date()
    except ValueError:
        flash("Invalid amount or date format.", "danger")
        return redirect(url_for("employee.dashboard"))

    # Currency conversion to company currency
    company = current_user.company
    amount_in_company_currency = amount
    if currency != company.currency_code:
        try:
            import requests as req
            resp = req.get(
                f"https://api.exchangerate-api.com/v4/latest/{currency}",
                timeout=5
            )
            rates = resp.json().get("rates", {})
            rate = rates.get(company.currency_code, 1)
            amount_in_company_currency = round(amount * rate, 2)
        except Exception as e:
            current_app.logger.warning(f"Currency conversion failed ({currency}->{company.currency_code}): {e}")
            amount_in_company_currency = amount

    # Handle receipt upload
    receipt_filename = None
    receipt_file = request.files.get("receipt")
    if receipt_file and receipt_file.filename and _allowed_file(receipt_file.filename):
        ext = receipt_file.filename.rsplit(".", 1)[1].lower()
        unique_name = f"{uuid.uuid4().hex}.{ext}"
        receipt_filename = unique_name
        receipt_file.save(os.path.join(current_app.config["UPLOAD_FOLDER"], unique_name))

    expense = Expense(
        employee_id=current_user.id,
        company_id=current_user.company_id,
        rule_id=int(rule_id) if rule_id else None,
        title=title,
        description=description,
        category=category,
        amount=amount,
        currency=currency,
        amount_in_company_currency=amount_in_company_currency,
        expense_date=expense_date,
        receipt_filename=receipt_filename,
        vendor=vendor,
        status="draft",
        current_step=0,
    )
    db.session.add(expense)
    db.session.flush()

    # Build approval chain if rule is selected
    if rule_id:
        _build_approval_chain(expense)
        expense.status = "pending"
        expense.current_step = 1
    else:
        # No rule = auto-approve (or leave as draft for admin to handle)
        expense.status = "pending"

    db.session.commit()
    flash("Expense submitted successfully.", "success")
    return redirect(url_for("employee.dashboard"))


def _build_approval_chain(expense):
    """Build ExpenseApproval rows from the rule, inserting manager as step 1 if required."""
    rule = ApprovalRule.query.get(expense.rule_id)
    if not rule:
        return

    step_order = 1
    added_approver_ids = set()

    # If manager_is_first_approver, add the employee's manager first
    if rule.manager_is_first_approver:
        employee = User.query.get(expense.employee_id)
        if employee and employee.manager_id and employee.manager_id not in added_approver_ids:
            appr = ExpenseApproval(
                expense_id=expense.id,
                approver_id=employee.manager_id,
                step_order=step_order,
                status="pending",
            )
            db.session.add(appr)
            added_approver_ids.add(employee.manager_id)
            step_order += 1
        elif not (employee and employee.manager_id):
            from flask import flash as _flash
            _flash("Warning: rule requires manager approval but you have no assigned manager. Step skipped.", "warning")

    # Add rule-defined steps, skipping duplicates
    for step in rule.steps:
        if step.approver_id not in added_approver_ids:
            appr = ExpenseApproval(
                expense_id=expense.id,
                approver_id=step.approver_id,
                step_order=step_order,
                status="pending",
            )
            db.session.add(appr)
            added_approver_ids.add(step.approver_id)
            step_order += 1


@employee_bp.route("/expenses/<int:expense_id>/cancel", methods=["POST"])
@login_required
@role_required("employee")
def cancel_expense(expense_id):
    expense = Expense.query.get_or_404(expense_id)
    if expense.employee_id != current_user.id:
        flash("Unauthorized.", "danger")
        return redirect(url_for("employee.dashboard"))
    if expense.status not in ("draft", "pending"):
        flash("Cannot cancel an expense that has already been processed.", "warning")
        return redirect(url_for("employee.dashboard"))
    expense.status = "cancelled"
    expense.updated_at = datetime.utcnow()
    db.session.commit()
    flash("Expense cancelled.", "info")
    return redirect(url_for("employee.dashboard"))


@employee_bp.route("/ocr", methods=["POST"])
@login_required
@role_required("employee")
def ocr_receipt():
    """OCR endpoint: accepts uploaded image, returns extracted fields as JSON."""
    file = request.files.get("receipt")
    if not file or not file.filename:
        return jsonify({"error": "No file provided"}), 400

    if not _allowed_file(file.filename):
        return jsonify({"error": "Invalid file type"}), 400

    try:
        data = extract_receipt_data(file)
        return jsonify(data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@employee_bp.route("/convert-currency")
@login_required
def convert_currency():
    """Returns exchange rate from `from` to `to` currencies."""
    from_currency = request.args.get("from", "USD")
    to_currency = request.args.get("to", current_user.company.currency_code)
    try:
        import requests as req
        resp = req.get(
            f"https://api.exchangerate-api.com/v4/latest/{from_currency}",
            timeout=5
        )
        rates = resp.json().get("rates", {})
        rate = rates.get(to_currency, 1)
        return jsonify({"rate": rate, "from": from_currency, "to": to_currency})
    except Exception as e:
        return jsonify({"error": str(e), "rate": 1}), 500
