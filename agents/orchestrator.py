from typing import List, Optional, Union

from agents.finance_agent import FinanceAnalystAgent
from agents.data_agent import DataAnalystAgent
from agents.data_engineering_agent import DataEngineeringAgent
from agents.reviewer_agent import ReviewerAgent
from agents.decision_agent import DecisionPlannerAgent
from agents.supervisor_agent import SupervisorAgent


class FinanceWorkflowOrchestrator:
    def __init__(self):
        self.finance_agent = FinanceAnalystAgent()
        self.data_agent = DataAnalystAgent()
        self.data_engineering_agent = DataEngineeringAgent()
        self.reviewer_agent = ReviewerAgent()
        self.decision_planner = DecisionPlannerAgent()
        self.supervisor_agent = SupervisorAgent(
            self.data_engineering_agent,
            self.data_agent,
            self.finance_agent,
            self.reviewer_agent,
            self.decision_planner,
        )

    def run_workflow(
        self,
        request: str,
        source: Optional[Union[str, List[str]]] = None,
    ) -> dict:
        """Run a supervised multi-agent finance workflow."""
        workflow_result = self.supervisor_agent.execute(
            request,
            source or "data/sample_finance_data.csv",
        )
        if workflow_result.get("error"):
            return workflow_result

        response = {
            "request": workflow_result["request"],
            "route": workflow_result["route"],
            "workflow_path": workflow_result["workflow_path"],
            "summary": self._build_summary(workflow_result),
        }

        if workflow_result["route"] == "generic":
            response["response"] = workflow_result["response"]
            return response

        response["dataset"] = {
            "rows": workflow_result["data_engineering"].get("rows"),
            "columns": workflow_result["data_engineering"].get("columns"),
            "preview": workflow_result["data_engineering"].get("preview"),
            "file_count": workflow_result["data_engineering"].get("file_count", 0),
        }

        if workflow_result["route"] == "data_engineering":
            return response

        if workflow_result.get("data_analysis") is not None:
            response["data_summary"] = workflow_result["data_analysis"]

        if workflow_result["route"] == "data_analysis":
            return response

        if workflow_result.get("finance_analysis") is not None:
            response["finance_comment"] = workflow_result["finance_analysis"]
        if workflow_result.get("review") is not None:
            response["review"] = workflow_result["review"]
        if workflow_result.get("decision_plan") is not None:
            response["decision_plan"] = workflow_result["decision_plan"]

        return response

    def _build_summary(self, workflow_result: dict) -> str:
        route = workflow_result.get("route", "generic")
        if route == "generic":
            return workflow_result.get("response", "")

        steps = []
        steps.append("Step 1 — Data loading: The workflow loaded the financial dataset successfully.")

        if route in {"data_engineering", "data_analysis", "finance_analysis", "full_workflow"}:
            dataset = workflow_result.get("data_engineering", {})
            rows = dataset.get("rows", 0)
            columns = dataset.get("columns", [])
            steps.append(f"Step 2 — Dataset inspection: {rows} rows and {len(columns)} columns were loaded for review.")

        if route in {"data_analysis", "finance_analysis", "full_workflow"}:
            data_summary = workflow_result.get("data_analysis", {})
            summary_text = data_summary.get("summary", "") if isinstance(data_summary, dict) else ""
            if summary_text:
                steps.append(f"Step 3 — Data analysis: {summary_text}")
            else:
                steps.append("Step 3 — Data analysis: Key statistics and patterns were generated from the dataset.")

        if route in {"finance_analysis", "full_workflow"}:
            finance_comment = workflow_result.get("finance_analysis", {})
            recommendation = finance_comment.get("recommendation", "") if isinstance(finance_comment, dict) else ""
            risk = finance_comment.get("risk", {}) if isinstance(finance_comment, dict) else {}
            risk_score = risk.get("risk_score", "") if isinstance(risk, dict) else ""
            if recommendation:
                steps.append(f"Step 4 — Finance review: {recommendation}")
            if risk_score:
                steps.append(f"Step 5 — Risk signal: Risk score is {risk_score}.")
            else:
                steps.append("Step 5 — Risk signal: Portfolio risk was assessed.")

        if route == "full_workflow":
            review = workflow_result.get("review", "")
            decision_plan = workflow_result.get("decision_plan", "")
            if review:
                steps.append(f"Step 6 — Reviewer feedback: {review}")
            if decision_plan:
                steps.append(f"Step 7 — Final recommendation: {decision_plan}")
        elif route in {"finance_analysis", "data_analysis"}:
            steps.append("Final recommendation: Review the insights above and decide on the next action.")

        return "\n".join(steps)
