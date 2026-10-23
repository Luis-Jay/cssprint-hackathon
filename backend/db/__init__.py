"""SQLite persistence for accounts and auth sessions."""
import json
import os
import sqlite3
import hashlib
import secrets
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Optional

# Anchor on the package, not the process CWD, so the database does not move
# when the server is launched from a different directory.
DEFAULT_DB_PATH = Path(__file__).resolve().parent / "permitpal.db"

# OWASP's floor for PBKDF2-HMAC-SHA256 is 600,000 iterations.
PBKDF2_ITERATIONS = 600_000
SALT_BYTES = 16
TOKEN_BYTES = 32
SESSION_TTL = timedelta(days=7)


def _db_path() -> Path:
    return Path(os.getenv("DATABASE_PATH", str(DEFAULT_DB_PATH)))


@contextmanager
def connect():
    """Open a connection with sane defaults, committing on clean exit."""
    path = _db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=10.0)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    email         TEXT    NOT NULL,
    email_lower   TEXT    NOT NULL UNIQUE,
    name          TEXT    NOT NULL,
    password_hash BLOB    NOT NULL,
    password_salt BLOB    NOT NULL,
    iterations    INTEGER NOT NULL,
    created_at    TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS auth_sessions (
    token_hash TEXT    PRIMARY KEY,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at TEXT    NOT NULL,
    expires_at TEXT    NOT NULL,
    last_seen  TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_auth_sessions_user ON auth_sessions(user_id);

-- Links a signed-in user to their PermitPal agent session, so logging back in
-- restores the roadmap instead of starting over.
CREATE TABLE IF NOT EXISTS user_workspaces (
    user_id    INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    session_id TEXT    NOT NULL,
    updated_at TEXT    NOT NULL
);

-- The agent session itself: profile, roadmap, documents, verification and the
-- chat transcript.
--
-- Remembering only the session id was not enough. The id survived in
-- user_workspaces but the state lived solely in the in-memory SessionManager,
-- which has a 30-minute TTL and dies with the process - so logging back in
-- found an empty session, the roadmap fell back to the bundled stages and the
-- header reverted to the demo profile. Everything the user built is durable
-- now.
CREATE TABLE IF NOT EXISTS session_states (
    session_id TEXT PRIMARY KEY,
    state      TEXT NOT NULL,   -- JSON blob of AgentState
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""


def init_db() -> None:
    """Create tables if they do not exist. Safe to call on every startup."""
    with connect() as conn:
        conn.executescript(SCHEMA)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def hash_password(password: str, salt: Optional[bytes] = None,
                  iterations: int = PBKDF2_ITERATIONS) -> tuple:
    """Derive a password hash. Returns (hash, salt, iterations)."""
    salt = salt or secrets.token_bytes(SALT_BYTES)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return digest, salt, iterations


def verify_password(password: str, digest: bytes, salt: bytes, iterations: int) -> bool:
    """Constant-time password check."""
    candidate = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return secrets.compare_digest(candidate, digest)


def _hash_token(token: str) -> str:
    """
    Store only the hash of a session token.

    A dump of auth_sessions then yields nothing usable - the raw token exists
    only in the client's hands.
    """
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class EmailAlreadyRegistered(Exception):
    """Raised when signup targets an address that already has an account."""


def create_user(email: str, name: str, password: str) -> Dict[str, Any]:
    """
    Create an account.

    Raises:
        EmailAlreadyRegistered: if the address is taken
    """
    digest, salt, iterations = hash_password(password)
    now = _iso(_now())

    with connect() as conn:
        try:
            cur = conn.execute(
                "INSERT INTO users (email, email_lower, name, password_hash,"
                " password_salt, iterations, created_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                (email, email.strip().lower(), name, digest, salt, iterations, now),
            )
        except sqlite3.IntegrityError as e:
            raise EmailAlreadyRegistered(email) from e

        return {"id": cur.lastrowid, "email": email, "name": name, "created_at": now}


def get_user_by_email(email: str) -> Optional[sqlite3.Row]:
    with connect() as conn:
        return conn.execute(
            "SELECT * FROM users WHERE email_lower = ?", (email.strip().lower(),)
        ).fetchone()


def authenticate(email: str, password: str) -> Optional[Dict[str, Any]]:
    """Return the user on a correct password, else None."""
    row = get_user_by_email(email)
    if row is None:
        # Burn comparable time on an unknown address so response timing does
        # not reveal which addresses are registered.
        hash_password(password)
        return None

    if not verify_password(password, row["password_hash"], row["password_salt"],
                           row["iterations"]):
        return None

    return {"id": row["id"], "email": row["email"], "name": row["name"]}


def create_auth_session(user_id: int, ttl: timedelta = SESSION_TTL) -> str:
    """Issue an opaque bearer token. Only its hash is stored."""
    token = secrets.token_urlsafe(TOKEN_BYTES)
    now = _now()
    with connect() as conn:
        conn.execute(
            "INSERT INTO auth_sessions (token_hash, user_id, created_at, expires_at,"
            " last_seen) VALUES (?, ?, ?, ?, ?)",
            (_hash_token(token), user_id, _iso(now), _iso(now + ttl), _iso(now)),
        )
    return token


def resolve_auth_session(token: str) -> Optional[Dict[str, Any]]:
    """
    Look up the user behind a token, or None if unknown or expired.

    Expired rows are deleted on sight, which keeps the table from growing
    without a separate sweeper.
    """
    if not token:
        return None

    token_hash = _hash_token(token)
    now = _now()

    with connect() as conn:
        row = conn.execute(
            "SELECT s.token_hash, s.expires_at, u.id, u.email, u.name"
            " FROM auth_sessions s JOIN users u ON u.id = s.user_id"
            " WHERE s.token_hash = ?",
            (token_hash,),
        ).fetchone()

        if row is None:
            return None

        if datetime.fromisoformat(row["expires_at"]) <= now:
            conn.execute("DELETE FROM auth_sessions WHERE token_hash = ?", (token_hash,))
            return None

        conn.execute(
            "UPDATE auth_sessions SET last_seen = ? WHERE token_hash = ?",
            (_iso(now), token_hash),
        )
        return {"id": row["id"], "email": row["email"], "name": row["name"]}


def delete_auth_session(token: str) -> bool:
    """Log out one token. Returns True if a session was removed."""
    with connect() as conn:
        cur = conn.execute(
            "DELETE FROM auth_sessions WHERE token_hash = ?", (_hash_token(token),)
        )
        return cur.rowcount > 0


def purge_expired_sessions() -> int:
    """Delete every expired session. Returns how many went."""
    with connect() as conn:
        cur = conn.execute(
            "DELETE FROM auth_sessions WHERE expires_at <= ?", (_iso(_now()),)
        )
        return cur.rowcount


def set_workspace(user_id: int, session_id: str) -> None:
    """Remember which agent session belongs to this user."""
    with connect() as conn:
        conn.execute(
            "INSERT INTO user_workspaces (user_id, session_id, updated_at)"
            " VALUES (?, ?, ?)"
            " ON CONFLICT(user_id) DO UPDATE SET session_id = excluded.session_id,"
            " updated_at = excluded.updated_at",
            (user_id, session_id, _iso(_now())),
        )


def get_workspace(user_id: int) -> Optional[str]:
    """The agent session id this user last worked in, if any."""
    with connect() as conn:
        row = conn.execute(
            "SELECT session_id FROM user_workspaces WHERE user_id = ?", (user_id,)
        ).fetchone()
        return row["session_id"] if row else None


def save_session_state(session_id: str, state: Dict[str, Any]) -> None:
    """
    Persist an agent session: profile, roadmap, documents, verification and the
    chat transcript.

    Serialisation is best-effort - `default=str` keeps an unexpected value from
    turning a chat reply into a 500. Losing one field beats losing the turn.
    """
    payload = json.dumps(state, default=str)
    now = _iso(_now())
    with connect() as conn:
        conn.execute(
            "INSERT INTO session_states (session_id, state, created_at, updated_at)"
            " VALUES (?, ?, ?, ?)"
            " ON CONFLICT(session_id) DO UPDATE SET state = excluded.state,"
            " updated_at = excluded.updated_at",
            (session_id, payload, now, now),
        )


def load_session_state(session_id: str) -> Optional[Dict[str, Any]]:
    """Read a persisted agent session, or None if it was never stored."""
    with connect() as conn:
        row = conn.execute(
            "SELECT state FROM session_states WHERE session_id = ?", (session_id,)
        ).fetchone()
    if row is None:
        return None
    try:
        return json.loads(row["state"])
    except json.JSONDecodeError:
        return None


def delete_session_state(session_id: str) -> bool:
    """Forget a persisted agent session."""
    with connect() as conn:
        cur = conn.execute(
            "DELETE FROM session_states WHERE session_id = ?", (session_id,)
        )
        return cur.rowcount > 0
