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

## Generic Data Analysis Roadmap

The agent can now catalog a folder of CSV/JSON files independently instead of treating unrelated tables as one merged finance dataset. It identifies table names, row counts, columns, numeric fields, likely domains, missing values, and sample key relationships. Broad requests such as `analyze this data` return a dataset summary and ask which business question should be analyzed.

### Implemented foundation

- Source cataloging for each file
- Independent table profiling
- Domain detection for finance, transactions, portfolios, e-commerce, and mixed data
- Candidate identifier detection
- Sample-based relationship discovery between tables
- Bounded previews and full-file streaming statistics
- Evidence-based finance, transaction, and portfolio responses

### Remaining phases

#### Phase 5: Question-to-plan conversion

Implemented for supported generic questions. The configured LLM creates a JSON plan and deterministic code validates it against the source catalog.

Use the configured LLM to convert a question into a validated plan such as:

```json
{
   "task": "aggregation",
   "metric": "payment_value",
   "group_by": "customer_state",
   "tables": ["orders", "payments", "customers"]
}
```

The plan must be checked against the source catalog. Unknown tables, columns, and unsupported operations must produce clarification rather than executable SQL.

#### Phase 6: Safe generic query execution

Implemented with DuckDB for bounded read-only CSV queries. Unknown tables, columns, unsupported operations, duplicate tables, and disconnected joins are rejected.

Add DuckDB or Polars for read-only CSV/JSON queries. Permit only validated `SELECT` or equivalent relational operations, enforce row/column/time limits, and keep query results bounded. Never execute arbitrary model-generated SQL against production systems.

Required tools:

- `describe_table`
- `aggregate_data`
- `filter_data`
- `compare_groups`
- `analyze_time_trend`
- `check_data_quality`
- `query_tables`

#### Phase 7: Evidence-based generic responses

Implemented for supported generic query results.

Return every analysis in this shape:

```text
Dataset understanding
Tables used
Analysis performed
Evidence
Interpretation
Recommended next action
```

Finance, domain-specific adapters, and generic query responses follow this pattern.

### Acceptance test for the full generic-data capability

Given the seven-file e-commerce folder, the agent should answer questions such as:

- Which customer states generate the most payment value?
- What are the best-performing product categories?
- How many orders were delivered late?
- What is the average review score by product category?

It should select only the required tables, execute a bounded read-only analysis, cite the resulting metrics, and ask for clarification when the question is ambiguous.
