import sqlite3
import tempfile
import unittest
from pathlib import Path

from utils.state_store import AgentStateStore, SessionOwnershipError


class AgentStateStoreTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.database = Path(self.directory.name, "agent.sqlite3")
        self.store = AgentStateStore(self.database)

    def test_persists_conversation_and_audit_events(self):
        self.store.save_workflow(
            run_id="run-1",
            session_id="session-1",
            principal_id="analyst-1",
            request="Summarize revenue",
            status="completed",
            audit_events=[{"event_type": "agent_finished", "status": "completed"}],
            conversation=[],
            assistant_message="Revenue totals 100.",
        )

        self.assertEqual(
            self.store.load_conversation("session-1", "analyst-1"),
            [
                {"role": "user", "content": "Summarize revenue"},
                {"role": "assistant", "content": "Revenue totals 100."},
            ],
        )
        connection = sqlite3.connect(self.database)
        try:
            row = connection.execute(
                "SELECT request, status, audit_events_json FROM agent_runs WHERE run_id = ?",
                ("run-1",),
            ).fetchone()
        finally:
            connection.close()
        self.assertEqual(row[0:2], ("Summarize revenue", "completed"))
        self.assertIn("agent_finished", row[2])

    def test_session_isolation_rejects_another_principal(self):
        self.store.save_workflow(
            run_id="run-1",
            session_id="session-1",
            principal_id="analyst-1",
            request="hello",
            status="completed",
            audit_events=[],
            conversation=[],
            assistant_message="Hello.",
        )

        with self.assertRaises(SessionOwnershipError):
            self.store.load_conversation("session-1", "analyst-2")

        with self.assertRaises(SessionOwnershipError):
            self.store.save_workflow(
                run_id="run-2",
                session_id="session-1",
                principal_id="analyst-2",
                request="overwrite",
                status="completed",
                audit_events=[],
                conversation=[],
                assistant_message="No.",
            )


if __name__ == "__main__":
    unittest.main()
