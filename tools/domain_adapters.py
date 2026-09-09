from typing import Any, Dict


class DomainAnalysisTools:
    """Deterministic analyses for recognized business dataset domains."""

    @staticmethod
    def analyze_transaction_profile(profile: Dict[str, Any]) -> Dict[str, Any]:
        summary = profile.get("statistics", {}).get("summary", {})
        amount = summary.get("transaction_amount", {})
        risk = summary.get("risk_score", {})
        if not amount or not risk:
            return {
                "status": "incomplete",
                "recommendation": "Transaction analysis is incomplete because amount or risk values are missing.",
            }
        return {
            "status": "success",
            "average_transaction_amount": amount["mean"],
            "average_risk_score": risk["mean"],
            "missing_values": profile.get("statistics", {}).get("missing_values", {}),
            "recommendation": (
                f"Average transaction amount is {amount['mean']:.2f} and average risk score is {risk['mean']:.2f}. "
                "Investigate high-risk transactions before taking action."
            ),
        }

    @staticmethod
    def analyze_finance_profile(profile: Dict[str, Any]) -> Dict[str, Any]:
        summary = profile.get("statistics", {}).get("summary", {})
        revenue = summary.get("revenue", {}).get("mean")
        profit = summary.get("profit", {}).get("mean")
        expenses = summary.get("expenses", {}).get("mean")
        if revenue is None or profit is None or expenses is None or revenue == 0:
            return {
                "status": "incomplete",
                "recommendation": "Finance analysis is incomplete because revenue, profit, or expenses are missing.",
            }
        return {
            "status": "success",
            "average_revenue": revenue,
            "average_profit": profit,
            "average_expenses": expenses,
            "profit_margin": round(profit / revenue * 100, 2),
            "expense_ratio": round(expenses / revenue * 100, 2),
            "recommendation": "Review profit margin and expense ratio before approving new investments or cost changes.",
        }

    @staticmethod
    def analyze_portfolio_profile(profile: Dict[str, Any]) -> Dict[str, Any]:
        summary = profile.get("statistics", {}).get("summary", {})
        exposures = {
            column: summary[column]["mean"]
            for column in ("equities", "bonds", "cash")
            if column in summary
        }
        if not exposures:
            return {
                "status": "incomplete",
                "recommendation": "Portfolio analysis is incomplete because asset exposure fields are missing.",
            }
        largest_asset = max(exposures, key=exposures.get)
        return {
            "status": "success",
            "average_exposure": exposures,
            "largest_exposure": largest_asset,
            "recommendation": f"The largest average portfolio exposure is {largest_asset}. Review concentration and volatility before rebalancing.",
        }
