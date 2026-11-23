import math
from typing import Any, Dict, List

import duckdb


class AnalysisPlanError(ValueError):
    """Raised when an analysis plan is invalid or unsafe."""


class GenericQueryTools:
    """Validate and execute bounded read-only analysis plans."""

    ALLOWED_TASKS = {"aggregation", "summary", "count", "trend", "data_quality"}
    ALLOWED_AGGREGATIONS = {"sum", "avg", "min", "max", "count"}
    ALLOWED_FILTER_OPERATORS = {
        "=", "!=", ">", ">=", "<", "<=", "contains", "in", "is_null", "is_not_null",
    }
    ALLOWED_COMPARISON_OPERATORS = {">", ">=", "<", "<=", "=", "!="}

    @staticmethod
    def execute_plan(catalog: Dict[str, Any], plan: Dict[str, Any], row_limit: int = 100) -> Dict[str, Any]:
        validated = GenericQueryTools.validate_plan(catalog, plan, row_limit)
        tables = {table["table_name"]: table for table in catalog.get("tables", [])}
        aliases = {name: f"t{index}" for index, name in enumerate(validated["tables"])}
        connection = duckdb.connect(database=":memory:")
        try:
            connection.execute("SET memory_limit = '512MB'")
            connection.execute("SET threads = 2")
            for table_name in validated["tables"]:
                source = str(tables[table_name]["source"]).replace("'", "''")
                connection.execute(
                    f"CREATE VIEW {GenericQueryTools._quote_identifier(table_name)} "
                    f"AS SELECT * FROM read_csv_auto('{source}', header=true)"
                )

            query = GenericQueryTools._build_query(catalog, validated, aliases)
            result = connection.execute(query).fetchall()
            columns = [item[0] for item in connection.description]
            rows = [dict(zip(columns, row)) for row in result]
            return {
                "status": "success",
                "plan": validated,
                "tables_used": validated["tables"],
                "query": query,
                "rows": rows,
                "row_count": len(rows),
                "truncated": len(rows) >= validated["limit"],
                "recommendation": GenericQueryTools._build_recommendation(validated, rows),
            }
        finally:
            connection.close()

    @staticmethod
    def validate_plan(catalog: Dict[str, Any], plan: Dict[str, Any], row_limit: int) -> Dict[str, Any]:
        if not isinstance(plan, dict):
            raise AnalysisPlanError("Analysis plan must be an object.")
        task = plan.get("task")
        if not isinstance(task, str) or task not in GenericQueryTools.ALLOWED_TASKS:
            raise AnalysisPlanError(f"Unsupported analysis task: {task}")
        table_names = plan.get("tables")
        if not isinstance(table_names, list) or not table_names:
            raise AnalysisPlanError("Analysis plan must name at least one table.")
        if not all(isinstance(table_name, str) for table_name in table_names):
            raise AnalysisPlanError("Table names must be strings.")

        catalog_tables = {table["table_name"]: table for table in catalog.get("tables", [])}
        unknown_tables = set(table_names) - set(catalog_tables)
        if unknown_tables:
            raise AnalysisPlanError(f"Unknown tables: {sorted(unknown_tables)}")
        if len(table_names) != len(set(table_names)):
            raise AnalysisPlanError("Analysis plan contains duplicate tables.")

        available_columns = {
            column
            for table_name in table_names
            for column in catalog_tables[table_name].get("columns", [])
        }
        metric = plan.get("metric")
        group_by = plan.get("group_by")
        date_column = plan.get("date_column")
        for label, column in (("metric", metric), ("group_by", group_by)):
            if column is not None and (
                not isinstance(column, str) or column not in available_columns
            ):
                raise AnalysisPlanError(f"Unknown {label} column: {column}")
        if date_column is not None and (
            not isinstance(date_column, str) or date_column not in available_columns
        ):
            raise AnalysisPlanError(f"Unknown date_column column: {date_column}")
        if task == "trend" and not date_column:
            raise AnalysisPlanError("Trend analysis requires a date_column.")

        aggregation = plan.get("aggregation", "sum")
        if not isinstance(aggregation, str) or aggregation not in GenericQueryTools.ALLOWED_AGGREGATIONS:
            raise AnalysisPlanError(f"Unsupported aggregation: {aggregation}")
        if task == "summary" and not metric:
            raise AnalysisPlanError("Summary analysis requires a metric column.")
        if task == "summary" and aggregation != "sum":
            raise AnalysisPlanError("Summary analysis returns sum and average; do not specify another aggregation.")
        if task == "aggregation" and aggregation != "count" and not metric:
            raise AnalysisPlanError("Aggregation analysis requires a metric column.")
        if task == "trend" and aggregation != "sum":
            raise AnalysisPlanError("Trend analysis currently supports monthly sums only.")

        filters = plan.get("filters", [])
        if not isinstance(filters, list) or len(filters) > 20:
            raise AnalysisPlanError("Filters must be a list containing no more than 20 conditions.")
        validated_filters = []
        for condition in filters:
            if not isinstance(condition, dict):
                raise AnalysisPlanError("Each filter must be an object.")
            column = condition.get("column")
            operator = condition.get("operator")
            if not isinstance(column, str) or column not in available_columns:
                raise AnalysisPlanError(f"Unknown filter column: {column}")
            if not isinstance(operator, str) or operator not in GenericQueryTools.ALLOWED_FILTER_OPERATORS:
                raise AnalysisPlanError(f"Unsupported filter operator: {operator}")
            value = condition.get("value")
            if operator not in {"is_null", "is_not_null"}:
                if operator == "in":
                    if not isinstance(value, list) or not value or len(value) > 100:
                        raise AnalysisPlanError("The 'in' filter requires 1 to 100 scalar values.")
                    if any(not GenericQueryTools._is_scalar(item) for item in value):
                        raise AnalysisPlanError("The 'in' filter values must be non-null scalars.")
                elif not GenericQueryTools._is_scalar(value):
                    raise AnalysisPlanError("Filter values must be non-null scalar values.")
            validated_filters.append({"column": column, "operator": operator, "value": value})

        comparison = plan.get("comparison")
        if comparison is not None:
            if task != "count" or not isinstance(comparison, dict):
                raise AnalysisPlanError("Column comparisons are supported only for count analysis.")
            left_column = comparison.get("left_column")
            right_column = comparison.get("right_column")
            operator = comparison.get("operator")
            if (
                not isinstance(left_column, str)
                or not isinstance(right_column, str)
                or left_column not in available_columns
                or right_column not in available_columns
            ):
                raise AnalysisPlanError("Comparison columns must exist in the selected tables.")
            if (
                not isinstance(operator, str)
                or operator not in GenericQueryTools.ALLOWED_COMPARISON_OPERATORS
            ):
                raise AnalysisPlanError(f"Unsupported comparison operator: {operator}")
            comparison = {
                "left_column": left_column,
                "right_column": right_column,
                "operator": operator,
            }
        if task == "data_quality" and (comparison is not None or filters):
            raise AnalysisPlanError("Data-quality analysis does not accept filters or column comparisons.")

        safe_limit = max(1, min(int(row_limit), 1000))
        return {
            "task": task,
            "metric": metric,
            "group_by": group_by,
            "date_column": date_column,
            "aggregation": aggregation,
            "comparison": comparison,
            "tables": table_names,
            "filters": validated_filters,
            "limit": safe_limit,
        }

    @staticmethod
    def _build_query(catalog: Dict[str, Any], plan: Dict[str, Any], aliases: Dict[str, str]) -> str:
        tables = {table["table_name"]: table for table in catalog["tables"]}
        if plan["task"] == "data_quality":
            quality_queries = []
            for table_name in plan["tables"]:
                for column in tables[table_name].get("columns", []):
                    if column.startswith("_"):
                        continue
                    quoted_column = GenericQueryTools._quote_identifier(column.lstrip("\ufeff"))
                    quality_queries.append(
                        "SELECT "
                        f"{GenericQueryTools._quote_literal(table_name)} AS table_name, "
                        f"{GenericQueryTools._quote_literal(column)} AS column_name, "
                        "COUNT(*) AS record_count, "
                        f"SUM(CASE WHEN {quoted_column} IS NULL OR CAST({quoted_column} AS VARCHAR) = '' "
                        f"THEN 1 ELSE 0 END) AS missing_count "
                        f"FROM {GenericQueryTools._quote_identifier(table_name)}"
                    )
            if not quality_queries:
                raise AnalysisPlanError("Selected tables do not contain columns that can be checked.")
            return (
                " UNION ALL ".join(quality_queries)
                + " ORDER BY missing_count DESC LIMIT "
                + str(plan["limit"])
            )

        first = plan["tables"][0]
        from_clause = f"{GenericQueryTools._quote_identifier(first)} AS {aliases[first]}"
        joined = {first}
        join_clauses = []
        relationships = catalog.get("relationships", [])
        while len(joined) < len(plan["tables"]):
            progress = False
            for relationship in relationships:
                left = relationship["left_table"]
                right = relationship["right_table"]
                if left not in plan["tables"] or right not in plan["tables"]:
                    continue
                if left in joined and right not in joined:
                    join_clauses.append(
                        f"JOIN {GenericQueryTools._quote_identifier(right)} AS {aliases[right]} "
                        f"ON {aliases[left]}.{GenericQueryTools._quote_identifier(relationship['left_column'])} "
                        f"= {aliases[right]}.{GenericQueryTools._quote_identifier(relationship['right_column'])}"
                    )
                    joined.add(right)
                    progress = True
                elif right in joined and left not in joined:
                    join_clauses.append(
                        f"JOIN {GenericQueryTools._quote_identifier(left)} AS {aliases[left]} "
                        f"ON {aliases[right]}.{GenericQueryTools._quote_identifier(relationship['right_column'])} "
                        f"= {aliases[left]}.{GenericQueryTools._quote_identifier(relationship['left_column'])}"
                    )
                    joined.add(left)
                    progress = True
            if not progress:
                raise AnalysisPlanError("Selected tables do not have a known join path.")

        metric = plan.get("metric")
        group_by = plan.get("group_by")
        metric_table, metric_column = GenericQueryTools._locate_column(tables, plan["tables"], metric)
        group_table, group_column = GenericQueryTools._locate_column(tables, plan["tables"], group_by)
        conditions = GenericQueryTools._build_conditions(tables, plan, aliases)

        if plan["task"] == "trend":
            date_table, date_column = GenericQueryTools._locate_column(
                tables, plan["tables"], plan["date_column"]
            )
            date_field = GenericQueryTools._quote_identifier(date_column)
            period = (
                f"DATE_TRUNC('month', TRY_CAST({aliases[date_table]}.{date_field} AS TIMESTAMP))"
            )
            if metric:
                metric_field = GenericQueryTools._quote_identifier(metric_column)
                select_clause = (
                    f"{period} AS period, SUM({aliases[metric_table]}.{metric_field}) "
                    f"AS {GenericQueryTools._quote_identifier('total_' + metric_column)}"
                )
                order_clause = f"ORDER BY total_{metric_column} DESC"
            else:
                select_clause = f"{period} AS period, COUNT(*) AS record_count"
                order_clause = "ORDER BY period"
            where_clause = f"WHERE {period} IS NOT NULL"
            if conditions:
                where_clause += " AND " + " AND ".join(conditions)
            return (
                f"SELECT {select_clause} FROM {from_clause} {' '.join(join_clauses)} "
                f"{where_clause} GROUP BY {period} {order_clause} LIMIT {plan['limit']}"
            )

        if plan.get("comparison"):
            comparison = plan["comparison"]
            left_table, left_column = GenericQueryTools._locate_column(
                tables, plan["tables"], comparison["left_column"]
            )
            right_table, right_column = GenericQueryTools._locate_column(
                tables, plan["tables"], comparison["right_column"]
            )
            conditions.append(
                f"{aliases[left_table]}.{GenericQueryTools._quote_identifier(left_column)} "
                f"{comparison['operator']} "
                f"{aliases[right_table]}.{GenericQueryTools._quote_identifier(right_column)}"
            )
        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        group_clause = ""
        if group_by:
            group_clause = (
                f"GROUP BY {aliases[group_table]}."
                f"{GenericQueryTools._quote_identifier(group_column)}"
            )

        if plan["task"] == "count":
            select_clause = (
                f'{aliases[group_table]}.{GenericQueryTools._quote_identifier(group_column)} '
                f'AS {GenericQueryTools._quote_identifier(group_column)}, COUNT(*) AS record_count'
                if group_by else "COUNT(*) AS record_count"
            )
        elif plan["task"] == "summary":
            metric_field = GenericQueryTools._quote_identifier(metric_column)
            summary_columns = (
                "COUNT(*) AS record_count, "
                f"SUM({aliases[metric_table]}.{metric_field}) "
                f"AS {GenericQueryTools._quote_identifier('total_' + metric_column)}, "
                f"AVG({aliases[metric_table]}.{metric_field}) "
                f"AS {GenericQueryTools._quote_identifier('average_' + metric_column)}"
            )
            select_clause = (
                f'{aliases[group_table]}.{GenericQueryTools._quote_identifier(group_column)} '
                f'AS {GenericQueryTools._quote_identifier(group_column)}, {summary_columns}'
                if group_by else summary_columns
            )
        else:
            aggregate = plan["aggregation"].upper()
            if aggregate == "COUNT":
                metric_expression = "COUNT(*)"
                output_name = "record_count"
            else:
                metric_expression = (
                    f"{aggregate}({aliases[metric_table]}."
                    f"{GenericQueryTools._quote_identifier(metric_column)})"
                )
                name_prefix = {
                    "SUM": "total",
                    "AVG": "average",
                    "MIN": "min",
                    "MAX": "max",
                }[aggregate]
                output_name = GenericQueryTools._quote_identifier(f"{name_prefix}_{metric_column}")
            select_clause = (
                f'{aliases[group_table]}.{GenericQueryTools._quote_identifier(group_column)} '
                f'AS {GenericQueryTools._quote_identifier(group_column)}, '
                f"{metric_expression} AS {output_name}"
                if group_by else f"{metric_expression} AS {output_name}"
            )

        order_clause = "ORDER BY 2 DESC" if group_by else ""
        return (
            f"SELECT {select_clause} FROM {from_clause} {' '.join(join_clauses)} "
            f"{where_clause} {group_clause} {order_clause} LIMIT {plan['limit']}"
        )

    @staticmethod
    def _build_conditions(
        tables: Dict[str, Any],
        plan: Dict[str, Any],
        aliases: Dict[str, str],
    ) -> List[str]:
        conditions = []
        for condition in plan["filters"]:
            table_name, column = GenericQueryTools._locate_column(
                tables, plan["tables"], condition["column"]
            )
            field = f"{aliases[table_name]}.{GenericQueryTools._quote_identifier(column)}"
            operator = condition["operator"]
            value = condition["value"]
            if operator == "is_null":
                conditions.append(f"{field} IS NULL")
            elif operator == "is_not_null":
                conditions.append(f"{field} IS NOT NULL")
            elif operator == "contains":
                escaped = str(value).replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
                pattern = GenericQueryTools._quote_literal("%" + escaped + "%")
                conditions.append(f"CAST({field} AS VARCHAR) ILIKE {pattern} ESCAPE '\\'")
            elif operator == "in":
                values = ", ".join(GenericQueryTools._quote_literal(item) for item in value)
                conditions.append(f"{field} IN ({values})")
            else:
                conditions.append(f"{field} {operator} {GenericQueryTools._quote_literal(value)}")
        return conditions

    @staticmethod
    def _quote_identifier(identifier: str) -> str:
        return '"' + identifier.replace('"', '""') + '"'

    @staticmethod
    def _quote_literal(value: Any) -> str:
        if isinstance(value, bool):
            return "TRUE" if value else "FALSE"
        if isinstance(value, (int, float)):
            return str(value)
        return "'" + str(value).replace("'", "''") + "'"

    @staticmethod
    def _is_scalar(value: Any) -> bool:
        return (
            isinstance(value, (str, int, float, bool))
            and not (isinstance(value, float) and not math.isfinite(value))
        )

    @staticmethod
    def _locate_column(tables: Dict[str, Any], table_names: List[str], column: str | None):
        if not column:
            return table_names[0], "*"
        matches = [table for table in table_names if column in tables[table].get("columns", [])]
        if len(matches) != 1:
            raise AnalysisPlanError(f"Column must exist in exactly one selected table: {column}")
        return matches[0], column

    @staticmethod
    def _build_recommendation(plan: Dict[str, Any], rows: List[Dict[str, Any]]) -> str:
        if not rows:
            return "No matching records were found for this analysis."
        if plan.get("group_by"):
            top = rows[0]
            return (
                f"The leading group is {top.get(plan['group_by'])}, based on the requested metric. "
                "Review the result against business targets before acting."
            )
        return "The requested analysis completed successfully. Review the evidence above before taking action."
