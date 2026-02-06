# Penny Agent Orchestrator

Python-based orchestrator that manages autonomous Claude CLI agents. Each agent runs on a schedule, processing work via GitHub Issues.

## Quick Start

```bash
python agents/orchestrator.py              # Run continuously
python agents/orchestrator.py --once       # Run all due agents once and exit
python agents/orchestrator.py --list       # Show registered agents
```

## How It Works

The orchestrator loops every 30 seconds, checking which agents are due to run. When an agent is due, it:

1. Reads the agent's `CLAUDE.md` prompt
2. Calls `claude -p <prompt> --dangerously-skip-permissions`
3. Captures output to `agents/logs/<agent-name>.log`
4. Records success/failure and duration

Ctrl+C stops the orchestrator cleanly.

## Agents

Each agent is a directory with a single `CLAUDE.md` file (the prompt) and an entry in `orchestrator.py`:

```
agents/
  orchestrator.py          # Main loop
  base.py                  # Agent base class
  logs/                    # Per-agent output logs (gitignored)
  product-manager/
    CLAUDE.md              # PM agent prompt
```

### Product Manager

Monitors GitHub Issues on a 1-hour cycle:
- Expands `idea`-labeled issues into detailed specs
- Responds to feedback on `draft`-labeled issues
- All interaction via GitHub Issue comments and labels

## Adding a New Agent

1. Create a directory: `agents/my-agent/`
2. Write a `CLAUDE.md` prompt defining the agent's behavior
3. Register it in `orchestrator.py`:

```python
def get_agents() -> list[Agent]:
    return [
        Agent(
            name="product-manager",
            prompt_path=AGENTS_DIR / "product-manager" / "CLAUDE.md",
            interval_seconds=3600,
        ),
        Agent(
            name="my-agent",
            prompt_path=AGENTS_DIR / "my-agent" / "CLAUDE.md",
            interval_seconds=1800,  # every 30 minutes
        ),
    ]
```

## Agent Configuration

The `Agent` class accepts:

| Parameter | Default | Description |
|---|---|---|
| `name` | required | Agent identifier, used in logs |
| `prompt_path` | required | Path to CLAUDE.md prompt file |
| `interval_seconds` | 3600 | How often the agent runs |
| `working_dir` | project root | Working directory for Claude CLI |
| `timeout_seconds` | 600 | Max runtime before killing the process |
| `model` | None | Override Claude model (e.g. "opus") |
| `allowed_tools` | None | Restrict which tools Claude can use |

## Logs

- `agents/logs/orchestrator.log` — orchestrator events (start, stop, agent runs)
- `agents/logs/<agent-name>.log` — raw Claude output per agent, appended each cycle

## GitHub Issue Labels

All agents share this label workflow:

- **`backlog`** — Idea captured, not yet selected
- **`idea`** — Selected for PM to expand into a spec
- **`draft`** — Spec written, awaiting review
- **`approved`** — Ready for a worker agent to implement
- **`in-progress`** — Worker agent is coding
- **`review`** — PR open for review
- **`shipped`** — Merged and closed
