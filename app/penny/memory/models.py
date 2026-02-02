"""SQLModel models for Penny's memory."""

import json
from datetime import datetime
from typing import Optional

from sqlmodel import Field, SQLModel


class PromptLog(SQLModel, table=True):
    """Log of every prompt sent to Ollama and its response."""

    id: Optional[int] = Field(default=None, primary_key=True)
    timestamp: datetime = Field(default_factory=datetime.utcnow, index=True)
    model: str
    messages: str  # JSON-serialized list of message dicts
    tools: Optional[str] = None  # JSON-serialized tool definitions
    response: str  # JSON-serialized response dict
    thinking: Optional[str] = None  # Model's thinking/reasoning trace
    duration_ms: Optional[int] = None  # How long the call took

    def get_messages(self) -> list[dict]:
        return json.loads(self.messages)

    def get_response(self) -> dict:
        return json.loads(self.response)


class SearchLog(SQLModel, table=True):
    """Log of every Perplexity search call and its response."""

    id: Optional[int] = Field(default=None, primary_key=True)
    timestamp: datetime = Field(default_factory=datetime.utcnow, index=True)
    query: str = Field(index=True)
    response: str
    duration_ms: Optional[int] = None


class MessageLog(SQLModel, table=True):
    """Log of every user message and agent response."""

    id: Optional[int] = Field(default=None, primary_key=True)
    timestamp: datetime = Field(default_factory=datetime.utcnow, index=True)
    direction: str = Field(index=True)  # "incoming" or "outgoing"
    sender: str = Field(index=True)
    content: str
    parent_id: Optional[int] = Field(default=None, foreign_key="messagelog.id", index=True)
