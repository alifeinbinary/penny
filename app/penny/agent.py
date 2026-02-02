"""Main agent loop for Penny."""

import asyncio
import json
import logging
import signal
import sys
from typing import Any

import websockets

from penny.agentic import AgenticController
from penny.channels import MessageChannel, SignalChannel
from penny.config import Config, setup_logging
from penny.memory import Database
from penny.ollama import OllamaClient
from penny.tools import PerplexitySearchTool, ToolRegistry

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You are Penny, a helpful AI assistant. "
    "You MUST use the perplexity_search tool for every message to research your answer. "
    "Never answer from your own knowledge alone - always search first, then respond "
    "based on the search results. "
    "Only use plain text - no markdown, no bullet points, no formatting. "
    "Only use lowercase. "
    "Speak casually. "
    "End every response with an emoji."
)


class PennyAgent:
    """AI agent powered by Ollama via an agentic controller."""

    def __init__(self, config: Config, channel: MessageChannel | None = None):
        """Initialize the agent with configuration."""
        self.config = config
        self.channel = channel or SignalChannel(config.signal_api_url, config.signal_number)
        self.db = Database(config.db_path)
        self.db.create_tables()
        self.ollama_client = OllamaClient(config.ollama_api_url, config.ollama_model, db=self.db)

        tool_registry = ToolRegistry()
        if config.perplexity_api_key:
            tool_registry.register(PerplexitySearchTool(api_key=config.perplexity_api_key, db=self.db))
            logger.info("Perplexity search tool registered")
        else:
            logger.warning("No PERPLEXITY_API_KEY configured - agent will have no tools")

        self.controller = AgenticController(
            ollama_client=self.ollama_client,
            tool_registry=tool_registry,
            max_steps=config.message_max_steps,
        )

        self.running = True

        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

    def _signal_handler(self, signum: int, frame: Any) -> None:
        """Handle shutdown signals."""
        logger.info("Received shutdown signal, stopping agent...")
        self.running = False

    async def handle_message(self, envelope_data: dict) -> None:
        """Process an incoming message through the agentic controller."""
        try:
            message = self.channel.extract_message(envelope_data)
            if message is None:
                return

            logger.info("Received message from %s: %s", message.sender, message.content)

            # Find parent message if this is a quoted reply
            parent_id = None
            history = None
            if message.quoted_text:
                parent_msg = self.db.find_outgoing_by_content(message.quoted_text)
                if parent_msg:
                    parent_id = parent_msg.id
                    # Walk up the thread to build conversation history
                    thread = self.db.get_thread_history(parent_msg.id)
                    history = [
                        ("user" if m.direction == "incoming" else "assistant", m.content)
                        for m in thread
                    ]
                    logger.info("Built thread history with %d messages", len(history))

            # Log incoming message linked to parent
            incoming_id = self.db.log_message("incoming", message.sender, message.content, parent_id=parent_id)

            await self.channel.send_typing(message.sender, True)
            try:
                response = await self.controller.run(
                    current_message=message.content,
                    system_prompt=SYSTEM_PROMPT,
                    history=history,
                )

                answer = response.answer.strip() if response.answer else "Sorry, I couldn't generate a response."
                self.db.log_message("outgoing", self.config.signal_number, answer, parent_id=incoming_id)
                await self.channel.send_message(message.sender, answer)
            finally:
                await self.channel.send_typing(message.sender, False)

        except Exception as e:
            logger.exception("Error handling message: %s", e)

    async def listen_for_messages(self) -> None:
        """Listen for incoming messages from the channel."""
        connection_url = self.channel.get_connection_url()

        while self.running:
            try:
                logger.info("Connecting to channel: %s", connection_url)

                async with websockets.connect(connection_url) as websocket:
                    logger.info("Connected to Signal WebSocket")

                    while self.running:
                        try:
                            message = await asyncio.wait_for(
                                websocket.recv(),
                                timeout=30.0,
                            )

                            logger.debug("Received raw WebSocket message: %s", message[:200])

                            envelope = json.loads(message)
                            logger.info("Parsed envelope with keys: %s", envelope.keys())

                            asyncio.create_task(self.handle_message(envelope))

                        except asyncio.TimeoutError:
                            logger.debug("WebSocket receive timeout, continuing...")
                            continue

                        except json.JSONDecodeError as e:
                            logger.warning("Failed to parse message JSON: %s", e)
                            continue

            except websockets.exceptions.WebSocketException as e:
                logger.error("WebSocket error: %s", e)
                if self.running:
                    logger.info("Reconnecting in 5 seconds...")
                    await asyncio.sleep(5)

            except Exception as e:
                logger.exception("Unexpected error in message listener: %s", e)
                if self.running:
                    logger.info("Reconnecting in 5 seconds...")
                    await asyncio.sleep(5)

        logger.info("Message listener stopped")

    async def run(self) -> None:
        """Run the agent."""
        logger.info("Starting Penny AI agent...")
        logger.info("Signal number: %s", self.config.signal_number)
        logger.info("Ollama model: %s", self.config.ollama_model)

        try:
            await self.listen_for_messages()
        finally:
            await self.shutdown()

    async def shutdown(self) -> None:
        """Clean shutdown of resources."""
        logger.info("Shutting down agent...")
        await self.channel.close()
        await self.ollama_client.close()
        logger.info("Agent shutdown complete")


async def main() -> None:
    """Main entry point."""
    config = Config.load()
    setup_logging(config.log_level, config.log_file)

    agent = PennyAgent(config)
    await agent.run()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Agent stopped by user")
        sys.exit(0)
