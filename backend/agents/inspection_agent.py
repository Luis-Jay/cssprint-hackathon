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
from agents.document_checks import check_fields, failed
from agents.stage_documents import stage_outputs
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

In notes, say what the document appears to be ("This appears to be a DTI
Certificate of Business Name Registration for ..."). Never call a document
valid, verified, genuine or authentic: you can only see what it looks like.

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


def _unverified(results: List[Dict]) -> List[Dict]:
    """
    Keyword matching cannot tell a real clearance from a page that says
    "barangay clearance", so a fallback match is never reported as complete.
    """
    out = []
    for r in results:
        if r.get("status") == "complete":
            r = {**r, "status": "unverified",
                 "notes": "The automatic check is unavailable, so this couldn't be confirmed. "
                          "Try uploading again in a minute."}
        out.append(r)
    return out


def _fallback(checklist: List[str], documents: List[Dict]) -> List[Dict]:
    return _unverified(simple_document_check([], documents, {"requirements": checklist}))


def _norm(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (name or "").lower()).strip()


def _align(results: List[Dict], checklist: List[str]) -> List[Dict]:
    """
    Map the model's names back onto the checklist and report anything it
    skipped. The model sometimes rewords an item ("Mayor's Permit / Business
    Permit") or drops it, and an unmatched stage document silently failed the
    stage with no explanation.
    """
    by_norm = {_norm(c): c for c in checklist}
    aligned: Dict[str, Dict] = {}
    leftovers = []
    for r in results:
        target = by_norm.get(_norm(r.get("document_name", "")))
        if target and target not in aligned:
            aligned[target] = {**r, "document_name": target}
        else:
            leftovers.append(r)

    # Closest remaining item by shared words, for reworded names.
    for r in leftovers:
        words = set(_norm(r.get("document_name", "")).split())
        open_items = [c for c in checklist if c not in aligned]
        best = max(open_items, key=lambda c: len(words & set(_norm(c).split())), default=None)
        if best and len(words & set(_norm(best).split())) >= 2:
            aligned[best] = {**r, "document_name": best}

    return [aligned.get(c) or {
        "document_name": c, "status": "missing",
        "notes": "The check didn't report on this document. Try uploading again.",
    } for c in checklist]


def _tag(results: List[Dict], outputs: List[str]) -> List[Dict]:
    """Mark which results are the stage's own document and which are inputs."""
    return [{**r, "kind": "output" if r.get("document_name") in outputs else "requirement"}
            for r in results]


def _apply_field_checks(results: List[Dict], fields: Dict, profile: Dict) -> List[Dict]:
    """Run the deterministic checks on any stage document the model accepted."""
    checked = []
    for r in results:
        if r.get("kind") == "output" and r.get("status") == "complete":
            checks = check_fields(fields, profile)
            problems = failed(checks)
            r = {**r, "checks": checks}
            if problems:
                r["status"] = "incomplete"
                r["notes"] = problems[0]["detail"]
        checked.append(r)
    return checked


def _record_evidence(state: AgentState, step: Optional[Dict], outputs: List[str],
                     results: List[Dict], document: Dict) -> bool:
    """
    Remember what this stage has been shown, across uploads, and say whether
    every stage document has now been seen. One upload no longer has to
    satisfy everything at once - an ID and a lease are two files.
    """
    if not step:
        return verdict_is_pass(results)
    key = str(step.get("step_number"))
    evidence = dict(state.get("stage_evidence") or {})
    seen = dict(evidence.get(key) or {})
    for r in results:
        if r.get("status") == "complete":
            seen[r["document_name"]] = {
                "file": document.get("filename") or document.get("name"),
                "kind": r.get("kind", "requirement"),
            }
    evidence[key] = seen
    state["stage_evidence"] = evidence
    return bool(outputs) and all(o in seen for o in outputs)


def inspection_agent(state: AgentState) -> AgentState:
    """Check one upload against its stage's document and requirements"""
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
    outputs = stage_outputs(step) if step else []
    requirements = [r for s in scope for r in s.get("requirements", []) if r not in outputs]
    checklist = outputs + requirements
    profile = state.get("user_profile") or {}

    obs.emit("agent", f"Checking {len(documents)} upload(s) for "
                      f"{len(outputs)} stage document(s) and {len(requirements)} requirement(s)",
             agent=AGENT_NAME,
             step=step.get("title") if step else "entire roadmap",
             outputs=outputs,
             readable=[d.get("name") for d in documents if d.get("text")],
             unreadable=[d.get("name") for d in documents if not d.get("text")])

    def finish(results: List[Dict]) -> AgentState:
        results = _tag(results, outputs)
        passed = _record_evidence(state, step, outputs, results, documents[0])
        state["verification"] = results
        state["stage_passed"] = passed
        state["assistant_reply"] = _summarise(results, step, passed, outputs)
        state["responding_agent"] = AGENT_NAME
        return state

    attachments = [d["attachment"] for d in documents if d.get("attachment")]

    # Only give up when there is neither text NOR a file the model can look at.
    if not any(d.get("text") for d in documents) and not attachments:
        obs.emit("fallback", "No extractable text - cannot confirm anything",
                 agent=AGENT_NAME, status="warn")
        return finish(_fallback(checklist, documents))

    # Without the model only keyword matching is possible, which proves
    # nothing; report it as unconfirmed rather than passing the stage.
    if not llm_is_configured():
        obs.emit("fallback", "Gemini not configured - keyword match only, nothing confirmed",
                 agent=AGENT_NAME, status="warn")
        return finish(_fallback(checklist, documents))

    client = get_llm_client()

    # Government ID requirements get their own stricter check.
    id_reqs = [r for r in requirements if is_government_id_requirement(r)]
    others = [r for r in checklist if not is_government_id_requirement(r)]
    id_results = _check_government_ids(id_reqs, documents, client, roadmap, step)

    if not others:
        return finish(id_results)

    stage_label = (f"STAGE {step.get('step_number')}: {step.get('title')}" if step
                   else "THIS ROADMAP")
    output_lines = "\n".join(f"- {d}" for d in outputs) or "- (none)"
    requirement_lines = "\n".join(
        f"- {d}" for d in others if d not in outputs) or "- (none)"

    try:
        prompt = f"""Check this upload for {stage_label}.

UPLOADED DOCUMENT:
{_docs_block(documents)}

STAGE DOCUMENT - what the office issues when this stage is done:
{output_lines}

REQUIREMENTS - what the owner brings to apply:
{requirement_lines}

First read the document itself. Then decide, for every item in both lists,
whether THIS upload IS that document. Judge on content, not the filename.

Return ONLY a JSON object:
{{
  "document": {{
    "type": "what the document actually is, e.g. DTI Certificate of Business Name Registration",
    "business_name": "business name printed on it, or null",
    "owner_name": "owner or registrant name, or null",
    "document_number": "certificate / permit / reference number, or null",
    "issue_date": "YYYY-MM-DD or null",
    "expiry_date": "YYYY-MM-DD or null",
    "issuing_office": "issuing agency or office, or null"
  }},
  "results": [
    {{
      "document_name": "exactly as written in the lists above",
      "status": "complete | incomplete | missing | unreadable",
      "notes": "one short sentence on what the upload is",
      "evidence": "short quote from the document"
    }}
  ]
}}"""

        # Send the file itself. For a photographed ID or a scanned clearance
        # this IS the evidence - there is no text to match against.
        response = client.invoke_model(prompt=prompt,
                                       system_prompt=INSPECTION_SYSTEM_PROMPT,
                                       attachments=attachments or None,
                                       max_tokens=2048)
        parsed = extract_json(response.get("content", ""))
        if isinstance(parsed, list):  # older answer shape: results only
            parsed = {"document": {}, "results": parsed}
        results = parsed.get("results") if isinstance(parsed, dict) else None
        if not isinstance(results, list) or not results:
            raise ValueError("verification had no results")

        fields = parsed.get("document") or {}
        obs.emit("agent", f"Document read as: {fields.get('type') or 'unknown'}",
                 agent=AGENT_NAME, fields=fields)
        results = _align(results, others)
        results = _apply_field_checks(_tag(results, outputs), fields, profile)
        return finish(id_results + results)

    except Exception as e:
        logger.warning("Model verification unavailable (%s); nothing confirmed", e)
        obs.emit("fallback", "Model verification unavailable - keyword match only, nothing confirmed",
                 agent=AGENT_NAME, status="warn", error=f"{type(e).__name__}: {e}")
        return finish(id_results + [
            r for r in _fallback(others, documents)
            if not is_government_id_requirement(r["document_name"])
        ])


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
        return _unverified([r for r in simple_document_check(roadmap, documents, step)
                            if r["document_name"] in requirements])

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


def _summarise(results: List[Dict], step: Optional[Dict] = None,
               passed: bool = False, outputs: Optional[List[str]] = None) -> str:
    """Turn the check into something worth reading in the chat."""
    outputs = outputs or []
    total = len(results)
    where = f" for **{step['title']}**" if step else ""
    unreadable = [r for r in results if r.get("status") == "unreadable"]
    unverified = [r for r in results if r.get("status") == "unverified"]
    outstanding = [r for r in results if r.get("status") != "complete"]

    if total and len(unreadable) == total:
        return (f"I could not read that file, so I cannot confirm anything{where}. "
                f"{unreadable[0].get('notes', '')}")

    if unverified and not any(r.get("status") == "complete" for r in results):
        return ("I couldn't run the full document check just now, so nothing was "
                "confirmed. Try uploading again in a minute.")

    if passed:
        return (f"This looks like your **{' and '.join(outputs)}**. Stage "
                f"{step.get('step_number')} is done. Sellyo checks that a document looks "
                f"right; the issuing office has the final say.")

    if step and outputs:
        lines = [f"This doesn't look like the **{' and '.join(outputs)}** yet{where}."]
    else:
        complete = total - len(outstanding)
        lines = [f"I checked your upload against {total} item{'s' if total != 1 else ''}"
                 f"{where}: **{complete} matched**, {len(outstanding)} not yet."]
    for r in sorted(outstanding, key=lambda r: r.get("kind") != "output")[:4]:
        lines.append(f"- **{r.get('document_name')}** - {r.get('notes', '')}")
    return "\n\n".join([lines[0], "\n".join(lines[1:])]) if len(lines) > 1 else lines[0]
