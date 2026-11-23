import sqlite3
import tempfile
import unittest
from pathlib import Path

from utils.state_store import (
    AgentStateStore,
    ApprovalSelfDecisionError,
    ApprovalStateError,
)


class ApprovalFlowTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.database = Path(self.directory.name, "agent.sqlite3")
        self.store = AgentStateStore(self.database)
        self.approval_id = "approval-1"
        self.store.save_workflow(
            run_id="run-1",
            session_id="session-1",
            principal_id="requester",
            request="Rebalance the portfolio",
            status="approval_required",
            audit_events=[{"event_type": "approval_requested"}],
            conversation=[],
            assistant_message="Approval required.",
            approval={
                "approval_id": self.approval_id,
                "recommendation": "Review the proposed rebalance.",
            },
        )

    def test_independent_approver_records_decision_and_audit(self):
        approval = self.store.decide_approval(
            self.approval_id,
            decided_by="reviewer",
            decision="approved",
            note="Reviewed against policy.",
        )

        self.assertEqual(approval["status"], "approved")
        self.assertEqual(approval["decided_by"], "reviewer")
        self.assertFalse(approval["action_executed"])
        self.assertEqual(approval["audit_events"][-1]["event_type"], "approval_approved")
        self.assertEqual(approval["audit_events"][-1]["note"], "Reviewed against policy.")

        run = self.store.load_runs("session-1", "requester")[0]
        self.assertEqual(run["audit_events"][-1]["approval_id"], self.approval_id)
        self.assertEqual(run["audit_events"][-1]["actor_id"], "reviewer")

    def test_requester_cannot_approve_own_request(self):
        with self.assertRaises(ApprovalSelfDecisionError):
            self.store.decide_approval(
                self.approval_id,
                decided_by="requester",
                decision="approved",
            )

        self.assertEqual(self.store.get_approval(self.approval_id)["status"], "pending")

    def test_rejected_decision_is_terminal(self):
        self.store.decide_approval(
            self.approval_id,
            decided_by="reviewer",
            decision="rejected",
        )

        with self.assertRaises(ApprovalStateError):
            self.store.decide_approval(
                self.approval_id,
                decided_by="another-reviewer",
                decision="approved",
            )

        self.assertEqual(self.store.get_approval(self.approval_id)["status"], "rejected")

    def test_expired_request_is_marked_and_audited(self):
        connection = sqlite3.connect(self.database)
        try:
            connection.execute(
                "UPDATE approval_requests SET expires_at = '2000-01-01T00:00:00+00:00' "
                "WHERE approval_id = ?",
                (self.approval_id,),
            )
            connection.commit()
        finally:
            connection.close()

        approval = self.store.get_approval(self.approval_id)

        self.assertEqual(approval["status"], "expired")
        self.assertEqual(approval["audit_events"][-1]["event_type"], "approval_expired")
        with self.assertRaises(ApprovalStateError):
            self.store.decide_approval(
                self.approval_id,
                decided_by="reviewer",
                decision="approved",
            )


if __name__ == "__main__":
    unittest.main()
