"""Local OCR for photographed and scanned compliance documents.

Tesseract runs as an isolated native process, which keeps document images on
the machine and avoids sharing ML runtimes with the embedding model.
"""
from __future__ import annotations

import io
import logging
import re
import shutil
import subprocess
from typing import Optional

logger = logging.getLogger(__name__)

def _tesseract_command() -> str:
    command = shutil.which("tesseract")
    if not command:
        raise RuntimeError(
            "Tesseract is not installed. Install it with `brew install tesseract` "
            "(macOS) or `apt install tesseract-ocr` (Debian/Ubuntu)."
        )
    return command


def _classify_government_id(text: str) -> Optional[str]:
    """Identify common Philippine IDs only when multiple features agree."""
    normalized = re.sub(r"[^a-z0-9]+", " ", text.lower())
    # Each tuple contains independent evidence groups. At least two groups
    # must match, which prevents a random document mentioning "passport" or
    # "driver's license" from being accepted as the ID itself.
    patterns = (
        ("PhilID", (("philippine identification", "philid", "philsys"),
                    ("republic of the philippines",),
                    ("pcn", "philsys card number"))),
        ("Driver's License", (("driver s license",),
                              ("land transportation office", "lto"),
                              ("license no", "dl code"))),
        ("Passport", (("passport",),
                      ("republic of the philippines", "department of foreign affairs"),
                      ("passport no", "p<phl"))),
        ("UMID", (("unified multi purpose id", "umid"),
                  ("social security system", "government service insurance system"),
                  ("crn", "common reference number"))),
        ("Postal ID", (("postal id",),
                       ("philippine postal corporation", "philpost"),
                       ("prn", "postal reference number"))),
        ("Voter's ID", (("voter s id", "voter identification"),
                        ("commission on elections", "comelec"),
                        ("precinct", "voter s identification number"))),
    )
    for label, evidence_groups in patterns:
        matched_groups = sum(
            1 for markers in evidence_groups
            if any(marker in normalized for marker in markers)
        )
        if matched_groups >= 2:
            return label
    return None


def _annotate(text: str) -> str:
    id_type = _classify_government_id(text)
    if not id_type:
        return text
    return (
        f"DOCUMENT CLASSIFICATION: Philippine government-issued ID; "
        f"owner identity document; type: {id_type}.\n{text}"
    )


def read_image(data: bytes) -> Optional[str]:
    """Extract text from image bytes, returning None when nothing is legible."""
    if not data:
        return None

    # Normalize every supported camera format before passing it to Tesseract.
    # pillow-heif registers HEIC/HEIF support here; EXIF transposition fixes
    # phone photos whose pixels are stored sideways.
    from PIL import Image, ImageOps
    from pillow_heif import register_heif_opener

    register_heif_opener()
    with Image.open(io.BytesIO(data)) as source:
        image = ImageOps.exif_transpose(source).convert("RGB")
        normalized = io.BytesIO()
        image.save(normalized, format="PNG")

    result = subprocess.run(
        [_tesseract_command(), "stdin", "stdout", "-l", "eng", "--psm", "6"],
        input=normalized.getvalue(),
        capture_output=True,
        timeout=30,
        check=False,
    )
    if result.returncode != 0:
        error = result.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"Tesseract failed: {error or result.returncode}")

    text = result.stdout.decode("utf-8", errors="replace").strip()
    return _annotate(text) if text else None


def read_scanned_pdf(data: bytes, max_pages: int = 3) -> Optional[str]:
    """Render the first pages of a scanned PDF and OCR them locally."""
    if not data:
        return None

    import pypdfium2 as pdfium

    pdf = pdfium.PdfDocument(data)
    pages = []
    try:
        for index in range(min(len(pdf), max_pages)):
            page = pdf[index]
            bitmap = page.render(scale=2)
            try:
                buffer = io.BytesIO()
                bitmap.to_pil().convert("RGB").save(buffer, format="JPEG", quality=90)
                text = read_image(buffer.getvalue())
                if text:
                    pages.append(text)
            finally:
                bitmap.close()
                page.close()
    finally:
        pdf.close()

    return "\n\n".join(pages) or None

