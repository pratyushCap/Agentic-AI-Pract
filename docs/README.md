# Finance Workflow Planner

This project is a bounded, auditable **finance and data-analysis agent**. It accepts a natural-language question, profiles CSV/JSON sources, identifies a supported analysis, executes a validated read-only query, and returns bounded evidence and interpretation. Ambiguous or unsupported requests should ask for clarification rather than invent a result.

The current milestone is a local-file analysis prototype. It is not a trading/action system and must not be treated as production-ready financial advice.

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
3. Optionally copy `.env.example` to `.env` and set `LLM_API_KEY` to enable LLM-assisted open-ended planning. An LLM key is not required for local deterministic tests and supported fallback plans.
4. Run the API locally:
   ```bash
   uvicorn api.app:app --reload --host 127.0.0.1 --port 8000
   ```

## API

- `POST /workflow`
   - request body: `{ "prompt": "Your finance question here", "source": "sample_finance_data.csv", "session_id": "optional-id" }`
   - response includes `session_id`, `run_id`, status, response or clarification, tool results, and audit events
   - omit `session_id` to create a persisted session; reuse the returned id for follow-up turns
   - conversations and audit events are stored in SQLite at `AGENT_STATE_DB` (default: `state/agent_state.sqlite3`)
   - API source paths are resolved only inside `DATA_ROOT` (default: the repository's `data` directory); arbitrary host paths are rejected
- `GET /health` is an unauthenticated liveness check.
- `GET /samples` returns example prompts.
- `GET /sessions/{session_id}/runs` returns persisted run/audit records for the authenticated principal's session.

Authentication is optional only for local development. Set `API_KEY` to protect an instance with one analyst credential. For multiple principals and roles, set `API_KEYS_JSON` to a JSON list of objects with `key`, `principal_id`, `role` (`viewer`, `analyst`, or `admin`), and optional `data_root` inside `DATA_ROOT`. Sessions are isolated by principal; viewers may read samples and their own run history but cannot run analyses. In `ENVIRONMENT=production`, authentication is required and requests fail closed if credentials are missing or invalid.

## Agent Responsibilities

- `Finance Analyst` — evaluates investments, recommends finance actions, and validates outcomes
- `Data Analyst` — analyzes trends, summarizes datasets, and surfaces actionable insights
- `Data Engineering` — prepares data, validates datasets, and executes SQL queries
- `Reviewer` — audits recommendations, checks risk, and ensures governance compliance

The default `python run_agent.py` command runs the bounded LangGraph agent. `--workflow` is retained as a deprecated compatibility alias and now uses the same agent path; the separate legacy workflow class remains available for older integrations but is not the supported CLI/API route.

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
- Generic aggregation (`sum`, `avg`, `min`, `max`, `count`), grouped counts, supported filters, date trends, and data-quality checks
- Validated column-to-column comparisons, including late-delivery counts
- SQLite persistence for session conversations and per-run audit events
- API-key authentication, analyst/viewer/admin roles, per-principal session isolation, and `DATA_ROOT` path restriction
- LLM request timeouts and bounded retries; DuckDB memory/thread limits

### Plan and query capability status

#### Phase 5: Question-to-plan conversion

Implemented for supported generic questions. The configured LLM can create a JSON plan and deterministic code validates it against the source catalog. Deterministic fallback plans cover the acceptance examples below when the LLM is unavailable.

The planner can convert a question into a validated plan such as:

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

Implemented with DuckDB for bounded read-only CSV queries. Unknown tables, columns, unsupported operations, duplicate tables, invalid filters, and disconnected joins are rejected.

Only validated query plans are translated to SQL. Never execute arbitrary model-generated SQL against production systems.

#### Phase 7: Evidence-based generic responses

Implemented for supported generic query results.

Generic and recognized-domain analyses return in this shape:

```text
Dataset understanding
Tables used
Analysis performed
Evidence
Interpretation
Recommended action / next step
```

Finance, domain-specific adapters, and generic query responses follow this pattern.

### Acceptance test for the generic-data capability

Given the seven-file e-commerce folder, the agent should answer questions such as:

- Which customer states generate the most payment value?
- What are the best-performing product categories?
- How many orders were delivered late?
- What is the average review score by product category?

It should select connected tables, execute a bounded read-only analysis, cite the resulting metrics, and ask for clarification when the question is ambiguous. For "best-performing categories", the deterministic fallback currently ranks total listed item price (not profit or margin); specify the business metric if a different definition is intended.

## Deliberate non-goals and remaining production work

- Tools are read-only. A request to trade, rebalance, send, or update is paused for approval, but there is no action executor or resumable approval workflow. Do not add one without a separately designed policy and human-approval process.
- SQLite persistence is suitable for a single-instance prototype. It is not encrypted by the application, not a multi-replica coordination layer, and does not replace managed PostgreSQL/Redis for production scale. Protect the volume, back it up, and plan a migration before handling sensitive production records.
- `API_KEYS_JSON` provides simple application roles and per-principal source roots, not an enterprise identity provider, key rotation service, rate limiting, or fine-grained business authorization.
- Data is selected from a server-side data directory; this release does not provide an upload endpoint or a database connector. Do not mount untrusted files into `DATA_ROOT`.
- The API runs analysis synchronously (FastAPI dispatches the blocking route in its worker pool). A queue/background-job service should be added only with a measured latency/throughput requirement and job-status contract.
- Persistent audit records currently cover workflow event traces, but production audit retention, encryption-at-rest, alerting, distributed tracing, and operational dashboards still need deployment-specific implementation.

## Container deployment

The Compose file builds from the repository root and runs as a non-root user. Provide `API_KEY` and `LLM_API_KEY` through the deployment environment before starting it:

```powershell
$env:API_KEY = "<long-random-secret>"
$env:LLM_API_KEY = "<provider-secret>"
docker compose -f infra/docker-compose.yml up --build
```

For production, use a secret manager rather than committing `.env` or passing secrets in source control. The named `agent_state` volume persists the SQLite state.
