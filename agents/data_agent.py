from tools.data_tools import DataAnalysisTools
from utils.agents.agents import BaseAgent


class DataAnalystAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            name="data_analyst",
            description="Analyzes business and financial data, extracts insights, and supports decision recommendations.",
            system_prompt=(
                "You are a data analyst assistant. "
                "Inspect datasets, summarize trends, identify anomalies, and provide actionable insights."
            ),
            tools={
                "get_summary_statistics": DataAnalysisTools.get_summary_statistics,
                "get_correlation_matrix": DataAnalysisTools.get_correlation_matrix,
                "find_outliers": DataAnalysisTools.find_outliers,
            },
        )

    def summarize_data(self, data) -> dict:
        """Summarize provided dataset information."""
        profile = DataAnalysisTools.profile_dataset(data)
        statistics = profile["statistics"]
        correlation = profile["correlation"]

        numeric_columns = profile["numeric_columns"]
        outliers = None
        if numeric_columns:
            outliers = self.tools["find_outliers"](data, numeric_columns[0])

        trend_summary = self._build_summary(profile, statistics)

        return {
            "domain": profile["domain"],
            "rows": profile["rows"],
            "columns": profile["columns"],
            "statistics": statistics,
            "correlation": correlation,
            "outliers": outliers,
            "summary": trend_summary,
        }

    def _build_summary(self, profile: dict, statistics: dict) -> str:
        domain = profile["domain"]
        summary = statistics.get("summary", {})
        if domain == "transactions":
            amount = summary.get("transaction_amount", {}).get("mean")
            risk = summary.get("risk_score", {}).get("mean")
            if amount is None or risk is None:
                return (
                    f"Transaction data contains {profile['rows']:,} records, but required numeric fields are incomplete. "
                    "Resolve missing transaction amounts or risk scores before taking action."
                )
            return (
                f"Transaction data contains {profile['rows']:,} records. "
                f"Average transaction amount is {amount:.2f} and average risk score is {risk:.2f}. "
                "Review high-risk transactions and missing values before taking action."
            )
        if domain == "finance":
            return "Finance data includes revenue, profit, and expenses. Review margin, expense ratio, and trends before taking action."
        if domain == "portfolio":
            return "Portfolio data includes asset exposures. Review allocation, volatility, and concentration risk before taking action."
        return f"The dataset was profiled successfully with {profile['rows']:,} records and {len(profile['columns'])} columns."

    def _is_numeric(self, value) -> bool:
        try:
            float(value)
            return True
        except Exception:
            return False
