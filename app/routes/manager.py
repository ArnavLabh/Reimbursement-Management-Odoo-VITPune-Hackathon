from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from datetime import datetime
from .... import db
from ..models import (
    User, Expense, ApprovalRequest, ApprovalRule, ApprovalStep,
    ExpenseStatusEnum, ApprovalRequestStatusEnum, RoleEnum
)
from ..utils import role_required

manager_bp = Blueprint("manager", __name__)


@manager_bp.route("/")
@login_required
@role_required("manager", "admin")
def dashboard():
    # Pending requests assigned to this manager/approver
    pending_requests = (
        ApprovalRequest.query
        .filter_by(approver_id=current_user.id, status=ApprovalRequestStatusEnum.pending)
        .join(Expense, ApprovalRequest.expense_id == Expense.id)
        .filter(Expense.status == ExpenseStatusEnum.pending)
        .order_by(ApprovalRequest.created_at.asc())
        .all()
    )

    # All requests this user has acted on (history)
    acted_requests = (
        ApprovalRequest.query
        .filter(
            ApprovalRequest.approver_id == current_user.id,
            ApprovalRequest.status != ApprovalRequestStatusEnum.pending,
        )
        .order_by(ApprovalRequest.acted_at.desc())
        .limit(20)
        .all()
    )

    # Team expenses (employees who report to this manager)
    direct_reports = User.query.filter_by(manager_id=current_user.id).all()
    report_ids = [u.id for u in direct_reports]
    team_expenses = []
    if report_ids:
        team_expenses = (
            Expense.query
            .filter(Expense.employee_id.in_(report_ids))
            .order_by(Expense.created_at.desc())
            .limit(30)
            .all()
        )

    company = current_user.company

    return render_template(
        "manager/dashboard.html",
        pending_requests=pending_requests,
        acted_requests=acted_requests,
        team_expenses=team_expenses,
        company=company,
    )


@manager_bp.route("/approve/<int:request_id>", methods=["POST"])
@login_required
@role_required("manager", "admin")
def approve(request_id):
    ar = ApprovalRequest.query.get_or_404(request_id)
    if ar.approver_id != current_user.id:
        flash("You are not authorized to act on this request.", "error")
        return redirect(url_for("manager.dashboard"))
    if ar.status != ApprovalRequestStatusEnum.pending:
        flash("This request has already been acted upon.", "info")
        return redirect(url_for("manager.dashboard"))

    comment = request.form.get("comment", "").strip()
    ar.status = ApprovalRequestStatusEnum.approved
    ar.comment = comment
    ar.acted_at = datetime.utcnow()

    _advance_or_close(ar.expense, "approve")

    db.session.commit()
    flash(f"Expense #{ar.expense_id} approved.", "success")
    return redirect(url_for("manager.dashboard"))


@manager_bp.route("/reject/<int:request_id>", methods=["POST"])
@login_required
@role_required("manager", "admin")
def reject(request_id):
    ar = ApprovalRequest.query.get_or_404(request_id)
    if ar.approver_id != current_user.id:
        flash("You are not authorized to act on this request.", "error")
        return redirect(url_for("manager.dashboard"))
    if ar.status != ApprovalRequestStatusEnum.pending:
        flash("This request has already been acted upon.", "info")
        return redirect(url_for("manager.dashboard"))

    comment = request.form.get("comment", "").strip()
    ar.status = ApprovalRequestStatusEnum.rejected
    ar.comment = comment
    ar.acted_at = datetime.utcnow()

    expense = ar.expense
    expense.status = ExpenseStatusEnum.rejected

    db.session.commit()
    flash(f"Expense #{ar.expense_id} rejected.", "info")
    return redirect(url_for("manager.dashboard"))


def _advance_or_close(expense, action):
    """
    After an approval, check conditional rules and decide whether to:
    - Auto-approve (specific approver rule OR percentage-of-FULL-CHAIN met)
    - Create the next ApprovalRequest in sequence
    - Mark expense as fully approved once all steps pass
    """
    rule = expense.approval_rule
    if not rule:
        expense.status = ExpenseStatusEnum.approved
        return

    # Full chain tells us the TOTAL number of approvers planned (not just created so far).
    # This is critical for the percentage rule: 60% of 5 approvers = 3, not 60% of 1.
    full_chain = get_effective_approver_sequence(expense, rule)
    total_chain_length = len(full_chain)

    all_requests = expense.approval_requests.order_by(
        ApprovalRequest.step_order.asc()
    ).all()

    approved_count = sum(1 for r in all_requests if r.status == ApprovalRequestStatusEnum.approved)

    # --- Specific approver rule (hybrid: OR logic — auto-approves regardless of %) ---
    if rule.specific_approver_id:
        specific_approved = any(
            r.approver_id == rule.specific_approver_id
            and r.status == ApprovalRequestStatusEnum.approved
            for r in all_requests
        )
        if specific_approved:
            expense.status = ExpenseStatusEnum.approved
            return

    # --- Percentage rule: use FULL chain as denominator ---
    if rule.approval_percentage and total_chain_length > 0:
        pct = (approved_count / total_chain_length) * 100
        if pct >= rule.approval_percentage:
            expense.status = ExpenseStatusEnum.approved
            return

    # --- Sequential: advance to next step ---
    current_step = expense.current_step or 1
    next_step = current_step + 1

    if next_step <= total_chain_length:
        next_approver_id = full_chain[next_step - 1]
        new_ar = ApprovalRequest(
            expense_id=expense.id,
            approver_id=next_approver_id,
            step_order=next_step,
            status=ApprovalRequestStatusEnum.pending,
        )
        db.session.add(new_ar)
        expense.current_step = next_step
    else:
        # Reached end of chain. If no conditional rule fired, all steps must be approved.
        # approved_count == total_chain_length means every step in the chain approved.
        if approved_count >= total_chain_length:
            expense.status = ExpenseStatusEnum.approved
        # Otherwise it stays "pending" (edge case: chain ended without 100% but also under %)


def get_effective_approver_sequence(expense, rule):
    """
    Returns the fully ordered list of approver user IDs for this expense + rule.
    Manager step (if is_manager_approver and manager exists) is always index 0.
    Exported so employee.py can call it identically.
    """
    sequence = []
    employee = User.query.get(expense.employee_id)

    if rule.is_manager_approver and employee and employee.manager_id:
        sequence.append(employee.manager_id)

    steps = sorted(rule.steps, key=lambda s: s.sequence_order)
    for step in steps:
        sequence.append(step.approver_id)

    return sequence
