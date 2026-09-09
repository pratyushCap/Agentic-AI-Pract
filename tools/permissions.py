from dataclasses import dataclass
from typing import Literal


ToolCategory = Literal["read_only", "simulation", "action"]


@dataclass(frozen=True)
class ToolPermission:
    category: ToolCategory
    requires_approval: bool = False


def ensure_tool_allowed(permission: ToolPermission, approved: bool = False) -> None:
    """Reject sensitive tools unless an explicit approval has been provided."""
    if permission.requires_approval and not approved:
        raise PermissionError("This action requires human approval before execution.")
