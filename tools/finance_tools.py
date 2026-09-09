from typing import Any, Dict, List


class FinanceAnalysisTools:
    """Tools for finance and investment analysis."""

    @staticmethod
    def generate_finance_report(financial_data: Dict[str, Any]) -> Dict[str, Any]:
        """Generate a basic finance report from provided metrics."""
        revenue = financial_data.get("revenue")
        profit = financial_data.get("profit")
        expenses = financial_data.get("expenses")

        insights = []
        if revenue is not None and profit is not None:
            margin = (profit / revenue) * 100 if revenue else 0
            insights.append(f"Profit margin is {margin:.1f}%.")
        if expenses is not None and revenue is not None:
            expense_ratio = (expenses / revenue) * 100 if revenue else 0
            insights.append(f"Expense ratio is {expense_ratio:.1f}%.")

        recommendation = (
            "Focus on high-margin opportunities and reduce cost drivers "
            "while maintaining revenue growth." if insights else "Review the financial inputs for completeness."
        )

        return {
            "status": "success",
            "insights": insights,
            "recommendation": recommendation,
            "summary": financial_data,
        }

    @staticmethod
    def calculate_risk_score(portfolio_data: Dict[str, Any]) -> Dict[str, Any]:
        """Calculate a simple risk score for an investment portfolio."""
        exposure = portfolio_data.get("exposure", {})
        volatility = portfolio_data.get("volatility", {})
        score = 50

        if exposure:
            max_exposure = max(exposure.values())
            score += min(30, max_exposure * 0.5)

        if volatility:
            avg_volatility = sum(volatility.values()) / len(volatility)
            score += min(20, avg_volatility * 10)

        score = min(100, round(score))
        recommendation = (
            "Risk is moderate to high. Consider rebalancing toward lower volatility assets."
            if score >= 60
            else "Risk is within acceptable bounds, but continue monitoring exposures."
        )

        return {
            "status": "success",
            "risk_score": score,
            "recommendation": recommendation,
            "details": {
                "max_exposure": max(exposure.values()) if exposure else 0,
                "avg_volatility": round(avg_volatility, 3) if volatility else 0,
            },
        }

    @staticmethod
    def simulate_portfolio(assets: List[Dict[str, Any]], allocations: Dict[str, float]) -> Dict[str, Any]:
        """Run a simple portfolio simulation given asset returns and allocations."""
        expected_return = 0.0
        risk = 0.0

        for asset in assets:
            symbol = asset.get("symbol")
            avg_return = asset.get("average_return", 0.0)
            volatility = asset.get("volatility", 0.0)
            weight = allocations.get(symbol, 0.0)
            expected_return += avg_return * weight
            risk += volatility * weight

        return {
            "status": "success",
            "expected_return": round(expected_return, 4),
            "expected_risk": round(risk, 4),
            "recommendation": (
                "Portfolio appears well balanced for the target return."
                if expected_return > 0.05 and risk < 0.2
                else "Consider rebalancing to improve risk-adjusted return."
            ),
        }
