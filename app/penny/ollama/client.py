"""Ollama API client for LLM inference."""

import logging

import ollama

logger = logging.getLogger(__name__)


class OllamaClient:
    """Client for interacting with Ollama API using the official SDK."""

    def __init__(self, api_url: str, model: str):
        """
        Initialize Ollama client.

        Args:
            api_url: Base URL for Ollama API (e.g., http://localhost:11434)
            model: Model name to use (e.g., llama3.2)
        """
        self.api_url = api_url.rstrip("/")
        self.model = model

        # Initialize the official Ollama client
        self.client = ollama.AsyncClient(host=api_url)

        logger.info("Initialized Ollama client: url=%s, model=%s", api_url, model)

    async def chat(
        self,
        messages: list[dict[str, str]],
        tools: list[dict] | None = None,
    ) -> dict:
        """
        Generate a chat completion with optional tool calling.

        Args:
            messages: List of message dicts with 'role' and 'content'
            tools: Optional list of tool definitions in Ollama format

        Returns:
            Response dict with 'message' containing the assistant's response
        """
        try:
            logger.debug("Sending chat request to Ollama")
            logger.debug("Messages: %s", messages)
            if tools:
                logger.debug("Tools: %d available", len(tools))

            response = await self.client.chat(
                model=self.model,
                messages=messages,
                tools=tools,
            )

            # Convert response to dict if it's not already
            if hasattr(response, 'model_dump'):
                response_dict = response.model_dump()
            elif hasattr(response, '__dict__'):
                response_dict = dict(response)
            else:
                response_dict = dict(response)

            logger.debug("Raw Ollama response type: %s", type(response))
            logger.debug("Response keys: %s", list(response_dict.keys()) if isinstance(response_dict, dict) else "not a dict")

            # Extract message from response
            message = response_dict.get("message", {})

            # Log tool calls if present (check for both existence and non-None)
            tool_calls = message.get("tool_calls")
            if tool_calls:
                logger.info("Received %d tool call(s)", len(tool_calls))
                for tc in tool_calls:
                    logger.debug("Tool call: %s", tc)

            # Log thinking if present
            thinking = response_dict.get("thinking")
            if thinking:
                logger.debug("Model thinking: %s", thinking[:200])

            # Check message for thinking too
            message_thinking = message.get("thinking")
            if message_thinking:
                logger.debug("Message thinking: %s", message_thinking[:200])

            return response_dict

        except Exception as e:
            logger.exception("Ollama chat error: %s", e)
            raise

    async def generate(self, prompt: str, tools: list[dict] | None = None) -> dict:
        """
        Generate a completion for a prompt (converts to chat format internally).

        Args:
            prompt: The prompt to generate from
            tools: Optional list of tool definitions

        Returns:
            Response dict with 'message'
        """
        messages = [{"role": "user", "content": prompt}]
        return await self.chat(messages, tools)

    async def close(self) -> None:
        """Close the client (SDK handles cleanup automatically)."""
        logger.info("Ollama client closed")
