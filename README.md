# Penny

A simple, local-first AI agent that communicates via Signal and runs entirely on your machine.

**Author:** Jared Lockhart

## Overview

Penny is a personal AI agent built with simplicity and privacy in mind. It runs locally, uses open-source models via Ollama, and communicates through Signal for a secure, familiar interface.

## Architecture

### Components

```
┌─────────────────────────────────────┐
│          HOST ENVIRONMENT            │
│                                      │
│  signal-cli-rest-api (json-rpc)     │
│  ├─ REST: localhost:8080            │
│  │  └─ POST /v2/send                │
│  └─ WebSocket: ws://localhost:8080  │
│     └─ /v1/receive/<number>         │
│                                      │
│  ollama                              │
│  └─ API: localhost:11434            │
│     └─ POST /api/generate            │
│                                      │
│  ./data/agent.db (SQLite)           │
│                                      │
└──────────────┬───────────────────────┘
               │ --network host
        ┌──────▼────────┐
        │  CONTAINER    │
        │               │
        │  Penny Agent  │
        │  (Python)     │
        │               │
        │  - WebSocket  │
        │  - HTTP       │
        │  - Skills     │
        │  - Memory     │
        └───────────────┘
```

### Design Decisions

- **Host Services**: signal-cli-rest-api and Ollama run directly on host (easier debugging, no nested containers)
- **Containerized Agent**: Only the Python agent runs in Docker (simple, portable, reproducible)
- **Networking**: `--network host` for simplicity (all local, no security concerns)
- **Persistence**: SQLite on host filesystem via volume mount (survives container restarts)
- **Communication**: WebSocket for receiving (real-time), REST for sending (simple)

## Python Agent Loop

### Core Loop Design

```python
# High-level pseudocode (MVP - simple relay)

1. Initialize
   - Load configuration from .env file
   - Connect to SQLite (./data/agent.db)
   - Initialize database schema if needed

2. Open WebSocket to signal-cli
   - Connect to ws://localhost:8080/v1/receive/<number>
   - Handle connection errors/reconnection

3. Message Loop
   For each incoming message:

   a. Parse message
      - Extract sender, content, timestamp
      - Identify conversation thread

   b. Store incoming message
      - Save to SQLite (messages table, type='incoming')

   c. Build context
      - Load recent conversation history (last N messages)
      - Format for Ollama prompt

   d. Generate response
      - Send context + message to Ollama
      - Wait for complete response

   e. Send reply
      - POST to signal-cli /v2/send
      - Include original sender as recipient

   f. Store outgoing response
      - Save assistant reply to SQLite (type='outgoing')

4. Error Handling
   - Reconnect WebSocket on disconnect
   - Retry failed sends (with backoff)
   - Log errors to SQLite (type='error') and stdout
```

### Key Modules (MVP)

- **`agent.py`**: Main loop, WebSocket handling, message routing
- **`memory.py`**: SQLite operations, conversation history, context building
- **`llm.py`**: Ollama API client, prompt building, response handling
- **`config.py`**: Configuration management, loads from .env file

## Data Model

### SQLite Schema (MVP)

```sql
-- Messages: complete log of all Signal messages and LLM responses
CREATE TABLE messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id TEXT NOT NULL,   -- Phone number or group ID
    sender TEXT NOT NULL,             -- Phone number (or 'assistant')
    content TEXT NOT NULL,
    timestamp INTEGER NOT NULL,
    message_type TEXT DEFAULT 'text', -- 'incoming', 'outgoing', 'error'
    created_at INTEGER DEFAULT (strftime('%s', 'now'))
);

CREATE INDEX idx_messages_conversation ON messages(conversation_id, timestamp);
CREATE INDEX idx_messages_timestamp ON messages(timestamp DESC);
```

## Setup & Running

### Prerequisites

1. **signal-cli-rest-api** running on host (port 8080)
2. **Ollama** running on host (port 11434)
3. Docker & Docker Compose installed

### Quick Start

```bash
# 1. Create .env file with your configuration
cp .env.example .env
# Edit .env with your settings

# 2. Start the agent
docker-compose up --build
```

### docker-compose.yml

```yaml
services:
  penny:
    build: .
    network_mode: host
    volumes:
      - ./data:/app/data
      - ./.env:/app/.env
    restart: unless-stopped
```

## Configuration

Configuration is managed via a `.env` file in the project root:

```bash
# .env
SIGNAL_NUMBER="+1234567890"
SIGNAL_API_URL="http://localhost:8080"
OLLAMA_API_URL="http://localhost:11434"
OLLAMA_MODEL="llama3"
LOG_LEVEL="INFO"
```

**Configuration Options:**
- `SIGNAL_NUMBER`: Your registered Signal number (required)
- `SIGNAL_API_URL`: signal-cli REST API endpoint (default: http://localhost:8080)
- `OLLAMA_API_URL`: Ollama API endpoint (default: http://localhost:11434)
- `OLLAMA_MODEL`: Model name to use (default: llama3)
- `LOG_LEVEL`: Logging verbosity (default: INFO)

## Development

### Local Development (without Docker)

```bash
# Install uv if you haven't already
curl -LsSf https://astral.sh/uv/install.sh | sh

# Navigate to app directory
cd app

# Install dependencies
uv pip install -e .

# Install dev dependencies
uv pip install ruff ty

# Create .env file (in project root)
cd ..
cp .env.example .env
# Edit .env with your settings

# Run the agent
cd app
python -m penny.agent

# Format code
ruff format .

# Lint code
ruff check .

# Type check
ty
```

### Project Structure

```
penny/                       # Project root
├── docker-compose.yml       # Container orchestration
├── .env.example             # Configuration template
├── README.md                # This file
├── data/                    # SQLite database (git-ignored)
│   └── agent.db
└── app/                     # Application code
    ├── Dockerfile           # Container definition
    ├── pyproject.toml       # Dependencies & tool config (uv, ruff, ty)
    └── penny/               # Python package
        ├── __init__.py
        ├── agent.py         # Main loop & WebSocket handling
        ├── config.py        # Configuration management
        ├── memory.py        # SQLite operations
        └── llm.py           # Ollama client
```

## Development Roadmap

### MVP (v0.1) - Simple Signal ↔ Ollama Relay
- [ ] Core agent loop with WebSocket message handling
- [ ] SQLite message logging (incoming/outgoing)
- [ ] Ollama integration for LLM responses
- [ ] Conversation context (last N messages)
- [ ] Docker containerization
- [ ] Error handling and reconnection logic

### Future Enhancements
- [ ] Skills system architecture
- [ ] Perplexity search skill
- [ ] Internal memory/learning system
- [ ] Multi-user conversation management
- [ ] Response streaming
- [ ] Attachment support

## Inspiration

Based on learnings from openclaw - built to be simpler, cleaner, and more maintainable.

## License

[Your preferred license]
