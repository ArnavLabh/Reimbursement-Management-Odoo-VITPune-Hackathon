from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app
from flask_login import login_required, current_user
from datetime import date, datetime
from .... import db
from ..models import (
    Expense, ApprovalRule, ApprovalRequest, ApprovalStep,
    ExpenseStatusEnum, ApprovalRequestStatusEnum, User
)
from ..utils import role_required
import os
import uuid
import requests as http_requests

employee_bp = Blueprint("employee", __name__)

ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "pdf", "webp"}


def _allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def _convert_currency(amount, from_currency, to_currency):
    """Convert amount from one currency to another using exchangerate-api."""
    if from_currency.upper() == to_currency.upper():
        return amount
    try:
        url = f"https://api.exchangerate-api.com/v4/latest/{from_currency.upper()}"
        resp = http_requests.get(url, timeout=5)
        data = resp.json()
        rate = data["rates"].get(to_currency.upper())
        if rate:
            return round(amount * rate, 2)
    except Exception:
        pass
    return None


@employee_bp.route("/")
@login_required
@role_required("employee")
def dashboard():
    expenses = (
        Expense.query
        .filter_by(employee_id=current_user.id)
        .order_by(Expense.created_at.desc())
        .all()
    )
    company = current_user.company
    rules = ApprovalRule.query.filter_by(company_id=company.id).all()
    return render_template(
        "employee/dashboard.html",
        expenses=expenses,
        company=company,
        rules=rules,
        today=date.today().isoformat(),
    )


@employee_bp.route("/submit", methods=["POST"])
@login_required
@role_required("employee")
def submit_expense():
    amount_str = request.form.get("amount", "").strip()
    currency = request.form.get("currency", "").strip().upper()
    category = request.form.get("category", "").strip()
    description = request.form.get("description", "").strip()
    expense_date_str = request.form.get("date", "").strip()
    rule_id = request.form.get("rule_id") or None
    receipt_file = request.files.get("receipt")

    errors = []
    if not amount_str:
        errors.append("Amount is required.")
    if not currency:
        errors.append("Currency is required.")
    if not category:
        errors.append("Category is required.")
    if not expense_date_str:
        errors.append("Date is required.")

    try:
        amount = float(amount_str)
        if amount <= 0:
            errors.append("Amount must be positive.")
    except (ValueError, TypeError):
        errors.append("Invalid amount.")
        amount = 0

    try:
        expense_date = datetime.strptime(expense_date_str, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        errors.append("Invalid date format.")
        expense_date = date.today()

    if errors:
        for e in errors:
            flash(e, "error")
        return redirect(url_for("employee.dashboard"))

    company = current_user.company

    # Currency conversion
    amount_in_company_currency = _convert_currency(amount, currency, company.currency_code)

    # Handle receipt upload
    receipt_path = None
    if receipt_file and receipt_file.filename and _allowed_file(receipt_file.filename):
        ext = receipt_file.filename.rsplit(".", 1)[1].lower()
        filename = f"{uuid.uuid4().hex}.{ext}"
        upload_dir = current_app.config["UPLOAD_FOLDER"]
        receipt_file.save(os.path.join(upload_dir, filename))
        receipt_path = f"uploads/{filename}"

    expense = Expense(
        employee_id=current_user.id,
        amount=amount,
        currency=currency,
        amount_in_company_currency=amount_in_company_currency,
        category=category,
        description=description,
        date=expense_date,
        receipt_path=receipt_path,
        status=ExpenseStatusEnum.draft,
        approval_rule_id=int(rule_id) if rule_id else None,
    )
    db.session.add(expense)
    db.session.flush()

    # Kick off approval chain
    if rule_id:
        _initiate_approval(expense, int(rule_id))
    else:
        expense.status = ExpenseStatusEnum.pending

    db.session.commit()
    flash("Expense submitted successfully.", "success")
    return redirect(url_for("employee.dashboard"))


def _initiate_approval(expense, rule_id):
    """
    Seed the first ApprovalRequest in the chain.
    Uses get_effective_approver_sequence() from manager module to stay DRY.
    Edge case: if is_manager_approver is True but employee has no manager assigned,
    the manager step is silently skipped (chain starts at first explicit step).
    """
    from .manager import get_effective_approver_sequence
    rule = ApprovalRule.query.get(rule_id)
    if not rule:
        expense.status = ExpenseStatusEnum.pending
        return

    chain = get_effective_approver_sequence(expense, rule)

    if not chain:
        # Rule exists but has no steps and no manager — treat as auto-approved
        expense.status = ExpenseStatusEnum.approved
        return

    expense.status = ExpenseStatusEnum.pending
    expense.current_step = 1

    ar = ApprovalRequest(
        expense_id=expense.id,
        approver_id=chain[0],
        step_order=1,
        status=ApprovalRequestStatusEnum.pending,
    )
    db.session.add(ar)


@employee_bp.route("/expense/<int:expense_id>")
@login_required
@role_required("employee", "manager", "admin")
def expense_detail(expense_id):
    expense = Expense.query.get_or_404(expense_id)
    # Employees can only view their own; managers/admins can view any in their company
    from ..models import RoleEnum
    if current_user.role == RoleEnum.employee and expense.employee_id != current_user.id:
        from flask import abort
        abort(403)

    # Build timeline from approval requests + project future steps
    from .manager import get_effective_approver_sequence
    approval_requests = expense.approval_requests.order_by(
        ApprovalRequest.step_order.asc()
    ).all()
    acted_step_orders = {ar.step_order for ar in approval_requests}

    timeline = []
    if expense.approval_rule:
        chain = get_effective_approver_sequence(expense, expense.approval_rule)
        for idx, approver_id in enumerate(chain):
            step_num = idx + 1
            approver = User.query.get(approver_id)
            existing_ar = next((ar for ar in approval_requests if ar.step_order == step_num), None)
            timeline.append({
                "step": step_num,
                "approver": approver,
                "request": existing_ar,
                "is_future": existing_ar is None,
            })
    else:
        for ar in approval_requests:
            timeline.append({
                "step": ar.step_order,
                "approver": ar.approver,
                "request": ar,
                "is_future": False,
            })

    return render_template(
        "employee/expense_detail.html",
        expense=expense,
        timeline=timeline,
        company=current_user.company,
    )


@employee_bp.route("/expense/<int:expense_id>/cancel", methods=["POST"])
@login_required
@role_required("employee")
def cancel_expense(expense_id):
    expense = Expense.query.get_or_404(expense_id)
    if expense.employee_id != current_user.id:
        flash("Unauthorized.", "error")
        return redirect(url_for("employee.dashboard"))
    if expense.status not in (ExpenseStatusEnum.draft, ExpenseStatusEnum.pending):
        flash("Cannot cancel an expense that is already processed.", "error")
        return redirect(url_for("employee.dashboard"))
    expense.status = ExpenseStatusEnum.rejected
    db.session.commit()
    flash("Expense cancelled.", "info")
    return redirect(url_for("employee.dashboard"))
