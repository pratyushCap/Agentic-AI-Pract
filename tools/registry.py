from dataclasses import dataclass
from typing import Any, Callable, Dict

from tools.permissions import ToolPermission, ensure_tool_allowed
from tools.sql_tools import DataEngineeringTools
from tools.domain_adapters import DomainAnalysisTools
from tools.generic_query import GenericQueryTools


@dataclass(frozen=True)
class RegisteredTool:
    name: str
    description: str
    function: Callable[..., Any]
    permission: ToolPermission


class ToolRegistry:
    """Deterministic tool boundary used by the finance agent."""

    def __init__(self) -> None:
        self._tools: Dict[str, RegisteredTool] = {}

    def register(self, tool: RegisteredTool) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> RegisteredTool:
        if name not in self._tools:
            raise KeyError(f"Unknown tool: {name}")
        return self._tools[name]

    def execute(self, name: str, arguments: Dict[str, Any], approved: bool = False) -> Any:
        tool = self.get(name)
        ensure_tool_allowed(tool.permission, approved)
        return tool.function(**arguments)

    def names(self) -> list[str]:
        return list(self._tools)


def create_default_registry() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(RegisteredTool(
        "load_dataset",
        "Load and standardize one or more CSV or JSON sources.",
        _load_dataset_for_agent,
        ToolPermission("read_only"),
    ))
    registry.register(RegisteredTool(
        "profile_dataset",
        "Calculate statistics, missing values, correlations, and outliers.",
        DataEngineeringTools.catalog_sources,
        ToolPermission("read_only"),
    ))
    registry.register(RegisteredTool(
        "analyze_transactions",
        "Analyze a transaction-domain profile.",
        DomainAnalysisTools.analyze_transaction_profile,
        ToolPermission("read_only"),
    ))
    registry.register(RegisteredTool(
        "analyze_finance",
        "Analyze a revenue, profit, and expenses profile.",
        DomainAnalysisTools.analyze_finance_profile,
        ToolPermission("read_only"),
    ))
    registry.register(RegisteredTool(
        "analyze_portfolio",
        "Analyze a portfolio exposure profile.",
        DomainAnalysisTools.analyze_portfolio_profile,
        ToolPermission("read_only"),
    ))
    registry.register(RegisteredTool(
        "query_data",
        "Execute a validated, bounded, read-only analysis plan.",
        GenericQueryTools.execute_plan,
        ToolPermission("read_only"),
    ))
    return registry


def _load_dataset_for_agent(source: str | list[str]) -> dict[str, Any]:
    """Return source metadata and a preview without retaining every record."""
    return DataEngineeringTools.load_data_source(source, include_records=False)
