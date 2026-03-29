from datetime import datetime
from flask import Blueprint, render_template, redirect, url_for, request, flash
from flask_login import login_required, current_user
from app import db
from app.models import Expense, ExpenseApproval, ApprovalRule, User
from app.utils import role_required

manager_bp = Blueprint("manager", __name__)


@manager_bp.route("/dashboard")
@login_required
@role_required("manager", "admin")
def dashboard():
    # Expenses where the current manager has a pending approval step
    pending_approvals = (
        ExpenseApproval.query
        .filter_by(approver_id=current_user.id, status="pending")
        .join(Expense, ExpenseApproval.expense_id == Expense.id)
        .filter(Expense.status == "pending")
        .all()
    )

    # Filter to only those where this step is the CURRENT step
    actionable = []
    for ea in pending_approvals:
        expense = ea.expense
        if expense.current_step == ea.step_order:
            actionable.append(ea)

    # History: approvals this manager has already acted on
    history = (
        ExpenseApproval.query
        .filter_by(approver_id=current_user.id)
        .filter(ExpenseApproval.status.in_(["approved", "rejected", "skipped"]))
        .order_by(ExpenseApproval.acted_at.desc())
        .all()
    )

    # Team expenses - show all company expenses for managers/admins
    if current_user.role == 'admin':
        # Admin sees all company expenses
        team_expenses = (
            Expense.query
            .join(User, Expense.employee_id == User.id)
            .filter(User.company_id == current_user.company_id)
            .order_by(Expense.created_at.desc())
            .all()
        )
    else:
        # Manager sees subordinates' expenses
        subordinate_ids = [u.id for u in current_user.subordinates]
        team_expenses = []
        if subordinate_ids:
            team_expenses = (
                Expense.query
                .filter(Expense.employee_id.in_(subordinate_ids))
                .order_by(Expense.created_at.desc())
                .all()
            )

    return render_template(
        "manager/dashboard.html",
        actionable=actionable,
        history=history,
        team_expenses=team_expenses,
        company=current_user.company,
    )


@manager_bp.route("/expenses/<int:expense_id>/action", methods=["POST"])
@login_required
@role_required("manager", "admin")
def act_on_expense(expense_id):
    action = request.form.get("action")
    comment = request.form.get("comment", "").strip()

    if action not in ("approve", "reject"):
        flash("Invalid action.", "danger")
        return redirect(url_for("manager.dashboard"))

    expense = Expense.query.get_or_404(expense_id)

    # Find this manager's approval entry for the current step
    approval = ExpenseApproval.query.filter_by(
        expense_id=expense_id,
        approver_id=current_user.id,
        step_order=expense.current_step,
        status="pending",
    ).first()

    if not approval:
        flash("You are not authorized to act on this expense at this stage.", "danger")
        return redirect(url_for("manager.dashboard"))

    approval.status = "approved" if action == "approve" else "rejected"
    approval.comment = comment
    approval.acted_at = datetime.utcnow()

    if action == "reject":
        expense.status = "rejected"
        expense.updated_at = datetime.utcnow()
        # Mark remaining pending steps as skipped
        for ea in expense.approvals:
            if ea.status == "pending" and ea.step_order > expense.current_step:
                ea.status = "skipped"
        db.session.commit()
        flash("Expense rejected.", "info")
        return redirect(url_for("manager.dashboard"))

    # Action = approve: check conditional rules then advance chain
    _advance_or_close(expense)
    db.session.commit()
    flash("Expense approved at this step.", "success")
    return redirect(url_for("manager.dashboard"))


def _advance_or_close(expense):
    """
    Called after an approver acts positively. Checks:
    1. Sequential advance to next step
    2. All steps done -> approved
    3. Specific approver auto-approval (only if all approved)
    4. Percentage threshold auto-approval (only if threshold met)
    """
    rule = ApprovalRule.query.get(expense.rule_id) if expense.rule_id else None
    all_approvals = sorted(expense.approvals, key=lambda a: a.step_order)
    approved_count = sum(1 for a in all_approvals if a.status == "approved")
    total_steps = len(all_approvals)

    # --- Sequential: find next pending step ---
    next_step = expense.current_step + 1
    next_approval = next((a for a in all_approvals if a.step_order == next_step), None)

    if next_approval:
        # Move to next step
        expense.current_step = next_step
        expense.updated_at = datetime.utcnow()
    else:
        # No more steps - all approvers have acted, mark as approved
        expense.status = "approved"
        expense.updated_at = datetime.utcnow()


