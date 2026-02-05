"""Pytest fixtures for Penny tests."""

import asyncio
import contextlib
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from typing import Any, cast

import pytest

from penny.config import Config
from penny.penny import Penny

# Re-export mock fixtures so they can be used directly in tests
from penny.tests.mocks.ollama_patches import mock_ollama  # noqa: F401
from penny.tests.mocks.search_patches import (
    mock_search,  # noqa: F401
    mock_search_with_results,  # noqa: F401
)
from penny.tests.mocks.search_patches import mock_search as _mock_search  # noqa: F401
from penny.tests.mocks.signal_server import MockSignalServer

# Configure pytest-asyncio
pytest_plugins = ("pytest_asyncio",)

# Default config values for tests (background tasks disabled)
DEFAULT_TEST_CONFIG = {
    "channel_type": "signal",
    "signal_number": "+15551234567",
    "discord_bot_token": None,
    "discord_channel_id": None,
    "ollama_api_url": "http://localhost:11434",
    "ollama_foreground_model": "test-model",
    "ollama_background_model": "test-model",
    "perplexity_api_key": "test-api-key",
    "log_level": "DEBUG",
    # Disable background tasks by default
    "summarize_idle_seconds": 99999.0,
    "profile_idle_seconds": 99999.0,
    "followup_idle_seconds": 99999.0,
    "followup_min_seconds": 99999.0,
    "followup_max_seconds": 99999.0,
    "discovery_idle_seconds": 99999.0,
    "discovery_min_seconds": 99999.0,
    "discovery_max_seconds": 99999.0,
    # Fast retries for tests
    "ollama_max_retries": 1,
    "ollama_retry_delay": 0.1,
}


@pytest.fixture
async def signal_server():
    """Start a mock Signal server and yield it."""
    server = MockSignalServer()
    await server.start()
    yield server
    await server.stop()


@pytest.fixture
def test_db(tmp_path):
    """Create a temporary test database path."""
    return str(tmp_path / "test.db")


@pytest.fixture
def make_config(signal_server, test_db) -> Callable[..., Config]:
    """
    Factory fixture for creating test configs with custom overrides.

    Usage:
        config = make_config()  # defaults
        config = make_config(summarize_idle_seconds=0.5)  # with override
    """

    def _make_config(**overrides: Any) -> Config:
        config_kwargs: dict[str, Any] = {
            **DEFAULT_TEST_CONFIG,
            "signal_api_url": f"http://localhost:{signal_server.port}",
            "db_path": test_db,
            **overrides,
        }
        return Config(**cast(Any, config_kwargs))

    return _make_config


@pytest.fixture
def test_config(make_config) -> Config:
    """
    Create a test Config pointing to mock servers.

    Background schedules are disabled by setting high idle times.
    For custom configs, use make_config fixture instead.
    """
    return make_config()


@pytest.fixture
def running_penny() -> Callable[[Config], AbstractAsyncContextManager[Penny]]:
    """
    Async context manager fixture for running Penny with proper cleanup.

    Usage:
        async with running_penny(config) as penny:
            # penny is running and ready
            await signal_server.push_message(...)
    """

    @asynccontextmanager
    async def _running_penny(config: Config) -> AsyncIterator[Penny]:
        penny = Penny(config)
        penny_task = asyncio.create_task(penny.run())
        try:
            # Wait for WebSocket connection to establish
            await asyncio.sleep(0.3)
            yield penny
        finally:
            penny_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await penny_task
            await penny.shutdown()

    return _running_penny
