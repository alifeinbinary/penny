"""Parse model outputs to detect tool calls vs final answers."""

import logging

from pydantic import ValidationError

from penny.tools import ToolCall

logger = logging.getLogger(__name__)


class OutputParser:
    """Parses model output to detect tool calls or final answers."""

    @staticmethod
    def parse(output: str) -> ToolCall | str:
        """
        Parse model output.

        Args:
            output: Raw model output

        Returns:
            Either a ToolCall (if valid JSON tool call) or str (final answer)
        """
        output = output.strip()

        logger.debug("Parsing output (length: %d): %s", len(output), output[:200])

        # Try to parse as JSON tool call using Pydantic
        if output.startswith("{") and output.endswith("}"):
            try:
                tool_call = ToolCall.model_validate_json(output)
                logger.info("Parsed tool call: %s with args: %s", tool_call.tool, tool_call.arguments)
                return tool_call

            except ValidationError as e:
                logger.warning("Failed to parse as tool call: %s", e)
                logger.debug("Invalid JSON content: %s", output[:500])
                # Fall through to treat as final answer

        # Otherwise, it's a final answer
        logger.info("Parsed as final answer (length: %d)", len(output))
        return output
