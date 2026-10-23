"""Agent execution tracing."""
import logging
import threading
import time
import uuid
from collections import deque
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field, asdict
from typing import Any, Deque, Dict, List, Optional

logger = logging.getLogger(__name__)

# How much of a prompt or model response to keep. Enough to see what actually
# went to the model; short enough that a trace is not megabytes.
MAX_TEXT = 4000

# Per-session history and live buffers.
MAX_TRACES_PER_SESSION = 20
MAX_LIVE_EVENTS = 500
MAX_SESSIONS = 200


@dataclass
class TraceEvent:
    """One thing that happened during a turn."""
    seq: int
    ts: float
    phase: str          # route | agent | retrieval | model | parse | fallback | done
    label: str          # human-readable one-liner
    agent: Optional[str] = None
    status: str = "ok"  # ok | warn | error
    duration_ms: Optional[float] = None
    detail: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _truncate(value: Any, limit: int = MAX_TEXT) -> Any:
    """Bound a value's size so a trace stays readable and small."""
    if isinstance(value, str) and len(value) > limit:
        return value[:limit] + f"\n... [{len(value) - limit} more chars]"
    return value


def _redact(text: str) -> str:
    """
    Strip secrets that could ride along in an error string.

    invoke_model embeds the upstream response body in its exception message,
    and the API key header is built one line away from it.
    """
    if not isinstance(text, str) or not text:
        return text
    try:
        from utils.llm_client import get_settings
        token = get_settings().gemini_api_key
    except Exception:
        token = ""
    if token and len(token) > 6:
        text = text.replace(token, "***REDACTED***")
    return text


class Trace:
    """Events for a single turn."""

    def __init__(self, session_id: str, kind: str = "chat"):
        self.id = uuid.uuid4().hex[:12]
        self.session_id = session_id
        self.kind = kind
        self.started_at = time.time()
        self.finished_at: Optional[float] = None
        self.events: List[TraceEvent] = []
        self._seq = 0
        self._lock = threading.Lock()

    def emit(self, phase: str, label: str, *, agent: Optional[str] = None,
             status: str = "ok", duration_ms: Optional[float] = None,
             **detail: Any) -> TraceEvent:
        with self._lock:
            self._seq += 1
            event = TraceEvent(
                seq=self._seq,
                ts=time.time(),
                phase=phase,
                label=_redact(label),
                agent=agent,
                status=status,
                duration_ms=duration_ms,
                detail={k: _truncate(_redact(v) if isinstance(v, str) else v)
                        for k, v in detail.items()},
            )
            self.events.append(event)

        _publish(self.session_id, event)
        return event

    @contextmanager
    def span(self, phase: str, label: str, *, agent: Optional[str] = None, **detail: Any):
        """
        Time a block and emit one event when it ends.

        Yields a dict; anything put in it is merged into the event's detail, so
        a span can report what it found as well as how long it took.
        """
        started = time.perf_counter()
        extra: Dict[str, Any] = {}
        try:
            yield extra
        except Exception as e:
            self.emit(phase, f"{label} failed", agent=agent, status="error",
                      duration_ms=(time.perf_counter() - started) * 1000,
                      error=f"{type(e).__name__}: {e}", **{**detail, **extra})
            raise
        else:
            self.emit(phase, label, agent=agent,
                      duration_ms=(time.perf_counter() - started) * 1000,
                      **{**detail, **extra})

    def finish(self) -> None:
        self.finished_at = time.time()
        self.emit("done", "Turn complete",
                  duration_ms=(self.finished_at - self.started_at) * 1000,
                  events=len(self.events))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "session_id": self.session_id,
            "kind": self.kind,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "duration_ms": ((self.finished_at or time.time()) - self.started_at) * 1000,
            "events": [e.to_dict() for e in self.events],
        }


_current: ContextVar[Optional[Trace]] = ContextVar("current_trace", default=None)

# session_id -> completed traces (newest last)
_history: Dict[str, Deque[Trace]] = {}
# session_id -> live event feed for SSE subscribers
_live: Dict[str, Deque[TraceEvent]] = {}
_registry_lock = threading.Lock()


def _publish(session_id: str, event: TraceEvent) -> None:
    """Append to the live feed that SSE subscribers drain."""
    if not session_id:
        return
    with _registry_lock:
        buf = _live.get(session_id)
        if buf is None:
            buf = _live[session_id] = deque(maxlen=MAX_LIVE_EVENTS)
            _evict_locked()
        buf.append(event)


def _evict_locked() -> None:
    """Keep the registry bounded. Caller holds the lock."""
    while len(_live) > MAX_SESSIONS:
        _live.pop(next(iter(_live)), None)
    while len(_history) > MAX_SESSIONS:
        _history.pop(next(iter(_history)), None)


def current_trace() -> Optional[Trace]:
    """The trace for the turn in flight, if tracing is active."""
    return _current.get()


def emit(phase: str, label: str, **kwargs: Any) -> None:
    """
    Record an event against the active trace.

    A no-op when nothing is tracing, so instrumentation can sit permanently in
    agent code without a guard at every call site.
    """
    try:
        trace = _current.get()
        if trace is not None:
            trace.emit(phase, label, **kwargs)
    except Exception:
        logger.debug("trace emit failed", exc_info=True)


@contextmanager
def span(phase: str, label: str, **kwargs: Any):
    """Time a block against the active trace; no-op when not tracing."""
    trace = _current.get()
    if trace is None:
        yield {}
        return
    with trace.span(phase, label, **kwargs) as extra:
        yield extra


@contextmanager
def trace_turn(session_id: str, kind: str = "chat"):
    """
    Open a trace for one turn and file it in history when the block ends.

    Set up in the request coroutine; `run_in_threadpool` copies the context so
    agents running on the worker thread emit into the same trace.
    """
    trace = Trace(session_id, kind)
    token = _current.set(trace)
    try:
        yield trace
    finally:
        try:
            trace.finish()
            with _registry_lock:
                bucket = _history.get(session_id)
                if bucket is None:
                    bucket = _history[session_id] = deque(maxlen=MAX_TRACES_PER_SESSION)
                    _evict_locked()
                bucket.append(trace)
        except Exception:
            logger.debug("trace finalise failed", exc_info=True)
        finally:
            _current.reset(token)


def get_traces(session_id: str, limit: int = 5) -> List[Dict[str, Any]]:
    """Most recent completed traces for a session, newest last."""
    with _registry_lock:
        bucket = _history.get(session_id)
        traces = list(bucket)[-limit:] if bucket else []
    return [t.to_dict() for t in traces]


def live_events_since(session_id: str, after_seq: int = 0) -> List[Dict[str, Any]]:
    """
    Events published for a session since a sequence number.

    Sequence numbers restart per trace, so the SSE endpoint tracks position by
    identity rather than assuming a global counter.
    """
    with _registry_lock:
        buf = _live.get(session_id)
        events = list(buf) if buf else []
    return [e.to_dict() for e in events[after_seq:]]


def live_len(session_id: str) -> int:
    with _registry_lock:
        buf = _live.get(session_id)
        return len(buf) if buf else 0


def reset(session_id: Optional[str] = None) -> None:
    """Drop buffers. Used by tests and by session deletion."""
    with _registry_lock:
        if session_id is None:
            _history.clear()
            _live.clear()
        else:
            _history.pop(session_id, None)
            _live.pop(session_id, None)
