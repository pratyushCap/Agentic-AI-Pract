import hmac
import json
import os
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Union

from fastapi import Depends, FastAPI, HTTPException, Query, Security, status
from fastapi.security.api_key import APIKeyHeader
from pydantic import BaseModel, ConfigDict, Field, field_validator

from agents.graph import FinanceAgentGraph
from utils.audit import record_event
from utils.state_store import (
    AgentStateStore,
    ApprovalNotFoundError,
    ApprovalSelfDecisionError,
    ApprovalStateError,
    SessionOwnershipError,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = Path(os.getenv("DATA_ROOT", str(PROJECT_ROOT / "data")))
if not DATA_ROOT.is_absolute():
    DATA_ROOT = PROJECT_ROOT / DATA_ROOT
DATA_ROOT = DATA_ROOT.resolve()
STATE_DATABASE = Path(os.getenv("AGENT_STATE_DB", str(PROJECT_ROOT / "state" / "agent_state.sqlite3")))
if not STATE_DATABASE.is_absolute():
    STATE_DATABASE = PROJECT_ROOT / STATE_DATABASE

app = FastAPI(
    title="Finance Agent",
    description="Bounded LangGraph finance agent with domain analysis, approvals, and audit tracing.",
    version="0.2.0",
)

agent = FinanceAgentGraph()
state_store = AgentStateStore(STATE_DATABASE)

API_KEY = os.getenv("API_KEY", "")
auth_required_setting = os.getenv("API_AUTH_REQUIRED")
API_AUTH_REQUIRED = (
    auth_required_setting.lower() in {"1", "true", "yes"}
    if auth_required_setting is not None
    else os.getenv("ENVIRONMENT", "development").lower() == "production"
)
api_key_header = APIKeyHeader(name="X-API-KEY", auto_error=False)


@dataclass(frozen=True)
class AuthenticatedPrincipal:
    principal_id: str
    role: str
    data_root: Path


def _configured_credentials() -> List[Dict[str, str]]:
    configured = os.getenv("API_KEYS_JSON", "")
    if configured:
        credentials = json.loads(configured)
        if not isinstance(credentials, list):
            raise ValueError("API_KEYS_JSON must be a JSON list.")
        normalized = []
        for item in credentials:
            if not isinstance(item, dict):
                raise ValueError("Each API_KEYS_JSON entry must be an object.")
            key = item.get("key")
            principal_id = item.get("principal_id")
            role = item.get("role")
            if not all(isinstance(value, str) and value for value in (key, principal_id, role)):
                raise ValueError("API key entries require non-empty key, principal_id, and role.")
            if role not in {"viewer", "analyst", "admin"}:
                raise ValueError("API key role must be viewer, analyst, or admin.")
            root = Path(item.get("data_root", str(DATA_ROOT)))
            if not root.is_absolute():
                root = DATA_ROOT / root
            try:
                root = root.resolve(strict=True)
                root.relative_to(DATA_ROOT)
            except (OSError, ValueError) as exc:
                raise ValueError("Each API key data_root must exist inside DATA_ROOT.") from exc
            normalized.append({
                "key": key,
                "principal_id": principal_id,
                "role": role,
                "data_root": str(root),
            })
        return normalized
    if API_KEY:
        return [{
            "key": API_KEY,
            "principal_id": "default",
            "role": "analyst",
            "data_root": str(DATA_ROOT),
        }]
    return []


API_CREDENTIALS = _configured_credentials()


def get_api_key(api_key: Optional[str] = Security(api_key_header)) -> AuthenticatedPrincipal:
    if not API_CREDENTIALS:
        if API_AUTH_REQUIRED:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="API authentication is required but no API credentials are configured.",
            )
        return AuthenticatedPrincipal("local", "admin", DATA_ROOT)
    if api_key is not None:
        for credential in API_CREDENTIALS:
            if hmac.compare_digest(api_key, credential["key"]):
                return AuthenticatedPrincipal(
                    principal_id=credential["principal_id"],
                    role=credential["role"],
                    data_root=Path(credential["data_root"]),
                )
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or missing API Key",
    )


class ConversationTurn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=8000)


class WorkflowRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    prompt: str = Field(min_length=1, max_length=4000)
    source: Optional[Union[str, List[str]]] = None
    session_id: Optional[str] = Field(default=None, min_length=1, max_length=128)
    conversation: List[ConversationTurn] = Field(default_factory=list, max_length=24)

    @field_validator("prompt")
    @classmethod
    def strip_prompt(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Prompt must not be blank.")
        return value


class WorkflowResponse(BaseModel):
    request: str
    session_id: str
    run_id: str
    status: str
    step_count: int
    max_steps: int
    response: Optional[str] = None
    recommendation: Optional[str] = None
    clarification: Optional[str] = None
    approval_required: bool = False
    approval_status: str = "not_required"
    approval_id: Optional[str] = None
    action_executed: bool = False
    findings: List[str] = Field(default_factory=list)
    errors: List[str] = Field(default_factory=list)
    observations: List[Dict[str, object]] = Field(default_factory=list)
    tool_results: Dict[str, object] = Field(default_factory=dict)
    audit_events: List[Dict[str, object]] = Field(default_factory=list)


class ApprovalDecisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: Literal["approved", "rejected"]
    note: Optional[str] = Field(default=None, max_length=2000)


def _resolve_api_source(
    source: Optional[Union[str, List[str]]],
    allowed_root: Path,
) -> Union[str, List[str]]:
    requested_sources = source or str(allowed_root / "sample_finance_data.csv")
    sources = requested_sources if isinstance(requested_sources, list) else [requested_sources]
    resolved_sources = []
    for source_path in sources:
        candidate = Path(source_path)
        if not candidate.is_absolute():
            if candidate.parts and candidate.parts[0] == allowed_root.name:
                candidate = Path(*candidate.parts[1:])
            candidate = allowed_root / candidate
        try:
            resolved = candidate.resolve(strict=True)
            resolved.relative_to(allowed_root)
        except (OSError, ValueError):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Source must exist inside the configured DATA_ROOT.",
            )
        if not resolved.is_file() and not resolved.is_dir():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Source must be a file or directory.",
            )
        resolved_sources.append(str(resolved))
    return resolved_sources if isinstance(requested_sources, list) else resolved_sources[0]


def _assistant_message(result: Dict[str, object]) -> str:
    for key in ("response", "clarification", "recommendation"):
        value = result.get(key)
        if isinstance(value, str) and value:
            return value
    errors = result.get("errors", [])
    return "; ".join(errors) if isinstance(errors, list) else ""


def _public_tool_results(tool_results: object) -> Dict[str, object]:
    if not isinstance(tool_results, dict):
        return {}
    public_results: Dict[str, object] = {}
    analysis_fields = {
        "status",
        "average_revenue",
        "average_profit",
        "average_expenses",
        "profit_margin",
        "expense_ratio",
        "average_transaction_amount",
        "average_risk_score",
        "average_exposure",
        "largest_exposure",
        "missing_values",
        "recommendation",
    }
    for tool_name in ("analyze_finance", "analyze_transactions", "analyze_portfolio"):
        result = tool_results.get(tool_name)
        if isinstance(result, dict):
            public_results[tool_name] = {
                key: value for key, value in result.items() if key in analysis_fields
            }

    query_result = tool_results.get("query_data")
    if isinstance(query_result, dict):
        public_query: Dict[str, object] = {
            key: query_result[key]
            for key in ("status", "tables_used", "rows", "row_count", "truncated", "recommendation")
            if key in query_result
        }
        plan = query_result.get("plan")
        if isinstance(plan, dict):
            public_query["plan"] = {
                key: plan[key]
                for key in ("task", "metric", "aggregation", "group_by", "date_column", "tables", "limit")
                if key in plan
            }
        public_results["query_data"] = public_query
    return public_results


def _public_audit_events(events: object) -> List[Dict[str, object]]:
    if not isinstance(events, list):
        return []
    public_events = []
    event_fields = {"timestamp", "event_type", "decision", "tool", "step_count", "status"}
    summary_fields = {"status", "domain", "file_count", "rows"}
    for event in events:
        if not isinstance(event, dict):
            continue
        public_event = {
            key: event[key]
            for key in event_fields
            if key in event
        }
        summary = event.get("result_summary")
        if isinstance(summary, dict):
            public_event["result_summary"] = {
                key: summary[key]
                for key in summary_fields
                if key in summary and isinstance(summary[key], (str, int, float, bool, type(None)))
            }
        public_events.append(public_event)
    return public_events


def _redact_local_paths(value: Any, data_root: Path) -> Any:
    if isinstance(value, dict):
        return {key: _redact_local_paths(item, data_root) for key, item in value.items()}
    if isinstance(value, list):
        return [_redact_local_paths(item, data_root) for item in value]
    if isinstance(value, str):
        redacted = value
        for root in {str(data_root), str(data_root).replace("\\", "/")}:
            redacted = redacted.replace(root, "<DATA_ROOT>")
        return redacted
    return value


def _public_run_history(runs: object, data_root: Path) -> List[Dict[str, object]]:
    if not isinstance(runs, list):
        return []
    public_runs = []
    for run in runs:
        if not isinstance(run, dict):
            continue
        public_run = {
            key: run[key]
            for key in ("run_id", "request", "status", "created_at")
            if key in run
        }
        safe_events = _public_audit_events(run.get("audit_events"))
        public_run["audit_events"] = _redact_local_paths(safe_events, data_root)
        public_runs.append(_redact_local_paths(public_run, data_root))
    return public_runs


@app.post("/workflow", response_model=WorkflowResponse)
def run_workflow(
    request: WorkflowRequest,
    principal: AuthenticatedPrincipal = Depends(get_api_key),
):
    if principal.role not in {"analyst", "admin"}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="This role cannot run analyses.")
    session_id = request.session_id or uuid.uuid4().hex
    principal_id = principal.principal_id
    try:
        stored_conversation = state_store.load_conversation(session_id, principal_id)
    except SessionOwnershipError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    conversation = (
        stored_conversation
        if stored_conversation is not None
        else [turn.model_dump() for turn in request.conversation]
    )
    source = _resolve_api_source(request.source, principal.data_root)
    result = agent.run(request.prompt, source, conversation=conversation)

    run_id = uuid.uuid4().hex
    approval_record = None
    if result["status"] == "approval_required":
        approval_id = uuid.uuid4().hex
        approval_record = {
            "approval_id": approval_id,
            "recommendation": str(result.get("recommendation") or ""),
        }
        record_event(
            result["audit_events"],
            "approval_requested",
            approval_id=approval_id,
            requester_id=principal_id,
        )
    try:
        state_store.save_workflow(
            run_id=run_id,
            session_id=session_id,
            principal_id=principal_id,
            request=request.prompt,
            status=str(result["status"]),
            audit_events=result.get("audit_events", []),
            conversation=conversation,
            assistant_message=_assistant_message(result),
            approval=approval_record,
        )
    except SessionOwnershipError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    response = dict(result)
    response["tool_results"] = _public_tool_results(result.get("tool_results"))
    response["audit_events"] = _public_audit_events(result.get("audit_events"))
    response = _redact_local_paths(response, principal.data_root)
    response["session_id"] = session_id
    response["run_id"] = run_id
    response["approval_id"] = approval_record["approval_id"] if approval_record else None
    response["action_executed"] = False
    return WorkflowResponse(**response)


def _require_admin(principal: AuthenticatedPrincipal) -> None:
    if principal.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This role cannot manage approval requests.",
        )


@app.get("/approvals")
def approval_requests(
    status_filter: Optional[Literal["pending", "approved", "rejected", "expired"]] = Query(
        default=None,
        alias="status",
    ),
    principal: AuthenticatedPrincipal = Depends(get_api_key),
):
    _require_admin(principal)
    return {"approvals": state_store.list_approvals(status_filter)}


@app.get("/approvals/{approval_id}")
def approval_request(
    approval_id: str,
    principal: AuthenticatedPrincipal = Depends(get_api_key),
):
    approval = state_store.get_approval(approval_id)
    if approval is None or (
        principal.role != "admin" and approval["requester_id"] != principal.principal_id
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Approval request not found.",
        )
    return approval


@app.post("/approvals/{approval_id}/decision")
def decide_approval(
    approval_id: str,
    request: ApprovalDecisionRequest,
    principal: AuthenticatedPrincipal = Depends(get_api_key),
):
    _require_admin(principal)
    try:
        approval = state_store.decide_approval(
            approval_id,
            decided_by=principal.principal_id,
            decision=request.decision,
            note=request.note,
        )
    except ApprovalNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ApprovalSelfDecisionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except ApprovalStateError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return {
        **approval,
        "message": (
            "Approval recorded. No action was executed; this prototype has no "
            "write-capable action tools."
        ),
    }


@app.get("/sessions/{session_id}/runs")
def session_runs(
    session_id: str,
    principal: AuthenticatedPrincipal = Depends(get_api_key),
):
    try:
        runs = state_store.load_runs(session_id, principal.principal_id)
        return {
            "session_id": session_id,
            "runs": _public_run_history(runs, principal.data_root),
        }
    except SessionOwnershipError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/samples")
def workflow_samples(principal: AuthenticatedPrincipal = Depends(get_api_key)):
    """Return example prompts clients can use to exercise the workflow."""
    samples = [
        "Summarize the latest financial dataset",
        "Load the latest CSV data source",
        "Assess portfolio risk and recommend actions",
        "Evaluate a new investment opportunity and recommend allocation",
        "Hello, what can you do?",
    ]
    return {
        "samples": samples,
        "note": "The endpoint uses the bounded LangGraph agent. Include X-API-KEY when API_KEY is configured.",
    }
