"""
Deterministic checks on the fields the model reads off a document.

The model reads (business name, dates, numbers); this code decides. That keeps
the verdict explainable - "the certificate says JUAN'S BAKESHOP" - and lets
the rules be unit-tested, which a prompt cannot be.
"""
import re
import unicodedata
from datetime import date
from typing import Dict, List, Optional

# Words that say what kind of business it is rather than which one, so
# "Manila Artisanal Cafe" and "Manila Artisanal Café Shop" still match.
_GENERIC = {
    "the", "and", "of", "ng", "sa", "at",
    "inc", "corp", "corporation", "co", "company", "opc", "enterprise",
    "enterprises", "trading", "store", "shop", "services", "service",
}


def _tokens(name: str) -> set:
    plain = unicodedata.normalize("NFKD", name or "").encode("ascii", "ignore").decode()
    words = re.findall(r"[a-z0-9]+", plain.lower())
    return {w for w in words if w not in _GENERIC and len(w) > 1}


def names_match(on_document: str, expected: str) -> bool:
    """Same business name, ignoring case, accents, punctuation and filler words."""
    a, b = _tokens(on_document), _tokens(expected)
    if not a or not b:
        return False
    if a <= b or b <= a:
        return True
    return len(a & b) / len(a | b) >= 0.6


def parse_date(value) -> Optional[date]:
    """ISO dates from the model; anything else is treated as unreadable."""
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def check_fields(fields: Dict, profile: Dict, today: Optional[date] = None) -> List[Dict]:
    """
    Checks for a document the model judged to be the stage's output.

    Each check is {"label", "ok", "detail"}; ok is None when the field could
    not be read, which is reported but does not by itself fail the document.
    """
    today = today or date.today()
    checks = []

    expected = (profile or {}).get("business_name") or ""
    found = (fields or {}).get("business_name") or ""
    if expected:
        if not found:
            checks.append({"label": "Business name", "ok": None,
                           "detail": "Couldn't read a business name on the document."})
        elif names_match(found, expected):
            checks.append({"label": "Business name", "ok": True,
                           "detail": f"Matches {expected}."})
        else:
            checks.append({"label": "Business name", "ok": False,
                           "detail": f"The document says {found}, but your business is {expected}."})

    expiry = parse_date((fields or {}).get("expiry_date"))
    if expiry:
        if expiry < today:
            checks.append({"label": "Still valid", "ok": False,
                           "detail": f"Expired on {expiry:%b %d, %Y}."})
        else:
            checks.append({"label": "Still valid", "ok": True,
                           "detail": f"Valid until {expiry:%b %d, %Y}."})

    issued = parse_date((fields or {}).get("issue_date"))
    if issued and issued > today:
        checks.append({"label": "Issue date", "ok": False,
                       "detail": f"Issued {issued:%b %d, %Y}, which is in the future."})

    return checks


def failed(checks: List[Dict]) -> List[Dict]:
    return [c for c in checks if c["ok"] is False]
