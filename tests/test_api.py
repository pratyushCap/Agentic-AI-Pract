import tempfile
import unittest
from importlib import import_module
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException

from utils.state_store import AgentStateStore

api = import_module("api.app")


class ApiBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name).resolve()
        self.data_file = self.root / "sample.csv"
        self.data_file.write_text("revenue\n100\n", encoding="utf-8")
        self.principal = api.AuthenticatedPrincipal("analyst-1", "analyst", self.root)

    def test_api_source_is_limited_to_principal_data_root(self):
        self.assertEqual(api._resolve_api_source("sample.csv", self.root), str(self.data_file))

        with self.assertRaises(HTTPException) as raised:
            api._resolve_api_source("../outside.csv", self.root)
        self.assertEqual(raised.exception.status_code, 400)

    def test_viewer_role_cannot_start_analysis(self):
        viewer = api.AuthenticatedPrincipal("viewer-1", "viewer", self.root)

        with self.assertRaises(HTTPException) as raised:
            api.run_workflow(api.WorkflowRequest(prompt="Analyze revenue"), viewer)
        self.assertEqual(raised.exception.status_code, 403)

    def test_api_key_authentication_maps_a_principal_and_fails_closed(self):
        credentials = [{
            "key": "test-secret",
            "principal_id": "analyst-1",
            "role": "analyst",
            "data_root": str(self.root),
        }]
        with patch.object(api, "API_CREDENTIALS", credentials):
            principal = api.get_api_key("test-secret")
            self.assertEqual(principal.principal_id, "analyst-1")

            with self.assertRaises(HTTPException) as raised:
                api.get_api_key("wrong-secret")
            self.assertEqual(raised.exception.status_code, 401)

        with patch.object(api, "API_CREDENTIALS", []), patch.object(api, "API_AUTH_REQUIRED", True):
            with self.assertRaises(HTTPException) as raised:
                api.get_api_key(None)
            self.assertEqual(raised.exception.status_code, 503)

    def test_workflow_persists_and_reuses_session_conversation(self):
        class FakeAgent:
            def __init__(self):
                self.conversations = []

            def run(self, prompt, source, conversation):
                self.conversations.append(list(conversation))
                return {
                    "request": prompt,
                    "status": "completed",
                    "step_count": 1,
                    "max_steps": 8,
                    "response": "The dataset contains one row.",
                    "audit_events": [{"event_type": "agent_finished", "status": "completed"}],
                }

        database = self.root / "agent.sqlite3"
        fake_agent = FakeAgent()
        with patch.object(api, "state_store", AgentStateStore(database)):
            with patch.object(api, "agent", fake_agent):
                first = api.run_workflow(
                    api.WorkflowRequest(prompt="Summarize the data", source="sample.csv"),
                    self.principal,
                )
                second = api.run_workflow(
                    api.WorkflowRequest(
                        prompt="What did you find?",
                        source="sample.csv",
                        session_id=first.session_id,
                    ),
                    self.principal,
                )
                runs = api.state_store.load_runs(first.session_id, self.principal.principal_id)

        self.assertEqual(first.session_id, second.session_id)
        self.assertEqual(fake_agent.conversations[0], [])
        self.assertEqual(fake_agent.conversations[1][-2]["content"], "Summarize the data")
        self.assertEqual(fake_agent.conversations[1][-1]["content"], "The dataset contains one row.")
        self.assertEqual(len(runs), 2)
        self.assertEqual(runs[0]["status"], "completed")


if __name__ == "__main__":
    unittest.main()
