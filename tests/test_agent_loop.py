import os
import tempfile
import unittest

from agents.graph import FinanceAgentGraph
from tools.data_tools import DataAnalysisTools
from tools.sql_tools import DataEngineeringTools
from tools.permissions import ToolPermission, ensure_tool_allowed
from unittest.mock import patch


class FinanceAgentLoopTests(unittest.TestCase):
    def _source(self, content: str) -> str:
        handle = tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, encoding="utf-8")
        handle.write(content)
        handle.close()
        self.addCleanup(lambda: os.remove(handle.name))
        return handle.name

    def test_agent_dynamically_loads_profiles_and_recommends(self):
        source = self._source("transaction_amount,risk_score\n100,0.2\n300,0.8\n")

        state = FinanceAgentGraph().run("Assess transaction risk", source)

        self.assertEqual(state["status"], "completed")
        self.assertEqual(state["step_count"], 4)
        self.assertIn("load_dataset", state["tool_results"])
        self.assertIn("profile_dataset", state["tool_results"])
        self.assertIn("analyze_transactions", state["tool_results"])
        self.assertIsNone(state["tool_results"]["load_dataset"]["records"])
        self.assertIn("evidence:", state["recommendation"].lower())
        self.assertIn("recommended action:", state["recommendation"].lower())

    def test_streaming_loader_keeps_full_profile_but_not_records(self):
        source = self._source(
            "transaction_amount,risk_score\n"
            + "\n".join(f"{index},0.5" for index in range(1000))
            + "\n"
        )

        loaded = DataEngineeringTools.load_data_source(source, include_records=False)
        profile = DataEngineeringTools.profile_data_source(source)

        self.assertEqual(loaded["rows"], 1000)
        self.assertIsNone(loaded["records"])
        self.assertEqual(profile["statistics"]["summary"]["transaction_amount"]["count"], 1000)
        self.assertEqual(profile["statistics"]["summary"]["risk_score"]["count"], 1000)

    def test_agent_requests_clarification_without_source(self):
        state = FinanceAgentGraph().run("Analyze my finance data")

        self.assertEqual(state["status"], "needs_clarification")
        self.assertIn("which csv", state["clarification"].lower())

    def test_agent_answers_greeting_without_loading_data(self):
        state = FinanceAgentGraph().run("hello", "data/sample_finance_data.csv")

        self.assertEqual(state["status"], "completed")
        self.assertEqual(state["step_count"], 1)
        self.assertIn("Hello", state["response"])
        self.assertEqual(state["tool_results"], {})

    def test_agent_answers_general_llm_question_without_loading_data(self):
        state = FinanceAgentGraph().run("what is llm ?", "data/sample_finance_data.csv")

        self.assertEqual(state["status"], "completed")
        self.assertEqual(state["step_count"], 1)
        self.assertIn("large language model", state["response"].lower())
        self.assertEqual(state["tool_results"], {})

    @patch(
        "agents.planner_agent.llm_client.chat",
        side_effect=[
            "INTENT: GENERAL",
            "A balanced diet should be personalized to your age, health, activity, and goals. Consult a qualified professional for medical needs.",
        ],
    )
    def test_agent_uses_llm_for_general_question(self, mock_chat):
        state = FinanceAgentGraph().run(
            "What is a perfect diet, and can you plan one for my body type?",
            "data/sample_finance_data.csv",
        )

        self.assertEqual(state["status"], "completed")
        self.assertEqual(state["intent"], "general")
        self.assertIn("balanced diet", state["response"])
        self.assertEqual(state["tool_results"], {})
        self.assertEqual(mock_chat.call_count, 2)

    def test_agent_requests_approval_for_sensitive_action(self):
        source = self._source("transaction_amount,risk_score\n100,0.2\n")

        state = FinanceAgentGraph().run("Rebalance the portfolio based on this data", source)

        self.assertEqual(state["status"], "approval_required")
        self.assertTrue(state["approval_required"])
        self.assertEqual(state["approval_status"], "pending")

    def test_permission_boundary_rejects_unapproved_action(self):
        with self.assertRaises(PermissionError):
            ensure_tool_allowed(ToolPermission("action", requires_approval=True))

    def test_profile_detects_transaction_domain_and_aligned_correlation(self):
        records = [
            {"transaction_amount": "10", "risk_score": "0.1"},
            {"transaction_amount": "20", "risk_score": ""},
            {"transaction_amount": "30", "risk_score": "0.3"},
        ]

        profile = DataAnalysisTools.profile_dataset(records)

        self.assertEqual(profile["domain"], "transactions")
        self.assertEqual(profile["statistics"]["summary"]["risk_score"]["count"], 2)
        self.assertEqual(profile["correlation"]["correlation"]["transaction_amount"]["risk_score"], 1.0)

    def test_agent_selects_finance_adapter(self):
        source = self._source(
            "revenue,profit,expenses\n"
            "1000,200,700\n"
            "1200,240,800\n"
        )

        state = FinanceAgentGraph().run("Review business profitability", source)

        self.assertEqual(state["status"], "completed")
        self.assertIn("analyze_finance", state["tool_results"])
        recommendation = state["tool_results"]["analyze_finance"]["recommendation"].lower()
        self.assertIn("profit margin is 20.00%", recommendation)
        self.assertIn("recommended action", recommendation)

    def test_agent_selects_portfolio_adapter(self):
        source = self._source(
            "equities,bonds,cash\n"
            "60,25,15\n"
            "70,20,10\n"
        )

        state = FinanceAgentGraph().run("Review portfolio concentration", source)

        self.assertEqual(state["status"], "completed")
        self.assertIn("analyze_portfolio", state["tool_results"])
        self.assertIn("evidence:", state["recommendation"].lower())
        self.assertIn("recommended action:", state["recommendation"].lower())

    def test_agent_records_execution_trace_without_tool_arguments(self):
        source = self._source("transaction_amount,risk_score\n100,0.2\n")

        state = FinanceAgentGraph().run("Assess transaction risk", source)

        event_types = [event["event_type"] for event in state["audit_events"]]
        self.assertEqual(event_types[0], "agent_started")
        self.assertIn("decision_made", event_types)
        self.assertIn("tool_started", event_types)
        self.assertIn("tool_completed", event_types)
        self.assertEqual(event_types[-1], "agent_finished")
        self.assertTrue(all("arguments" not in event for event in state["audit_events"]))


if __name__ == "__main__":
    unittest.main()
