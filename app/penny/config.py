"""Configuration management for Penny."""

import logging
import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


@dataclass
class Config:
    """Application configuration loaded from .env file."""

    signal_number: str
    signal_api_url: str
    log_level: str

    @classmethod
    def load(cls) -> "Config":
        """Load configuration from .env file."""
        # Load .env file from project root or /app/.env in container
        env_paths = [
            Path.cwd() / ".env",
            Path("/app/.env"),
        ]

        for env_path in env_paths:
            if env_path.exists():
                load_dotenv(env_path)
                break

        # Required fields
        signal_number = os.getenv("SIGNAL_NUMBER")
        if not signal_number:
            raise ValueError("SIGNAL_NUMBER environment variable is required")

        # Optional fields with defaults
        signal_api_url = os.getenv("SIGNAL_API_URL", "http://localhost:8080")
        log_level = os.getenv("LOG_LEVEL", "INFO")

        return cls(
            signal_number=signal_number,
            signal_api_url=signal_api_url,
            log_level=log_level,
        )


def setup_logging(log_level: str) -> None:
    """Configure logging for the application."""
    logging.basicConfig(
        level=getattr(logging, log_level.upper()),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
