from tools.finance_tools import FinanceAnalysisTools
from utils.agents.agents import BaseAgent


class FinanceAnalystAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            name="finance_analyst",
            description="Analyzes financial performance, creates investment recommendations, and evaluates business financial decisions.",
            system_prompt=(
                "You are a finance analyst assistant. "
                "Analyze financial performance, interpret results, create investment recommendations, "
                "and help the business make finance decisions."
            ),
            tools={
                "generate_finance_report": FinanceAnalysisTools.generate_finance_report,
                "calculate_risk_score": FinanceAnalysisTools.calculate_risk_score,
                "simulate_portfolio": FinanceAnalysisTools.simulate_portfolio,
            },
        )

    def analyze_financials(self, data_summary: dict) -> dict:
        """Analyze financial summary data and produce recommendations."""
        finance_data = data_summary.get("finance_data", {})
        portfolio_data = data_summary.get("portfolio", {})
        simulation_data = data_summary.get("simulation", {})

        report = self.tools["generate_finance_report"](finance_data)
        risk = self.tools["calculate_risk_score"](portfolio_data)
        simulation = self.tools["simulate_portfolio"](
            simulation_data.get("assets", []),
            simulation_data.get("allocations", {}),
        )

        recommendation = (
            "The current financial position looks reasonably strong, but keep an eye on cost ratios and risk exposures. "
            "Consider a balanced portfolio reallocation if volatility remains elevated."
        )

        return {
            "report": report,
            "risk": risk,
            "simulation": simulation,
            "recommendation": recommendation,
        }
