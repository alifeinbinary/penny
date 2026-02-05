"""Integration tests for the basic message flow."""

import asyncio

import pytest
from sqlmodel import select

from penny.database.models import MessageLog


@pytest.mark.asyncio
async def test_basic_message_flow(
    signal_server, mock_ollama, test_config, _mock_search, running_penny
):
    """
    Test the complete message flow:
    1. User sends a message via Signal
    2. Penny receives and processes it
    3. Ollama returns a tool call (search)
    4. Search tool executes (mocked)
    5. Ollama returns final response
    6. Penny sends reply via Signal
    """
    # Configure Ollama to return search tool call, then final response
    mock_ollama.set_default_flow(
        search_query="test search query",
        final_response="here's what i found about your question! 🌟",
    )

    async with running_penny(test_config) as penny:
        # Verify we have a WebSocket connection
        assert len(signal_server._websockets) == 1, "Penny should have connected to WebSocket"

        # Send incoming message
        await signal_server.push_message(
            sender="+15559876543",
            content="what's the weather like today?",
        )

        # Wait for response
        response = await signal_server.wait_for_message(timeout=10.0)

        # Verify the response
        assert response["recipients"] == ["+15559876543"]
        assert "here's what i found" in response["message"].lower()

        # Verify Ollama was called twice (tool call + final response)
        assert len(mock_ollama.requests) == 2, "Expected 2 Ollama calls (tool + final)"

        # First request should have user message
        first_request = mock_ollama.requests[0]
        messages = first_request.get("messages", [])
        user_messages = [m for m in messages if m.get("role") == "user"]
        assert any("weather" in m.get("content", "").lower() for m in user_messages)

        # Second request should include tool result
        second_request = mock_ollama.requests[1]
        messages = second_request.get("messages", [])
        tool_messages = [m for m in messages if m.get("role") == "tool"]
        assert len(tool_messages) >= 1, "Second request should include tool result"

        # Verify typing indicators were sent
        assert len(signal_server.typing_events) >= 1, "Should have sent typing indicator"

        # Verify messages were logged to database
        incoming_messages = penny.db.get_user_messages("+15559876543")
        assert len(incoming_messages) >= 1, "Incoming message should be logged"

        with penny.db.get_session() as session:
            outgoing = list(
                session.exec(select(MessageLog).where(MessageLog.direction == "outgoing")).all()
            )
        assert len(outgoing) >= 1, "Outgoing message should be logged"


@pytest.mark.asyncio
async def test_message_without_tool_call(
    signal_server, mock_ollama, test_config, _mock_search, running_penny
):
    """Test handling a message where Ollama doesn't call a tool."""

    # Configure Ollama to return direct response (no tool call)
    def direct_response(request, count):
        return mock_ollama._make_text_response(request, "just a simple response! 🌟")

    mock_ollama.set_response_handler(direct_response)

    async with running_penny(test_config):
        await signal_server.push_message(
            sender="+15559876543",
            content="hello penny",
        )

        response = await signal_server.wait_for_message(timeout=10.0)

        assert response["recipients"] == ["+15559876543"]
        assert "simple response" in response["message"].lower()

        # Only one Ollama call (no tool)
        assert len(mock_ollama.requests) == 1


@pytest.mark.asyncio
async def test_summarize_background_task(
    signal_server, mock_ollama, _mock_search, make_config, running_penny
):
    """
    Test the summarize background task:
    1. Send a message and get a response (creates a thread)
    2. Wait for idle time to pass
    3. Verify SummarizeAgent generates and stores a summary
    """
    # Create config with short summarize idle time
    config = make_config(summarize_idle_seconds=0.5)

    # Track request count to provide different responses
    request_count = [0]

    def multi_phase_handler(request, count):
        request_count[0] += 1
        if request_count[0] == 1:
            # First call: message agent tool call
            return mock_ollama._make_tool_call_response(
                request, "search", {"query": "weather forecast today"}
            )
        elif request_count[0] == 2:
            # Second call: message agent final response
            return mock_ollama._make_text_response(request, "here's the weather info! 🌤️")
        else:
            # Third call onwards: summarize agent
            return mock_ollama._make_text_response(
                request, "user asked about weather, assistant provided forecast"
            )

    mock_ollama.set_response_handler(multi_phase_handler)

    async with running_penny(config) as penny:
        # Send message to create a thread
        await signal_server.push_message(
            sender="+15559876543",
            content="what's the weather like?",
        )

        # Wait for message response
        response = await signal_server.wait_for_message(timeout=10.0)
        assert "weather" in response["message"].lower()

        # Get the outgoing message id
        with penny.db.get_session() as session:
            outgoing = session.exec(
                select(MessageLog).where(MessageLog.direction == "outgoing")
            ).first()
            assert outgoing is not None
            message_id = outgoing.id
            # Verify it has a parent (thread link) but no summary yet
            assert outgoing.parent_id is not None
            assert outgoing.parent_summary is None

        # Wait for summarize task to trigger (idle time + scheduler tick)
        # Scheduler ticks every 1s, summarize idle is 0.5s
        await asyncio.sleep(2.0)

        # Verify summary was generated
        with penny.db.get_session() as session:
            outgoing = session.get(MessageLog, message_id)
            assert outgoing is not None
            assert outgoing.parent_summary is not None
            assert len(outgoing.parent_summary) > 0
            assert "weather" in outgoing.parent_summary.lower()

        # Verify SummarizeAgent made an Ollama call (should be 3+ total)
        assert len(mock_ollama.requests) >= 3, "Expected at least 3 Ollama calls"
