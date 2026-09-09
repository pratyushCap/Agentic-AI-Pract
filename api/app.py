from typing import Dict, List, Optional, Union
import os

from fastapi import FastAPI, Depends, HTTPException, status, Security
from fastapi.security.api_key import APIKeyHeader
from pydantic import BaseModel
from agents.graph import FinanceAgentGraph

app = FastAPI(
    title="Finance Agent",
    description="Bounded LangGraph finance agent with domain analysis, approvals, and audit tracing.",
    version="0.1.0",
)

agent = FinanceAgentGraph()

# Optional API key protection: set environment variable API_KEY to enable
API_KEY = os.getenv("API_KEY", "")
api_key_header = APIKeyHeader(name="X-API-KEY", auto_error=False)


def get_api_key(api_key: Optional[str] = Security(api_key_header)) -> Optional[str]:
    if not API_KEY:
        return None
    if api_key == API_KEY:
        return api_key
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or missing API Key",
    )


class WorkflowRequest(BaseModel):
    prompt: str
    source: Optional[Union[str, List[str]]] = None


class WorkflowResponse(BaseModel):
    request: str
    status: str
    step_count: int
    max_steps: int
    recommendation: Optional[str] = None
    clarification: Optional[str] = None
    approval_required: bool = False
    approval_status: str = "not_required"
    findings: List[str] = []
    errors: List[str] = []
    observations: List[Dict[str, object]] = []
    tool_results: Dict[str, object] = {}
    audit_events: List[Dict[str, object]] = []


@app.post("/workflow", response_model=WorkflowResponse)
def run_workflow(request: WorkflowRequest, api_key: Optional[str] = Depends(get_api_key)):
    result = agent.run(
        request.prompt,
        request.source or "data/sample_finance_data.csv",
    )
    return WorkflowResponse(**result)


@app.get("/samples")
def workflow_samples():
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
        "note": "The endpoint runs the LangGraph Finance Agent. If API_KEY is set, include header X-API-KEY.",
    }
