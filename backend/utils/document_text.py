"""Extract readable text from an uploaded document."""
import base64
import logging
from typing import Optional, Tuple

from utils.local_ocr import read_image, read_scanned_pdf

logger = logging.getLogger(__name__)

# Enough to identify a document without shipping a whole contract to the model.
MAX_EXTRACT_CHARS = 6000

# Below this there is nothing meaningful to match against.
MIN_USEFUL_CHARS = 20

# Claude accepts attachments up to ~5MB once base64-encoded. Anything larger
# is rejected with a clear message rather than failing opaquely upstream.
MAX_ATTACHMENT_BYTES = 3_500_000

IMAGE_TYPES = {
    "jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png",
    "gif": "image/gif", "webp": "image/webp", "heic": "image/heic",
    "heif": "image/heif",
}

# Model image inputs do not accept HEIC even though local OCR does.
ATTACHMENT_IMAGE_TYPES = {
    ext: media_type for ext, media_type in IMAGE_TYPES.items()
    if ext not in {"heic", "heif"}
}


def as_attachment(filename: str, content_type: Optional[str],
                  data: bytes) -> Optional[dict]:
    """
    Package a file for the model to look at directly.

    Claude accepts image blocks and PDF document blocks, which beats OCR: a
    photographed driver's licence or a scanned barangay clearance has no
    extractable text, and shipping the file itself is the only way to verify
    it. Returns {"kind", "media_type", "data"} or None if unsupported/too big.
    """
    if not data or len(data) > MAX_ATTACHMENT_BYTES:
        return None

    name = (filename or "").lower()
    ctype = (content_type or "").lower()

    for ext, mt in ATTACHMENT_IMAGE_TYPES.items():
        if name.endswith("." + ext) or ctype.startswith(mt):
            return {"kind": "image", "media_type": mt,
                    "data": base64.b64encode(data).decode("ascii")}

    if name.endswith(".pdf") or "pdf" in ctype:
        return {"kind": "document", "media_type": "application/pdf",
                "data": base64.b64encode(data).decode("ascii")}

    return None


def extract_text(filename: str, content_type: Optional[str],
                 data: bytes) -> Tuple[Optional[str], str]:
    """Pull text out of an uploaded file."""
    if not data:
        return None, "empty"

    name = (filename or "").lower()
    ctype = (content_type or "").lower()

    if name.endswith(".pdf") or "pdf" in ctype:
        text = _extract_pdf(data)
        if text and len(text.strip()) >= MIN_USEFUL_CHARS:
            return text[:MAX_EXTRACT_CHARS], "pdf"
        # A PDF without embedded text is usually a scan. Render and read it
        # locally so verification still works without a cloud vision model.
        try:
            text = read_scanned_pdf(data)
            if text and len(text.strip()) >= MIN_USEFUL_CHARS:
                return text[:MAX_EXTRACT_CHARS], "local_ocr"
        except Exception as e:
            logger.warning("Local OCR failed for PDF: %s", e)
        return None, "unreadable"

    if (name.endswith((".txt", ".md", ".csv", ".json"))
            or ctype.startswith("text/")
            or "json" in ctype):
        try:
            text = data.decode("utf-8", errors="replace")
        except Exception:
            return None, "unreadable"
        if len(text.strip()) >= MIN_USEFUL_CHARS:
            return text[:MAX_EXTRACT_CHARS], "text"
        return None, "empty"

    # Read images locally first. The optional vision model receives the image
    # too, but is no longer required for photographed IDs and certificates.
    if ctype.startswith("image/") or name.endswith(tuple("." + e for e in IMAGE_TYPES)):
        try:
            text = read_image(data)
            if text and len(text.strip()) >= MIN_USEFUL_CHARS:
                return text[:MAX_EXTRACT_CHARS], "local_ocr"
        except Exception as e:
            logger.warning("Local OCR failed for image: %s", e)
        return None, "unreadable"

    return None, "unsupported"


def _extract_pdf(data: bytes) -> Optional[str]:
    try:
        import io
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(data))
        parts = []
        # A few pages is plenty to identify a certificate or clearance.
        for page in reader.pages[:10]:
            try:
                parts.append(page.extract_text() or "")
            except Exception:
                continue
        return "\n".join(parts).strip() or None
    except Exception as e:
        logger.info("PDF text extraction failed: %s", e)
        return None


def describe(method: str) -> str:
    """Human-readable reason a document could not be verified."""
    return {
        "empty": "the file is empty",
        "image": "it is an image, and no readable text was found",
        "too_large": (f"the file is larger than "
                      f"{MAX_ATTACHMENT_BYTES // 1_000_000}MB, which is more than the "
                      f"model accepts - upload a smaller photo"),
        "unsupported": "the format is not supported - upload a PDF, an image or a text file",
        "unreadable": "no text could be extracted (it may be a scan; try uploading it as an image)",
    }.get(method, "no text could be read")
