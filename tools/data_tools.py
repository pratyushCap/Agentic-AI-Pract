# tools/data_tools.py
import csv
import json
from typing import Dict, Any, List
from utils.errors import ToolExecutionError


class DataAnalysisTools:
    """Tools for data analysis agent"""

    @staticmethod
    def profile_dataset(data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Build a bounded, schema-aware profile for a dataset."""
        if not data:
            raise ToolExecutionError("Dataset profiling failed: no data records available")

        columns = list(dict.fromkeys(column for row in data for column in row))
        numeric_columns = [
            column for column in columns
            if any(DataAnalysisTools._to_number(row.get(column)) is not None for row in data)
        ]
        categorical_columns = [column for column in columns if column not in numeric_columns]
        domain = DataAnalysisTools.detect_domain(columns)

        return {
            "status": "success",
            "domain": domain,
            "rows": len(data),
            "columns": columns,
            "numeric_columns": numeric_columns,
            "categorical_columns": categorical_columns,
            "statistics": DataAnalysisTools.get_summary_statistics(data),
            "correlation": DataAnalysisTools.get_correlation_matrix(data),
        }

    @staticmethod
    def detect_domain(columns: List[str]) -> str:
        """Classify common business dataset shapes from normalized column names."""
        normalized = {column.lower() for column in columns}
        if {"transaction_amount", "risk_score"}.issubset(normalized):
            return "transactions"
        if {"revenue", "profit", "expenses"}.issubset(normalized):
            return "finance"
        if {"equities", "bonds", "cash"}.issubset(normalized):
            return "portfolio"
        return "general"

    @staticmethod
    def load_data(file_path: str) -> Dict[str, Any]:
        """Load CSV or JSON file"""
        try:
            if file_path.endswith('.csv'):
                with open(file_path, newline='', encoding='utf-8') as f:
                    reader = csv.DictReader(f)
                    records = [row for row in reader]
                columns = reader.fieldnames or []
            elif file_path.endswith('.json'):
                with open(file_path, encoding='utf-8') as f:
                    records = json.load(f)
                columns = list(records[0].keys()) if records else []
            else:
                raise ValueError("Unsupported file format. Use .csv or .json")

            return {
                "status": "success",
                "rows": len(records),
                "columns": columns,
                "preview": records[:5],
                "records": records,
            }
        except Exception as e:
            raise ToolExecutionError(f"Failed to load data: {str(e)}")

    @staticmethod
    def get_summary_statistics(data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Get summary statistics for numeric columns"""
        try:
            if not data:
                raise ValueError("No data records available")

            columns = list(dict.fromkeys(column for row in data for column in row))
            stats = {}
            numeric_columns = [
                column for column in columns
                if any(DataAnalysisTools._to_number(row.get(column)) is not None for row in data)
            ]

            for column in numeric_columns:
                values = [
                    number for row in data
                    if (number := DataAnalysisTools._to_number(row.get(column))) is not None
                ]
                if not values:
                    continue
                stats[column] = {
                    "count": len(values),
                    "mean": sum(values) / len(values),
                    "min": min(values),
                    "max": max(values),
                }

            missing_values = {
                column: sum(1 for row in data if DataAnalysisTools._to_number(row.get(column)) is None and row.get(column) in (None, "", "NaN"))
                for column in columns
            }

            return {
                "status": "success",
                "summary": stats,
                "missing_values": missing_values,
            }
        except Exception as e:
            raise ToolExecutionError(f"Summary statistics failed: {str(e)}")

    @staticmethod
    def get_correlation_matrix(data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Calculate correlation between numeric columns using Pearson"""
        try:
            if not data:
                raise ValueError("No data records available")

            columns = list(dict.fromkeys(column for row in data for column in row))
            numeric_columns = [
                column for column in columns
                if any(DataAnalysisTools._to_number(row.get(column)) is not None for row in data)
            ]
            matrix = {}
            for col_a in numeric_columns:
                matrix[col_a] = {}
                for col_b in numeric_columns:
                    if col_a == col_b:
                        matrix[col_a][col_b] = 1.0
                        continue
                    paired_values = [
                        (number_a, number_b)
                        for row in data
                        if (number_a := DataAnalysisTools._to_number(row.get(col_a))) is not None
                        and (number_b := DataAnalysisTools._to_number(row.get(col_b))) is not None
                    ]
                    if len(paired_values) < 2:
                        matrix[col_a][col_b] = None
                        continue
                    vals_a, vals_b = zip(*paired_values)
                    mean_a = sum(vals_a) / len(vals_a)
                    mean_b = sum(vals_b) / len(vals_b)
                    cov = sum((a - mean_a) * (b - mean_b) for a, b in zip(vals_a, vals_b))
                    std_a = (sum((a - mean_a) ** 2 for a in vals_a) / len(vals_a)) ** 0.5
                    std_b = (sum((b - mean_b) ** 2 for b in vals_b) / len(vals_b)) ** 0.5
                    value = cov / (std_a * std_b) if std_a and std_b else None
                    matrix[col_a][col_b] = round(max(-1.0, min(1.0, value)), 10) if value is not None else None

            return {
                "status": "success",
                "correlation": matrix,
            }
        except Exception as e:
            raise ToolExecutionError(f"Correlation calculation failed: {str(e)}")

    @staticmethod
    def find_outliers(data: List[Dict[str, Any]], column: str, method: str = "iqr") -> Dict[str, Any]:
        """Detect outliers using IQR or simple z-score approximation"""
        try:
            values = [
                number for row in data
                if (number := DataAnalysisTools._to_number(row.get(column))) is not None
            ]
            if not values:
                raise ValueError(f"Column '{column}' has no numeric values")

            if method == "iqr":
                sorted_vals = sorted(values)
                q1 = sorted_vals[len(sorted_vals) // 4]
                q3 = sorted_vals[(len(sorted_vals) * 3) // 4]
                iqr = q3 - q1
                lower = q1 - 1.5 * iqr
                upper = q3 + 1.5 * iqr
                outliers = [
                    row for row in data
                    if (number := DataAnalysisTools._to_number(row.get(column))) is not None
                    and (number < lower or number > upper)
                ]
            else:
                mean = sum(values) / len(values)
                std = (sum((x - mean) ** 2 for x in values) / len(values)) ** 0.5
                outliers = [
                    row for row in data
                    if (number := DataAnalysisTools._to_number(row.get(column))) is not None
                    and abs((number - mean) / std) > 3
                ] if std else []

            return {
                "status": "success",
                "outlier_count": len(outliers),
                "outlier_percentage": (len(outliers) / len(data)) * 100,
                "outliers": outliers[:10],
            }
        except Exception as e:
            raise ToolExecutionError(f"Outlier detection failed: {str(e)}")

    @staticmethod
    def _to_number(value: Any):
        if value in (None, "", "NaN"):
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None
