"""High-level Agent abstraction with agentic loop."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from penny.agent.models import ChatMessage, ControllerResponse, MessageRole
from penny.constants import CONTINUE_PROMPT, MessageDirection
from penny.database import Database
from penny.ollama import OllamaClient
from penny.tools import Tool, ToolCall, ToolExecutor, ToolRegistry
from penny.tools.models import SearchResult

if TYPE_CHECKING:
    from penny.database.models import MessageLog

logger = logging.getLogger(__name__)


class Agent:
    """
    AI agent with a specific persona and capabilities.

    Each Agent instance owns its own OllamaClient (for model isolation)
    and can have optional tools for agentic behavior.
    """

    _instances: list[Agent] = []

    def __init__(
        self,
        system_prompt: str,
        model: str,
        ollama_api_url: str,
        tools: list[Tool],
        db: Database,
        max_steps: int = 5,
        max_retries: int = 3,
        retry_delay: float = 0.5,
    ):
        self.system_prompt = system_prompt
        self.model = model
        self.tools = tools
        self.db = db
        self.max_steps = max_steps

        self._ollama_client = OllamaClient(
            api_url=ollama_api_url,
            model=model,
            db=db,
            max_retries=max_retries,
            retry_delay=retry_delay,
        )

        self._tool_registry = ToolRegistry()
        for tool in self.tools:
            self._tool_registry.register(tool)

        self._tool_executor = ToolExecutor(self._tool_registry)

        Agent._instances.append(self)

        logger.info(
            "Initialized agent: model=%s, tools=%d, max_steps=%d",
            model,
            len(self.tools),
            max_steps,
        )

    def _build_messages(
        self,
        prompt: str,
        history: list[tuple[str, str]] | None = None,
    ) -> list[dict]:
        """Build message list for Ollama chat API."""
        messages = []

        now = datetime.now(UTC).strftime("%A, %B %d, %Y at %I:%M %p UTC")
        system_content = f"Current date and time: {now}\n\n{self.system_prompt}"
        messages.append(ChatMessage(role=MessageRole.SYSTEM, content=system_content).to_dict())

        if history:
            for role, content in history:
                messages.append(ChatMessage(role=MessageRole(role), content=content).to_dict())

        messages.append(ChatMessage(role=MessageRole.USER, content=prompt).to_dict())

        return messages

    async def run(
        self,
        prompt: str,
        history: list[tuple[str, str]] | None = None,
    ) -> ControllerResponse:
        """
        Run the agent with a prompt.

        Args:
            prompt: The user message/prompt to respond to
            history: Optional conversation history as (role, content) tuples

        Returns:
            ControllerResponse with answer, thinking, and attachments
        """
        messages = self._build_messages(prompt, history)
        tools = self._tool_registry.get_ollama_tools()
        logger.debug("Using %d tools", len(tools))

        attachments: list[str] = []
        source_urls: list[str] = []
        called_tools: set[str] = set()

        for step in range(self.max_steps):
            logger.info("Agent step %d/%d", step + 1, self.max_steps)

            try:
                response = await self._ollama_client.chat(messages=messages, tools=tools)
            except Exception as e:
                logger.error("Error calling Ollama: %s", e)
                return ControllerResponse(
                    answer="Sorry, I encountered an error communicating with the model."
                )

            if response.has_tool_calls:
                logger.info(
                    "Model requested %d tool call(s)", len(response.message.tool_calls or [])
                )

                messages.append(response.message.to_input_message())

                for ollama_tool_call in response.message.tool_calls or []:
                    tool_name = ollama_tool_call.function.name
                    arguments = ollama_tool_call.function.arguments

                    if tool_name in called_tools:
                        logger.info("Skipping repeat call to tool: %s", tool_name)
                        result_str = (
                            "Tool already called. DO NOT search again. Write your response NOW."
                        )
                        messages.append(
                            ChatMessage(role=MessageRole.TOOL, content=result_str).to_dict()
                        )
                        continue

                    logger.info("Executing tool: %s", tool_name)
                    called_tools.add(tool_name)

                    tool_call = ToolCall(tool=tool_name, arguments=arguments)
                    tool_result = await self._tool_executor.execute(tool_call)

                    if tool_result.error:
                        result_str = f"Error: {tool_result.error}"
                    elif isinstance(tool_result.result, SearchResult):
                        result_str = tool_result.result.text
                        if tool_result.result.urls:
                            source_urls.extend(tool_result.result.urls)
                            result_str += f"\n\nSources:\n{'\n'.join(tool_result.result.urls)}"
                        if tool_result.result.image_base64:
                            attachments.append(tool_result.result.image_base64)
                        result_str += (
                            "\n\nDO NOT search again. Write your response NOW using these results."
                        )
                    else:
                        result_str = str(tool_result.result)
                    logger.debug("Tool result: %s", result_str[:200])

                    messages.append(
                        ChatMessage(role=MessageRole.TOOL, content=result_str).to_dict()
                    )

                continue

            # No tool calls - final answer
            content = response.content.strip()

            if not content:
                logger.error("Model returned empty content!")
                return ControllerResponse(answer="Sorry, the model generated an empty response.")

            thinking = response.thinking or response.message.thinking

            if thinking:
                logger.info("Extracted thinking text (length: %d)", len(thinking))

            if source_urls and "http" not in content:
                content += "\n\n" + source_urls[0]

            logger.info("Got final answer (length: %d)", len(content))
            return ControllerResponse(answer=content, thinking=thinking, attachments=attachments)

        logger.warning("Max steps reached without final answer")
        return ControllerResponse(
            answer="Sorry, I couldn't complete that request within the allowed steps."
        )

    async def close(self) -> None:
        """Clean up this agent's resources."""
        await self._ollama_client.close()
        if self in Agent._instances:
            Agent._instances.remove(self)

    @classmethod
    async def close_all(cls) -> None:
        """Close all agent instances."""
        for agent in cls._instances[:]:
            await agent.close()


class MessageAgent(Agent):
    """Agent for handling incoming user messages."""

    async def handle(
        self,
        content: str,
        quoted_text: str | None = None,
    ) -> tuple[int | None, ControllerResponse]:
        """
        Handle an incoming message, preparing context and running the agent.

        Args:
            content: The message content from the user
            quoted_text: Optional quoted text if this is a reply

        Returns:
            Tuple of (parent_id, response) where parent_id links to the quoted message
        """
        parent_id = None
        history = None
        if quoted_text:
            parent_id, history = self.db.get_thread_context(quoted_text)
        response = await self.run(prompt=content, history=history)
        return parent_id, response


class SummarizeAgent(Agent):
    """Agent for summarizing conversation threads."""

    async def summarize(self, message_id: int) -> str | None:
        """
        Summarize a thread, returning the summary text.

        Args:
            message_id: ID of the message whose thread to summarize

        Returns:
            Summary text, empty string if thread too short, None on error
        """
        thread = self.db._walk_thread(message_id)
        if len(thread) < 2:
            return ""  # Mark as processed but no real summary needed
        thread_text = self._format_thread(thread)
        response = await self.run(prompt=thread_text)
        return response.answer.strip() if response.answer else None

    def _format_thread(self, thread: list[MessageLog]) -> str:
        """Format thread as 'role: content' lines for summarization."""
        return "\n".join(
            "{}: {}".format(
                MessageRole.USER.value
                if m.direction == MessageDirection.INCOMING
                else MessageRole.ASSISTANT.value,
                m.content,
            )
            for m in thread
        )


class ContinueAgent(Agent):
    """Agent for spontaneously continuing conversations."""

    async def continue_conversation(
        self,
        leaf_id: int,
    ) -> tuple[str | None, ControllerResponse | None]:
        """
        Continue a conversation from a leaf message.

        Args:
            leaf_id: ID of the leaf message to continue from

        Returns:
            Tuple of (recipient, response) or (None, None) if cannot continue
        """
        thread = self.db._walk_thread(leaf_id)
        recipient = self._find_recipient(thread)
        if not recipient:
            return None, None
        history = self._format_history(thread)
        response = await self.run(prompt=CONTINUE_PROMPT, history=history)
        return recipient, response

    def _find_recipient(self, thread: list[MessageLog]) -> str | None:
        """Find the user's sender ID from the thread."""
        for msg in thread:
            if msg.direction == MessageDirection.INCOMING:
                return msg.sender
        return None

    def _format_history(self, thread: list[MessageLog]) -> list[tuple[str, str]]:
        """Format thread as (role, content) tuples for history."""
        return [
            (
                MessageRole.USER.value
                if m.direction == MessageDirection.INCOMING
                else MessageRole.ASSISTANT.value,
                m.content,
            )
            for m in thread
        ]
