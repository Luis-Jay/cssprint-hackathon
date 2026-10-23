"""
What each roadmap stage produces, and how it is filed.

A stage's `requirements` are what you bring to apply; its outputs are the
document the office hands back (the DTI certificate, the barangay clearance).
Uploading the output is what proves the stage is done. Verification used to
check uploads against the requirements instead, so a genuine DTI certificate
failed Stage 1 for not being "3 proposed business names".

Roadmaps come from the model, so stages are recognised by the words their
titles reliably contain. Keep in step with stageKind() in the frontend's
roadmap-data.ts.
"""
import re
from typing import Dict, List

DTI_CERTIFICATE = "DTI Certificate of Business Name Registration"
BARANGAY_CLEARANCE = "Barangay Business Clearance"
ZONING_CLEARANCE = "Zoning Clearance"
OCCUPANCY_PERMIT = "Certificate of Occupancy"
SANITARY_PERMIT = "Sanitary Permit"
FIRE_CERTIFICATE = "Fire Safety Inspection Certificate (FSIC)"
MAYORS_PERMIT = "Mayor's Permit (Business Permit)"
BIR_COR = "BIR Certificate of Registration (Form 2303)"

# How each kind of stage is filed. "both" lists the online route first.
FILING: Dict[str, Dict] = {
    "dti": {
        "mode": "both",
        "note": "Register online in about 30 minutes, or at a DTI office or Negosyo Center.",
        "links": [{"label": "bnrs.dti.gov.ph", "url": "https://bnrs.dti.gov.ph"}],
    },
    "barangay": {
        "mode": "in_person",
        "note": "Apply at the barangay hall that covers your business address.",
        "links": [],
    },
    "bureaus": {
        "mode": "in_person",
        "note": "Ask the Bureau of Permits at Manila City Hall where each clearance is processed.",
        "links": [],
    },
    "mayor": {
        "mode": "both",
        "note": "Apply through GO! Manila, or at the Bureau of Permits in Manila City Hall.",
        "links": [{"label": "bpls.gomanila.com", "url": "https://bpls.gomanila.com"}],
    },
    "bir": {
        "mode": "both",
        "note": "Register online through ORUS, or at the Revenue District Office for your address.",
        "links": [{"label": "orus.bir.gov.ph", "url": "https://orus.bir.gov.ph"}],
    },
    "other": {
        "mode": "check",
        "note": "Confirm with the office whether this can be done online.",
        "links": [],
    },
}


def _text(step: Dict) -> str:
    return f"{step.get('title', '')} {step.get('location', '')}".lower()


def stage_kind(step: Dict) -> str:
    """dti | barangay | bureaus | mayor | bir | other"""
    title = (step.get("title") or "").lower()
    text = _text(step)
    # Title first: a Mayor's Permit stage often names the barangay clearance
    # among its requirements or location, never the other way round.
    for source in (title, text):
        if re.search(r"\bdti\b|business name", source):
            return "dti"
        if re.search(r"\bbir\b|internal revenue", source):
            return "bir"
        if re.search(r"mayor|bpls|bplo|business permit", source):
            return "mayor"
        if re.search(r"barangay|brgy", source):
            return "barangay"
        if re.search(r"zoning|locational|sanitary|health|fire|bfp|occupancy|line bureau|clearance", source):
            return "bureaus"
    return "other"


def stage_outputs(step: Dict) -> List[str]:
    """The document(s) whose upload completes this stage."""
    kind = stage_kind(step)
    if kind == "dti":
        return [DTI_CERTIFICATE]
    if kind == "barangay":
        return [BARANGAY_CLEARANCE]
    if kind == "mayor":
        return [MAYORS_PERMIT]
    if kind == "bir":
        return [BIR_COR]
    if kind == "bureaus":
        title = (step.get("title") or "").lower()
        outputs = []
        if re.search(r"zoning|locational", title):
            outputs.append(ZONING_CLEARANCE)
        if "occupancy" in title:
            outputs.append(OCCUPANCY_PERMIT)
        if re.search(r"sanitary|health", title):
            outputs.append(SANITARY_PERMIT)
        if re.search(r"fire|bfp", title):
            outputs.append(FIRE_CERTIFICATE)
        return outputs or [step.get("title") or "Clearance for this stage"]
    return [step.get("title") or "Document for this stage"]


def annotate_roadmap(roadmap: List[Dict]) -> List[Dict]:
    """Add `outputs` and `filing` to each step, for the client and the checker."""
    annotated = []
    for step in roadmap or []:
        kind = stage_kind(step)
        annotated.append({
            **step,
            "outputs": stage_outputs(step),
            "filing": FILING[kind],
        })
    return annotated
