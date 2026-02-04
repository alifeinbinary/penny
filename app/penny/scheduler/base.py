"""Base classes for background task scheduling."""

from abc import ABC, abstractmethod
from typing import Protocol, runtime_checkable


class Schedule(ABC):
    """Abstract base class for schedule policies."""

    agent: "ScheduledAgent"  # Set by subclasses

    @abstractmethod
    def should_run(self, idle_seconds: float) -> bool:
        """
        Check if the schedule condition is met.

        Args:
            idle_seconds: How long since the last message was received

        Returns:
            True if the task should run now
        """
        pass

    @abstractmethod
    def reset(self) -> None:
        """Reset schedule state. Called when a new message arrives."""
        pass

    @abstractmethod
    def mark_complete(self) -> None:
        """Called after task execution completes."""
        pass


@runtime_checkable
class ScheduledAgent(Protocol):
    """Protocol for agents that can be scheduled."""

    @property
    def name(self) -> str:
        """Task name for logging."""
        ...

    async def execute(self) -> bool:
        """
        Execute the scheduled task.

        Returns:
            True if work was done, False if no work available
        """
        ...
