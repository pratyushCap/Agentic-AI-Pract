from typing import Any, Dict, List, Optional, Union

from agents.planner_agent import FinancePlannerAgent
from agents.state import AgentState
from tools.registry import ToolRegistry, create_default_registry


class FinanceAgentGraph:
    """Bounded stateful finance-agent loop.

    The node methods are intentionally small so this boundary can be migrated
    to LangGraph StateGraph without changing the planner or tool contracts.
    """

    def __init__(self, registry: Optional[ToolRegistry] = None, planner: Optional[FinancePlannerAgent] = None):
        self.registry = registry or create_default_registry()
        self.planner = planner or FinancePlannerAgent()

    def run(
        self,
        request: str,
        source: Optional[Union[str, List[str]]] = None,
        max_steps: int = 8,
    ) -> AgentState:
        state: AgentState = {
            "request": request,
            "source": source,
            "goal": request.strip(),
            "plan": self.planner.create_plan(request),
            "current_step": "",
            "observations": [],
            "tool_results": {},
            "findings": [],
            "recommendation": None,
            "approval_required": False,
            "approval_status": "not_required",
            "clarification": None,
            "errors": [],
            "step_count": 0,
            "max_steps": max_steps,
            "status": "running",
        }

        while state["status"] == "running":
            if state["step_count"] >= max_steps:
                state["status"] = "failed"
                state["errors"].append("Maximum agent steps exceeded.")
                break

            decision = self.planner.decide(state)
            state["step_count"] += 1
            state["current_step"] = decision.decision_type

            if decision.decision_type == "tool_call":
                self._execute_tool(state, decision.tool_name, decision.arguments or {})
            elif decision.decision_type == "clarification":
                state["clarification"] = decision.message
                state["status"] = "needs_clarification"
            elif decision.decision_type == "approval_request":
                state["recommendation"] = decision.message
                state["approval_required"] = True
                state["approval_status"] = "pending"
                state["status"] = "approval_required"
            else:
                state["recommendation"] = decision.message
                state["findings"].append(decision.message)
                state["status"] = "completed"

        return state

    def _execute_tool(self, state: AgentState, tool_name: str, arguments: Dict[str, Any]) -> None:
        try:
            result = self.registry.execute(tool_name, arguments)
            state["tool_results"][tool_name] = result
            state["observations"].append({"tool": tool_name, "status": "success"})
        except Exception as exc:
            state["errors"].append(str(exc))
            state["status"] = "failed"
