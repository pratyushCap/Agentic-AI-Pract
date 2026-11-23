import json
import sqlite3
from pathlib import Path
from typing import Any, Dict, List


class SessionOwnershipError(PermissionError):
    """Raised when a caller attempts to read or update another principal's session."""


class AgentStateStore:
    """Persist API conversations and bounded workflow audit records in SQLite."""

    def __init__(self, database_path: str | Path):
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        connection = self._connect()
        try:
            with connection:
                connection.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS agent_sessions (
                        session_id TEXT PRIMARY KEY,
                        principal_id TEXT NOT NULL,
                        conversation_json TEXT NOT NULL,
                        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                    );
                    CREATE TABLE IF NOT EXISTS agent_runs (
                        run_id TEXT PRIMARY KEY,
                        session_id TEXT NOT NULL,
                        principal_id TEXT NOT NULL,
                        request TEXT NOT NULL,
                        status TEXT NOT NULL,
                        audit_events_json TEXT NOT NULL,
                        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                    );
                    CREATE INDEX IF NOT EXISTS idx_agent_runs_session
                        ON agent_runs (principal_id, session_id, created_at);
                    """
                )
        finally:
            connection.close()

    def load_conversation(self, session_id: str, principal_id: str) -> List[Dict[str, str]] | None:
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT principal_id, conversation_json FROM agent_sessions WHERE session_id = ?",
                (session_id,),
            ).fetchone()
        finally:
            connection.close()
        if row is None:
            return None
        if row[0] != principal_id:
            raise SessionOwnershipError("Session does not belong to this caller.")
        return json.loads(row[1])

    def load_runs(self, session_id: str, principal_id: str) -> List[Dict[str, Any]]:
        connection = self._connect()
        try:
            owner = connection.execute(
                "SELECT principal_id FROM agent_sessions WHERE session_id = ?",
                (session_id,),
            ).fetchone()
            if owner is None:
                return []
            if owner[0] != principal_id:
                raise SessionOwnershipError("Session does not belong to this caller.")
            rows = connection.execute(
                """
                SELECT run_id, request, status, audit_events_json, created_at
                FROM agent_runs
                WHERE principal_id = ? AND session_id = ?
                ORDER BY created_at, rowid
                """,
                (principal_id, session_id),
            ).fetchall()
        finally:
            connection.close()
        return [
            {
                "run_id": row[0],
                "request": row[1],
                "status": row[2],
                "audit_events": json.loads(row[3]),
                "created_at": row[4],
            }
            for row in rows
        ]

    def save_workflow(
        self,
        *,
        run_id: str,
        session_id: str,
        principal_id: str,
        request: str,
        status: str,
        audit_events: List[Dict[str, Any]],
        conversation: List[Dict[str, str]],
        assistant_message: str,
    ) -> None:
        serialized_events = json.dumps(audit_events, ensure_ascii=False, default=str)
        connection = self._connect()
        try:
            with connection:
                connection.execute("BEGIN IMMEDIATE")
                row = connection.execute(
                    "SELECT principal_id, conversation_json FROM agent_sessions WHERE session_id = ?",
                    (session_id,),
                ).fetchone()
                if row is not None and row[0] != principal_id:
                    raise SessionOwnershipError("Session does not belong to this caller.")
                current_conversation = (
                    json.loads(row[1])
                    if row is not None
                    else conversation
                )
                updated_conversation = (
                    current_conversation
                    + [
                        {"role": "user", "content": request},
                        {"role": "assistant", "content": assistant_message},
                    ]
                )[-24:]
                serialized_conversation = json.dumps(updated_conversation, ensure_ascii=False)
                connection.execute(
                    """
                    INSERT INTO agent_sessions (session_id, principal_id, conversation_json, updated_at)
                    VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                    ON CONFLICT(session_id) DO UPDATE SET
                        conversation_json = excluded.conversation_json,
                        updated_at = CURRENT_TIMESTAMP
                    """,
                    (session_id, principal_id, serialized_conversation),
                )
                connection.execute(
                    """
                    INSERT INTO agent_runs (
                        run_id, session_id, principal_id, request, status, audit_events_json
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (run_id, session_id, principal_id, request, status, serialized_events),
                )
        finally:
            connection.close()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=10)
        connection.execute("PRAGMA busy_timeout = 10000")
        return connection
