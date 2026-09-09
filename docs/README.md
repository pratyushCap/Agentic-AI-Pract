# Finance Workflow Planner

This prototype is a finance and investment agent.
Its primary CLI path uses a bounded LangGraph StateGraph with specialist tools for data loading, profiling, domain analysis, review, and recommendations. Each run produces a structured execution trace.

## Getting started

1. Create a Python virtual environment:
   ```bash
   python -m venv .venv
   .venv\Scripts\activate
   ```
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Add `.env` with:
   ```text
   LLM_API_KEY=your_key_here
   ```
4. Run the API locally:
   ```bash
   uvicorn api.app:app --reload --host 0.0.0.0 --port 8000
   ```

## API

- `POST /workflow`
  - request body: `{ "prompt": "Your finance question here" }`
  - response: workflow summary, finance comment, and review

## Agent Responsibilities

- `Finance Analyst` — evaluates investments, recommends finance actions, and validates outcomes
- `Data Analyst` — analyzes trends, summarizes datasets, and surfaces actionable insights
- `Data Engineering` — prepares data, validates datasets, and executes SQL queries
- `Reviewer` — audits recommendations, checks risk, and ensures governance compliance

The legacy fixed workflow remains available with `python run_agent.py --workflow`. The default `python run_agent.py` command runs the stateful Finance Agent.
