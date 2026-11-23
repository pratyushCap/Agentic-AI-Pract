import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List


class SessionOwnershipError(PermissionError):
    """Raised when a caller attempts to read or update another principal's session."""


class ApprovalNotFoundError(LookupError):
    """Raised when an approval request does not exist."""


class ApprovalStateError(ValueError):
    """Raised when an approval request is no longer pending."""


class ApprovalSelfDecisionError(PermissionError):
    """Raised when a requester attempts to decide their own approval."""


class AgentStateStore:
    """Persist API conversations and bounded workflow audit records in SQLite."""

    APPROVAL_TTL = timedelta(hours=24)

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
                    CREATE TABLE IF NOT EXISTS approval_requests (
                        approval_id TEXT PRIMARY KEY,
                        run_id TEXT NOT NULL UNIQUE,
                        session_id TEXT NOT NULL,
                        requester_id TEXT NOT NULL,
                        request TEXT NOT NULL,
                        recommendation TEXT NOT NULL,
                        status TEXT NOT NULL CHECK (
                            status IN ('pending', 'approved', 'rejected', 'expired')
                        ),
                        created_at TEXT NOT NULL,
                        expires_at TEXT NOT NULL,
                        decided_at TEXT,
                        decided_by TEXT,
                        decision_note TEXT,
                        audit_events_json TEXT NOT NULL
                    );
                    CREATE INDEX IF NOT EXISTS idx_approval_requests_status
                        ON approval_requests (status, expires_at);
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

    def get_approval(self, approval_id: str) -> Dict[str, Any] | None:
        connection = self._connect()
        try:
            with connection:
                row = connection.execute(
                    "SELECT status, expires_at FROM approval_requests WHERE approval_id = ?",
                    (approval_id,),
                ).fetchone()
                if row is None:
                    return None
                if row[0] == "pending" and self._is_expired(row[1]):
                    connection.execute(
                        "UPDATE approval_requests SET status = 'expired' WHERE approval_id = ?",
                        (approval_id,),
                    )
                    self._record_approval_event(
                        connection,
                        approval_id,
                        "approval_expired",
                        actor_id=None,
                    )
            row = self._select_approval(connection, approval_id)
        finally:
            connection.close()
        return self._approval_dict(row) if row else None

    def list_approvals(self, status: str | None = None) -> List[Dict[str, Any]]:
        connection = self._connect()
        try:
            with connection:
                self._expire_pending_approvals(connection)
            query = """
                SELECT approval_id, run_id, session_id, requester_id, request,
                       recommendation, status, created_at, expires_at, decided_at,
                       decided_by, decision_note, audit_events_json
                FROM approval_requests
            """
            parameters: tuple[str, ...] = ()
            if status is not None:
                query += " WHERE status = ?"
                parameters = (status,)
            query += " ORDER BY created_at, approval_id"
            rows = connection.execute(query, parameters).fetchall()
        finally:
            connection.close()
        return [self._approval_dict(row) for row in rows]

    def decide_approval(
        self,
        approval_id: str,
        *,
        decided_by: str,
        decision: str,
        note: str | None = None,
    ) -> Dict[str, Any]:
        if decision not in {"approved", "rejected"}:
            raise ValueError("Approval decision must be approved or rejected.")
        connection = self._connect()
        expired = False
        try:
            with connection:
                connection.execute("BEGIN IMMEDIATE")
                row = connection.execute(
                    """
                    SELECT requester_id, status, expires_at
                    FROM approval_requests
                    WHERE approval_id = ?
                    """,
                    (approval_id,),
                ).fetchone()
                if row is None:
                    raise ApprovalNotFoundError("Approval request not found.")
                if row[0] == decided_by:
                    raise ApprovalSelfDecisionError(
                        "The requester cannot decide their own approval."
                    )
                if row[1] != "pending":
                    raise ApprovalStateError(f"Approval request is already {row[1]}.")
                if self._is_expired(row[2]):
                    connection.execute(
                        "UPDATE approval_requests SET status = 'expired' WHERE approval_id = ?",
                        (approval_id,),
                    )
                    self._record_approval_event(
                        connection,
                        approval_id,
                        "approval_expired",
                        actor_id=None,
                    )
                    expired = True
                else:
                    decided_at = datetime.now(timezone.utc).isoformat()
                    connection.execute(
                        """
                        UPDATE approval_requests
                        SET status = ?, decided_at = ?, decided_by = ?, decision_note = ?
                        WHERE approval_id = ? AND status = 'pending'
                        """,
                        (decision, decided_at, decided_by, note, approval_id),
                    )
                    self._record_approval_event(
                        connection,
                        approval_id,
                        f"approval_{decision}",
                        actor_id=decided_by,
                        note=note,
                    )
            if expired:
                raise ApprovalStateError("Approval request has expired.")
            row = self._select_approval(connection, approval_id)
        finally:
            connection.close()
        if row is None:
            raise ApprovalNotFoundError("Approval request not found.")
        return self._approval_dict(row)

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
        approval: Dict[str, str] | None = None,
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
                if approval is not None:
                    created_at = datetime.now(timezone.utc)
                    expires_at = created_at + self.APPROVAL_TTL
                    approval_event = {
                        "timestamp": created_at.isoformat(),
                        "event_type": "approval_requested",
                        "approval_id": approval["approval_id"],
                        "requester_id": principal_id,
                        "expires_at": expires_at.isoformat(),
                    }
                    connection.execute(
                        """
                        INSERT INTO approval_requests (
                            approval_id, run_id, session_id, requester_id, request,
                            recommendation, status, created_at, expires_at, audit_events_json
                        ) VALUES (?, ?, ?, ?, ?, ?, 'pending', ?, ?, ?)
                        """,
                        (
                            approval["approval_id"],
                            run_id,
                            session_id,
                            principal_id,
                            request,
                            approval["recommendation"],
                            created_at.isoformat(),
                            expires_at.isoformat(),
                            json.dumps([approval_event], ensure_ascii=False),
                        ),
                    )
        finally:
            connection.close()

    def _select_approval(
        self,
        connection: sqlite3.Connection,
        approval_id: str,
    ) -> tuple[Any, ...] | None:
        return connection.execute(
            """
            SELECT approval_id, run_id, session_id, requester_id, request,
                   recommendation, status, created_at, expires_at, decided_at,
                   decided_by, decision_note, audit_events_json
            FROM approval_requests
            WHERE approval_id = ?
            """,
            (approval_id,),
        ).fetchone()

    def _expire_pending_approvals(self, connection: sqlite3.Connection) -> None:
        rows = connection.execute(
            """
            SELECT approval_id
            FROM approval_requests
            WHERE status = 'pending' AND julianday(expires_at) <= julianday('now')
            """
        ).fetchall()
        for (approval_id,) in rows:
            connection.execute(
                "UPDATE approval_requests SET status = 'expired' WHERE approval_id = ?",
                (approval_id,),
            )
            self._record_approval_event(
                connection,
                approval_id,
                "approval_expired",
                actor_id=None,
            )

    def _record_approval_event(
        self,
        connection: sqlite3.Connection,
        approval_id: str,
        event_type: str,
        *,
        actor_id: str | None,
        note: str | None = None,
    ) -> None:
        row = connection.execute(
            "SELECT run_id, audit_events_json FROM approval_requests WHERE approval_id = ?",
            (approval_id,),
        ).fetchone()
        if row is None:
            return
        event: Dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event_type": event_type,
            "actor_id": actor_id,
        }
        if note is not None:
            event["note"] = note
        approval_events = json.loads(row[1])
        approval_events.append(event)
        connection.execute(
            "UPDATE approval_requests SET audit_events_json = ? WHERE approval_id = ?",
            (json.dumps(approval_events, ensure_ascii=False), approval_id),
        )
        run_row = connection.execute(
            "SELECT audit_events_json FROM agent_runs WHERE run_id = ?",
            (row[0],),
        ).fetchone()
        if run_row is not None:
            run_events = json.loads(run_row[0])
            run_events.append({"approval_id": approval_id, **event})
            connection.execute(
                "UPDATE agent_runs SET audit_events_json = ? WHERE run_id = ?",
                (json.dumps(run_events, ensure_ascii=False), row[0]),
            )

    def _approval_dict(self, row: tuple[Any, ...]) -> Dict[str, Any]:
        return {
            "approval_id": row[0],
            "run_id": row[1],
            "session_id": row[2],
            "requester_id": row[3],
            "request": row[4],
            "recommendation": row[5],
            "status": row[6],
            "created_at": row[7],
            "expires_at": row[8],
            "decided_at": row[9],
            "decided_by": row[10],
            "decision_note": row[11],
            "audit_events": json.loads(row[12]),
            "action_executed": False,
        }

    def _is_expired(self, expires_at: str) -> bool:
        expires = datetime.fromisoformat(expires_at)
        return expires <= datetime.now(timezone.utc)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=10)
        connection.execute("PRAGMA busy_timeout = 10000")
        return connection
