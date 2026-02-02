"""Built-in tools."""

from datetime import datetime
from typing import Any

from penny.tools.base import Tool


class GetCurrentTimeTool(Tool):
    """Get the current date and time."""

    @property
    def name(self) -> str:
        return "get_current_time"

    @property
    def description(self) -> str:
        return "Get the current date and time in ISO format. Use this when the user asks about the current time or date."

    @property
    def parameters(self) -> dict[str, Any]:
        # No parameters needed
        return {
            "type": "object",
            "properties": {},
        }

    async def execute(self, **kwargs) -> str:
        """Get current time."""
        return datetime.now().isoformat()
