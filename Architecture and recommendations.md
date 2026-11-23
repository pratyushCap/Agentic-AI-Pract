# Agentic AI Prototype: Technology Stack and Recommendations

## 1. Best Technology Stack

### Core Language
- Python
  - easiest language for AI and agent development
  - large ecosystem of libraries
  - strong support for LLM integration

### LLM and Agent Frameworks
Choose one based on your comfort level:

- LangChain
  - good for rapid prototyping
  - strong community support
  - many tutorials and integrations

- LangGraph
  - best for multi-agent workflows and stateful agents
  - very suitable for supervisor + worker agent patterns

- Semantic Kernel
  - strong for enterprise-style orchestration
  - good fit for Microsoft-based ecosystems

- CrewAI
  - good for role-based multi-agent systems
  - simple and fast for prototypes

### Recommendation
- Use LangGraph for the core orchestration if you want a scalable multi-agent architecture.
- Use CrewAI if you want faster prototyping with less setup.

---

## 2. Recommended Packages

### AI / LLM
- openai
- anthropic
- langchain
- langgraph
- langchain-community

### Data and Analytics
- pandas
- numpy
- sqlalchemy
- psycopg2-binary
- duckdb

### Web / API Layer
- fastapi
- uvicorn
- pydantic

### Database
- PostgreSQL
  - best choice for production-ready systems
- SQLite
  - good for prototypes
- Redis
  - useful for caching and session state

### Authentication and Security
- python-jose
- passlib
- bcrypt
- python-dotenv

### Monitoring and Observability
- loguru
- prometheus-client
- opentelemetry
- structlog

### Testing
- pytest
- pytest-asyncio

### Deployment
- Docker
- docker-compose
- Kubernetes (later)
- Azure / AWS / GCP depending on your organization’s cloud preference

---

## 3. Techniques to Use

### A. Supervisor-Worker Pattern
This is the most important pattern for multi-agent systems.

- One supervisor agent receives the business problem.
- It decides which specialist agent should handle the task.
- Specialist agents work on sub-tasks.

Example:
- Supervisor Agent
- Data Agent
- Finance Agent
- Operations Agent
- Action Agent

### B. Tool Calling
Give agents tools instead of letting them rely only on reasoning.

Examples of tools:
- search a database
- run SQL queries
- call REST APIs
- send email
- update a CRM system
- generate reports
- trigger internal workflows

This makes agents more reliable and action-oriented.

### C. Memory
Real-world agents need memory.

Use:
- short-term memory for the current conversation
- long-term memory for previous cases and decisions
- vector databases for semantic memory

Useful packages:
- chroma
- faiss
- weaviate
- pgvector

### D. Guardrails
For enterprise use, safety is essential.

Use:
- input validation
- prompt templates
- tool access restrictions
- approval workflows for sensitive actions
- human-in-the-loop review for critical decisions

### E. Workflow Orchestration
Do not let agents act freely for everything.

Use workflows for:
- approval steps
- retry logic
- fallback logic
- human review

Example:
- agent proposes an action
- the system asks for approval
- the action runs only after approval

---

## 4. Production-Ready Design Principles

### Security
- authentication
- role-based access control (RBAC)
- secret management
- API permissions

### Reliability
- retries
- timeouts
- fallback logic
- structured error handling

### Observability
- logging
- tracing
- audit trails
- action history

### Governance
- approval for sensitive actions
- role-based access
- compliance support

### Scalability
- stateless services
- queue-based job execution
- asynchronous processing

---

## 5. Recommended Architecture for the Prototype

### Frontend
- simple web interface or chat-based UI

### Backend API
- FastAPI

### Agent Orchestrator
- LangGraph or CrewAI

### Specialist Agents
- Planner Agent
- Data Agent
- Action Agent
- Reviewer Agent

### Tools
- SQL tool
- API tool
- File tool
- Notification tool

### Storage
- PostgreSQL
- Redis
- optional vector database

---

## 6. How Agents Can Call Each Other

### Pattern 1: Supervisor Routes Requests
- The Supervisor Agent receives a request.
- It sends it to the most suitable specialist agent.

### Pattern 2: Agent Handoff
- One agent completes part of the task.
- It passes the result to the next agent.

Example:
- Planner Agent creates a plan
- Data Agent analyzes the data
- Decision Agent decides on the action
- Action Agent executes it

### Pattern 3: Shared Memory / Shared State
- Each agent reads from and writes to a shared state object.
- This is useful when multiple agents need to collaborate.

This is usually better than letting agents communicate freely without structure.

---

## 7. Final Recommendation

For a strong prototype that can grow into a production-ready system, start with:
- Python
- FastAPI
- LangGraph
- PostgreSQL
- Redis
- OpenAI or Azure OpenAI
- Docker
- Pydantic
- pytest

This stack offers a strong balance of speed, flexibility, and enterprise readiness.

---

## 7.1 Chosen Project Focus

- Domain: Finance and Investment
- Orchestration: LangGraph
- Core agents:
  - Finance Analyst
  - Data Analyst
  - Data Engineering
  - Reviewer
- Initial action capabilities:
  - run SQL
  - generate finance reports
  - analyze data
  - recommend actions
  - portfolio simulations
  - risk scoring
  - decision recommendations

---

## 7.2 Agent Responsibilities

### Finance Analyst
- Evaluate investment opportunities and business financial decisions
- Create risk-adjusted recommendations and portfolio strategies
- Translate financial metrics into business actions
- Validate quantitative assumptions and forecast outcomes

### Data Analyst
- Inspect financial and market datasets for patterns and anomalies
- Summarize trends, correlations, and drivers of performance
- Support decision-making with data-driven insights
- Produce concise explanations for non-technical stakeholders

### Data Engineering
- Prepare and validate finance data for analysis
- Run SQL queries, clean datasets, and build analytical views
- Ensure repeatable, auditable data workflows
- Provide datasets optimized for modeling and reporting

### Reviewer
- Review recommendations for risk, compliance, and governance
- Check assumptions and flag overly aggressive actions
- Provide approval guidance before execution
- Ensure recommendations align with business policy

---

## 7.3 Conversation Decisions

| Question | Decision |
|---|---|
| Domain focus | Finance and Investment |
| Orchestration | LangGraph |
| Core agent roles | Finance Analyst, Data Analyst, Data Engineering, Reviewer |
| Initial capabilities | SQL, finance reports, data analysis, recommendations, portfolio simulations, risk scoring |
| Interaction | CLI plus FastAPI service |
| Deployment | Docker-ready prototype |

---

## 8. Project Build Checklist

### 8.1 Current and Proposed Directory Layout
- `api/` - FastAPI endpoints, REST/WebSocket interfaces, web service logic
- `agents/` - specialist agent implementations, supervisor/worker orchestration, role-based agent definitions
- `llm/` - LLM client wrapper and OpenAI/Generative Engine utilities
- `tools/` - tool integrations for SQL, data analysis, API calls, file handling
- `utils/` - shared helpers, logging, error handling, base agent abstractions
- `data/` - example datasets, sample CSV/JSON inputs, vector store seed data
- `infra/` - deployment files, Docker, docker-compose, environment setup scripts
- `docs/` - design notes, architecture diagrams, onboarding and usage guides
- `tests/` - unit and integration tests for agents, tools, API, and workflows
- root files: `config.py`, `run_agent.py`, `chat.py`, `chat2.py`, `requirements.txt`

### 8.2 Setup Checklist
- [ ] Create and activate a Python virtual environment
- [ ] Install dependencies from `requirements.txt`
- [ ] Add `.env` with required environment variables:
  - `LLM_API_KEY`
  - optional: `LLM_BASE_URL`, `LLM_MODEL`, `LLM_TEMPERATURE`, `LLM_MAX_TOKENS`
- [ ] Confirm `config.py` loads environment values correctly
- [ ] Confirm `llm/llm_config.py` wraps the LLM client
- [ ] Confirm `utils/agents/agents.py` contains the shared `BaseAgent` abstraction
- [ ] Confirm `tools/` contains deterministic tool implementations
- [ ] Keep `chat.py` and `chat2.py` as API exploration examples, not production entrypoints

### 8.3 Development Flow
- [ ] Build core LLM wrapper and config initialization
- [ ] Define base agent and tool schema support
- [ ] Add the first specialist agent (data analysis / engineering)
- [ ] Add tool-call integration and local fallback planning
- [ ] Add CLI prototype in `run_agent.py`
- [ ] Add API layer in `api/` with task submission and agent orchestration
- [ ] Add state/memory support for multi-turn context
- [ ] Add guardrails and validation for tools and inputs
- [ ] Add logging, error handling, and audit-friendly traces
- [ ] Add tests for modules and end-to-end workflows
- [ ] Add infra files for Docker / local deployment

### 8.4 Recommended Milestones
1. Environment, config, and LLM client
2. Base agent and tool abstractions
3. Data and SQL tool modules
4. CLI prototype in `run_agent.py`
5. FastAPI service skeleton in `api/`
6. Multi-agent orchestration and memory support
7. Tests, docs, and deploy config

### 8.5 Collaboration Notes
- Keep each agent implementation modular under `agents/`
- Use `tools/` for deterministic functionality, not reasoning
- Keep `chat.py` / `chat2.py` as examples only
- Keep secrets out of source control with `.env`
- Add `README.md` in `docs/` for onboarding and project instructions

---

## 9. Agent Roadmap: From Workflow to Real Agent

### 9.1 Current State

The current project is a useful deterministic multi-agent workflow. Its normal path is:

```text
User request
  -> Supervisor classification
  -> Data Engineering
  -> Data Analysis
  -> Finance Analysis
  -> Review
  -> Decision Plan
```

The workflow is reliable for a known sequence, but it is not yet a fully autonomous agent. The LLM is mainly used for generic responses and routing. The specialist classes currently perform predefined operations rather than choosing and revising their own steps.

### 9.2 Target Agent Behavior

A real Finance Agent should work toward a goal through a bounded decision loop:

```text
Understand goal
  -> Create plan
  -> Select a permitted tool
  -> Execute tool
  -> Observe result
  -> Evaluate progress
  -> Continue, revise, ask, escalate, or finish
```

The agent must be able to:

- decide which tools are needed for the request
- use the result of one tool to select the next step
- detect missing or poor-quality data
- revise its plan when evidence changes
- ask the user for clarification
- produce a recommendation with supporting evidence
- request approval before sensitive actions
- stop after a maximum number of steps
- record decisions, tool calls, errors, and approvals

The existing workflow should not be discarded. It should first become a reliable tool or subgraph that the new agent can call when appropriate. Later, individual workflow stages can become agent graph nodes.

### 9.3 Target Architecture

```text
User Request
  -> Finance Agent Planner
  -> Shared Agent State
  -> Tool Registry
     |-- Data and file tools
     |-- Finance and simulation tools
     |-- SQL tools
     |-- Policy and review tools
     `-- Action tools
  -> Observation and evaluation
  -> Recommendation or clarification
  -> Policy check
  -> Human approval when required
  -> Action execution
  -> Final response and audit record
```

Use LangGraph for the stateful loop, conditional routing, retries, approval pauses, and resumable execution.

### 9.4 Shared Agent State

Create a typed state object in `agents/state.py`. It should contain at least:

```python
{
  "request": "",
  "goal": "",
  "plan": [],
  "current_step": "",
  "observations": [],
  "tool_results": {},
  "findings": [],
  "recommendation": None,
  "approval_required": False,
  "approval_status": "not_required",
  "errors": [],
  "step_count": 0,
  "completed": False,
}
```

This state is the shared context for the agent loop. It is preferable to passing unrelated dictionaries between agents.

### 9.5 Tool Registry and Permissions

Create `tools/registry.py` and `tools/permissions.py`. Every tool should define:

- name and description
- input schema
- implementation
- read-only, simulation, or action category
- risk level
- whether human approval is required

Initial tool groups:

| Group | Examples | Approval |
|---|---|---|
| Read-only | Load data, profile data, statistics, SQL query | No |
| Simulation | Portfolio simulation, forecast, scenario comparison | No |
| Recommendation | Risk assessment, policy check, review | No, but must be recorded |
| Action | Rebalance portfolio, send instruction, update production data | Yes |

The agent must never execute sensitive tools merely because an LLM requested them. Permission checks belong in deterministic Python code.

### 9.6 LangGraph Nodes

The first graph should contain these nodes:

```text
understand_request
  -> plan_next_step
  -> execute_tool
  -> evaluate_observation
  -> generate_recommendation
  -> policy_check
  -> request_approval
  -> execute_action
  -> final_response
  -> handle_error
```

Conditional edges should support:

- another tool call
- clarification from the user
- recommendation without execution
- approval pause
- rejected approval and plan revision
- retry or controlled failure

### 9.7 Implementation Phases

#### Phase 1: Correctness Foundation

- profile datasets and detect their domain or schema
- add transaction, finance, and portfolio data adapters
- replace hardcoded analyst summaries with calculated findings
- prevent finance calculations when required fields are absent
- fix correlation to use aligned non-missing pairs
- keep large-file processing bounded and avoid returning one million records in state

#### Phase 2: First Real Agent

- add `agents/state.py`
- add a planner that returns structured next-step decisions
- add a bounded agent loop with a maximum step count
- add `tools/registry.py` and permission checks
- expose the existing workflow as an agent-callable tool
- add tests for tool selection, observation, replanning, and completion

#### Phase 3: LangGraph Migration

- add `agents/graph.py`
- convert planning, tool execution, review, and final response into graph nodes
- add conditional edges and resumable state
- add retries, timeouts, and controlled error handling
- preserve the current workflow as a compatibility path during migration

#### Phase 4: Governance and Human Approval

- [x] Persist approval records with pending, approved, rejected, and expired states; pending requests expire after 24 hours.
- [x] Pause sensitive requests at the approval-required graph outcome and expose API endpoints for requesters and admins.
- [x] Require an admin principal other than the requester to decide; record decisions and expiration in approval and run audit records.
- [ ] Add deployment-specific policy rules for finance and portfolio actions.
- [ ] Add a resumable action executor only after action-specific policy and authorization are designed. Approval currently records a decision only and never executes an action.

#### Phase 5: Memory and Production Services

- add task memory and conversation history
- add PostgreSQL persistence for cases, approvals, and audit records
- add Redis for sessions, queues, and background jobs
- add file upload handling instead of accepting arbitrary server paths
- add authentication, RBAC, monitoring, and deployment hardening

### 9.8 Recommended Initial File Structure

```text
agents/
  state.py
  planner_agent.py
  graph.py
  action_agent.py
  supervisor_agent.py

tools/
  registry.py
  permissions.py
  action_tools.py

policies/
  finance_policy.py
  approval_policy.py

memory/
  conversation_store.py

utils/
  audit.py
  telemetry.py

tests/
  test_agent_loop.py
  test_tool_permissions.py
  test_approval_flow.py
  test_graph.py
```

### 9.9 First Development Milestone

The first milestone is complete when the Finance Agent can:

1. receive a finance request
2. create a structured plan
3. dynamically call at least two read-only tools
4. inspect tool results and choose the next step
5. stop when the goal is complete
6. ask for clarification when required data is missing
7. return a recommendation with evidence
8. refuse or pause sensitive actions without approval
9. stop after a configured maximum number of steps
10. produce an auditable execution trace

Do not add PostgreSQL, Redis, vector search, or trade execution before this milestone works with local deterministic tools and tests.

### 9.10 Definition of Done for the Agent Upgrade

The project should be called a real agent only when the execution path is selected from the current state and observations, rather than always following one fixed sequence. The system must also have bounded execution, tool permissions, clear failure behavior, and a separation between recommendations and approved actions.

### 9.11 Generic Data Phase Status

The generic-data expansion is being implemented in seven phases:

| Phase | Status | Current result |
|---|---|---|
| 1. Independent source profiling | Complete | Each CSV/JSON file is cataloged separately with rows, columns, types, domains, previews, and missing values. |
| 2. Generic dataset understanding | Complete | Finance, transaction, portfolio, e-commerce, mixed, and general dataset shapes are recognized. |
| 3. Generic analysis foundation | Complete | Bounded statistics, previews, data-quality metadata, and domain-specific adapters are available. |
| 4. Relationship discovery | Complete | Identifier candidates and matching-column relationships are reported with confidence labels. |
| 5. LLM question-to-plan conversion | Complete for supported tasks | The configured LLM creates plans for supported analysis tasks; deterministic acceptance fallbacks cover the documented e-commerce examples. Plans are validated against the catalog. |
| 6. Safe query execution | Complete for supported tasks | DuckDB executes bounded read-only CSV aggregation, summary, count, trend, data-quality, filter, and column-comparison plans. Unknown or invalid plans are rejected. |
| 7. Evidence-based generic response | Complete for supported tasks | Generic results include bounded evidence, tables used, interpretation, and recommended action. |

For the real `Raw data` folder, the current agent verified 7 tables, 547,664 total records, and 8 candidate or sample-confirmed relationships. A broad request such as `analyze this data` now asks the user to choose a goal instead of returning an unrelated finance recommendation.

The acceptance suite covers customer-state payment totals, product-category item-price totals, late-delivery counts, average review score by category, and clarification for ambiguous questions. Query plans are converted to SQL only after validation; model-generated SQL is never executed.

The CLI default path, `--workflow` compatibility alias, and API all use the bounded LangGraph agent. SQLite stores API sessions and audit records for single-instance persistence. API authentication supports API keys, simple roles, principal-scoped sessions, and source roots restricted beneath `DATA_ROOT`; the container runs as non-root and requires credentials in production mode.

Production work still required before handling sensitive business data includes managed identity/key rotation, encrypted and scalable database-backed persistence, distributed job processing when needed, durable audit retention/monitoring, and a separately governed action-approval lifecycle. The agent currently has no write-capable action tools, so sensitive requests pause rather than execute.