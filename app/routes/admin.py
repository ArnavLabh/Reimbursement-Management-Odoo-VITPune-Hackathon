from flask import Blueprint, render_template, redirect, url_for, request, flash, jsonify
from flask_login import login_required, current_user
from werkzeug.security import generate_password_hash
from datetime import datetime
from app import db
from app.models import User, Company, ApprovalRule, ApprovalStep, Expense, ExpenseApproval
from app.utils import role_required, EXPENSE_CATEGORIES

admin_bp = Blueprint("admin", __name__)


@admin_bp.route("/dashboard")
@login_required
@role_required("admin")
def dashboard():
    company = current_user.company
    users = User.query.filter_by(company_id=company.id).all()
    rules = ApprovalRule.query.filter_by(company_id=company.id).all()
    expenses = (Expense.query
                .join(User, Expense.employee_id == User.id)
                .filter(User.company_id == company.id)
                .order_by(Expense.created_at.desc())
                .all())
    managers_and_admins = [u for u in users if u.role in ("manager", "admin")]
    employees_only = [u for u in users if u.role == "employee"]
    return render_template(
        "admin/dashboard.html",
        users=users,
        rules=rules,
        expenses=expenses,
        managers=managers_and_admins,
        all_approvers=managers_and_admins,
        employees=employees_only,
        categories=EXPENSE_CATEGORIES,
        company=company,
    )


# ── User Management ──────────────────────────────────────────────

@admin_bp.route("/users/create", methods=["POST"])
@login_required
@role_required("admin")
def create_user():
    name = request.form.get("name", "").strip()
    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")
    role = request.form.get("role", "employee")
    manager_id = request.form.get("manager_id") or None

    if not all([name, email, password, role]):
        flash("All fields are required.", "danger")
        return redirect(url_for("admin.dashboard"))

    if User.query.filter_by(email=email).first():
        flash("Email already in use.", "danger")
        return redirect(url_for("admin.dashboard"))

    if role not in ("employee", "manager", "admin"):
        flash("Invalid role.", "danger")
        return redirect(url_for("admin.dashboard"))

    user = User(
        name=name,
        email=email,
        password_hash=generate_password_hash(password),
        role=role,
        company_id=current_user.company_id,
        manager_id=int(manager_id) if manager_id else None,
    )
    db.session.add(user)
    db.session.commit()
    flash(f"User '{name}' created as {role}.", "success")
    return redirect(url_for("admin.dashboard"))


@admin_bp.route("/users/<int:user_id>/edit", methods=["POST"])
@login_required
@role_required("admin")
def edit_user(user_id):
    user = User.query.get_or_404(user_id)
    if user.company_id != current_user.company_id:
        flash("Unauthorized.", "danger")
        return redirect(url_for("admin.dashboard"))

    user.name = request.form.get("name", user.name).strip()
    user.role = request.form.get("role", user.role)
    manager_id = request.form.get("manager_id") or None
    user.manager_id = int(manager_id) if manager_id else None

    new_password = request.form.get("password", "").strip()
    if new_password:
        user.password_hash = generate_password_hash(new_password)

    db.session.commit()
    flash(f"User '{user.name}' updated.", "success")
    return redirect(url_for("admin.dashboard"))


@admin_bp.route("/users/<int:user_id>/delete", methods=["POST"])
@login_required
@role_required("admin")
def delete_user(user_id):
    user = User.query.get_or_404(user_id)
    if user.id == current_user.id:
        flash("Cannot delete yourself.", "danger")
        return redirect(url_for("admin.dashboard"))
    if user.company_id != current_user.company_id:
        flash("Unauthorized.", "danger")
        return redirect(url_for("admin.dashboard"))
    db.session.delete(user)
    db.session.commit()
    flash("User deleted.", "success")
    return redirect(url_for("admin.dashboard"))


# ── Approval Rules ────────────────────────────────────────────────

@admin_bp.route("/rules/create", methods=["POST"])
@login_required
@role_required("admin")
def create_rule():
    name = request.form.get("rule_name", "").strip()
    manager_is_first = request.form.get("manager_is_first_approver") == "on"
    approval_percentage = float(request.form.get("approval_percentage") or 0)
    specific_approver_id = request.form.get("specific_approver_id") or None
    approver_ids = request.form.getlist("approver_ids[]")

    if not name:
        flash("Rule name is required.", "danger")
        return redirect(url_for("admin.dashboard"))

    # Ensure at least one approval mechanism is configured
    has_steps = any(aid for aid in approver_ids if aid)
    if not manager_is_first and not has_steps and not specific_approver_id and not approval_percentage:
        flash("At least one approver or rule condition must be configured.", "danger")
        return redirect(url_for("admin.dashboard"))

    rule = ApprovalRule(
        name=name,
        company_id=current_user.company_id,
        manager_is_first_approver=manager_is_first,
        approval_percentage=approval_percentage,
        specific_approver_id=int(specific_approver_id) if specific_approver_id else None,
    )
    db.session.add(rule)
    db.session.flush()

    for order, approver_id in enumerate(approver_ids, start=1):
        if approver_id:
            step = ApprovalStep(
                rule_id=rule.id,
                approver_id=int(approver_id),
                step_order=order,
            )
            db.session.add(step)

    db.session.commit()
    flash(f"Approval rule '{name}' created.", "success")
    return redirect(url_for("admin.dashboard"))


@admin_bp.route("/rules/<int:rule_id>/delete", methods=["POST"])
@login_required
@role_required("admin")
def delete_rule(rule_id):
    rule = ApprovalRule.query.get_or_404(rule_id)
    if rule.company_id != current_user.company_id:
        flash("Unauthorized.", "danger")
        return redirect(url_for("admin.dashboard"))
    db.session.delete(rule)
    db.session.commit()
    flash("Rule deleted.", "success")
    return redirect(url_for("admin.dashboard"))


# ── Expense Override ──────────────────────────────────────────────

@admin_bp.route("/expenses/<int:expense_id>/override", methods=["POST"])
@login_required
@role_required("admin")
def override_expense(expense_id):
    expense = Expense.query.get_or_404(expense_id)
    action = request.form.get("action")
    comment = request.form.get("comment", "Admin override").strip()

    if action == "approve":
        expense.status = "approved"
    elif action == "reject":
        expense.status = "rejected"
    else:
        flash("Invalid action.", "danger")
        return redirect(url_for("admin.dashboard"))

    # Mark all pending approvals as skipped
    for appr in expense.approvals:
        if appr.status == "pending":
            appr.status = "skipped"
            appr.comment = comment
            appr.acted_at = datetime.utcnow()

    expense.updated_at = datetime.utcnow()
    db.session.commit()
    flash(f"Expense #{expense_id} {action}d by admin override.", "success")
    return redirect(url_for("admin.dashboard"))


# ── Company Settings ──────────────────────────────────────────────

@admin_bp.route("/settings", methods=["GET", "POST"])
@login_required
@role_required("admin")
def settings():
    company = current_user.company

    if request.method == "POST":
        company.name = request.form.get("company_name", company.name).strip()
        company.country = request.form.get("country", company.country).strip()
        currency_code = request.form.get("currency_code", company.currency_code).strip().upper()
        company.currency_code = currency_code
        from app.utils import get_currency_symbol
        company.currency_symbol = get_currency_symbol(currency_code)

        db.session.commit()
        flash("Company settings updated successfully.", "success")
        return redirect(url_for("admin.dashboard"))

    return render_template("settings.html", company=company)
