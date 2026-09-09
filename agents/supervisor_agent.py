from typing import Any, Dict, List, Union

from llm.llm_config import llm_client
from utils.agents.agents import BaseAgent


class SupervisorAgent(BaseAgent):
    def __init__(
        self,
        data_engineering_agent: Any,
        data_agent: Any,
        finance_agent: Any,
        reviewer_agent: Any,
        decision_planner_agent: Any,
    ):
        super().__init__(
            name="supervisor",
            description="Supervises the finance workflow and orchestrates handoffs between specialist agents.",
            system_prompt=(
                "You are a workflow supervisor assistant. "
                "Route the business request through data engineering, data analysis, finance analysis, review, and decision planning."
            ),
            tools={},
        )
        self.data_engineering_agent = data_engineering_agent
        self.data_agent = data_agent
        self.finance_agent = finance_agent
        self.reviewer_agent = reviewer_agent
        self.decision_planner_agent = decision_planner_agent

    def execute(
        self,
        request: str,
        source_path: Union[str, List[str]] = "data/sample_finance_data.csv",
    ) -> Dict[str, Any]:
        """Execute the multi-agent finance workflow with explicit handoffs."""
        workflow: Dict[str, Any] = {
            "request": request,
            "workflow_path": [],
        }

        route = self._classify_request(request)
        workflow["route"] = route

        if route == "generic":
            llm_route, llm_response = self._get_llm_decision(request)
            if llm_route != "generic":
                route = llm_route
                workflow["route"] = route
                workflow["llm_routing_hint"] = llm_response or None
            else:
                workflow["response"] = llm_response or self._answer_with_llm(request)
                return workflow

        if route == "data_engineering":
            dataset = self.data_engineering_agent.build_dataset(source_path)
            workflow["data_engineering"] = dataset
            workflow["workflow_path"].append("data_engineering")
            return workflow

        dataset = self.data_engineering_agent.build_dataset(source_path)
        workflow["data_engineering"] = dataset
        workflow["workflow_path"].append("data_engineering")

        records = dataset.get("records", [])
        if not records:
            workflow["error"] = "Unable to load financial dataset."
            return workflow

        if route in {"data_analysis", "finance_analysis", "full_workflow"}:
            data_summary = self.data_agent.summarize_data(records)
            workflow["data_analysis"] = data_summary
            workflow["workflow_path"].append("data_analysis")
            if route == "data_analysis":
                return workflow

        latest_row = records[-1]
        finance_input = self._build_finance_input(latest_row)
        workflow["finance_input"] = finance_input

        finance_comment = self.finance_agent.analyze_financials(finance_input)
        workflow["finance_analysis"] = finance_comment
        workflow["workflow_path"].append("finance_analysis")

        if route == "finance_analysis":
            return workflow

        review = self.reviewer_agent.review_recommendation(finance_comment["recommendation"])
        workflow["review"] = review
        workflow["workflow_path"].append("review")

        decision = self.decision_planner_agent.plan_actions(finance_comment, review)
        workflow["decision_plan"] = decision.get("decision_plan")
        workflow["workflow_path"].append("decision_planning")

        return workflow

    def _classify_request(self, request: str) -> str:
        normalized = request.lower().strip()

        if not normalized:
            return "generic"

        greeting_tokens = ["help", "how can", "how do", "what can", "hello", "hi", "hey", "thanks", "thank you"]
        if any(token in normalized for token in greeting_tokens):
            return "generic"

        if any(token in normalized for token in ["what is", "who are", "explain", "tell me about", "can you"]):
            return "generic"

        scores = {
            "data_engineering": 0,
            "data_analysis": 0,
            "finance_analysis": 0,
            "full_workflow": 0,
        }

        finance_signals = [
            "investment",
            "portfolio",
            "risk",
            "profit",
            "revenue",
            "expense",
            "cash",
            "financial",
            "finance",
            "return",
            "allocation",
            "volatility",
        ]
        data_signals = ["summary", "summarize", "describe", "statistics", "correlation", "outlier", "anomaly", "dataset", "data"]
        engineering_signals = ["sql", "query", "load", "csv", "json", "database", "table", "source"]
        review_signals = ["review", "recommend", "recommendation", "decision", "action", "plan", "suggest", "optimize", "adjust"]

        for token in engineering_signals:
            if token in normalized:
                scores["data_engineering"] += 3

        for token in data_signals:
            if token in normalized:
                scores["data_analysis"] += 3

        for token in finance_signals:
            if token in normalized:
                scores["finance_analysis"] += 2

        for token in review_signals:
            if token in normalized:
                scores["full_workflow"] += 3

        if "analyze" in normalized or "evaluate" in normalized or "assess" in normalized:
            scores["finance_analysis"] += 2

        if scores["data_engineering"] >= max(scores.values()) and scores["data_engineering"] > 0:
            return "data_engineering"
        if scores["data_analysis"] >= max(scores.values()) and scores["data_analysis"] > 0:
            return "data_analysis"
        if scores["full_workflow"] >= max(scores.values()) and scores["full_workflow"] > 0:
            return "full_workflow"
        if scores["finance_analysis"] >= max(scores.values()) and scores["finance_analysis"] > 0:
            return "finance_analysis"

        return "generic"

    def _get_llm_decision(self, request: str) -> tuple[str, str]:
        known_routes = {"generic", "data_engineering", "data_analysis", "finance_analysis", "full_workflow"}
        try:
            response = llm_client.chat(
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are a routing assistant. Decide whether the user's request should be answered directly or routed to a specialist. "
                            "Return a short response in this format:\n"
                            "ACTION: answer|route\n"
                            "ROUTE: generic|data_engineering|data_analysis|finance_analysis|full_workflow\n"
                            "RESPONSE: <your answer or routing note>"
                        ),
                    },
                    {"role": "user", "content": request},
                ],
                temperature=0.2,
                max_tokens=220,
            )
            if not isinstance(response, str) or not response.strip():
                return "generic", ""

            action = "answer"
            route = "generic"
            response_text = ""

            for line in response.splitlines():
                stripped = line.strip()
                if not stripped:
                    continue
                if stripped.upper().startswith("ACTION:"):
                    action = stripped.split(":", 1)[1].strip().lower()
                elif stripped.upper().startswith("ROUTE:"):
                    route_value = stripped.split(":", 1)[1].strip().lower().replace("-", "_")
                    if route_value in known_routes:
                        route = route_value
                elif stripped.upper().startswith("RESPONSE:"):
                    response_text = stripped.split(":", 1)[1].strip()

            if action == "route" and route in known_routes:
                return route, response_text or response.strip()

            return "generic", response_text or response.strip()
        except Exception:
            return "generic", ""

    def _answer_with_llm(self, request: str) -> str:
        llm_route, llm_response = self._get_llm_decision(request)
        if llm_response:
            return llm_response

        cleaned_request = request.strip()
        if cleaned_request:
            return (
                f"I can help with that. I will respond directly to your request: '{cleaned_request}'. "
                "If you want me to analyze data or finance information, describe the task more specifically and I will route it to the right agent."
            )

        return (
            "I can help with general questions, data tasks, or finance analysis. "
            "Describe what you want and I will respond or route it to the appropriate agent."
        )

    def _build_finance_input(self, latest_row: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "finance_data": {
                "revenue": float(latest_row.get("revenue", 0)),
                "profit": float(latest_row.get("profit", 0)),
                "expenses": float(latest_row.get("expenses", 0)),
            },
            "portfolio": {
                "exposure": {
                    "equities": float(latest_row.get("equities", 0)),
                    "bonds": float(latest_row.get("bonds", 0)),
                    "cash": float(latest_row.get("cash", 0)),
                },
                "volatility": {
                    "equities": float(latest_row.get("volatility", 0)),
                    "bonds": 0.07,
                    "cash": 0.01,
                },
            },
            "simulation": {
                "assets": [
                    {"symbol": "STK1", "average_return": float(latest_row.get("average_return", 0.08)), "volatility": float(latest_row.get("volatility", 0.16))},
                    {"symbol": "BND1", "average_return": 0.035, "volatility": 0.05},
                ],
                "allocations": {"STK1": 0.6, "BND1": 0.4},
            },
        }
