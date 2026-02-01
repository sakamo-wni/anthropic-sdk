"""Base class for tools."""

from abc import ABC, abstractmethod
from typing import Any


class BaseTool(ABC):
    """Abstract base class for all tools."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Tool name used in Claude tool calls."""
        ...

    @property
    @abstractmethod
    def description(self) -> str:
        """Tool description for Claude."""
        ...

    @property
    @abstractmethod
    def input_schema(self) -> dict[str, Any]:
        """JSON schema for tool input parameters."""
        ...

    @abstractmethod
    async def execute(self, **kwargs: Any) -> str:
        """Execute the tool with given parameters."""
        ...

    def to_anthropic_tool(self) -> dict[str, Any]:
        """Convert to Anthropic tool definition format."""
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
        }


class ReadOnlyTool(BaseTool):
    """Base class for read-only tools (no approval required)."""

    requires_approval: bool = False


class ActionTool(BaseTool):
    """Base class for action tools (approval required)."""

    requires_approval: bool = True
