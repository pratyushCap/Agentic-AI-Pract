from utils.agents.agents import BaseAgent


class ReviewerAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            name="reviewer",
            description="Reviews recommendations, checks for risk and compliance, and validates actions before execution.",
            system_prompt=(
                "You are a reviewer assistant. "
                "Review recommendations, validate assumptions, and provide governance feedback."
            ),
            tools={},
        )

    def review_recommendation(self, recommendation: str) -> str:
        """Review a business recommendation and provide validation feedback."""
        return (
            "The recommendation appears reasonable, but ensure risk exposure remains within policy limits "
            "and verify all assumptions before execution."
        )
