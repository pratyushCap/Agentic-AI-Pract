from typing import Any, Dict, List, Literal, Optional, TypedDict


AgentStatus = Literal["running", "completed", "needs_clarification", "approval_required", "failed"]


class AgentState(TypedDict, total=False):
    request: str
    source: Any
    goal: str
    plan: List[str]
    current_step: str
    observations: List[Dict[str, Any]]
    tool_results: Dict[str, Any]
    findings: List[str]
    recommendation: Optional[str]
    response: Optional[str]
    intent: str
    intent_checked: bool
    approval_required: bool
    approval_status: str
    clarification: Optional[str]
    errors: List[str]
    audit_events: List[Dict[str, Any]]
    pending_decision: str
    pending_message: str
    pending_tool: str
    pending_arguments: Dict[str, Any]
    step_count: int
    max_steps: int
    status: AgentStatus
