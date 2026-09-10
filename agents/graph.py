from typing import Any, Dict, List, Optional, Union

from langgraph.graph import END, StateGraph

from agents.planner_agent import FinancePlannerAgent
from agents.state import AgentState
from tools.registry import ToolRegistry, create_default_registry
from utils.audit import record_event

class FinanceAgentGraph:
    """LangGraph-based bounded finance agent with an auditable execution trace."""

    def __init__(
        self,
        registry: Optional[ToolRegistry] = None,
        planner: Optional[FinancePlannerAgent] = None,
    ):
        self.registry = registry or create_default_registry()
        self.planner = planner or FinancePlannerAgent()
        self.graph = self._build_graph()

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
            "response": None,
            "intent": "",
            "intent_checked": False,
            "approval_required": False,
            "approval_status": "not_required",
            "clarification": None,
            "errors": [],
            "audit_events": [],
            "pending_decision": "",
            "pending_message": "",
            "pending_tool": "",
            "pending_arguments": {},
            "step_count": 0,
            "max_steps": max_steps,
            "status": "running",
        }
        record_event(state["audit_events"], "agent_started", request=request, source=source)
        result = self.graph.invoke(state)
        return result

    def _build_graph(self):
        graph = StateGraph(AgentState)
        graph.add_node("decide", self._decide)
        graph.add_node("execute_tool", self._execute_tool)
        graph.add_node("finish", self._finish)
        graph.set_entry_point("decide")
        graph.add_conditional_edges(
            "decide",
            self._route_decision,
            {
                "tool_call": "execute_tool",
                "response": "finish",
                "recommendation": "finish",
                "clarification": "finish",
                "approval_request": "finish",
                "failed": "finish",
            },
        )
        graph.add_edge("execute_tool", "decide")
        graph.add_edge("finish", END)
        return graph.compile()

    def _decide(self, state: AgentState) -> AgentState:
        if state["step_count"] >= state["max_steps"]:
            state["status"] = "failed"
            state["errors"].append("Maximum agent steps exceeded.")
            state["pending_decision"] = "failed"
            record_event(state["audit_events"], "agent_limit_reached", step_count=state["step_count"])
            return state

        decision = self.planner.decide(state)
        state["step_count"] += 1
        state["current_step"] = decision.decision_type
        state["pending_decision"] = decision.decision_type
        state["pending_message"] = decision.message
        state["pending_tool"] = decision.tool_name
        state["pending_arguments"] = decision.arguments or {}
        record_event(
            state["audit_events"],
            "decision_made",
            decision=decision.decision_type,
            tool=decision.tool_name or None,
            step_count=state["step_count"],
        )
        return state

    def _execute_tool(self, state: AgentState) -> AgentState:
        tool_name = state["pending_tool"]
        arguments = state["pending_arguments"]
        record_event(state["audit_events"], "tool_started", tool=tool_name)
        try:
            result = self.registry.execute(tool_name, arguments)
            state["tool_results"][tool_name] = result
            state["observations"].append({"tool": tool_name, "status": "success"})
            record_event(
                state["audit_events"],
                "tool_completed",
                tool=tool_name,
                result_summary=self._result_summary(result),
            )
        except Exception as exc:
            state["errors"].append(str(exc))
            state["status"] = "failed"
            state["pending_decision"] = "failed"
            state["pending_message"] = f"Tool '{tool_name}' failed: {exc}"
            record_event(state["audit_events"], "tool_failed", tool=tool_name, error=str(exc))
        return state

    def _finish(self, state: AgentState) -> AgentState:
        decision = state["pending_decision"]
        message = state["pending_message"]
        if decision == "clarification":
            state["clarification"] = message
            state["status"] = "needs_clarification"
        elif decision == "approval_request":
            state["recommendation"] = message
            state["approval_required"] = True
            state["approval_status"] = "pending"
            state["status"] = "approval_required"
        elif decision == "recommendation":
            state["recommendation"] = message
            state["findings"].append(message)
            state["status"] = "completed"
        elif decision == "response":
            state["response"] = message
            state["status"] = "completed"
        record_event(state["audit_events"], "agent_finished", status=state["status"])
        return state

    def _route_decision(self, state: AgentState) -> str:
        return state["pending_decision"]

    def _result_summary(self, result: Any) -> Dict[str, Any]:
        if not isinstance(result, dict):
            return {"type": type(result).__name__}
        summary = {key: result[key] for key in ("status", "domain", "rows", "file_count") if key in result}
        if "records" in result:
            summary["records_retained"] = result["records"] is not None
        return summary
