import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from utils.agents.agents import BaseAgent
from tools.data_tools import DataAnalysisTools
from tools.sql_tools import DataEngineeringTools


class BaseAgentTests(unittest.TestCase):
    def test_build_tool_schema(self):
        def sample_tool(value: int) -> int:
            """Return the provided value."""
            return value

        agent = BaseAgent(
            name="demo",
            description="demo agent",
            system_prompt="You are a demo agent.",
            tools={"sample_tool": sample_tool},
        )

        schema = agent._build_tool_schema()

        self.assertEqual(len(schema), 1)
        self.assertEqual(schema[0]["function"]["name"], "sample_tool")
        self.assertEqual(schema[0]["function"]["description"], "Return the provided value.")

    def test_run_executes_tool_calls(self):
        def add(a: int, b: int) -> int:
            """Add two numbers."""
            return a + b

        agent = BaseAgent(
            name="calculator",
            description="calculator agent",
            system_prompt="You are a calculator agent.",
            tools={"add": add},
        )

        class FakeLLMClient:
            def __init__(self):
                self.calls = 0

            def chat(self, messages, temperature=None, max_tokens=None, tools=None):
                self.calls += 1
                if self.calls == 1:
                    return {
                        "type": "tool_call",
                        "tool_calls": [
                            SimpleNamespace(
                                function=SimpleNamespace(
                                    name="add",
                                    arguments='{"a": 2, "b": 3}',
                                )
                            )
                        ],
                        "message": None,
                    }
                return "The answer is 5."

        fake_client = FakeLLMClient()
        with patch("utils.agents.agents.llm_client", fake_client):
            result = agent.run("Add 2 and 3")

        self.assertEqual(result, "The answer is 5.")

    def test_try_local_tool_plan_uses_file_loader(self):
        def load_data(path: str):
            return {"status": "success", "path": path}

        agent = BaseAgent(
            name="loader",
            description="loader agent",
            system_prompt="You are a loader agent.",
            tools={"load_data": load_data},
        )

        result = agent._try_local_tool_plan("Load data.csv")

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["path"], "data.csv")

    def test_load_then_summarize_uses_loaded_dataframe(self):
        with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False) as handle:
            handle.write("a,b\n1,2\n3,4\n")
            path = handle.name

        try:
            agent = BaseAgent(
                name="loader",
                description="loader agent",
                system_prompt="You are a loader agent.",
                tools={
                    "load_data": DataAnalysisTools.load_data,
                    "get_summary_statistics": DataAnalysisTools.get_summary_statistics,
                },
            )

            load_result = agent._try_local_tool_plan(f"Load {path}")
            summary_result = agent._try_local_tool_plan("Summarize it")

            self.assertEqual(load_result["status"], "success")
            self.assertEqual(summary_result["status"], "success")
            self.assertIn("summary", summary_result)
        finally:
            os.remove(path)


class FinanceWorkflowOrchestratorTests(unittest.TestCase):
    def test_load_data_source_merges_and_standardizes_files(self):
        with tempfile.TemporaryDirectory() as directory:
            first = os.path.join(directory, "first.csv")
            second = os.path.join(directory, "second.json")
            with open(first, "w", encoding="utf-8") as handle:
                handle.write("Revenue,Profit\n100,10\n")
            with open(second, "w", encoding="utf-8") as handle:
                handle.write('[{"revenue": "200", "expenses": "150"}]')

            result = DataEngineeringTools.load_data_source(directory)

            self.assertEqual(result["file_count"], 2)
            self.assertEqual(result["rows"], 2)
            self.assertEqual(result["columns"], ["_source_file", "_source_name", "expenses", "profit", "revenue"])
            self.assertIsNone(result["records"][0]["expenses"])
            self.assertEqual(result["records"][1]["revenue"], "200")

    def test_workflow_analyzes_a_folder_of_files(self):
        from agents.orchestrator import FinanceWorkflowOrchestrator

        with tempfile.TemporaryDirectory() as directory:
            with open(os.path.join(directory, "one.csv"), "w", encoding="utf-8") as handle:
                handle.write("revenue,profit,expenses\n100,10,80\n")
            with open(os.path.join(directory, "two.json"), "w", encoding="utf-8") as handle:
                handle.write('[{"revenue": "200", "profit": "30", "expenses": "150"}]')

            result = FinanceWorkflowOrchestrator().run_workflow(
                "Summarize the business dataset",
                directory,
            )

            self.assertEqual(result["route"], "data_analysis")
            self.assertEqual(result["dataset"]["rows"], 2)
            self.assertEqual(result["dataset"]["file_count"], 2)

    def test_generic_prompt_returns_direct_response(self):
        from agents.orchestrator import FinanceWorkflowOrchestrator

        orchestrator = FinanceWorkflowOrchestrator()
        result = orchestrator.run_workflow("Hello, can you help me with a general question?")

        self.assertEqual(result["route"], "generic")
        self.assertTrue(result["response"].strip())

    def test_financial_dataset_summary_stays_on_data_analysis_path(self):
        from agents.orchestrator import FinanceWorkflowOrchestrator

        orchestrator = FinanceWorkflowOrchestrator()
        result = orchestrator.run_workflow("Summarize the latest financial dataset")

        self.assertEqual(result["route"], "data_analysis")

    def test_llm_router_hint_can_delegate_a_general_question(self):
        from agents.supervisor_agent import SupervisorAgent

        supervisor = SupervisorAgent(
            data_engineering_agent=SimpleNamespace(build_dataset=lambda path: {"records": [], "columns": [], "preview": []}),
            data_agent=SimpleNamespace(summarize_data=lambda records: {}),
            finance_agent=SimpleNamespace(analyze_financials=lambda data: {}),
            reviewer_agent=SimpleNamespace(review_recommendation=lambda recommendation: ""),
            decision_planner_agent=SimpleNamespace(plan_actions=lambda finance_comment, review: {}),
        )

        with patch(
            "agents.supervisor_agent.llm_client.chat",
            return_value="ACTION: answer\nROUTE: generic\nRESPONSE: Data analysis is the process of inspecting and interpreting data.",
        ):
            result = supervisor.execute("What is data analysis?")

        self.assertEqual(result["route"], "generic")
        self.assertIn("data analysis", result["response"].lower())

    def test_full_workflow_route_includes_all_steps(self):
        from agents.orchestrator import FinanceWorkflowOrchestrator

        orchestrator = FinanceWorkflowOrchestrator()
        result = orchestrator.run_workflow("Assess portfolio risk and recommend actions")

        self.assertEqual(result["route"], "full_workflow")
        self.assertIn("dataset", result)
        self.assertIn("data_summary", result)
        self.assertIn("finance_comment", result)
        self.assertIn("review", result)
        self.assertIn("decision_plan", result)
        self.assertEqual(
            result["workflow_path"],
            ["data_engineering", "data_analysis", "finance_analysis", "review", "decision_planning"],
        )

    def test_data_engineering_route_returns_dataset_only(self):
        from agents.orchestrator import FinanceWorkflowOrchestrator

        orchestrator = FinanceWorkflowOrchestrator()
        result = orchestrator.run_workflow("Load the latest CSV data source")

        self.assertEqual(result["route"], "data_engineering")
        self.assertIn("dataset", result)
        self.assertNotIn("data_summary", result)
        self.assertNotIn("finance_comment", result)
        self.assertNotIn("review", result)
        self.assertNotIn("decision_plan", result)


if __name__ == "__main__":
    unittest.main()
