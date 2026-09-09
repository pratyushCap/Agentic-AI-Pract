# Finance Workflow Planner

This prototype is a multi-agent finance and investment workflow planner.
It uses LangGraph-style orchestration with specialist assistants for finance, data, data engineering, and review.

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
