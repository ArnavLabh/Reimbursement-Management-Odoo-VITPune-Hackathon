from flask import Blueprint, render_template, redirect, url_for, request, flash
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import login_user, logout_user, login_required, current_user
from app import db
from app.models import User, Company
from app.utils import get_currency_symbol

auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/")
def index():
    if current_user.is_authenticated:
        return _role_redirect(current_user.role)
    return redirect(url_for("auth.login"))


@auth_bp.route("/signup", methods=["GET", "POST"])
def signup():
    # Only allow signup if no admin exists yet (first-time setup)
    if User.query.filter_by(role="admin").first():
        flash("System already initialized. Please log in.", "info")
        return redirect(url_for("auth.login"))

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        company_name = request.form.get("company_name", "").strip()
        country = request.form.get("country", "").strip()
        currency_code = request.form.get("currency_code", "USD").strip()
        currency_symbol = request.form.get("currency_symbol", "$").strip()

        if not all([name, email, password, company_name, country, currency_code]):
            flash("All fields are required.", "danger")
            return render_template("auth/signup.html")

        if User.query.filter_by(email=email).first():
            flash("Email already registered.", "danger")
            return render_template("auth/signup.html")

        company = Company(
            name=company_name,
            country=country,
            currency_code=currency_code,
            currency_symbol=currency_symbol or get_currency_symbol(currency_code)
        )
        db.session.add(company)
        db.session.flush()

        admin = User(
            name=name,
            email=email,
            password_hash=generate_password_hash(password),
            role="admin",
            company_id=company.id
        )
        db.session.add(admin)
        db.session.commit()

        login_user(admin)
        flash(f"Welcome, {name}! Company '{company_name}' created.", "success")
        return redirect(url_for("admin.dashboard"))

    return render_template("auth/signup.html")


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return _role_redirect(current_user.role)

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        remember = request.form.get("remember") == "on"

        user = User.query.filter_by(email=email).first()
        if user and check_password_hash(user.password_hash, password):
            login_user(user, remember=remember)
            next_page = request.args.get("next")
            return redirect(next_page or _role_redirect_url(user.role))
        flash("Invalid email or password.", "danger")

    no_admin = User.query.filter_by(role="admin").first() is None
    return render_template("auth/login.html", no_admin=no_admin)


@auth_bp.route("/logout")
@login_required
def logout():
    logout_user()
    flash("Logged out successfully.", "info")
    return redirect(url_for("auth.login"))


def _role_redirect(role):
    return redirect(_role_redirect_url(role))


def _role_redirect_url(role):
    mapping = {
        "admin": url_for("admin.dashboard"),
        "manager": url_for("manager.dashboard"),
        "employee": url_for("employee.dashboard"),
    }
    return mapping.get(role, url_for("auth.login"))
