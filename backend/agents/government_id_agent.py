"""Philippine Government ID check for the current upload only"""
import logging
import sys
from pathlib import Path
from typing import Dict, Optional

sys.path.insert(0, str(Path(__file__).parent.parent))

from agents.json_utils import extract_json

logger = logging.getLogger(__name__)

GOVERNMENT_ID_SYSTEM_PROMPT = """You are Negosyo Copilot's Philippine Government ID checking agent.

Review only the currently uploaded image or PDF. Use the document's visible content and OCR text, never its filename or previous uploads.

Determine whether it appears to be a Philippine government-issued ID, such as:

- PhilID or ePhilID
- Passport
- Driver's license
- UMID, SSS ID, or GSIS ID
- PRC ID
- Postal ID
- Voter's ID
- Senior Citizen ID
- PWD ID
- Other IDs issued by a Philippine government agency

Only accept the document when you can identify at least three of these:

1. ID title
2. Government issuing agency
3. ID or reference number
4. Holder's name or photograph
5. Issue or expiration date
6. QR code, barcode, or machine-readable section

Do not accept receipts, certificates, clearances, school IDs, company IDs, application forms, or random images.

Do not guess unreadable information. Do not claim the ID is authentic—only determine whether it appears to be a valid type of government ID.

Return only JSON:

{
  "verdict": "recognized | incomplete | expired | unreadable | not_government_id | manual_review",
  "document_type": "Detected ID type or unknown",
  "issuing_authority": "Detected agency or unknown",
  "confidence": "high | medium | low",
  "reason": "Short explanation",
  "satisfies_requirement": true
}"""

VERDICTS = {"recognized", "incomplete", "expired", "unreadable",
            "not_government_id", "manual_review"}

# How each verdict lands in the inspection checklist.
VERDICT_STATUS = {
    "recognized": "complete",
    "incomplete": "incomplete",
    "expired": "incomplete",
    "manual_review": "incomplete",
    "unreadable": "unreadable",
    "not_government_id": "missing",
}

# Local OCR prepends its own guess; the model must judge the document, not it.
_CLASSIFICATION_PREFIX = "DOCUMENT CLASSIFICATION:"


def is_government_id_requirement(requirement: str) -> bool:
    text = (requirement or "").lower()
    return "government" in text and "id" in text.replace("-", " ").split()


def _ocr_text(document: Dict) -> str:
    text = document.get("text") or ""
    if text.startswith(_CLASSIFICATION_PREFIX):
        text = text.split("\n", 1)[1] if "\n" in text else ""
    return text[:4000]


def _normalise(raw: Dict) -> Dict:
    """Coerce the model's answer into the documented shape."""
    verdict = raw.get("verdict")
    if verdict not in VERDICTS:
        verdict = "manual_review"
    confidence = raw.get("confidence")
    if confidence not in ("high", "medium", "low"):
        confidence = "low"
    return {
        "verdict": verdict,
        "document_type": raw.get("document_type") or "unknown",
        "issuing_authority": raw.get("issuing_authority") or "unknown",
        "confidence": confidence,
        "reason": raw.get("reason") or "",
        # Only a recognized ID satisfies the requirement, whatever the model says.
        "satisfies_requirement": verdict == "recognized"
                                 and raw.get("satisfies_requirement") is True,
    }


def check_government_id(document: Dict, client) -> Optional[Dict]:
    """
    Run the government ID check on a single upload.

    Returns None when the model call fails so the caller can fall back.
    """
    attachment = document.get("attachment")
    text = _ocr_text(document)

    if not attachment and not text:
        return {
            "verdict": "unreadable",
            "document_type": "unknown",
            "issuing_authority": "unknown",
            "confidence": "high",
            "reason": "No image or readable text was available for this upload.",
            "satisfies_requirement": False,
        }

    # The filename is deliberately left out.
    prompt = ("Check the attached upload.\n\nOCR TEXT:\n\"\"\"\n"
              f"{text or '(none extracted)'}\n\"\"\"")
    try:
        response = client.invoke_model(prompt=prompt,
                                       system_prompt=GOVERNMENT_ID_SYSTEM_PROMPT,
                                       attachments=[attachment] if attachment else None,
                                       max_tokens=512)
        raw = extract_json(response.get("content", ""))
        if not isinstance(raw, dict):
            raise ValueError("government ID check was not a JSON object")
        return _normalise(raw)
    except Exception as e:
        logger.warning("Government ID check unavailable (%s)", e)
        return None


def to_verification(requirement: str, result: Dict) -> Dict:
    """Express a government ID result as an inspection checklist entry."""
    status = VERDICT_STATUS[result["verdict"]]
    if status == "complete" and not result["satisfies_requirement"]:
        status = "incomplete"
    detected = result["document_type"]
    if result["issuing_authority"] != "unknown":
        detected = f"{detected} ({result['issuing_authority']})"
    return {
        "document_name": requirement,
        "status": status,
        "notes": f"{detected}: {result['reason']}".strip(": "),
        "government_id": result,
    }
