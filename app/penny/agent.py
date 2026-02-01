"""Main agent loop for Penny - Simple Signal echo test."""

import asyncio
import json
import logging
import signal
import sys
from typing import Any

import httpx
import websockets

from penny.config import Config, setup_logging

logger = logging.getLogger(__name__)


class PennyAgent:
    """Simple agent that echoes Signal messages."""

    def __init__(self, config: Config):
        """Initialize the agent with configuration."""
        self.config = config
        self.http_client = httpx.AsyncClient(timeout=30.0)
        self.running = True

        # Setup signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

    def _signal_handler(self, signum: int, frame: Any) -> None:
        """Handle shutdown signals."""
        logger.info("Received shutdown signal, stopping agent...")
        self.running = False

    async def send_signal_message(self, recipient: str, message: str) -> bool:
        """
        Send a message via Signal.

        Args:
            recipient: Phone number to send to
            message: Message content

        Returns:
            True if successful, False otherwise
        """
        try:
            url = f"{self.config.signal_api_url}/v2/send"
            payload = {
                "message": message,
                "number": self.config.signal_number,
                "recipients": [recipient],
            }

            logger.debug("Sending to %s: %s", url, payload)

            response = await self.http_client.post(url, json=payload)
            response.raise_for_status()

            logger.info("Sent message to %s (length: %d), status: %d", recipient, len(message), response.status_code)
            logger.debug("Response: %s", response.text)
            return True

        except httpx.HTTPError as e:
            logger.error("Failed to send Signal message: %s", e)
            if hasattr(e, 'response') and e.response is not None:
                logger.error("Response status: %d, body: %s", e.response.status_code, e.response.text)
            return False

    async def handle_message(self, envelope: dict) -> None:
        """
        Process an incoming Signal message.

        Args:
            envelope: Signal message envelope from WebSocket
        """
        try:
            logger.debug("Processing envelope: %s", envelope)

            # Extract the inner envelope
            inner_envelope = envelope.get("envelope", {})

            # Extract message data
            data_message = inner_envelope.get("dataMessage", {})
            sender = inner_envelope.get("source", "unknown")
            content = data_message.get("message", "").strip()

            logger.info("Extracted - sender: %s, content: '%s'", sender, content)

            if not content:
                logger.debug("Ignoring empty message from %s", sender)
                return

            logger.info("Received message from %s: %s", sender, content)

            # Echo the message back
            echo_response = f"Echo: {content}"
            logger.info("Sending echo response to %s: %s", sender, echo_response)

            success = await self.send_signal_message(sender, echo_response)

            if success:
                logger.info("Successfully sent echo response")
            else:
                logger.error("Failed to send echo response")

        except Exception as e:
            logger.exception("Error handling message: %s", e)

    async def listen_for_messages(self) -> None:
        """Listen for incoming Signal messages via WebSocket."""
        ws_url = f"ws://{self.config.signal_api_url.replace('http://', '')}/v1/receive/{self.config.signal_number}"

        while self.running:
            try:
                logger.info("Connecting to Signal WebSocket: %s", ws_url)

                async with websockets.connect(ws_url) as websocket:
                    logger.info("Connected to Signal WebSocket")

                    while self.running:
                        try:
                            # Receive message with timeout
                            message = await asyncio.wait_for(
                                websocket.recv(),
                                timeout=30.0,
                            )

                            logger.debug("Received raw WebSocket message: %s", message[:200])

                            # Parse JSON envelope
                            envelope = json.loads(message)
                            logger.info("Parsed envelope with keys: %s", envelope.keys())

                            # Handle message in background
                            asyncio.create_task(self.handle_message(envelope))

                        except asyncio.TimeoutError:
                            # Timeout is expected - just continue listening
                            logger.debug("WebSocket receive timeout, continuing...")
                            continue

                        except json.JSONDecodeError as e:
                            logger.warning("Failed to parse message JSON: %s", e)
                            logger.debug("Raw message: %s", message)
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
        logger.info("Starting Penny echo agent...")
        logger.info("Signal number: %s", self.config.signal_number)

        try:
            await self.listen_for_messages()
        finally:
            await self.shutdown()

    async def shutdown(self) -> None:
        """Clean shutdown of resources."""
        logger.info("Shutting down agent...")
        await self.http_client.aclose()
        logger.info("Agent shutdown complete")


async def main() -> None:
    """Main entry point."""
    # Load configuration
    config = Config.load()
    setup_logging(config.log_level)

    # Create and run agent
    agent = PennyAgent(config)
    await agent.run()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Agent stopped by user")
        sys.exit(0)
