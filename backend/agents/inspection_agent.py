"""Inspection Readiness Agent Verifies uploaded documents against the required checklist"""
import json
import logging
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional

sys.path.insert(0, str(Path(__file__).parent.parent))

from agents.state import AgentState
from agents.json_utils import extract_json
from agents.government_id_agent import (
    check_government_id,
    is_government_id_requirement,
    to_verification,
)
from utils.llm_client import llm_is_configured, get_llm_client
from utils.document_text import describe
import observability as obs

logger = logging.getLogger(__name__)

AGENT_NAME = "Inspection Readiness Agent"

# Words that carry no identifying weight when matching a requirement.
STOPWORDS = {
    "the", "and", "for", "with", "from", "your", "you", "a", "an", "of", "or",
    "to", "in", "on", "at", "by", "is", "are", "be", "any", "all", "each",
    "valid", "original", "copy", "copies", "photocopy", "certified", "proof",
    "document", "documents", "form", "forms", "required", "if", "applicable",
    "options", "option", "e.g", "etc",
}

# Share of a requirement's significant words that must appear in the document
# text before it counts as satisfied.
MATCH_THRESHOLD = 0.5

INSPECTION_SYSTEM_PROMPT = """You are a document verification officer for Manila LGU compliance.

You are given an uploaded document - as extracted text, as an attached image,
as an attached PDF, or some combination - and a checklist of required documents.
Decide, for each requirement, whether THIS upload satisfies it.

Judge on content, never on the filename. A filename can say anything.

When an image or PDF is attached, READ IT. Identify the document type from what
you can see: the issuing authority, the title, card layout, reference numbers,
photo and signature panels. A Philippine driver's licence, PhilID, passport,
UMID, postal ID or voter's ID all satisfy a "valid government ID" requirement -
name the one you actually see in your note.

status values:
- "complete"   - the extracted text clearly IS this document (issuing office,
                 title, reference numbers or fields consistent with it)
- "incomplete" - it is plausibly the right kind of document but key details are
                 missing, illegible or blank
- "missing"    - the upload is not this document at all
- "unreadable" - the attachment is too blurred, cropped or dark to identify

Be strict. If the upload is unrelated to the requirement - a receipt, a selfie,
lorem ipsum, an unrelated letter - the status is "missing" and the note must say
what the document actually appears to be.

Do not mark anything "complete" without positive evidence in the text.

Return ONLY valid JSON. Temperature is 0, so be deterministic and factual."""


def _significant_words(text: str) -> set:
    """
    Identifying words from a requirement, minus filler.

    Two-character tokens are kept: "ID" and "TIN" carry most of the meaning in
    "Valid government ID" and dropping them left the requirement matching on
    "government" alone.
    """
    words = re.findall(r"[a-z0-9]+", (text or "").lower())
    return {w for w in words if len(w) >= 2 and w not in STOPWORDS}


def _required_ratio(needed: set) -> float:
    """
    How much of a requirement must appear before it counts as satisfied.

    Short requirements carry little signal per word, so they must match in
    full; longer ones tolerate wording differences.
    """
    return 1.0 if len(needed) <= 2 else MATCH_THRESHOLD


def simple_document_check(
    roadmap: List[Dict],
    documents: List[Dict],
    target_step: Optional[Dict] = None,
) -> List[Dict]:
    """Deterministic verification used when the model is unavailable."""
    steps = [target_step] if target_step else roadmap
    required_docs = []
    for step in steps:
        required_docs.extend(step.get("requirements", []))

    results = []
    for req_doc in required_docs:
        needed = _significant_words(req_doc)
        if not needed:
            results.append({
                "document_name": req_doc,
                "status": "missing",
                "notes": "Please upload this document",
            })
            continue

        best = None
        best_score = 0.0
        for doc in documents:
            text = (doc.get("text") or "")
            if not text:
                continue
            # Government-ID requirements require the trusted classification
            # produced by local OCR. Ordinary text containing words like
            # "government" and "ID" is not identity evidence.
            if {"government", "id"}.issubset(needed) and not text.startswith(
                "DOCUMENT CLASSIFICATION: Philippine government-issued ID;"
            ):
                continue
            present = _significant_words(text)
            score = len(needed & present) / len(needed)
            if score > best_score:
                best_score, best = score, doc

        if best_score >= _required_ratio(needed):
            results.append({
                "document_name": req_doc,
                "status": "complete",
                "notes": f"Matched content in {best.get('name', 'the upload')}",
                "matched": best.get("name"),
                "confidence": round(best_score, 2),
            })
            continue

        # Distinguish "nothing readable" from "readable but wrong", because the
        # user needs different advice in each case.
        unreadable = [d for d in documents if not d.get("text")]
        if documents and len(unreadable) == len(documents):
            method = unreadable[0].get("extract_method", "unreadable")
            reason = describe(method)
            # Advice has to match the actual problem
            advice = ("Try again shortly." if method == "image"
                      else "Upload a text-based PDF or a photo of the document.")
            results.append({
                "document_name": req_doc,
                "status": "unreadable",
                "notes": f"Could not verify - {reason}. {advice}",
            })
        elif best_score > 0:
            results.append({
                "document_name": req_doc,
                "status": "incomplete",
                "notes": (f"The upload mentions only some of what this requires "
                          f"({int(best_score * 100)}% match). Check you uploaded "
                          f"the right document."),
                "confidence": round(best_score, 2),
            })
        else:
            results.append({
                "document_name": req_doc,
                "status": "missing",
                "notes": "The uploaded file does not appear to be this document",
            })

    return results


def _target_step(state: AgentState) -> Optional[Dict]:
    """The roadmap step this upload was filed under, if the client said."""
    step_number = state.get("pending_step")
    if not step_number:
        return None
    for step in state.get("roadmap") or []:
        if step.get("step_number") == step_number:
            return step
    return None


def _docs_block(documents: List[Dict]) -> str:
    """Render uploads for the prompt, leading with their extracted text."""
    blocks = []
    for doc in documents:
        text = doc.get("text")
        header = (f"- FILE: {doc.get('name', 'Unknown')} "
                  f"({doc.get('type', 'unknown type')}, {doc.get('size', 0)} bytes)")
        if text:
            blocks.append(f"{header}\n  EXTRACTED TEXT:\n  \"\"\"\n{text[:4000]}\n  \"\"\"")
        else:
            why = describe(doc.get("extract_method", "unreadable"))
            blocks.append(f"{header}\n  NO TEXT COULD BE EXTRACTED - {why}. "
                          f"Treat as unreadable; do NOT mark anything complete from it.")
    return "\n\n".join(blocks)


def inspection_agent(state: AgentState) -> AgentState:
    """Verify documents against roadmap requirements"""
    logger.info("Inspection Readiness Agent running")

    roadmap = state.get("roadmap", [])
    # Verify only the file submitted in this request. Previously the entire
    # upload history was checked, so one old valid ID made every later upload
    # appear valid.
    pending_document = state.get("pending_document")
    documents = [pending_document] if pending_document else state.get("documents", [])

    if not roadmap:
        state["assistant_reply"] = (
            "I need your compliance roadmap before I can check documents. "
            "Tell me about your business first and I'll build one."
        )
        state["responding_agent"] = AGENT_NAME
        return state

    if not documents:
        # Leave `documents` alone
        state["assistant_reply"] = (
            "No documents uploaded yet. Drop your certificates into any unlocked "
            "stage and I'll check them against the requirements."
        )
        state["responding_agent"] = AGENT_NAME
        return state

    step = _target_step(state)
    scope = [step] if step else roadmap
    required_docs = [r for s in scope for r in s.get("requirements", [])]

    obs.emit("agent", f"Verifying {len(documents)} upload(s) against "
                      f"{len(required_docs)} requirement(s)",
             agent=AGENT_NAME,
             step=step.get("title") if step else "entire roadmap",
             readable=[d.get("name") for d in documents if d.get("text")],
             unreadable=[d.get("name") for d in documents if not d.get("text")])

    attachments = [d["attachment"] for d in documents if d.get("attachment")]

    # Only give up when there is neither text NOR a file the model can look at.
    if not any(d.get("text") for d in documents) and not attachments:
        results = simple_document_check(roadmap, documents, step)
        state["verification"] = results
        state["assistant_reply"] = _summarise(results, step)
        state["responding_agent"] = AGENT_NAME
        obs.emit("fallback", "No extractable text - cannot confirm anything",
                 agent=AGENT_NAME, status="warn")
        return state

    # Local OCR is sufficient for deterministic requirement matching. Avoid
    # a doomed network request (and keep document images local) when Gemini
    # has not been configured.
    if not llm_is_configured():
        results = simple_document_check(roadmap, documents, step)
        state["verification"] = results
        state["assistant_reply"] = _summarise(results, step)
        state["responding_agent"] = AGENT_NAME
        obs.emit("fallback", "Local OCR/content matcher used; Gemini not configured",
                 agent=AGENT_NAME, status="ok")
        return state

    client = get_llm_client()

    # Government ID requirements get their own stricter check.
    id_reqs = [r for r in required_docs if is_government_id_requirement(r)]
    other_reqs = [r for r in required_docs if not is_government_id_requirement(r)]
    id_results = _check_government_ids(id_reqs, documents, client, roadmap, step)

    if not other_reqs:
        state["verification"] = id_results
        state["assistant_reply"] = _summarise(id_results, step)
        state["responding_agent"] = AGENT_NAME
        return state

    try:
        prompt = f"""Verify this upload against the checklist below.

UPLOADED DOCUMENT(S):
{_docs_block(documents)}

REQUIRED FOR {"STAGE " + str(step.get("step_number")) + ": " + step.get("title") if step else "THIS ROADMAP"}:
{chr(10).join(f"- {d}" for d in other_reqs[:20])}

For each required document decide whether the extracted text above IS that
document. Judge on the text, not the filename.

Return ONLY valid JSON array:
[
  {{
    "document_name": "DTI Certificate",
    "status": "complete",
    "notes": "Extracted text shows a DTI Business Name certificate, cert no. 12345",
    "evidence": "short quote from the extracted text"
  }}
]"""

        # Send the file itself. For a photographed ID or a scanned clearance
        # this IS the evidence - there is no text to match against.
        response = client.invoke_model(prompt=prompt,
                                       system_prompt=INSPECTION_SYSTEM_PROMPT,
                                       attachments=attachments or None,
                                       max_tokens=2048)
        verification_results = extract_json(response.get("content", ""))

        if not isinstance(verification_results, list) or not verification_results:
            raise ValueError("verification was not a non-empty array")

        verification_results = id_results + [
            r for r in verification_results
            if not is_government_id_requirement(r.get("document_name", ""))
        ]
        state["verification"] = verification_results
        state["assistant_reply"] = _summarise(verification_results, step)
        state["responding_agent"] = AGENT_NAME

    except Exception as e:
        logger.warning("Model verification unavailable (%s); using content matcher", e)
        obs.emit("fallback", "Model verification unavailable - content matcher used",
                 agent=AGENT_NAME, status="warn", error=f"{type(e).__name__}: {e}")
        results = id_results + [
            r for r in simple_document_check(roadmap, documents, step)
            if not is_government_id_requirement(r["document_name"])
        ]
        state["verification"] = results
        state["assistant_reply"] = _summarise(results, step)
        state["responding_agent"] = AGENT_NAME

    return state


def _check_government_ids(
    requirements: List[str],
    documents: List[Dict],
    client,
    roadmap: List[Dict],
    step: Optional[Dict],
) -> List[Dict]:
    """Run the government ID agent, falling back to the local matcher."""
    if not requirements:
        return []

    checks = [check_government_id(doc, client) for doc in documents]
    checks = [c for c in checks if c]
    if not checks:
        obs.emit("fallback", "Government ID check unavailable - content matcher used",
                 agent=AGENT_NAME, status="warn")
        return [r for r in simple_document_check(roadmap, documents, step)
                if r["document_name"] in requirements]

    best = next((c for c in checks if c["satisfies_requirement"]), checks[0])
    obs.emit("agent", f"Government ID verdict: {best['verdict']}",
             agent=AGENT_NAME, document_type=best["document_type"],
             confidence=best["confidence"])
    return [to_verification(req, best) for req in requirements]


def verdict_is_pass(results: List[Dict]) -> bool:
    """
    Did this upload actually satisfy the stage?

    Used by the API so the client can stop marking a stage complete regardless
    of the outcome - which it did before, even for an empty file.
    """
    if not results:
        return False
    return all(r.get("status") == "complete" for r in results)


def _summarise(results: List[Dict], step: Optional[Dict] = None) -> str:
    """Turn verification into something worth reading in the chat."""
    total = len(results)
    complete = sum(1 for r in results if r.get("status") == "complete")
    unreadable = [r for r in results if r.get("status") == "unreadable"]
    outstanding = [r for r in results
                   if r.get("status") in ("missing", "incomplete", "unreadable")]

    where = f" for **{step['title']}**" if step else ""

    if unreadable and len(unreadable) == total:
        return (f"I could not read that file, so I cannot confirm anything{where}. "
                f"{unreadable[0].get('notes', '')}")

    if complete == total:
        return f"All {total} requirement{'s' if total != 1 else ''}{where} are satisfied - you're inspection ready."

    lines = [f"I checked your upload against {total} requirement"
             f"{'s' if total != 1 else ''}{where}: **{complete} satisfied**, "
             f"{len(outstanding)} still outstanding."]
    for r in outstanding[:4]:
        note = r.get("notes", "")
        lines.append(f"- **{r.get('document_name')}** - {note}")
    return "\n\n".join([lines[0], "\n".join(lines[1:])]) if len(lines) > 1 else lines[0]
