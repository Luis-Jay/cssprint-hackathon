"""
Section 8: SSE live delivery, against a REAL uvicorn server.

This cannot be tested with Starlette's TestClient: its ASGI transport buffers
the response body, so an endless event stream blocks before a response object
is ever handed back. A real server and a real socket are required to prove
that events reach the client *during* a turn rather than in one dump at the end
- which is the entire point of the live view.

Usage:
    uv run python test_sse_live.py [base_url]
"""
import json
import sys
import threading
import time

import httpx

BASE = (sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8010") + "/api"

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"  {'PASS' if cond else 'FAIL'}  {name}{('  -- ' + detail) if detail else ''}")
    sys.stdout.flush()


print("=" * 72)
print("  8. SSE stream delivers events while a turn is still running")
print("=" * 72)

client = httpx.Client(timeout=30.0)

try:
    client.get(f"{BASE}/health", timeout=3.0)
except Exception as e:
    print(f"  SKIP - no server at {BASE}: {e}")
    sys.exit(2)

# A session with a profile and roadmap so the turn routes to the QA agent and
# produces a realistic multi-step trace.
sid = client.post(f"{BASE}/session").json()["session_id"]
client.post(f"{BASE}/roadmap", json={
    "session_id": sid,
    "profile": {"business_name": "SSE Cafe", "business_type": "cafe",
                "location": "Sampaloc, Zone 30, City of Manila", "serves_food": True},
})

received = []          # (monotonic_offset, event)
meta = {}
stop = threading.Event()


def reader():
    """Drain the stream, timestamping each event as it lands."""
    t0 = time.perf_counter()
    try:
        with httpx.stream("GET", f"{BASE}/trace/{sid}/stream", timeout=30.0) as resp:
            meta["status"] = resp.status_code
            meta["ctype"] = resp.headers.get("content-type", "")
            meta["opened_at"] = time.perf_counter() - t0
            for line in resp.iter_lines():
                if stop.is_set():
                    break
                if line.startswith("data:"):
                    received.append((time.perf_counter() - t0,
                                     json.loads(line[5:].strip())))
    except Exception as e:  # noqa: BLE001
        meta["error"] = f"{type(e).__name__}: {e}"


th = threading.Thread(target=reader, daemon=True)
th.start()
time.sleep(1.0)          # let the subscription establish

check("stream opened with 200", meta.get("status") == 200, str(meta.get("status")))
check("content-type is text/event-stream",
      "text/event-stream" in meta.get("ctype", ""), meta.get("ctype", ""))
check("no stream error", "error" not in meta, meta.get("error", ""))

# Fire a turn. Events must arrive while this request is still in flight.
t_start = time.perf_counter()
during = len(received)
r = client.post(f"{BASE}/chat",
                json={"session_id": sid, "message": "What is a barangay clearance?"})
t_chat = time.perf_counter() - t_start

check("chat -> 200", r.status_code == 200, str(r.status_code))
time.sleep(1.2)          # let the tail of the stream arrive
stop.set()

events = [e for _, e in received]
labels = [e["label"] for e in events]

print()
for offset, e in received:
    print(f"        +{offset:5.2f}s  [{e['phase']:<9}] {e['label']}")
print()
print(f"        (chat request took {t_chat:.2f}s)")
print()

check("events were delivered", len(events) >= 3, f"{len(events)} events")
check("the full agent chain came through, not just a summary",
      any(e["phase"] == "route" for e in events)
      and any(e["phase"] == "retrieval" for e in events)
      and any(e["phase"] == "model" for e in events),
      str(sorted({e["phase"] for e in events})))
check("sequence numbers are ordered",
      [e["seq"] for e in events] == sorted(e["seq"] for e in events),
      str([e["seq"] for e in events]))
check("a done event closes the turn", any(e["phase"] == "done" for e in events))

# The load-bearing assertion: at least one event landed BEFORE the POST
# returned. If delivery were batched at the end this would fail while every
# other check above still passed.
first_offsets = [off for off, _ in received]
chat_started_at = first_offsets[0] if first_offsets else None
check("events arrived DURING the turn, not after it",
      len(received) > during and any(
          off < (received[-1][0]) for off in first_offsets[:-1]),
      f"first at +{chat_started_at:.2f}s, last at +{received[-1][0]:.2f}s"
      if received else "none")

# Look for an actual credential, not the word "Bearer": a leak is the scheme
# followed by a long opaque token. The bare `b'Bearer '` in an error string
# from an unconfigured server is not a leak, and an earlier version of this
# check flagged it as one.
import re
leaked = re.findall(r"Bearer\s+[A-Za-z0-9_\-\.]{16,}", json.dumps(events))
check("no credential leaked over the wire", not leaked, str(leaked[:1]))

client.close()

print()
print("=" * 72)
print(f"  {len(PASS)} passed, {len(FAIL)} failed")
for f in FAIL:
    print(f"    FAILED: {f}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
