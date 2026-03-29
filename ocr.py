"""
OCR endpoint for receipt scanning.
Accepts a POST with a receipt image (multipart/form-data or base64 JSON).
Returns JSON with extracted expense fields.

Uses the Anthropic Messages API (claude-sonnet-4-20250514) with vision.
Falls back to pytesseract if ANTHROPIC_API_KEY is not set.
"""

import os
import base64
import json
import re
from flask import Blueprint, request, jsonify, current_app
from flask_login import login_required, current_user
from ..utils import role_required

ocr_bp = Blueprint("ocr", __name__, url_prefix="/ocr")

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

ALLOWED_MIME = {
    "jpg":  "image/jpeg",
    "jpeg": "image/jpeg",
    "png":  "image/png",
    "gif":  "image/gif",
    "webp": "image/webp",
}


def _extract_via_anthropic(image_b64: str, media_type: str) -> dict:
    """
    Call Anthropic Messages API with the receipt image.
    Returns a dict with keys: amount, currency, date, description, category, vendor.
    """
    import urllib.request
    import urllib.error

    prompt = """You are an expense receipt OCR assistant.
Examine this receipt image and extract the following fields. 
Return ONLY a valid JSON object with exactly these keys — no extra text, no markdown fences:
{
  "amount": <float or null — the total amount paid>,
  "currency": <3-letter ISO code string or null — e.g. "USD", "INR", "EUR">,
  "date": <"YYYY-MM-DD" string or null>,
  "vendor": <string — business/restaurant/store name, or null>,
  "description": <string — brief description of what was purchased, or null>,
  "category": <one of: "Travel", "Meals & Entertainment", "Accommodation", "Office Supplies", "Software & Tools", "Training & Conferences", "Medical", "Fuel", "Other">
}
If you cannot read a field, set it to null. Never invent values."""

    payload = json.dumps({
        "model": "claude-sonnet-4-20250514",
        "max_tokens": 512,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": media_type,
                            "data": image_b64,
                        }
                    },
                    {
                        "type": "text",
                        "text": prompt,
                    }
                ]
            }
        ]
    }).encode("utf-8")

    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "x-api-key": ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01",
        },
        method="POST",
    )

    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read())

    # Extract the text content block
    text = ""
    for block in data.get("content", []):
        if block.get("type") == "text":
            text += block.get("text", "")

    # Strip any accidental markdown fences
    text = text.strip()
    text = re.sub(r"^```[a-z]*\n?", "", text)
    text = re.sub(r"\n?```$", "", text)

    return json.loads(text.strip())


def _extract_via_tesseract(image_bytes: bytes) -> dict:
    """Fallback: pytesseract + simple regex parsing."""
    try:
        import pytesseract
        from PIL import Image
        import io

        img = Image.open(io.BytesIO(image_bytes))
        text = pytesseract.image_to_string(img)
    except Exception:
        return {}

    result = {
        "amount": None,
        "currency": None,
        "date": None,
        "vendor": None,
        "description": None,
        "category": "Other",
    }

    # Amount: look for patterns like $12.50, USD 100.00, 1,234.56
    amount_match = re.search(
        r"(?:total|amount|grand total)[:\s]*[$€£₹]?\s*([\d,]+\.?\d*)", text, re.I
    )
    if not amount_match:
        amount_match = re.search(r"[$€£₹]\s*([\d,]+\.?\d*)", text)
    if amount_match:
        try:
            result["amount"] = float(amount_match.group(1).replace(",", ""))
        except ValueError:
            pass

    # Date: YYYY-MM-DD, DD/MM/YYYY, MM/DD/YYYY
    date_match = re.search(
        r"(\d{4}[-/]\d{2}[-/]\d{2}|\d{2}[-/]\d{2}[-/]\d{4})", text
    )
    if date_match:
        raw = date_match.group(1).replace("/", "-")
        parts = raw.split("-")
        if len(parts[0]) == 4:
            result["date"] = raw
        else:
            # Try DD-MM-YYYY -> YYYY-MM-DD
            result["date"] = f"{parts[2]}-{parts[1]}-{parts[0]}"

    # Currency symbols
    if "$" in text:
        result["currency"] = "USD"
    elif "€" in text:
        result["currency"] = "EUR"
    elif "£" in text:
        result["currency"] = "GBP"
    elif "₹" in text:
        result["currency"] = "INR"

    # First non-empty line as vendor
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    if lines:
        result["vendor"] = lines[0][:80]
        result["description"] = " ".join(lines[:3])[:200]

    return result


@ocr_bp.route("/scan", methods=["POST"])
@login_required
@role_required("employee", "admin")
def scan():
    """
    Accepts multipart 'receipt' file.
    Returns JSON:
      { success: bool, data: { amount, currency, date, vendor, description, category } }
    """
    receipt = request.files.get("receipt")
    if not receipt or not receipt.filename:
        return jsonify({"success": False, "error": "No file provided."}), 400

    ext = receipt.filename.rsplit(".", 1)[-1].lower() if "." in receipt.filename else ""
    if ext not in ALLOWED_MIME:
        return jsonify({"success": False, "error": "Unsupported file type."}), 400

    image_bytes = receipt.read()
    if len(image_bytes) > 10 * 1024 * 1024:
        return jsonify({"success": False, "error": "File too large (max 10 MB)."}), 400

    media_type = ALLOWED_MIME[ext]

    try:
        if ANTHROPIC_API_KEY:
            image_b64 = base64.standard_b64encode(image_bytes).decode("utf-8")
            data = _extract_via_anthropic(image_b64, media_type)
        else:
            # Tesseract fallback — useful for local dev without an API key
            data = _extract_via_tesseract(image_bytes)

        return jsonify({"success": True, "data": data})

    except Exception as exc:
        current_app.logger.exception("OCR scan failed: %s", exc)
        return jsonify({
            "success": False,
            "error": "OCR failed. Please fill in the fields manually.",
        }), 500
