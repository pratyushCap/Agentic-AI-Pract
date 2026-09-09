from dataclasses import dataclass
from typing import Any, Dict, Literal

from agents.state import AgentState


DecisionType = Literal["tool_call", "clarification", "recommendation", "approval_request"]


@dataclass(frozen=True)
class AgentDecision:
    decision_type: DecisionType
    message: str = ""
    tool_name: str = ""
    arguments: Dict[str, Any] | None = None


class FinancePlannerAgent:
    """Chooses the next bounded step from the current state and observations."""

    def create_plan(self, request: str) -> list[str]:
        return ["load_dataset", "profile_dataset", "domain_analysis", "evaluate_results"]

    def decide(self, state: AgentState) -> AgentDecision:
        results = state.get("tool_results", {})
        if "load_dataset" not in results:
            source = state.get("source")
            if not source:
                return AgentDecision(
                    "clarification",
                    "Which CSV, JSON, or data folder should I analyze?",
                )
            return AgentDecision("tool_call", tool_name="load_dataset", arguments={"source": source})

        if "profile_dataset" not in results:
            if not results["load_dataset"].get("rows"):
                return AgentDecision("clarification", "The selected source contains no usable records.")
            return AgentDecision("tool_call", tool_name="profile_dataset", arguments={"source": state["source"]})

        domain_analysis = self._domain_analysis_result(results)
        if domain_analysis is None:
            domain = results["profile_dataset"].get("domain")
            tool_by_domain = {
                "transactions": "analyze_transactions",
                "finance": "analyze_finance",
                "portfolio": "analyze_portfolio",
            }
            tool_name = tool_by_domain.get(domain)
            if not tool_name:
                return AgentDecision("recommendation", self._recommendation(state))
            return AgentDecision(
                "tool_call",
                tool_name=tool_name,
                arguments={"profile": results["profile_dataset"]},
            )

        recommendation = self._recommendation(state)
        if self._requires_approval(state["request"]):
            return AgentDecision("approval_request", recommendation)
        return AgentDecision("recommendation", recommendation)

    def _recommendation(self, state: AgentState) -> str:
        profile = state["tool_results"]["profile_dataset"]
        domain_analysis = self._domain_analysis_result(state["tool_results"])
        if domain_analysis:
            return domain_analysis.get("recommendation", "Domain analysis completed without a recommendation.")
        columns = set(profile.get("columns", []))
        if {"revenue", "profit", "expenses"}.issubset(columns):
            return "The dataset supports finance analysis. Review profitability, expense ratio, and risk before taking action."
        if "transaction_amount" in columns and "risk_score" in columns:
            stats = profile.get("statistics", {}).get("summary", {})
            amount = stats.get("transaction_amount", {}).get("mean")
            risk = stats.get("risk_score", {}).get("mean")
            if amount is None or risk is None:
                return "Transaction analysis is incomplete because amount or risk values are missing. Resolve the data quality issue before action."
            return (
                f"Transaction analysis is available. Average transaction amount is {amount:.2f} "
                f"and average risk score is {risk:.2f}. Investigate high-risk transactions before action."
            )
        return "The data was profiled successfully, but it does not contain enough recognized finance fields for a specific recommendation."

    def _domain_analysis_result(self, results: Dict[str, Any]) -> Dict[str, Any] | None:
        for tool_name in ("analyze_transactions", "analyze_finance", "analyze_portfolio"):
            if tool_name in results:
                return results[tool_name]
        return None

    def _requires_approval(self, request: str) -> bool:
        sensitive_terms = ("execute", "trade", "rebalance", "send", "update production")
        normalized = request.lower()
        return any(term in normalized for term in sensitive_terms)
