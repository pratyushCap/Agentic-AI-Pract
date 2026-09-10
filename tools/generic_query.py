import json
from pathlib import Path
from typing import Any, Dict, List

import duckdb


class AnalysisPlanError(ValueError):
    """Raised when an analysis plan is invalid or unsafe."""


class GenericQueryTools:
    """Validate and execute bounded read-only analysis plans."""

    ALLOWED_TASKS = {"aggregation", "summary", "count", "trend", "data_quality"}

    @staticmethod
    def execute_plan(catalog: Dict[str, Any], plan: Dict[str, Any], row_limit: int = 100) -> Dict[str, Any]:
        validated = GenericQueryTools.validate_plan(catalog, plan, row_limit)
        tables = {table["table_name"]: table for table in catalog.get("tables", [])}
        aliases = {name: f"t{index}" for index, name in enumerate(validated["tables"])}
        connection = duckdb.connect(database=":memory:")
        try:
            for table_name in validated["tables"]:
                source = str(tables[table_name]["source"]).replace("'", "''")
                connection.execute(
                    f'CREATE VIEW "{table_name}" AS SELECT * FROM read_csv_auto(\'{source}\', header=true)'
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
                "truncated": len(rows) >= row_limit,
                "recommendation": GenericQueryTools._build_recommendation(validated, rows),
            }
        finally:
            connection.close()

    @staticmethod
    def validate_plan(catalog: Dict[str, Any], plan: Dict[str, Any], row_limit: int) -> Dict[str, Any]:
        if not isinstance(plan, dict):
            raise AnalysisPlanError("Analysis plan must be an object.")
        task = plan.get("task")
        if task not in GenericQueryTools.ALLOWED_TASKS:
            raise AnalysisPlanError(f"Unsupported analysis task: {task}")
        table_names = plan.get("tables")
        if not isinstance(table_names, list) or not table_names:
            raise AnalysisPlanError("Analysis plan must name at least one table.")
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
            if column and column not in available_columns:
                raise AnalysisPlanError(f"Unknown {label} column: {column}")
        if date_column and date_column not in available_columns:
            raise AnalysisPlanError(f"Unknown date_column column: {date_column}")
        if task == "trend" and not date_column:
            raise AnalysisPlanError("Trend analysis requires a date_column.")
        safe_limit = max(1, min(int(row_limit), 1000))
        return {
            "task": task,
            "metric": metric,
            "group_by": group_by,
            "date_column": date_column,
            "tables": table_names,
            "filters": plan.get("filters", []),
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
                    query_column = column.lstrip("\ufeff")
                    escaped_column = query_column.replace('"', '""')
                    quality_queries.append(
                        "SELECT "
                        f"'{table_name}' AS table_name, '{column}' AS column_name, "
                        f"COUNT(*) AS record_count, "
                        f"SUM(CASE WHEN \"{escaped_column}\" IS NULL OR CAST(\"{escaped_column}\" AS VARCHAR) = '' THEN 1 ELSE 0 END) AS missing_count "
                        f'FROM "{table_name}"'
                    )
            return " UNION ALL ".join(quality_queries) + " ORDER BY missing_count DESC LIMIT " + str(plan["limit"])

        first = plan["tables"][0]
        from_clause = f'"{first}" AS {aliases[first]}'
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
                        f'JOIN "{right}" AS {aliases[right]} ON {aliases[left]}."{relationship["left_column"]}" = {aliases[right]}."{relationship["right_column"]}"'
                    )
                    joined.add(right)
                    progress = True
                elif right in joined and left not in joined:
                    join_clauses.append(
                        f'JOIN "{left}" AS {aliases[left]} ON {aliases[right]}."{relationship["right_column"]}" = {aliases[left]}."{relationship["left_column"]}"'
                    )
                    joined.add(left)
                    progress = True
            if not progress:
                raise AnalysisPlanError("Selected tables do not have a known join path.")

        metric = plan.get("metric")
        group_by = plan.get("group_by")
        metric_table, metric_column = GenericQueryTools._locate_column(tables, plan["tables"], metric)
        group_table, group_column = GenericQueryTools._locate_column(tables, plan["tables"], group_by)
        if plan["task"] == "trend":
            date_table, date_field = GenericQueryTools._locate_column(tables, plan["tables"], plan["date_column"])
            period = f"DATE_TRUNC('month', TRY_CAST({aliases[date_table]}.\"{date_field}\" AS TIMESTAMP))"
            if metric:
                select_clause = f"{period} AS period, SUM({aliases[metric_table]}.\"{metric_column}\") AS total_{metric_column}"
                order_clause = f"ORDER BY total_{metric_column} DESC"
            else:
                select_clause = f"{period} AS period, COUNT(*) AS record_count"
                order_clause = "ORDER BY period"
            return f"SELECT {select_clause} FROM {from_clause} {' '.join(join_clauses)} WHERE {period} IS NOT NULL GROUP BY {period} {order_clause} LIMIT {plan['limit']}"
        if plan["task"] == "count":
            select_clause = "COUNT(*) AS record_count"
            group_clause = ""
        elif plan["task"] == "summary":
            select_clause = f'COUNT(*) AS record_count, SUM({aliases[metric_table]}."{metric_column}") AS total_{metric_column}, AVG({aliases[metric_table]}."{metric_column}") AS average_{metric_column}'
            group_clause = ""
        else:
            if not metric:
                raise AnalysisPlanError("Aggregation requires a metric column.")
            aggregate = f'SUM({aliases[metric_table]}."{metric_column}") AS total_{metric_column}'
            select_clause = f'{aliases[group_table]}."{group_column}" AS "{group_column}", {aggregate}' if group_by else aggregate
            group_clause = f'GROUP BY {aliases[group_table]}."{group_column}"' if group_by else ""
        order_clause = "ORDER BY 2 DESC" if group_by or plan["task"] == "summary" else ""
        return f"SELECT {select_clause} FROM {from_clause} {' '.join(join_clauses)} {group_clause} {order_clause} LIMIT {plan['limit']}"

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
            return f"The leading group is {top.get(plan['group_by'])}, based on the requested metric. Review the result against business targets before acting."
        return "The requested analysis completed successfully. Review the evidence above before taking action."
