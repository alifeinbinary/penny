"""Prompt builder for agentic loops."""

import json

from penny.tools import ToolDefinition


class PromptBuilder:
    """Builds prompts with tool descriptions."""

    @staticmethod
    def build_system_prompt(tools: list[ToolDefinition]) -> str:
        """
        Build system prompt with tool descriptions.

        Args:
            tools: Available tools

        Returns:
            System prompt string
        """
        sections = []

        # Core identity
        sections.append(
            "You are Penny, a helpful AI assistant communicating via messages."
        )

        # Tool calling instructions
        if tools:
            sections.append("\n## Available Tools\n")
            sections.append(
                "You have access to the following tools. "
                "To use a tool, respond with ONLY a JSON object in this exact format:\n"
            )
            sections.append('{"tool": "tool_name", "arguments": {...}}\n')

            sections.append("\nTools:\n")
            for tool in tools:
                sections.append(f"\n### {tool.name}")
                sections.append(f"\n{tool.description}")
                if tool.parameters.get("properties"):
                    sections.append(f"\nParameters: {json.dumps(tool.parameters, indent=2)}")

            sections.append("\n\n## Response Rules\n")
            sections.append(
                "You must choose ONE of these response modes:\n"
                "1. Tool call: Respond with ONLY the JSON tool call, nothing else\n"
                "2. Final answer: Respond with plain text (no JSON)\n\n"
                "Do NOT mix JSON and text in the same response."
            )

        return "".join(sections)

    @staticmethod
    def build_conversation_history(history: list, current_message: str) -> str:
        """
        Build conversation history section.

        Args:
            history: List of Message objects
            current_message: Current user message

        Returns:
            Formatted conversation string
        """
        parts = []

        if history:
            parts.append("Recent conversation:\n")
            for msg in history:
                if msg.direction == "incoming":
                    parts.append(f"User: {msg.content}\n")
                else:
                    # Only show first chunk to avoid duplication
                    if msg.chunk_index is None or msg.chunk_index == 0:
                        parts.append(f"Penny: {msg.content}\n")

        parts.append(f"\nUser: {current_message}\n")
        parts.append("Penny:")

        result = "".join(parts)

        # Ensure we always have valid content
        if not result.strip():
            raise ValueError("Generated empty conversation prompt!")

        return result
