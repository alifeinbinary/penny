"""Database connection and session management."""

import logging
from datetime import datetime
from pathlib import Path

from sqlmodel import Session, SQLModel, create_engine

from penny.constants import DatabaseConstants
from penny.memory.models import Memory, Message, Task, TaskStatus

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

    def get_conversation_history(self, sender: str, recipient: str, limit: int = 20) -> list:
        """
        Get recent conversation history between sender and recipient.
        Groups chunked messages into single conversation turns.

        Args:
            sender: Phone number of sender
            recipient: Phone number of recipient
            limit: Maximum number of conversation turns to retrieve

        Returns:
            List of Message objects (with chunks stitched together), ordered by timestamp (oldest first)
        """
        with self.get_session() as session:
            # Get more messages than limit to ensure we have enough after grouping
            # Fetch limit * multiplier to account for multi-chunk messages
            messages = session.query(Message).filter(
                ((Message.sender == sender) & (Message.recipient == recipient))
                | ((Message.sender == recipient) & (Message.recipient == sender))
            ).order_by(Message.timestamp.desc()).limit(limit * DatabaseConstants.MESSAGE_FETCH_MULTIPLIER).all()

            # Reverse to get chronological order (oldest first)
            messages = list(reversed(messages))

            # Group messages by conversation turn (same direction, sequential chunks)
            turns = []
            current_turn = None

            for msg in messages:
                # Check if this is part of current turn (same direction, chunk_index continues)
                if current_turn and msg.direction == current_turn.direction:
                    # Check if this is next chunk in sequence
                    if msg.chunk_index is not None and current_turn.chunk_index is not None:
                        if msg.chunk_index == current_turn.chunk_index + 1:
                            # Stitch content together with newline
                            current_turn.content += "\n" + msg.content
                            current_turn.chunk_index = msg.chunk_index
                            continue

                # Start new turn
                if current_turn:
                    turns.append(current_turn)

                # Create a copy of the message for the new turn
                current_turn = Message(
                    direction=msg.direction,
                    sender=msg.sender,
                    recipient=msg.recipient,
                    content=msg.content,
                    chunk_index=msg.chunk_index,
                    thinking=msg.thinking,
                    timestamp=msg.timestamp,
                )

            # Don't forget the last turn
            if current_turn:
                turns.append(current_turn)

            # Return last N turns
            return turns[-limit:] if len(turns) > limit else turns

    def log_message(
        self,
        direction: str,
        sender: str,
        recipient: str,
        content: str,
        chunk_index: int | None = None,
        thinking: str | None = None,
    ) -> None:
        """
        Log a message to the database.

        Args:
            direction: "incoming" or "outgoing"
            sender: Phone number of sender
            recipient: Phone number of recipient
            content: Message content
            chunk_index: Optional chunk index for streaming responses
            thinking: Optional LLM reasoning text for thinking models
        """

        try:
            with self.get_session() as session:
                message = Message(
                    direction=direction,
                    sender=sender,
                    recipient=recipient,
                    content=content,
                    chunk_index=chunk_index,
                    thinking=thinking,
                )
                session.add(message)
                session.commit()
                logger.debug("Logged %s message: %s -> %s", direction, sender, recipient)
        except Exception as e:
            logger.error("Failed to log message: %s", e)

    def store_memory(self, content: str) -> None:
        """
        Store a long-term memory.

        Args:
            content: The memory content to store
        """

        try:
            with self.get_session() as session:
                memory = Memory(content=content)
                session.add(memory)
                session.commit()
                logger.info("Stored memory: %s", content[:50])
        except Exception as e:
            logger.error("Failed to store memory: %s", e)

    def get_all_memories(self) -> list:
        """
        Get all stored memories.

        Returns:
            List of Memory objects, ordered by creation time
        """

        with self.get_session() as session:
            memories = session.query(Memory).order_by(Memory.created_at).all()
            return list(memories)

    def compact_memories(self, summary: str) -> None:
        """
        Replace all memories with a single summary memory.

        Args:
            summary: The compacted memory summary
        """

        with self.get_session() as session:
            # Delete all existing memories
            session.query(Memory).delete()

            # Create new summary memory
            memory = Memory(content=summary)
            session.add(memory)
            session.commit()
            logger.info("Compacted memories into summary (%d chars)", len(summary))

    def create_task(self, content: str, requester: str):
        """
        Create a new pending task.

        Args:
            content: The task description
            requester: Phone number of the requester

        Returns:
            The created Task object
        """

        with self.get_session() as session:
            task = Task(content=content, requester=requester)
            session.add(task)
            session.commit()
            session.refresh(task)
            logger.info("Created task %d: %s", task.id, content[:50])
            return task

    def get_pending_tasks(self) -> list:
        """
        Get all pending tasks ordered by creation time.

        Returns:
            List of Task objects with status="pending"
        """

        with self.get_session() as session:
            tasks = (
                session.query(Task)
                .filter(Task.status == TaskStatus.PENDING.value)
                .order_by(Task.created_at)
                .all()
            )
            return list(tasks)

    def update_task_status(self, task_id: int, status: str, started_at=None) -> None:
        """
        Update task status.

        Args:
            task_id: ID of the task to update
            status: New status (pending/in_progress/completed)
            started_at: Optional datetime when task started
        """


        with self.get_session() as session:
            task = session.get(Task, task_id)
            if task:
                task.status = status
                if started_at:
                    task.started_at = started_at
                session.commit()
                logger.info("Updated task %d status to %s", task_id, status)

    def complete_task(self, task_id: int, result: str) -> None:
        """
        Mark task as completed with result.

        Args:
            task_id: ID of the task to complete
            result: Final result text
        """


        with self.get_session() as session:
            task = session.get(Task, task_id)
            if task:
                task.status = TaskStatus.COMPLETED.value
                task.completed_at = datetime.utcnow()
                task.result = result
                session.commit()
                logger.info("Completed task %d", task_id)
