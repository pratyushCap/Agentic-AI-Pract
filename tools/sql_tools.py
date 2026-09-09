# tools/sql_tools.py
from typing import Any, Dict, Iterator, List, Union
import csv
import json
from sqlalchemy import create_engine, text
from pathlib import Path

from utils.errors import ToolExecutionError

class DataEngineeringTools:
    """Tools for data engineering agent"""
    
    @staticmethod
    def execute_query(sql_query: str, connection_string: str) -> Dict[str, Any]:
        """Execute SQL query"""
        try:
            engine = create_engine(connection_string)
            with engine.connect() as connection:
                result = connection.execute(text(sql_query))
                rows = [dict(row._mapping) for row in result]
                columns = list(result.keys())

                return {
                    "status": "success",
                    "rows": len(rows),
                    "columns": columns,
                    "data": rows[:10],
                    "sample_count": min(10, len(rows)),
                    "records": rows,
                }
        except Exception as e:
            raise ToolExecutionError(f"SQL execution failed: {str(e)}")
    
    @staticmethod
    def load_data_source(
        source: Union[str, List[str]],
        include_records: bool = True,
        max_records: int = 0,
    ) -> Dict[str, Any]:
        '''Load one or more CSV/JSON data sources for data engineering.
Supports:
    - Single file path: "data/transactions.csv"
    - Multiple file paths: ["jan.csv", "feb.csv", "accounts.json"]
    - Folder path: "data/finance_files/"

    The returned structure keeps the existing agent contract unchanged.'''
        try:
                       
            file_paths = DataEngineeringTools._resolve_input_sources(source)

            if not file_paths:
                raise ValueError("No supported .csv or .json files found.")

            merged_records = []
            preview = []
            all_columns = set()
            row_count = 0

            for standardized_record in DataEngineeringTools._iter_source_records(file_paths):
                row_count += 1
                all_columns.update(standardized_record.keys())
                if len(preview) < 10:
                    preview.append(standardized_record)
                if include_records and (max_records <= 0 or len(merged_records) < max_records):
                    merged_records.append(standardized_record)

            columns = sorted(all_columns)
            for record in preview + merged_records:
                for column in columns:
                    record.setdefault(column, None)


            return {
                "status": "success",
                "file_count": len(file_paths),
                "rows": row_count,
                "columns": columns,
                "data": preview,
                "sample_count": len(preview),
                "records": merged_records if include_records else None,
                "records_truncated": include_records and max_records > 0 and row_count > len(merged_records),
            }

        except Exception as e:
            raise ToolExecutionError(f"Data source load failed: {str(e)}")

    @staticmethod
    def profile_data_source(
        source: Union[str, List[str]],
        preview_limit: int = 10,
    ) -> Dict[str, Any]:
        """Profile a source in one pass without retaining all of its records."""
        try:
            file_paths = DataEngineeringTools._resolve_input_sources(source)
            if not file_paths:
                raise ValueError("No supported .csv or .json files found.")

            columns = set()
            preview = []
            numeric_stats = {}
            pair_stats = {}
            missing_counts = {}
            row_count = 0

            for row in DataEngineeringTools._iter_source_records(file_paths):
                row_count += 1
                new_columns = set(row) - columns
                for column in new_columns:
                    missing_counts[column] = row_count - 1
                columns.update(row.keys())
                for column in columns:
                    if row.get(column) in (None, "", "NaN"):
                        missing_counts[column] = missing_counts.get(column, 0) + 1
                if len(preview) < preview_limit:
                    preview.append(row)

                numeric_values = {}
                for column, value in row.items():
                    number = DataEngineeringTools._to_number(value)
                    if number is None:
                        continue
                    numeric_values[column] = number
                    stats = numeric_stats.setdefault(column, {"count": 0, "sum": 0.0, "min": number, "max": number})
                    stats["count"] += 1
                    stats["sum"] += number
                    stats["min"] = min(stats["min"], number)
                    stats["max"] = max(stats["max"], number)

                for first_index, first_column in enumerate(numeric_values):
                    for second_column in list(numeric_values)[first_index + 1:]:
                        key = (first_column, second_column)
                        first_value = numeric_values[first_column]
                        second_value = numeric_values[second_column]
                        pair = pair_stats.setdefault(key, {"n": 0, "sum_x": 0.0, "sum_y": 0.0, "sum_xx": 0.0, "sum_yy": 0.0, "sum_xy": 0.0})
                        pair["n"] += 1
                        pair["sum_x"] += first_value
                        pair["sum_y"] += second_value
                        pair["sum_xx"] += first_value * first_value
                        pair["sum_yy"] += second_value * second_value
                        pair["sum_xy"] += first_value * second_value

            missing_values = {
                column: missing_counts.get(column, row_count)
                for column in columns
            }
            summary = {
                column: {
                    "count": stats["count"],
                    "mean": stats["sum"] / stats["count"],
                    "min": stats["min"],
                    "max": stats["max"],
                }
                for column, stats in numeric_stats.items()
            }
            correlation = DataEngineeringTools._correlation_from_pairs(pair_stats, numeric_stats)

            from tools.data_tools import DataAnalysisTools
            domain = DataAnalysisTools.detect_domain(list(columns))
            return {
                "status": "success",
                "domain": domain,
                "rows": row_count,
                "columns": sorted(columns),
                "numeric_columns": sorted(numeric_stats),
                "preview": preview,
                "statistics": {"status": "success", "summary": summary, "missing_values": missing_values},
                "correlation": {"status": "success", "correlation": correlation},
            }
        except Exception as e:
            raise ToolExecutionError(f"Data source profiling failed: {str(e)}")

    @staticmethod
    def _iter_source_records(file_paths: List[Path]) -> Iterator[Dict[str, Any]]:
        for file_path in file_paths:
            for record in DataEngineeringTools._iter_single_file(file_path):
                standardized_record = DataEngineeringTools._standardize_record(record)
                standardized_record["_source_file"] = str(file_path)
                standardized_record["_source_name"] = file_path.name
                yield standardized_record

    @staticmethod
    def _iter_single_file(file_path: Path) -> Iterator[Dict[str, Any]]:
        if file_path.suffix.lower() == ".csv":
            with file_path.open(newline="", encoding="utf-8") as handle:
                yield from csv.DictReader(handle)
            return

        with file_path.open(encoding="utf-8") as handle:
            payload = json.load(handle)
        if isinstance(payload, dict):
            payload = payload.get("records", [payload])
        if not isinstance(payload, list) or not all(isinstance(row, dict) for row in payload):
            raise ValueError(f"JSON source must contain an object or a list of objects: {file_path}")
        yield from payload

    @staticmethod
    def _to_number(value: Any):
        if value in (None, "", "NaN"):
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _correlation_from_pairs(pair_stats: Dict[Any, Dict[str, float]], numeric_stats: Dict[str, Dict[str, float]]) -> Dict[str, Dict[str, Any]]:
        matrix = {column: {column: 1.0} for column in numeric_stats}
        for (first_column, second_column), pair in pair_stats.items():
            count = pair["n"]
            covariance = pair["sum_xy"] - pair["sum_x"] * pair["sum_y"] / count
            variance_x = pair["sum_xx"] - pair["sum_x"] ** 2 / count
            variance_y = pair["sum_yy"] - pair["sum_y"] ** 2 / count
            value = covariance / (variance_x * variance_y) ** 0.5 if variance_x > 0 and variance_y > 0 else None
            if value is not None:
                value = round(max(-1.0, min(1.0, value)), 10)
            matrix.setdefault(first_column, {})[second_column] = value
            matrix.setdefault(second_column, {})[first_column] = value
        return matrix

    @staticmethod
    def _resolve_input_sources(source: Union[str, List[str]]) -> List[Path]:
        sources = [source] if isinstance(source, str) else source
        file_paths = []

        for item in sources or []:
            path = Path(item)
            if path.is_dir():
                file_paths.extend(
                    child for child in sorted(path.iterdir())
                    if child.is_file() and child.suffix.lower() in {".csv", ".json"}
                )
            elif path.is_file() and path.suffix.lower() in {".csv", ".json"}:
                file_paths.append(path)
            else:
                raise ValueError(f"Unsupported or missing data source: {item}")

        return file_paths

    @staticmethod
    def _standardize_record(record: Dict[str, Any]) -> Dict[str, Any]:
        standardized = {}
        for key, value in record.items():
            normalized_key = "_".join(str(key).strip().lower().split())
            if not normalized_key:
                continue
            standardized[normalized_key] = value.strip() if isinstance(value, str) and value.strip() else (
                None if value in ("", "NaN") else value
            )
        return standardized
    
    @staticmethod
    def get_table_schema(table_name: str, connection_string: str) -> Dict[str, Any]:
        """Get table schema and metadata"""
        try:
            engine = create_engine(connection_string)
            with engine.connect() as connection:
                query = f"SELECT * FROM {table_name} LIMIT 0"
                result = connection.execute(text(query))
                
                columns = result.keys()
                return {
                    "status": "success",
                    "table_name": table_name,
                    "columns": list(columns),
                    "column_count": len(columns)
                }
        except Exception as e:
            raise ToolExecutionError(f"Schema retrieval failed: {str(e)}")
