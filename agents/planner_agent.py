from dataclasses import dataclass
from typing import Any, Dict, Literal

from agents.state import AgentState
from llm.llm_config import llm_client


DecisionType = Literal["response", "tool_call", "clarification", "recommendation", "approval_request"]


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
        if not results and self._is_greeting(state["request"]):
            return AgentDecision(
                "response",
                "Hello. I can analyze finance, transaction, or portfolio data. What would you like to review?",
            )
        if not results and not state.get("intent_checked"):
            state["intent_checked"] = True
            llm_intent = self._classify_with_llm(state["request"])
            if llm_intent == "general":
                state["intent"] = "general"
                answer = self._answer_with_llm(state["request"])
                return AgentDecision("response", answer or self._general_response(state["request"]))
            if llm_intent == "data":
                state["intent"] = "data"
            elif self._is_general_question(state["request"]):
                state["intent"] = "general"
                answer = self._answer_with_llm(state["request"])
                return AgentDecision("response", answer or self._general_response(state["request"]))
            else:
                state["intent"] = "data"
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

    def _is_greeting(self, request: str) -> bool:
        normalized = request.lower().strip(" !?,.")
        return normalized in {"hello", "hi", "hey", "good morning", "good afternoon", "good evening"}

    def _is_general_question(self, request: str) -> bool:
        normalized = request.lower().strip()
        if any(token in normalized for token in ("dataset", "data", ".csv", ".json", "portfolio", "transaction")):
            return False
        return normalized.startswith(("what is ", "what are ", "who is ", "explain ", "tell me about ", "how does "))

    def _general_response(self, request: str) -> str:
        normalized = request.lower()
        if "llm" in normalized or "large language model" in normalized:
            return "An LLM, or large language model, is an AI system that understands and generates natural language. In this project, it can help interpret requests and explain analysis results."
        if "fastapi" in normalized:
            return "FastAPI is the Python web framework that exposes this finance agent through HTTP endpoints such as POST /workflow."
        if "langgraph" in normalized:
            return "LangGraph is the orchestration layer that manages the agent state, tool calls, conditional routing, and completion."
        return "I can explain finance and AI concepts, or analyze a CSV, JSON, folder, transaction dataset, finance dataset, or portfolio dataset."

    def _classify_with_llm(self, request: str) -> str | None:
        """Ask the configured model whether to answer directly or use data tools."""
        try:
            response = llm_client.chat(
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are the intent gate for a finance data agent. "
                            "Classify the request as GENERAL or DATA. "
                            "GENERAL means answer directly from your knowledge, including health, diet, "
                            "education, technology, or casual questions. DATA means the user wants a file, "
                            "dataset, transaction, finance, portfolio, or business-data analysis. "
                            "Return exactly one line: INTENT: GENERAL or INTENT: DATA"
                        ),
                    },
                    {"role": "user", "content": request},
                ],
                temperature=0.0,
                max_tokens=500,
            )
            if not isinstance(response, str):
                return None

            intent = ""
            for line in response.splitlines():
                key, separator, value = line.partition(":")
                if not separator:
                    continue
                if key.strip().upper() == "INTENT":
                    intent = value.strip().upper()
            if intent in {"GENERAL", "DATA"}:
                return intent.lower()
        except Exception:
            return None
        return None

    def _answer_with_llm(self, request: str) -> str | None:
        """Generate the direct answer after the request is classified as general."""
        try:
            response = llm_client.chat(
                messages=[
                    {
                        "role": "system",
                        "content": "Answer the user's general question directly and clearly. Do not discuss internal routing, tools, or datasets. For health questions, give general information and recommend professional advice where appropriate.",
                    },
                    {"role": "user", "content": request},
                ],
                temperature=0.4,
                max_tokens=700,
            )
            if isinstance(response, str) and response.strip():
                return response.strip()
        except Exception:
            return None
        return None
