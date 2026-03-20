"""
Session lifecycle management.
One monitoring instance per logged-in session. Stops on logout or expiration.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime

from core.config import SESSION_REGISTRY_FILE
from core.models import SessionInfo

logger = logging.getLogger("SessionManager")


class SessionManager:
    """Manages user session lifecycle for the monitoring system."""

    def __init__(self):
        self._sessions: dict[str, SessionInfo] = {}
        self._load_registry()

    # ─── Public API ───────────────────────────────────────────────────────

    def create_session(self, user_id: str) -> SessionInfo:
        """Create and register a new monitoring session."""
        session = SessionInfo(user_id=user_id)
        self._sessions[session.session_id] = session
        self._save_registry()
        logger.info(f"Session created: {session.session_id} for user {user_id}")
        return session

    def get_session(self, session_id: str) -> SessionInfo | None:
        """Retrieve a session by ID."""
        return self._sessions.get(session_id)

    def is_active(self, session_id: str) -> bool:
        """Check if a session is still active."""
        session = self._sessions.get(session_id)
        return session is not None and session.is_active

    def deactivate_session(self, session_id: str) -> None:
        """Mark a session as inactive (logout or expiry)."""
        if session_id in self._sessions:
            self._sessions[session_id].is_active = False
            self._save_registry()
            logger.info(f"Session deactivated: {session_id}")

    def deactivate_all(self) -> None:
        """Deactivate all sessions (shutdown)."""
        for sid in self._sessions:
            self._sessions[sid].is_active = False
        self._save_registry()
        logger.info("All sessions deactivated.")

    def get_active_sessions(self) -> list[SessionInfo]:
        """Return all currently active sessions."""
        return [s for s in self._sessions.values() if s.is_active]

    # ─── Persistence ──────────────────────────────────────────────────────

    def _load_registry(self) -> None:
        """Load session registry from disk."""
        if SESSION_REGISTRY_FILE.exists():
            try:
                data = json.loads(SESSION_REGISTRY_FILE.read_text(encoding="utf-8"))
                for entry in data:
                    session = SessionInfo(**entry)
                    self._sessions[session.session_id] = session
            except Exception as e:
                logger.warning(f"Could not load session registry: {e}")

    def _save_registry(self) -> None:
        """Persist session registry to disk."""
        try:
            data = [s.model_dump() for s in self._sessions.values()]
            SESSION_REGISTRY_FILE.write_text(
                json.dumps(data, indent=2, default=str),
                encoding="utf-8",
            )
        except Exception as e:
            logger.error(f"Could not save session registry: {e}")
