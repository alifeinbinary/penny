"""Discord agent for Penny - Communicates via Discord using discord.py."""

import asyncio
import logging
import os
import signal
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from penny.channels.discord import DiscordChannel
from penny.config import setup_logging
from penny.memory import Database, build_context
from penny.ollama import OllamaClient

logger = logging.getLogger(__name__)


class DiscordConfig:
    """Discord-specific configuration."""

    def __init__(
        self,
        bot_token: str,
        channel_id: str,
        ollama_api_url: str,
        ollama_model: str,
        db_path: str,
        log_level: str,
    ):
        self.bot_token = bot_token
        self.channel_id = channel_id
        self.ollama_api_url = ollama_api_url
        self.ollama_model = ollama_model
        self.db_path = db_path
        self.log_level = log_level

    @classmethod
    def load(cls) -> "DiscordConfig":
        """Load Discord configuration from .env file."""
        env_paths = [
            Path.cwd() / ".env",
            Path("/app/.env"),
        ]

        for env_path in env_paths:
            if env_path.exists():
                load_dotenv(env_path)
                break

        bot_token = os.getenv("DISCORD_BOT_TOKEN")
        if not bot_token or bot_token == "your-bot-token-here":
            raise ValueError(
                "DISCORD_BOT_TOKEN environment variable is required. "
                "Get your bot token from https://discord.com/developers/applications"
            )

        channel_id = os.getenv("DISCORD_CHANNEL_ID")
        if not channel_id:
            raise ValueError("DISCORD_CHANNEL_ID environment variable is required")

        ollama_api_url = os.getenv("OLLAMA_API_URL", "http://host.docker.internal:11434")
        ollama_model = os.getenv("OLLAMA_MODEL", "llama3.2")
        log_level = os.getenv("LOG_LEVEL", "INFO")
        db_path = os.getenv("DB_PATH", "/app/data/penny.db")

        return cls(
            bot_token=bot_token,
            channel_id=channel_id,
            ollama_api_url=ollama_api_url,
            ollama_model=ollama_model,
            db_path=db_path,
            log_level=log_level,
        )


class DiscordAgent:
    """AI agent that responds via Discord and Ollama."""

    def __init__(self, config: DiscordConfig):
        """Initialize the Discord agent."""
        self.config = config
        self.ollama_client = OllamaClient(config.ollama_api_url, config.ollama_model)

        # Initialize database
        self.db = Database(config.db_path)
        self.db.create_tables()

        # Create Discord channel with message callback
        self.channel = DiscordChannel(
            token=config.bot_token,
            channel_id=config.channel_id,
            on_message_callback=self.handle_message,
        )

        self.running = True

        # Setup signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

    def _signal_handler(self, signum: int, frame: Any) -> None:
        """Handle shutdown signals."""
        logger.info("Received shutdown signal, stopping agent...")
        self.running = False

    async def _stream_and_send_response(self, sender: str, context: str) -> None:
        """
        Stream response from Ollama and send chunks to Discord.

        Args:
            sender: Username/ID of the sender (for logging)
            context: Conversation context to send to Ollama
        """
        logger.info("Generating streaming response with Ollama...")
        logger.debug("Context length: %d chars", len(context))
        chunk_count = 0

        try:
            async for chunk in self.ollama_client.stream_response(context):
                # Turn off typing indicator before sending
                await self.channel.send_typing(self.config.channel_id, False)

                logger.debug("Sending chunk %d: %s...", chunk_count, chunk.line[:50])
                await self.channel.send_message(self.config.channel_id, chunk.line)

                # Log to database
                self.db.log_message(
                    "outgoing",
                    "penny",
                    sender,
                    chunk.line,
                    chunk_count,
                    thinking=chunk.thinking,
                )
                chunk_count += 1

                # Turn typing indicator back on for next chunk
                await self.channel.send_typing(self.config.channel_id, True)

            logger.info("Sent %d chunks to Discord", chunk_count)

        except Exception as e:
            logger.error("Error during streaming generation: %s", e)
            error_msg = "Sorry, I encountered an error generating a response."
            await self.channel.send_message(self.config.channel_id, error_msg)
            self.db.log_message("outgoing", "penny", sender, error_msg)

    async def handle_message(self, envelope_data: dict) -> None:
        """
        Process an incoming message from Discord.

        Args:
            envelope_data: Raw message data from Discord event
        """
        try:
            # Extract message content from channel data
            message = self.channel.extract_message(envelope_data)
            if message is None:
                return

            logger.info("Received message from %s: %s", message.sender, message.content)

            # Log incoming message
            self.db.log_message("incoming", message.sender, "penny", message.content)

            # Send typing indicator
            await self.channel.send_typing(self.config.channel_id, True)

            try:
                # Build context from conversation history
                history = self.db.get_conversation_history(message.sender, "penny", limit=20)
                context = build_context(history, message.content)

                # Stream and send response
                await self._stream_and_send_response(message.sender, context)
            finally:
                # Always stop typing indicator
                await self.channel.send_typing(self.config.channel_id, False)

        except Exception as e:
            logger.exception("Error handling message: %s", e)

    async def run(self) -> None:
        """Run the Discord agent."""
        logger.info("Starting Penny Discord agent...")
        logger.info("Discord channel ID: %s", self.config.channel_id)
        logger.info("Ollama model: %s", self.config.ollama_model)

        try:
            # Start the Discord client
            await self.channel.start()

            # Keep running until shutdown signal
            while self.running:
                await asyncio.sleep(1)

        finally:
            await self.shutdown()

    async def shutdown(self) -> None:
        """Clean shutdown of resources."""
        logger.info("Shutting down Discord agent...")
        await self.channel.close()
        await self.ollama_client.close()
        logger.info("Discord agent shutdown complete")


async def main() -> None:
    """Main entry point for Discord agent."""
    # Load configuration
    config = DiscordConfig.load()
    setup_logging(config.log_level)

    # Create and run agent
    agent = DiscordAgent(config)
    await agent.run()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Discord agent stopped by user")
