from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from .... import db
from ..models import User, Company, Expense, ApprovalRule, ApprovalStep, RoleEnum
from ..utils import role_required

admin_bp = Blueprint("admin", __name__)


@admin_bp.route("/")
@login_required
@role_required("admin")
def dashboard():
    company = current_user.company
    employees = User.query.filter_by(
        company_id=company.id, role=RoleEnum.employee
    ).all()
    managers = User.query.filter_by(
        company_id=company.id, role=RoleEnum.manager
    ).all()
    all_users = User.query.filter(
        User.company_id == company.id,
        User.id != current_user.id
    ).all()
    approval_rules = ApprovalRule.query.filter_by(company_id=company.id).all()
    all_expenses = (
        Expense.query
        .join(User, Expense.employee_id == User.id)
        .filter(User.company_id == company.id)
        .order_by(Expense.created_at.desc())
        .limit(20)
        .all()
    )
    return render_template(
        "admin/dashboard.html",
        company=company,
        employees=employees,
        managers=managers,
        all_users=all_users,
        approval_rules=approval_rules,
        all_expenses=all_expenses,
    )


@admin_bp.route("/users/create", methods=["POST"])
@login_required
@role_required("admin")
def create_user():
    name = request.form.get("name", "").strip()
    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")
    role = request.form.get("role", "employee")
    manager_id = request.form.get("manager_id") or None

    errors = []
    if not name:
        errors.append("Name is required.")
    if not email:
        errors.append("Email is required.")
    if len(password) < 6:
        errors.append("Password must be at least 6 characters.")
    if role not in ("employee", "manager"):
        errors.append("Invalid role.")
    if User.query.filter_by(email=email).first():
        errors.append(f"Email {email} is already registered.")

    if errors:
        for e in errors:
            flash(e, "error")
        return redirect(url_for("admin.dashboard"))

    user = User(
        name=name,
        email=email,
        role=RoleEnum(role),
        company_id=current_user.company_id,
        manager_id=int(manager_id) if manager_id else None,
    )
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    flash(f"User '{name}' created successfully as {role}.", "success")
    return redirect(url_for("admin.dashboard"))


@admin_bp.route("/users/<int:user_id>/update", methods=["POST"])
@login_required
@role_required("admin")
def update_user(user_id):
    user = User.query.get_or_404(user_id)
    if user.company_id != current_user.company_id:
        flash("Unauthorized.", "error")
        return redirect(url_for("admin.dashboard"))

    role = request.form.get("role")
    manager_id = request.form.get("manager_id") or None

    if role in ("employee", "manager"):
        user.role = RoleEnum(role)
    if manager_id:
        user.manager_id = int(manager_id)
    else:
        user.manager_id = None

    db.session.commit()
    flash(f"User '{user.name}' updated.", "success")
    return redirect(url_for("admin.dashboard"))


@admin_bp.route("/settings", methods=["GET", "POST"])
@login_required
@role_required("admin")
def settings():
    company = current_user.company
    if request.method == "POST":
        name = request.form.get("company_name", "").strip()
        currency_code = request.form.get("currency_code", "").strip().upper()
        country = request.form.get("country", "").strip()
        if name:
            company.name = name
        if currency_code:
            company.currency_code = currency_code
        if country:
            company.country = country
        db.session.commit()
        flash("Company settings updated.", "success")
        return redirect(url_for("admin.settings"))
    return render_template("admin/settings.html", company=company)


@admin_bp.route("/users/<int:user_id>/delete", methods=["POST"])
@login_required
@role_required("admin")
def delete_user(user_id):
    user = User.query.get_or_404(user_id)
    if user.company_id != current_user.company_id:
        flash("Unauthorized.", "error")
        return redirect(url_for("admin.dashboard"))
    if user.id == current_user.id:
        flash("You cannot delete your own admin account.", "error")
        return redirect(url_for("admin.dashboard"))
    db.session.delete(user)
    db.session.commit()
    flash(f"User '{user.name}' deleted.", "success")
    return redirect(url_for("admin.dashboard"))



@login_required
@role_required("admin")
def create_rule():
    name = request.form.get("rule_name", "").strip()
    description = request.form.get("rule_description", "").strip()
    is_manager_approver = bool(request.form.get("is_manager_approver"))
    approval_percentage = request.form.get("approval_percentage") or None
    specific_approver_id = request.form.get("specific_approver_id") or None
    approver_ids = request.form.getlist("approver_ids[]")

    if not name:
        flash("Rule name is required.", "error")
        return redirect(url_for("admin.dashboard"))

    rule = ApprovalRule(
        company_id=current_user.company_id,
        name=name,
        description=description,
        is_manager_approver=is_manager_approver,
        approval_percentage=float(approval_percentage) if approval_percentage else None,
        specific_approver_id=int(specific_approver_id) if specific_approver_id else None,
    )
    db.session.add(rule)
    db.session.flush()

    for idx, approver_id in enumerate(approver_ids):
        if approver_id:
            step = ApprovalStep(
                rule_id=rule.id,
                approver_id=int(approver_id),
                sequence_order=idx + 1,
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
        flash("Unauthorized.", "error")
        return redirect(url_for("admin.dashboard"))
    db.session.delete(rule)
    db.session.commit()
    flash("Approval rule deleted.", "success")
    return redirect(url_for("admin.dashboard"))


@admin_bp.route("/expenses/<int:expense_id>/override", methods=["POST"])
@login_required
@role_required("admin")
def override_expense(expense_id):
    from ..models import Expense, ExpenseStatusEnum, ApprovalRequest, ApprovalRequestStatusEnum
    from datetime import datetime

    expense = Expense.query.get_or_404(expense_id)
    action = request.form.get("action")
    comment = request.form.get("comment", "Admin override")

    if action == "approve":
        expense.status = ExpenseStatusEnum.approved
    elif action == "reject":
        expense.status = ExpenseStatusEnum.rejected
    else:
        flash("Invalid action.", "error")
        return redirect(url_for("admin.dashboard"))

    # Mark all pending approval requests as acted upon
    pending = expense.approval_requests.filter_by(
        status=ApprovalRequestStatusEnum.pending
    ).all()
    for ar in pending:
        ar.status = ApprovalRequestStatusEnum(action + "d")
        ar.comment = comment
        ar.acted_at = datetime.utcnow()

    db.session.commit()
    flash(f"Expense #{expense_id} has been {action}d via admin override.", "success")
    return redirect(url_for("admin.dashboard"))
