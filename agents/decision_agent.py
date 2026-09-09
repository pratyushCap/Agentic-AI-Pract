from typing import Dict, Any

from utils.agents.agents import BaseAgent


class DecisionPlannerAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            name="decision_planner",
            description="Creates concrete finance and investment decisions based on analysis and review feedback.",
            system_prompt=(
                "You are a decision planner assistant. "
                "Turn financial analysis, risk review, and business context into clear recommended actions."
            ),
            tools={},
        )

    def plan_actions(self, finance_comment: Dict[str, Any], review: str) -> Dict[str, Any]:
        """Create a series of recommended actions from analysis output."""
        recommendation = finance_comment.get("recommendation", "")
        risk_score = finance_comment.get("risk", {}).get("risk_score", 0)
        report_summary = finance_comment.get("report", {}).get("summary", {})

        actions = []
        if risk_score >= 70:
            actions.append(
                "Review high-volatility positions and consider shifting to lower-risk assets to reduce portfolio risk."
            )
        else:
            actions.append(
                "Continue monitoring current risk levels and maintain the existing portfolio allocation."
            )

        profit = report_summary.get("profit")
        revenue = report_summary.get("revenue")
        if profit is not None and revenue:
            margin = (profit / revenue) * 100
            if margin < 15:
                actions.append(
                    "Identify opportunities to improve profit margins through cost optimization or higher-margin revenue streams."
                )
            else:
                actions.append(
                    "Preserve strong margin performance while validating growth investments."
                )

        if "risk" in review.lower():
            actions.append(
                "Engage compliance and risk teams to validate the recommendation assumptions before execution."
            )

        if not actions:
            actions.append(
                "Consolidate current finance insights and revisit the strategy once new data is available."
            )

        return {
            "status": "success",
            "decision_plan": {
                "recommendation": recommendation,
                "actions": actions,
                "review_note": review,
            },
        }
