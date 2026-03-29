import re
import io
from datetime import datetime


def extract_receipt_data(file_storage):
    """
    Accepts a Werkzeug FileStorage object (image).
    Returns dict with keys: amount, date, description, vendor, category.
    Falls back gracefully if tesseract is not installed.
    """
    try:
        import pytesseract
        from PIL import Image

        image = Image.open(io.BytesIO(file_storage.read()))
        file_storage.seek(0)  # reset for potential re-read
        text = pytesseract.image_to_string(image)
    except ImportError:
        return {"error": "pytesseract not installed", "raw_text": ""}
    except Exception as e:
        return {"error": str(e), "raw_text": ""}

    return _parse_receipt_text(text)


def _parse_receipt_text(text):
    result = {
        "raw_text": text,
        "amount": None,
        "date": None,
        "vendor": None,
        "description": None,
        "category": None,
    }

    lines = [l.strip() for l in text.splitlines() if l.strip()]

    # Vendor: usually the first non-empty line
    if lines:
        result["vendor"] = lines[0]

    # Amount: look for patterns like $12.50, USD 12.50, Total: 12.50
    amount_patterns = [
        r"(?:total|amount|subtotal|grand total)[:\s]*[\$€£₹]?\s*(\d+[\.,]\d{2})",
        r"[\$€£₹]\s*(\d+[\.,]\d{2})",
        r"\b(\d{1,6}[\.,]\d{2})\b",
    ]
    for pattern in amount_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            raw = match.group(1).replace(",", ".")
            try:
                result["amount"] = float(raw)
                break
            except ValueError:
                pass

    # Date: common formats
    date_patterns = [
        (r"\b(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})\b", ["%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y", "%m-%d-%Y",
                                                      "%d/%m/%y", "%m/%d/%y"]),
        (r"\b(\d{4}[/-]\d{2}[/-]\d{2})\b", ["%Y/%m/%d", "%Y-%m-%d"]),
        (r"\b(\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{2,4})\b",
         ["%d %B %Y", "%d %b %Y"]),
    ]
    for pattern, fmts in date_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            raw_date = match.group(1)
            for fmt in fmts:
                try:
                    parsed = datetime.strptime(raw_date, fmt)
                    result["date"] = parsed.strftime("%Y-%m-%d")
                    break
                except ValueError:
                    continue
            if result["date"]:
                break

    # Category heuristics
    text_lower = text.lower()
    category_keywords = {
        "Travel": ["uber", "lyft", "taxi", "flight", "airline", "train", "bus", "toll", "fuel", "petrol", "parking"],
        "Accommodation": ["hotel", "motel", "airbnb", "lodging", "inn", "resort"],
        "Meals & Entertainment": ["restaurant", "cafe", "coffee", "food", "lunch", "dinner", "breakfast", "bar", "pub"],
        "Office Supplies": ["staples", "office depot", "stationery", "paper", "pen", "printer"],
        "Software & Subscriptions": ["subscription", "saas", "software", "license", "aws", "azure", "google cloud"],
        "Medical": ["pharmacy", "medical", "doctor", "hospital", "clinic", "drug", "medicine"],
    }
    for cat, keywords in category_keywords.items():
        if any(kw in text_lower for kw in keywords):
            result["category"] = cat
            break

    # Description: concatenate first few lines (skip vendor)
    if len(lines) > 1:
        result["description"] = " | ".join(lines[1:4])

    return result
