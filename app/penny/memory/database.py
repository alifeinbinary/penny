"""Database connection and session management."""

import json
import logging
from pathlib import Path

from sqlmodel import Session, SQLModel, create_engine

from penny.memory.models import MessageLog, PromptLog, SearchLog

logger = logging.getLogger(__name__)


class Database:
    """Database manager for Penny's memory."""

    def __init__(self, db_path: str):
        """
        Initialize database connection.

        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = db_path

        # Ensure directory exists
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)

        # Create engine
        self.engine = create_engine(f"sqlite:///{db_path}")

        logger.info("Database initialized: %s", db_path)

    def create_tables(self) -> None:
        """Create all tables if they don't exist."""
        SQLModel.metadata.create_all(self.engine)
        logger.info("Database tables created")

    def get_session(self) -> Session:
        """Get a database session."""
        return Session(self.engine)

    def log_prompt(
        self,
        model: str,
        messages: list[dict],
        response: dict,
        tools: list[dict] | None = None,
        thinking: str | None = None,
        duration_ms: int | None = None,
    ) -> None:
        """
        Log a prompt/response exchange with Ollama.

        Args:
            model: Model name used
            messages: Messages sent to the model
            response: Response dict from the model
            tools: Optional tool definitions sent
            thinking: Optional model thinking/reasoning trace
            duration_ms: Optional call duration in milliseconds
        """
        try:
            with self.get_session() as session:
                log = PromptLog(
                    model=model,
                    messages=json.dumps(messages),
                    tools=json.dumps(tools) if tools else None,
                    response=json.dumps(response),
                    thinking=thinking,
                    duration_ms=duration_ms,
                )
                session.add(log)
                session.commit()
                logger.debug("Logged prompt exchange (model=%s)", model)
        except Exception as e:
            logger.error("Failed to log prompt: %s", e)

    def log_search(
        self,
        query: str,
        response: str,
        duration_ms: int | None = None,
    ) -> None:
        """
        Log a Perplexity search call.

        Args:
            query: The search query
            response: The search response text
            duration_ms: Optional call duration in milliseconds
        """
        try:
            with self.get_session() as session:
                log = SearchLog(
                    query=query,
                    response=response,
                    duration_ms=duration_ms,
                )
                session.add(log)
                session.commit()
                logger.debug("Logged search query: %s", query[:50])
        except Exception as e:
            logger.error("Failed to log search: %s", e)

    def log_message(
        self,
        direction: str,
        sender: str,
        content: str,
        parent_id: int | None = None,
    ) -> int | None:
        """
        Log a user message or agent response.

        Args:
            direction: "incoming" for user messages, "outgoing" for agent responses
            sender: Who sent the message (phone number or "agent")
            content: The message text
            parent_id: Optional id of the parent message in the thread

        Returns:
            The id of the created message, or None on failure
        """
        try:
            with self.get_session() as session:
                log = MessageLog(
                    direction=direction,
                    sender=sender,
                    content=content,
                    parent_id=parent_id,
                )
                session.add(log)
                session.commit()
                session.refresh(log)
                logger.debug("Logged %s message from %s (id=%d)", direction, sender, log.id)
                return log.id
        except Exception as e:
            logger.error("Failed to log message: %s", e)
            return None

    def find_outgoing_by_content(self, content: str) -> MessageLog | None:
        """
        Find the most recent outgoing message matching the given content.
        Used to look up which agent response a user is quoting.

        Args:
            content: The quoted text to search for

        Returns:
            The matching MessageLog, or None
        """
        with self.get_session() as session:
            return (
                session.query(MessageLog)
                .filter(
                    MessageLog.direction == "outgoing",
                    MessageLog.content == content,
                )
                .order_by(MessageLog.timestamp.desc())
                .first()
            )

    def get_thread_history(self, message_id: int, limit: int = 20) -> list[MessageLog]:
        """
        Walk up the parent chain from a message to build conversation history.
        Returns messages in chronological order (oldest first).

        Args:
            message_id: The message id to start walking from
            limit: Max number of messages to collect

        Returns:
            List of MessageLog entries, oldest first
        """
        history = []
        with self.get_session() as session:
            current_id = message_id
            while current_id is not None and len(history) < limit:
                msg = session.get(MessageLog, current_id)
                if msg is None:
                    break
                history.append(msg)
                current_id = msg.parent_id

        history.reverse()
        return history
