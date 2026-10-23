"""
Session Manager
Handles session state storage and retrieval
"""
import logging
import uuid
from typing import Dict, Optional
from datetime import datetime, timedelta
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from agents.state import AgentState, get_initial_state
import db

logger = logging.getLogger(__name__)


class SessionManager:
    """
    Manages user sessions in memory
    """
    
    def __init__(self, session_timeout_minutes: int = 30):
        """
        Initialize session manager
        
        Args:
            session_timeout_minutes: Session timeout in minutes
        """
        self.sessions: Dict[str, Dict] = {}
        self.session_timeout = timedelta(minutes=session_timeout_minutes)
    
    def create_session(self) -> str:
        """
        Create a new session
        
        Returns:
            Session ID
        """
        session_id = str(uuid.uuid4())
        state = get_initial_state()
        self.sessions[session_id] = {
            "state": state,
            "created_at": datetime.now(),
            "last_accessed": datetime.now()
        }
        self._persist(session_id, state)
        return session_id

    @staticmethod
    def _persist(session_id: str, state: AgentState) -> None:
        """
        Write the session through to SQLite.

        Best-effort: a storage hiccup must not fail the user's turn. The
        in-memory copy still serves the current request; only durability is
        lost, and the next write will try again.
        """
        try:
            db.save_session_state(session_id, state)
        except Exception:
            logger.exception("Could not persist session %s", session_id)
    
    def get_session(self, session_id: str) -> Optional[AgentState]:
        """Get session state"""
        session = self.sessions.get(session_id)

        # Expired in memory: fall through to disk rather than dropping the
        # user's work.
        if session and datetime.now() - session["last_accessed"] > self.session_timeout:
            del self.sessions[session_id]
            session = None

        if session is None:
            # Not in memory - the process may have restarted, or the entry may have aged out
            state = db.load_session_state(session_id)
            if state is None:
                return None
            self.sessions[session_id] = {
                "state": state,
                "created_at": datetime.now(),
                "last_accessed": datetime.now(),
            }
            return state

        # Update last accessed time
        session["last_accessed"] = datetime.now()

        return session["state"]
    
    def update_session(self, session_id: str, state: AgentState) -> bool:
        """Update session state"""
        # Accept updates for sessions restored from disk but not yet cached.
        if session_id not in self.sessions:
            if db.load_session_state(session_id) is None:
                return False
            self.sessions[session_id] = {
                "state": state,
                "created_at": datetime.now(),
                "last_accessed": datetime.now(),
            }

        self.sessions[session_id]["state"] = state
        self.sessions[session_id]["last_accessed"] = datetime.now()
        self._persist(session_id, state)
        return True
    
    def delete_session(self, session_id: str) -> bool:
        """Delete a session"""
        in_memory = self.sessions.pop(session_id, None) is not None
        try:
            on_disk = db.delete_session_state(session_id)
        except Exception:
            logger.exception("Could not delete persisted session %s", session_id)
            on_disk = False
        return in_memory or on_disk
    
    def cleanup_expired_sessions(self):
        """Remove all expired sessions"""
        now = datetime.now()
        expired = [
            sid for sid, session in self.sessions.items()
            if now - session["last_accessed"] > self.session_timeout
        ]
        # Evict from the cache only
        for sid in expired:
            self.sessions.pop(sid, None)
    
    def get_all_sessions(self) -> Dict[str, Dict]:
        """
        Get all active sessions (for admin/debugging)
        
        Returns:
            Dictionary of all sessions
        """
        self.cleanup_expired_sessions()
        return {
            sid: {
                "created_at": session["created_at"].isoformat(),
                "last_accessed": session["last_accessed"].isoformat(),
                "stage": session["state"]["current_stage"],
                "message_count": len(session["state"]["messages"])
            }
            for sid, session in self.sessions.items()
        }


# Global session manager instance
session_manager = SessionManager()
