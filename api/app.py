from typing import Dict, List, Optional, Union
import os

from fastapi import FastAPI, Depends, HTTPException, status, Security
from fastapi.security.api_key import APIKeyHeader
from pydantic import BaseModel
from agents.orchestrator import FinanceWorkflowOrchestrator

app = FastAPI(
    title="Finance Workflow Planner",
    description="Multi-agent finance and investment workflow planner using LangGraph-style orchestration.",
    version="0.1.0",
)

orchestrator = FinanceWorkflowOrchestrator()

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
    route: str
    workflow_path: List[str]
    response: Optional[str] = None
    dataset: Optional[Dict[str, object]] = None
    data_summary: Optional[Dict[str, object]] = None
    finance_comment: Optional[Dict[str, object]] = None
    review: Optional[str] = None
    decision_plan: Optional[Dict[str, object]] = None


@app.post("/workflow", response_model=WorkflowResponse)
def run_workflow(request: WorkflowRequest, api_key: Optional[str] = Depends(get_api_key)):
    result = orchestrator.run_workflow(request.prompt, request.source)
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
    return {"samples": samples, "note": "If API_KEY is set, include header X-API-KEY."}
