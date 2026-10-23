"""
FastAPI Routes
API endpoints for PermitPal backend
"""
from fastapi import (
    APIRouter, File, Form, HTTPException, Request, UploadFile,
)
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import StreamingResponse
import asyncio
import json
import logging
import sys
from pathlib import Path
from typing import Optional
sys.path.insert(0, str(Path(__file__).parent.parent))

from api.models import (
    ChatRequest, ChatResponse,
    DocumentUploadResponse, RoadmapCreateRequest, RoadmapResponse,
    SessionResponse, HealthResponse, ProgressRequest
)
from session import session_manager
from agents.workflow import app as workflow_app
from agents.state import AgentState
from agents.roadmap_agent import generate_roadmap, get_fallback_roadmap
from agents.inspection_agent import verdict_is_pass
from agents.stage_documents import annotate_roadmap
from utils.llm_client import get_settings
from agents.profiling_agent import _next_question
from utils.document_text import as_attachment, extract_text
from rag.retriever import get_retriever
import observability as obs

logger = logging.getLogger(__name__)

router = APIRouter()

# SSE tuning: how often to check for new events, and how often to send a
# comment line so idle connections are not culled by proxies.
POLL_INTERVAL = 0.15
HEARTBEAT_INTERVAL = 15.0


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """
    Main chat endpoint
    
    Process user messages and run the agent workflow
    """
    try:
        # Get or create session
        state = session_manager.get_session(request.session_id)
        if state is None:
            # Create new session
            session_id = session_manager.create_session()
            state = session_manager.get_session(session_id)
            # Use provided session_id if it's a valid format
            if request.session_id and len(request.session_id) > 5:
                session_manager.sessions[request.session_id] = session_manager.sessions.pop(session_id)
                session_id = request.session_id
        else:
            session_id = request.session_id
        
        user_message = {"role": "user", "content": request.message}

        # The API layer owns the transcript (see the note on AgentState.messages for why there is no
        turn_input = {**state, "messages": [*state.get("messages", []), user_message]}

        # Run workflow
        config = {"configurable": {"thread_id": session_id}}
        with obs.trace_turn(session_id, kind="chat") as trace:
            obs.emit("agent", "Turn started", message=request.message)
            result = await run_in_threadpool(workflow_app.invoke, turn_input, config)

        # Prefer what the agent actually said; the canned ladder is only a
        # fallback for turns where no agent produced a reply.
        response_message = result.get("assistant_reply") or generate_response_message(result)

        # Record the assistant's turn so the next one has the full exchange
        result["messages"] = [
            *result.get("messages", []),
            {"role": "assistant", "content": response_message},
        ]

        # Update session
        session_manager.update_session(session_id, result)

        return ChatResponse(
            session_id=session_id,
            response=response_message,
            agent=result.get("responding_agent"),
            stage=result["current_stage"],
            profile=result["user_profile"] if result["user_profile"] else None,
            roadmap=result["roadmap"] if result["roadmap"] else None,
            documents=result["documents"] if result["documents"] else None,
            verification=result.get("verification") or None,
            trace=trace.to_dict(),
        )

    except Exception as e:
        logger.exception("Chat turn failed")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/upload-document", response_model=DocumentUploadResponse)
async def upload_document(
    session_id: str = Form(...),
    document_name: str = Form(...),
    file: UploadFile = File(...),
    step_number: Optional[int] = Form(None),
):
    """
    Upload a document and run the Inspection Readiness Agent over it.

    session_id and document_name must be Form fields: FastAPI binds bare
    scalars in a multipart request as QUERY parameters, so declaring them
    without Form(...) made every normal multipart upload fail with 422.
    """
    try:
        # Get session
        state = session_manager.get_session(session_id)
        if state is None:
            raise HTTPException(status_code=404, detail="Session not found")

        # A typed text file can claim to be any certificate, so only scans,
        # photos and PDFs are checked - unless text is allowed for demos/tests.
        is_text = (file.content_type or "").startswith("text/") or \
            (file.filename or "").lower().endswith(".txt")
        if is_text and not get_settings().allow_text_uploads:
            raise HTTPException(
                status_code=415,
                detail="Upload a PDF or a photo of the document. Text files can't be checked.",
            )

        # Read file content
        content = await file.read()

        # Read what is actually IN the file. Verification used to run on the
        # filename alone, which accepted a grocery receipt as a government ID.
        # OCR/model initialization is CPU-heavy and must not block FastAPI's
        # event loop while other requests are being served.
        text, method = await run_in_threadpool(
            extract_text,
            file.filename or document_name,
            file.content_type,
            content,
        )

        # Photos and scans carry no text. Rather than bolting on an OCR engine,
        # hand the file to the model as an image / PDF block and let it read.
        attachment = as_attachment(file.filename or document_name,
                                   file.content_type, content)

        document = {
            "name": document_name,
            "type": file.content_type,
            "filename": file.filename,
            "size": len(content),
            "text": text,
            "extract_method": method,
            "attachment": attachment,
        }
        state["documents"].append(document)

        # Route the next graph turn to the Inspection Agent
        state["pending_inspection"] = True
        state["pending_step"] = step_number
        state["pending_document"] = document
        config = {"configurable": {"thread_id": session_id}}
        with obs.trace_turn(session_id, kind="upload") as trace:
            obs.emit("agent", f"Verifying {document_name}",
                     filename=file.filename, size=len(content),
                     content_type=file.content_type, extracted=method,
                     text_chars=len(text or ""), step_number=step_number,
                     attached=attachment["kind"] if attachment else None)
            result = await run_in_threadpool(workflow_app.invoke, state, config)

        # Record the verification summary as an assistant turn so the upload
        # shows up in the chat history alongside everything else.
        summary = result.get("assistant_reply")
        if summary:
            result["messages"] = [
                *result.get("messages", []),
                {"role": "assistant", "content": summary},
            ]

        session_manager.update_session(session_id, result)

        verification = result.get("verification") or []
        return DocumentUploadResponse(
            session_id=session_id,
            status="success",
            message=result.get("assistant_reply")
            or f"Document '{document_name}' uploaded successfully",
            verification_results={
                "documents": verification,
                "complete": sum(1 for v in verification if v.get("status") == "complete"),
                "missing": sum(1 for v in verification if v.get("status") == "missing"),
                "unreadable": sum(1 for v in verification if v.get("status") == "unreadable"),
                # Whether the stage may be marked done. The client used to
                # complete the stage no matter what came back.
                "passed": bool(result.get("stage_passed"))
                if result.get("stage_passed") is not None
                else verdict_is_pass(verification),
                "extracted": method,
            } if verification else None,
            agent=result.get("responding_agent"),
            # The chat renders this beside the findings, so an upload shows the
            # same agent activity a chat turn does.
            trace=trace.to_dict(),
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/roadmap", response_model=RoadmapResponse, status_code=201)
async def create_roadmap(request: RoadmapCreateRequest):
    """Generate the session's roadmap. Synchronous, and final."""
    state = session_manager.get_session(request.session_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Session not found")

    profile = request.profile or state.get("user_profile") or {}
    if not profile:
        raise HTTPException(
            status_code=400,
            detail="No business profile on the session; send one in the request body",
        )

    if request.profile:
        state["user_profile"] = profile

    # Already generated: hand back exactly what this session was given. Calling
    # this twice must never produce a different roadmap.
    if state.get("roadmap"):
        return RoadmapResponse(
            session_id=request.session_id,
            roadmap=annotate_roadmap(state["roadmap"]),
            profile=state["user_profile"],
            stage=state["current_stage"],
            source=state.get("roadmap_source"),
            refining=False,
        )

    # generate_roadmap never raises: it falls back to the template roadmap if
    # retrieval or the model is unavailable, so the user always gets something.
    with obs.trace_turn(request.session_id, kind="roadmap"):
        obs.emit("agent", "Generating compliance roadmap",
                 business=profile.get("business_name"),
                 business_type=profile.get("business_type"))
        roadmap, source = await run_in_threadpool(generate_roadmap, profile)

    state["roadmap"] = roadmap
    state["roadmap_source"] = source
    state["current_stage"] = "roadmap"
    session_manager.update_session(request.session_id, state)

    logger.info("Roadmap for %s: %d steps (source=%s)",
                request.session_id, len(roadmap), source)

    return RoadmapResponse(
        session_id=request.session_id,
        roadmap=annotate_roadmap(roadmap),
        profile=profile,
        stage=state["current_stage"],
        source=source,
        # Nothing changes after this point.
        refining=False,
    )


@router.get("/roadmap/{session_id}", response_model=RoadmapResponse)
async def get_roadmap(session_id: str):
    """
    Get roadmap for a session
    """
    try:
        state = session_manager.get_session(session_id)
        if state is None:
            raise HTTPException(status_code=404, detail="Session not found")

        return RoadmapResponse(
            session_id=session_id,
            roadmap=annotate_roadmap(state["roadmap"]),
            profile=state["user_profile"],
            stage=state["current_stage"],
            source=state.get("roadmap_source"),
            refining=False
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/session", response_model=SessionResponse, status_code=201)
async def create_session():
    """
    Create an empty session and return its id.

    The frontend calls this once after onboarding, then uses the id for
    /roadmap, /chat and /upload-document. Previously sessions could only be
    created as a side effect of /chat, which meant the client had no way to
    obtain an id before sending a message.
    """
    session_id = session_manager.create_session()
    state = session_manager.get_session(session_id)

    return SessionResponse(
        session_id=session_id,
        stage=state["current_stage"],
        profile=state["user_profile"],
        roadmap=annotate_roadmap(state["roadmap"]),
        documents=state["documents"],
        message_count=len(state["messages"]),
        messages=state["messages"],
        progress=state.get("ui_progress") or {"completed": [], "checked": []},
        source=state.get("roadmap_source"),
    )


@router.get("/session/{session_id}", response_model=SessionResponse)
async def get_session(session_id: str):
    """
    Get full session state
    """
    try:
        state = session_manager.get_session(session_id)
        if state is None:
            raise HTTPException(status_code=404, detail="Session not found")
        
        return SessionResponse(
            session_id=session_id,
            stage=state["current_stage"],
            profile=state["user_profile"],
            roadmap=annotate_roadmap(state["roadmap"]),
            documents=state["documents"],
            message_count=len(state["messages"]),
            # The transcript itself, so the chat panel can be redrawn after a
            # re-login instead of restarting from the welcome message.
            messages=state["messages"],
            progress=state.get("ui_progress") or {"completed": [], "checked": []},
            source=state.get("roadmap_source"),
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/session/{session_id}/progress", response_model=SessionResponse)
async def save_progress(session_id: str, request: ProgressRequest):
    """
    Persist which stages and sub-steps the user has ticked off.

    Progress used to live only in the browser's localStorage, which sign-out
    clears - so signing back in returned the roadmap with every step reset.
    Storing it alongside the session makes what the user sees after a re-login
    match what they left.
    """
    state = session_manager.get_session(session_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Session not found")

    state["ui_progress"] = {
        "completed": list(request.completed),
        "checked": list(request.checked),
    }
    session_manager.update_session(session_id, state)

    return SessionResponse(
        session_id=session_id,
        stage=state["current_stage"],
        profile=state["user_profile"],
        roadmap=annotate_roadmap(state["roadmap"]),
        documents=state["documents"],
        message_count=len(state["messages"]),
        messages=state["messages"],
        progress=state["ui_progress"],
        source=state.get("roadmap_source"),
    )


@router.delete("/session/{session_id}")
async def delete_session(session_id: str):
    """
    Delete a session
    """
    success = session_manager.delete_session(session_id)
    if not success:
        raise HTTPException(status_code=404, detail="Session not found")
    
    return {"status": "success", "message": f"Session {session_id} deleted"}


@router.get("/trace/{session_id}")
async def get_trace(session_id: str, limit: int = 5):
    """
    Recent completed agent traces for a session.

    Each trace is the full low-level record of one turn: the routing decision
    and why, what was retrieved from which ordinances, the exact prompt and
    the raw model response, every fallback taken, and timings throughout.
    """
    return {"session_id": session_id, "traces": obs.get_traces(session_id, limit=limit)}


@router.get("/trace/{session_id}/stream")
async def stream_trace(session_id: str, request: Request):
    """
    Server-sent events: agent activity as it happens.

    The UI opens this before sending a message so the user watches the agents
    deliberate instead of a spinner. Polls the session's live buffer rather
    than using an asyncio queue, because the agents run on a threadpool worker
    and a plain deque needs no cross-thread async primitives.
    """
    async def events():
        cursor = obs.live_len(session_id)
        idle = 0.0

        # Announce immediately so EventSource fires onopen even on a quiet
        # session; some proxies also need bytes before they forward anything.
        yield f": connected to {session_id}\n\n"

        while True:
            if await request.is_disconnected():
                break

            batch = obs.live_events_since(session_id, cursor)
            if batch:
                cursor += len(batch)
                idle = 0.0
                for event in batch:
                    yield f"event: trace\ndata: {json.dumps(event)}\n\n"
            else:
                await asyncio.sleep(POLL_INTERVAL)
                idle += POLL_INTERVAL
                if idle >= HEARTBEAT_INTERVAL:
                    idle = 0.0
                    yield ": heartbeat\n\n"

            if idle == 0.0 and not batch:
                continue

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            # Stops nginx buffering the stream into uselessness.
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/health", response_model=HealthResponse)
async def health_check():
    """
    Health check endpoint
    """
    # Report the real retriever state instead of a hardcoded "operational"
    import rag.retriever as _retriever_mod
    rag_status = "warm" if _retriever_mod._retriever is not None else "cold"

    return HealthResponse(
        status="ok",
        version="1.0.0",
        services={
            "workflow": "operational",
            "session_manager": f"{len(session_manager.sessions)} active sessions",
            "rag": rag_status,
        }
    )


def generate_response_message(state: AgentState) -> str:
    """Generate appropriate response message based on workflow state"""
    stage = state["current_stage"]
    profile = state["user_profile"]
    roadmap = state["roadmap"]
    
    if stage == "profiling":
        return _next_question(profile or {})
    
    elif stage == "roadmap":
        if roadmap and len(roadmap) > 0:
            return f"Perfect! I've created a {len(roadmap)}-step compliance roadmap for {profile.get('business_name', 'your business')}. Check out the timeline to see all the requirements."
        else:
            return "I'm generating your compliance roadmap based on Manila regulations..."
    
    elif stage == "inspection":
        doc_count = len(state.get("documents", []))
        if doc_count == 0:
            return "Your roadmap is ready! You can now start uploading your documents for verification."
        else:
            return f"I've received {doc_count} document(s). Keep uploading to complete your checklist!"
    
    else:
        return "How can I assist you with your business permit today?"
