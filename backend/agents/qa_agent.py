"""Compliance Q&A Agent"""
import logging
import sys
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent.parent))

from agents.state import AgentState
from utils.llm_client import get_llm_client
from rag.retriever import get_retriever
import observability as obs

logger = logging.getLogger(__name__)

AGENT_NAME = "GabAI"

MAX_RAG_CONTEXT_CHARS = 3500

QA_SYSTEM_PROMPT = """You are GabAI, Sellyo's assistant: a Manila LGU business-permit
compliance expert helping a small business owner through the permitting process.
Don't greet or introduce yourself. Only if the user asks who you are, say you
are GabAI from Sellyo, a guide that doesn't file anything for them.

Ground every factual claim in the MANILA SOURCES provided. When a source gives a
specific ordinance number, form number, fee or office, name it.

Rules:
- If the sources do not cover something, say so plainly rather than guessing.
- Never state a fee as final: Manila fees vary by barangay, capital, floor area
  and the assessor's SOA. Say "approximately" and name what it depends on.
- When THEIR ROADMAP lists a cost for a step, quote that figure so your answer
  matches what the app shows them. Only give a different number if a source
  says otherwise, and then say the roadmap figure may be out of date.
- Say whether a step can be done online or must be done in person when the
  sources say so.
- Be concrete and practical. Prefer a short ordered list of what to do next
  over general advice.
- Keep answers under 180 words unless the user asks for detail.
- You are guidance, not legal advice.
- Answer in the language the user wrote in (English or Filipino/Taglish).

FORMAT your answer as GitHub-flavoured Markdown - the chat panel renders it:
- Open with one short sentence answering the question directly. No heading.
- Then a `-` bullet list, or a `1.` numbered list when order matters.
- **Bold** the document, form or office name at the start of each bullet.
- Use `**Fees:**` / `**Where:**` / `**Processing time:**` as inline bold labels
  rather than headings.
- Never use h1/h2 headings, tables, or code blocks - they do not suit a narrow
  chat column."""


def _build_context(state: AgentState) -> str:
    """Assemble what the model knows about this specific user."""
    profile = state.get("user_profile") or {}
    roadmap = state.get("roadmap") or []
    verification = state.get("verification") or []

    parts = []

    if profile:
        bits = [f"{k}: {v}" for k, v in profile.items() if v not in (None, "")]
        parts.append("BUSINESS PROFILE:\n" + "\n".join(bits))

    if roadmap:
        steps = "\n".join(
            f"{s.get('step_number', i + 1)}. {s.get('title', 'Step')}"
            f" - {s.get('estimated_cost', 'cost TBD')}"
            f" at {s.get('location', 'TBD')}"
            for i, s in enumerate(roadmap)
        )
        parts.append(f"THEIR ROADMAP ({len(roadmap)} steps):\n{steps}")

    if verification:
        missing = [v.get("document_name") for v in verification if v.get("status") == "missing"]
        if missing:
            parts.append("STILL MISSING: " + ", ".join(str(m) for m in missing[:10]))

    return "\n\n".join(parts)


def answer_question(question: str, state: AgentState) -> str:
    """
    Answer one compliance question.

    Never raises - returns a graceful message if retrieval or the model fails,
    so a chat turn always produces something for the user to read.
    """
    obs.emit("agent", "GabAI reading the question", agent=AGENT_NAME,
             question=question)

    rag_context = ""
    try:
        retriever = get_retriever()
        rag_context = retriever.retrieve_context(
            question, top_k=5, max_chars=MAX_RAG_CONTEXT_CHARS
        )
        logger.info("QA retrieved %d chars for: %s", len(rag_context), question[:60])
    except Exception as e:
        logger.exception("QA retrieval failed; answering without sources")
        obs.emit("fallback", "Retrieval unavailable - answering without sources",
                 agent=AGENT_NAME, status="warn", error=f"{type(e).__name__}: {e}")

    user_context = _build_context(state)

    prompt = f"""{user_context}

MANILA SOURCES:
{rag_context or "(no sources retrieved - say you are not certain)"}

QUESTION:
{question}

Answer using the sources above and what you know about this business."""

    try:
        client = get_llm_client()
        response = client.invoke_model(
            prompt=prompt,
            system_prompt=QA_SYSTEM_PROMPT,
            max_tokens=1024,
        )
        answer = (response.get("content") or "").strip()
        if answer:
            obs.emit("agent", "Answer composed", agent=AGENT_NAME,
                     answer_chars=len(answer), grounded=bool(rag_context))
            return answer
        logger.warning("QA model returned an empty answer")
        obs.emit("agent", "Model returned an empty answer", agent=AGENT_NAME,
                 status="warn")
    except Exception as e:
        logger.exception("QA model call failed")
        obs.emit("fallback", "Falling back to the offline reply", agent=AGENT_NAME,
                 status="warn", error=f"{type(e).__name__}: {e}")

    # Formatted the same way as a real answer, so a degraded reply still reads
    # like the rest of the chat rather than a wall of apology.
    return (
        "I could not reach the compliance knowledge base just now, so I cannot "
        "ground an answer in the ordinances yet.\n\n"
        "- **Your roadmap is still accurate** - it is built from the Manila BPLS "
        "sequence and does not depend on this service.\n"
        "- **Keep going** on the current stage; uploads and checklists all work.\n"
        "- **Ask me again shortly** and I will pull the exact ordinance text."
    )


def qa_agent(state: AgentState) -> AgentState:
    """Answer the user's latest message."""
    logger.info("QA Agent running")

    messages = state.get("messages") or []
    last_user = next(
        (m for m in reversed(messages) if m.get("role") == "user"),
        None,
    )

    if not last_user or not (last_user.get("content") or "").strip():
        state["assistant_reply"] = "What would you like to know about your Manila permits?"
        state["responding_agent"] = AGENT_NAME
        return state

    state["assistant_reply"] = answer_question(last_user["content"], state)
    state["responding_agent"] = AGENT_NAME
    return state


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    test_state = AgentState(
        messages=[{"role": "user", "content": "What do I need for a barangay clearance?"}],
        user_profile={"business_name": "Juan's Cafe", "business_type": "cafe",
                      "location": "Sampaloc", "serves_food": True},
        roadmap=[],
        documents=[],
        verification=[],
        pending_inspection=False,
        assistant_reply=None,
        responding_agent=None,
        current_stage="roadmap",
        rag_context=None,
        roadmap_retry_count=0,
        roadmap_source=None,
        error=None,
    )

    result = qa_agent(test_state)
    print("\n" + "=" * 60)
    print(f"{result['responding_agent']}:")
    print("=" * 60)
    print(result["assistant_reply"])
