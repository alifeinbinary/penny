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

            logger.debug("Raw Ollama response: %s", response)

            # Extract message from response
            message = response.get("message", {})

            # Log tool calls if present
            if "tool_calls" in message:
                logger.info("Received %d tool call(s)", len(message["tool_calls"]))
                for tc in message["tool_calls"]:
                    logger.debug("Tool call: %s", tc)

            # Log thinking if present
            if "thinking" in response:
                logger.debug("Model thinking: %s", response["thinking"][:200])

            return response

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
