from functools import wraps
from flask import abort, redirect, url_for
from flask_login import current_user


def role_required(*roles):
    """Decorator that restricts access to users with specified roles."""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated:
                return redirect(url_for("auth.login"))
            if current_user.role not in roles:
                abort(403)
            return f(*args, **kwargs)
        return decorated_function
    return decorator


def get_currency_symbol(code):
    symbols = {
        "USD": "$", "EUR": "€", "GBP": "£", "INR": "₹", "JPY": "¥",
        "CNY": "¥", "AUD": "A$", "CAD": "C$", "CHF": "Fr", "KRW": "₩",
        "BRL": "R$", "MXN": "$", "SGD": "S$", "HKD": "HK$", "NOK": "kr",
        "SEK": "kr", "DKK": "kr", "NZD": "NZ$", "ZAR": "R", "RUB": "₽",
        "TRY": "₺", "AED": "د.إ", "SAR": "﷼", "THB": "฿", "IDR": "Rp",
        "MYR": "RM", "PHP": "₱", "VND": "₫", "PKR": "₨", "BDT": "৳",
    }
    return symbols.get(code, code)


EXPENSE_CATEGORIES = [
    "Travel", "Accommodation", "Meals & Entertainment", "Office Supplies",
    "Software & Subscriptions", "Training & Education", "Marketing",
    "Equipment", "Utilities", "Medical", "Miscellaneous"
]
