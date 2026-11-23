import json
from dataclasses import dataclass
from typing import Any, Dict, Literal

from agents.state import AgentState
from llm.llm_config import llm_client
from tools.generic_query import GenericQueryTools
from utils.logger import setup_logger


DecisionType = Literal["response", "tool_call", "clarification", "recommendation", "approval_request"]
logger = setup_logger(__name__)


@dataclass(frozen=True)
class AgentDecision:
    decision_type: DecisionType
    message: str = ""
    tool_name: str = ""
    arguments: Dict[str, Any] | None = None


class FinancePlannerAgent:
    """Chooses the next bounded step from the current state and observations."""

    def create_plan(self, request: str) -> list[str]:
        return ["load_dataset", "profile_dataset", "domain_analysis", "evaluate_results"]

    def decide(self, state: AgentState) -> AgentDecision:
        results = state.get("tool_results", {})
        if not results and self._is_greeting(state["request"]):
            return AgentDecision(
                "response",
                "Hello. I can analyze finance, transaction, or portfolio data. What would you like to review?",
            )
        if not results and not state.get("intent_checked"):
            state["intent_checked"] = True
            conversation = state.get("conversation", [])
            llm_intent = self._classify_with_llm(state["request"], conversation)
            if llm_intent is None:
                llm_intent = self._fallback_intent(state["request"])
            if llm_intent == "general":
                state["intent"] = "general"
                answer = self._answer_with_llm(state["request"], conversation)
                return AgentDecision("response", answer or self._general_response(state["request"]))
            if llm_intent == "capability":
                state["intent"] = "capability"
                answer = self._answer_with_llm(state["request"], conversation)
                return AgentDecision("response", answer or self._capability_response())
            if llm_intent == "ambiguous":
                state["intent"] = "ambiguous"
                return AgentDecision("clarification", self._request_clarification())
            if llm_intent == "data":
                state["intent"] = "data"
            elif self._is_general_question(state["request"]):
                state["intent"] = "general"
                answer = self._answer_with_llm(state["request"])
                return AgentDecision("response", answer or self._general_response(state["request"]))
            else:
                state["intent"] = "ambiguous"
                return AgentDecision("clarification", self._request_clarification())
        if "load_dataset" not in results:
            source = state.get("source")
            if not source:
                return AgentDecision(
                    "clarification",
                    "Which CSV, JSON, or data folder should I analyze?",
                )
            return AgentDecision("tool_call", tool_name="load_dataset", arguments={"source": source})

        if "profile_dataset" not in results:
            if not results["load_dataset"].get("rows"):
                return AgentDecision("clarification", "The selected source contains no usable records.")
            return AgentDecision("tool_call", tool_name="profile_dataset", arguments={"source": state["source"]})

        domain_analysis = self._domain_analysis_result(results)
        if domain_analysis is None:
            domain = results["profile_dataset"].get("domain")
            tool_by_domain = {
                "transactions": "analyze_transactions",
                "finance": "analyze_finance",
                "portfolio": "analyze_portfolio",
            }
            tool_name = tool_by_domain.get(domain)
            if not tool_name:
                catalog = results["profile_dataset"]
                if catalog.get("dataset_domain") in {"ecommerce", "mixed"} or len(catalog.get("tables", [])) > 1:
                    plan = self._plan_generic_question(
                        state["request"],
                        catalog,
                        state.get("conversation", []),
                    )
                    if plan is None:
                        return AgentDecision("clarification", self._catalog_response(catalog))
                    return AgentDecision(
                        "tool_call",
                        tool_name="query_data",
                        arguments={"catalog": catalog, "plan": plan},
                    )
                return AgentDecision("recommendation", self._recommendation(state))
            return AgentDecision(
                "tool_call",
                tool_name=tool_name,
                arguments={"profile": results["profile_dataset"]},
            )

        recommendation = self._recommendation(state)
        if self._requires_approval(state["request"]):
            return AgentDecision("approval_request", recommendation)
        return AgentDecision("recommendation", recommendation)

    def _recommendation(self, state: AgentState) -> str:
        profile = state["tool_results"]["profile_dataset"]
        domain_analysis = self._domain_analysis_result(state["tool_results"])
        domain = profile.get("dataset_domain") or profile.get("domain", "unknown")
        dataset_understanding = (
            f"{domain} data with {profile.get('rows', 0):,} records across "
            f"{profile.get('file_count', len(profile.get('tables', [])) or 1)} source(s)"
        )
        if domain_analysis:
            if "query_data" in state["tool_results"]:
                result = state["tool_results"]["query_data"]
                rows = result.get("rows", [])[:5]
                plan = result.get("plan", {})
                task = plan.get("task", "analysis")
                if task == "count":
                    operation = "count records"
                elif task == "data_quality":
                    operation = "data-quality check"
                elif task == "trend":
                    operation = f"trend over {plan.get('date_column')}"
                elif task == "summary":
                    operation = f"summary of {plan.get('metric')}"
                else:
                    operation = task
                if task == "aggregation" and plan.get("aggregation"):
                    operation = f"{plan['aggregation']} {plan.get('metric') or 'records'}"
                if plan.get("group_by"):
                    operation += f" grouped by {plan['group_by']}"
                elif plan.get("date_column"):
                    operation += f" over {plan['date_column']}"
                return (
                    f"Dataset understanding: {dataset_understanding}.\n"
                    f"Tables used: {', '.join(result.get('tables_used', []))}.\n"
                    f"Analysis performed: {operation}; {result.get('row_count', 0)} result row(s).\n"
                    f"Evidence: {json.dumps(rows, default=str)}\n"
                    f"Interpretation: {result.get('recommendation', 'Review the evidence against the requested business question.')}\n"
                    "Recommended action: validate the result against business context before acting."
                )
            recommendation = domain_analysis.get("recommendation", "")
            recommendation_lines = {
                line.partition(":")[0].strip().lower(): line.partition(":")[2].strip()
                for line in recommendation.splitlines()
                if ":" in line
            }
            metrics = {
                key: value
                for key, value in domain_analysis.items()
                if key not in {"status", "recommendation", "missing_values"}
            }
            missing = domain_analysis.get("status") == "incomplete"
            tables = [table.get("table_name") for table in profile.get("tables", [])]
            return (
                f"Dataset understanding: {dataset_understanding}.\n"
                f"Tables used: {', '.join(tables) if tables else 'the selected source'}.\n"
                f"Analysis performed: {domain} domain profile and deterministic metrics.\n"
                f"Evidence: {json.dumps(metrics, default=str) if metrics else domain_analysis.get('status', 'no metrics')}\n"
                f"Interpretation: {recommendation_lines.get('interpretation', 'The domain analysis completed; review the reported evidence.')}\n"
                f"Recommended action: {recommendation_lines.get('recommended action', 'Review the evidence before taking action.')}"
                + (" Resolve the missing required fields before relying on this result." if missing else "")
            )
        columns = set(profile.get("columns", []))
        if {"revenue", "profit", "expenses"}.issubset(columns):
            return (
                f"Dataset understanding: {dataset_understanding}.\n"
                "Tables used: the selected source.\n"
                "Analysis performed: finance-field availability check; no finance metrics were calculated.\n"
                "Evidence: revenue, profit, and expenses columns are present.\n"
                "Interpretation: the source has fields suitable for finance analysis.\n"
                "Recommended action: request a supported finance metric analysis before taking action."
            )
        if "transaction_amount" in columns and "risk_score" in columns:
            stats = profile.get("statistics", {}).get("summary", {})
            amount = stats.get("transaction_amount", {}).get("mean")
            risk = stats.get("risk_score", {}).get("mean")
            if amount is None or risk is None:
                return (
                    f"Dataset understanding: {dataset_understanding}.\n"
                    "Tables used: the selected source.\n"
                    "Analysis performed: transaction profile; required averages were unavailable.\n"
                    "Evidence: transaction amount or risk values are missing.\n"
                    "Interpretation: data quality prevents a complete risk summary.\n"
                    "Recommended action: resolve missing values before taking action."
                )
            return (
                f"Dataset understanding: {dataset_understanding}.\n"
                "Tables used: the selected source.\n"
                "Analysis performed: average transaction amount and average risk score.\n"
                f"Evidence: average transaction amount is {amount:.2f}; average risk score is {risk:.2f}.\n"
                "Interpretation: compare the risk score with the organization's approved threshold.\n"
                "Recommended action: investigate high-risk transactions before action."
            )
        return (
            f"Dataset understanding: {dataset_understanding}.\n"
            "Tables used: the selected source.\n"
            "Analysis performed: dataset profile; no supported domain metric was identified.\n"
            "Evidence: the available columns do not match a supported analysis plan.\n"
            "Interpretation: the data has been profiled, but cannot support a specific recommendation yet.\n"
            "Recommended action: ask a more specific question or provide the required fields."
        )

    def _catalog_response(self, catalog: Dict[str, Any]) -> str:
        tables = catalog.get("tables", [])
        names = ", ".join(table["table_name"] for table in tables[:8])
        relationships = catalog.get("relationships", [])
        relationship_text = ", ".join(
            f"{item['left_table']}.{item['left_column']} -> {item['right_table']}.{item['right_column']}"
            for item in relationships[:6]
        ) or "No relationships were confirmed from the sample."
        return (
            f"I found {catalog.get('file_count', 0)} related data files containing {catalog.get('rows', 0):,} records.\n"
            f"Detected tables: {names}.\n"
            f"Detected relationships: {relationship_text}\n"
            "This appears to be general or e-commerce data rather than a single finance dataset. "
            "Tell me whether you want sales, customers, products, payments, delivery, reviews, trends, or data-quality analysis."
        )

    def _plan_generic_question(
        self,
        request: str,
        catalog: Dict[str, Any],
        conversation: list[Dict[str, str]] | None = None,
    ) -> Dict[str, Any] | None:
        """Ask the LLM for a JSON plan, then validate it deterministically."""
        try:
            response = llm_client.chat(
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "Convert the user's data question into JSON only. Choose task from aggregation, summary, count, trend, data_quality. "
                            "Use only table and column names present in the catalog. Return null when the question is ambiguous or unsupported. "
                            "For aggregation, aggregation may be sum, avg, min, max, or count. "
                            "Summary requires a metric and returns its count, sum, and average; do not set aggregation for summary. "
                            "Trend returns monthly sums. "
                            "Filters are objects with column, operator, value. Operators are =, !=, >, >=, <, <=, contains, in, is_null, is_not_null. "
                            "For count comparisons between two columns, use comparison: {left_column, operator, right_column}. "
                            "Schema: {task, metric, aggregation, group_by, date_column, tables, filters, comparison}."
                        ),
                    },
                    {
                        "role": "user",
                        "content": json.dumps({
                            "question": request,
                            "conversation": conversation or [],
                            "catalog": catalog,
                        }),
                    },
                ],
                temperature=0.0,
                max_tokens=500,
            )
        except Exception as exc:
            logger.warning(
                "LLM plan generation unavailable (%s); using deterministic fallback.",
                type(exc).__name__,
            )
            return self._fallback_generic_plan(request, catalog)
        if not isinstance(response, str):
            return self._fallback_generic_plan(request, catalog)
        try:
            parsed = json.loads(response.strip().replace("```json", "").replace("```", "").strip())
        except json.JSONDecodeError as exc:
            logger.warning(
                "LLM returned an invalid plan format (%s); using deterministic fallback.",
                type(exc).__name__,
            )
            return self._fallback_generic_plan(request, catalog)
        if parsed is None:
            return self._fallback_generic_plan(request, catalog)
        try:
            return GenericQueryTools.validate_plan(catalog, parsed, 100)
        except (TypeError, ValueError) as exc:
            logger.warning(
                "LLM plan rejected by deterministic validation (%s); requesting clarification.",
                type(exc).__name__,
            )
            return None

    def _fallback_generic_plan(self, request: str, catalog: Dict[str, Any]) -> Dict[str, Any] | None:
        """Handle common explicit goals when the model cannot produce a valid plan."""
        normalized = request.lower()
        tables = catalog.get("tables", [])
        by_name = {table["table_name"]: table for table in tables}

        if "data quality" in normalized or "data-quality" in normalized or "quality" in normalized:
            return GenericQueryTools.validate_plan(catalog, {"task": "data_quality", "tables": list(by_name)}, 100)

        if any(term in normalized for term in ("late", "delivery delay", "delivered late")):
            delivered = self._find_column(tables, "order_delivered_customer_date")
            estimated = self._find_column(tables, "order_estimated_delivery_date")
            if delivered and estimated:
                table_names = self._tables_for_columns(
                    catalog,
                    delivered[1],
                    estimated[1],
                    start_table=delivered[0],
                    target_table=estimated[0],
                )
                if table_names:
                    return GenericQueryTools.validate_plan(
                        catalog,
                        {
                            "task": "count",
                            "tables": table_names,
                            "comparison": {
                                "left_column": delivered[1],
                                "operator": ">",
                                "right_column": estimated[1],
                            },
                            "filters": [
                                {"column": delivered[1], "operator": "is_not_null"},
                                {"column": estimated[1], "operator": "is_not_null"},
                            ],
                        },
                        100,
                    )

        if "review" in normalized and "score" in normalized:
            score = self._find_column(tables, "review_score")
            category = self._find_column(
                tables,
                "product_category_name",
                preferred_table_names=("products",),
            )
            if score and category:
                table_names = self._tables_for_columns(
                    catalog,
                    score[1],
                    category[1],
                    start_table=score[0],
                    target_table=category[0],
                )
                if table_names:
                    return GenericQueryTools.validate_plan(
                        catalog,
                        {
                            "task": "aggregation",
                            "aggregation": "avg",
                            "metric": score[1],
                            "group_by": category[1],
                            "tables": table_names,
                        },
                        100,
                    )

        if "payment" in normalized and ("state" in normalized or "customer" in normalized):
            payment = self._find_column(tables, "payment_value")
            state = self._find_column(tables, "customer_state")
            if payment and state:
                table_names = self._tables_for_columns(
                    catalog,
                    payment[1],
                    state[1],
                    start_table=payment[0],
                    target_table=state[0],
                )
                if table_names:
                    return GenericQueryTools.validate_plan(
                        catalog,
                        {
                            "task": "aggregation",
                            "aggregation": "sum",
                            "metric": payment[1],
                            "group_by": state[1],
                            "tables": table_names,
                        },
                        100,
                    )

        if "categor" in normalized and any(term in normalized for term in ("best", "perform", "sales", "top")):
            price = self._find_column(tables, "price")
            category = self._find_column(
                tables,
                "product_category_name",
                preferred_table_names=("products",),
            )
            if price and category:
                table_names = self._tables_for_columns(
                    catalog,
                    price[1],
                    category[1],
                    start_table=price[0],
                    target_table=category[0],
                )
                if table_names:
                    return GenericQueryTools.validate_plan(
                        catalog,
                        {
                            "task": "aggregation",
                            "aggregation": "sum",
                            "metric": price[1],
                            "group_by": category[1],
                            "tables": table_names,
                        },
                        100,
                    )

        orders = next((table for table in tables if "order_purchase_timestamp" in table.get("columns", [])), None)
        if "trend" in normalized or "trends" in normalized:
            if orders:
                metric_table = next((table for table in tables if "payment_value" in table.get("columns", [])), None)
                plan = {"task": "trend", "date_column": "order_purchase_timestamp", "tables": [orders["table_name"]]}
                if metric_table:
                    plan["metric"] = "payment_value"
                    plan["tables"].append(metric_table["table_name"])
                return GenericQueryTools.validate_plan(catalog, plan, 100)

        if "customer" in normalized or "customers" in normalized:
            customer_table = next((table for table in tables if "customer_state" in table.get("columns", [])), None)
            if customer_table:
                return GenericQueryTools.validate_plan(
                    catalog,
                    {"task": "count", "group_by": "customer_state", "tables": [customer_table["table_name"]]},
                    100,
                )
        return None

    def _find_column(
        self,
        tables: list[Dict[str, Any]],
        column_name: str,
        preferred_table_names: tuple[str, ...] = (),
    ):
        for preferred_name in preferred_table_names:
            for table in tables:
                if table["table_name"] == preferred_name and column_name in table.get("columns", []):
                    return table["table_name"], column_name
        for table in tables:
            if column_name in table.get("columns", []):
                return table["table_name"], column_name
        return None

    def _tables_for_columns(
        self,
        catalog: Dict[str, Any],
        *columns: str,
        start_table: str | None = None,
        target_table: str | None = None,
    ) -> list[str] | None:
        """Return the shortest catalog relationship path connecting the requested columns."""
        tables = {table["table_name"]: table for table in catalog.get("tables", [])}
        start_matches = [start_table] if start_table else [
            name for name, table in tables.items()
            if columns[0] in table.get("columns", [])
        ]
        target_matches = {target_table} if target_table else {
            name for name, table in tables.items()
            if columns[-1] in table.get("columns", [])
        }
        if len(start_matches) != 1 or len(target_matches) != 1:
            return None
        start = start_matches[0]
        targets = target_matches
        if start in targets:
            return [start]

        adjacency: Dict[str, set[str]] = {name: set() for name in tables}
        for relationship in catalog.get("relationships", []):
            left = relationship.get("left_table")
            right = relationship.get("right_table")
            if left in tables and right in tables:
                adjacency[left].add(right)
                adjacency[right].add(left)
        queue = [(start, [start])]
        visited = {start}
        while queue:
            current, path = queue.pop(0)
            for neighbor in adjacency[current]:
                if neighbor in visited:
                    continue
                next_path = path + [neighbor]
                if neighbor in targets:
                    return next_path
                visited.add(neighbor)
                queue.append((neighbor, next_path))
        return None

    def _domain_analysis_result(self, results: Dict[str, Any]) -> Dict[str, Any] | None:
        for tool_name in ("analyze_transactions", "analyze_finance", "analyze_portfolio", "query_data"):
            if tool_name in results:
                return results[tool_name]
        return None

    def _requires_approval(self, request: str) -> bool:
        sensitive_terms = ("execute", "trade", "rebalance", "send", "update production")
        normalized = request.lower()
        return any(term in normalized for term in sensitive_terms)

    def _is_greeting(self, request: str) -> bool:
        normalized = request.lower().strip(" !?,.")
        return normalized in {"hello", "hi", "hey", "good morning", "good afternoon", "good evening"}

    def _fallback_intent(self, request: str) -> str:
        """Use local cues only when the intent model is unavailable."""
        normalized = request.lower()
        task_cues = (
            "analyze", "analysis", "assess", "evaluate", "review", "summarize",
            "compare", "calculate", "query", "show", "find", "trend", "trends",
            "rebalance", "execute", "trade",
        )
        data_cues = (
            "data", "dataset", "finance", "financial", "portfolio", "transaction",
            "revenue", "profit", "expense", "customer", "order", "payment", "risk",
            ".csv", ".json",
        )
        if self._is_general_question(request):
            return "general"
        if any(cue in normalized for cue in task_cues) and any(cue in normalized for cue in data_cues):
            return "data"
        return "ambiguous"

    def _request_clarification(self) -> str:
        return (
            "I can help with finance analysis, data analysis, or data engineering. "
            "What outcome are you looking for? If it involves a dataset, tell me which source to use."
        )

    def _capability_response(self) -> str:
        return (
            "I can help inspect and validate data sources, analyze finance and portfolio data, "
            "and answer targeted questions with evidence. What problem are you trying to solve, "
            "and which data source should I use?"
        )

    def _is_general_question(self, request: str) -> bool:
        normalized = request.lower().strip()
        if any(token in normalized for token in ("dataset", "data", ".csv", ".json", "portfolio", "transaction")):
            return False
        return normalized.startswith(("what is ", "what are ", "who is ", "explain ", "tell me about ", "how does "))

    def _general_response(self, request: str) -> str:
        normalized = request.lower()
        if "llm" in normalized or "large language model" in normalized:
            return "An LLM, or large language model, is an AI system that understands and generates natural language. In this project, it can help interpret requests and explain analysis results."
        if "fastapi" in normalized:
            return "FastAPI is the Python web framework that exposes this finance agent through HTTP endpoints such as POST /workflow."
        if "langgraph" in normalized:
            return "LangGraph is the orchestration layer that manages the agent state, tool calls, conditional routing, and completion."
        return "I can explain finance and AI concepts, or analyze a CSV, JSON, folder, transaction dataset, finance dataset, or portfolio dataset."

    def _classify_with_llm(
        self,
        request: str,
        conversation: list[Dict[str, str]] | None = None,
    ) -> str | None:
        """Distinguish capability questions, actionable data tasks, and ambiguity."""
        try:
            response = llm_client.chat(
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You understand requests for a finance and data agent. Classify the user's actual intent. "
                            "GENERAL is an unrelated knowledge question. CAPABILITY asks what help the agent can provide "
                            "without specifying a task. DATA is an actionable request to inspect, transform, query, or analyze "
                            "a source or business data. AMBIGUOUS means the intended outcome is unclear. "
                            "Use recent conversation to resolve follow-up requests, but do not invent a goal when none was stated. "
                            "Do not classify a capability question as DATA just because it mentions data engineering, finance, "
                            "or analysis. Return exactly one line: INTENT: GENERAL|CAPABILITY|DATA|AMBIGUOUS"
                        ),
                    },
                    *(conversation or []),
                    {"role": "user", "content": request},
                ],
                temperature=0.0,
                max_tokens=500,
            )
            if not isinstance(response, str):
                return None

            intent = ""
            for line in response.splitlines():
                key, separator, value = line.partition(":")
                if not separator:
                    continue
                if key.strip().upper() == "INTENT":
                    intent = value.strip().upper()
            if intent in {"GENERAL", "CAPABILITY", "DATA", "AMBIGUOUS"}:
                return intent.lower()
        except Exception as exc:
            logger.warning(
                "LLM intent classification unavailable (%s); using deterministic fallback.",
                type(exc).__name__,
            )
            return None
        return None

    def _answer_with_llm(
        self,
        request: str,
        conversation: list[Dict[str, str]] | None = None,
    ) -> str | None:
        """Generate the direct answer after the request is classified as general."""
        try:
            response = llm_client.chat(
                messages=[
                    {
                        "role": "system",
                        "content": "Answer directly and clearly. For capability questions, describe relevant supported finance and data work without claiming work has already been done, then ask one focused follow-up if the task is unspecified. Avoid internal implementation details. For health questions, give general information and recommend professional advice where appropriate.",
                    },
                    *(conversation or []),
                    {"role": "user", "content": request},
                ],
                temperature=0.4,
                max_tokens=700,
            )
            if isinstance(response, str) and response.strip():
                return response.strip()
        except Exception as exc:
            logger.warning(
                "LLM response generation unavailable (%s); using a deterministic response.",
                type(exc).__name__,
            )
            return None
        return None
