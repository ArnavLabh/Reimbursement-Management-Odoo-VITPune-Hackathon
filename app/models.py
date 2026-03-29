from datetime import datetime
from flask_login import UserMixin
from app import db


class Company(db.Model):
    __tablename__ = "companies"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    country = db.Column(db.String(100), nullable=False)
    currency_code = db.Column(db.String(10), nullable=False)
    currency_symbol = db.Column(db.String(10), nullable=False, default="$")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    users = db.relationship("User", backref="company", lazy=True)
    approval_rules = db.relationship("ApprovalRule", backref="company", lazy=True)


class User(db.Model, UserMixin):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    email = db.Column(db.String(150), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(20), nullable=False, default="employee")  # admin, manager, employee
    company_id = db.Column(db.Integer, db.ForeignKey("companies.id"), nullable=False)
    manager_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    manager = db.relationship("User", remote_side=[id], backref="subordinates")
    expenses = db.relationship("Expense", foreign_keys="Expense.employee_id", backref="employee", lazy=True)


class ApprovalRule(db.Model):
    __tablename__ = "approval_rules"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    company_id = db.Column(db.Integer, db.ForeignKey("companies.id"), nullable=False)
    # Manager auto-added as first approver if True
    manager_is_first_approver = db.Column(db.Boolean, default=False)
    # Percentage of approvers that must approve for auto-approval (0 = disabled)
    approval_percentage = db.Column(db.Float, default=0)
    # Specific approver user_id whose single approval triggers auto-approval (None = disabled)
    specific_approver_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    steps = db.relationship("ApprovalStep", backref="rule", lazy=True, cascade="all, delete-orphan",
                            order_by="ApprovalStep.step_order")
    specific_approver = db.relationship("User", foreign_keys=[specific_approver_id])
    expenses = db.relationship("Expense", backref="approval_rule", lazy=True)


class ApprovalStep(db.Model):
    __tablename__ = "approval_steps"
    id = db.Column(db.Integer, primary_key=True)
    rule_id = db.Column(db.Integer, db.ForeignKey("approval_rules.id"), nullable=False)
    approver_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    step_order = db.Column(db.Integer, nullable=False)  # 1-based

    approver = db.relationship("User", foreign_keys=[approver_id])


class Expense(db.Model):
    __tablename__ = "expenses"
    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    company_id = db.Column(db.Integer, db.ForeignKey("companies.id"), nullable=False)
    rule_id = db.Column(db.Integer, db.ForeignKey("approval_rules.id"), nullable=True)

    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=True)
    category = db.Column(db.String(100), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    currency = db.Column(db.String(10), nullable=False)
    amount_in_company_currency = db.Column(db.Float, nullable=True)
    expense_date = db.Column(db.Date, nullable=False)
    receipt_filename = db.Column(db.String(256), nullable=True)
    vendor = db.Column(db.String(150), nullable=True)

    # draft, pending, approved, rejected, cancelled
    status = db.Column(db.String(30), default="draft")
    # Which step is currently awaiting action (1-based). 0 = not started.
    current_step = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    company = db.relationship("Company", foreign_keys=[company_id])
    approvals = db.relationship("ExpenseApproval", backref="expense", lazy=True,
                                cascade="all, delete-orphan", order_by="ExpenseApproval.step_order")


class ExpenseApproval(db.Model):
    __tablename__ = "expense_approvals"
    id = db.Column(db.Integer, primary_key=True)
    expense_id = db.Column(db.Integer, db.ForeignKey("expenses.id"), nullable=False)
    approver_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    step_order = db.Column(db.Integer, nullable=False)
    # pending, approved, rejected, skipped
    status = db.Column(db.String(20), default="pending")
    comment = db.Column(db.Text, nullable=True)
    acted_at = db.Column(db.DateTime, nullable=True)

    approver = db.relationship("User", foreign_keys=[approver_id])
