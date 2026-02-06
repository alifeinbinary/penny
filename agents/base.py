"""Base agent class for Penny's autonomous agent system.

Each agent wraps Claude CLI, running with a specific prompt on a schedule.
The orchestrator manages agent lifecycles and scheduling.
"""

from __future__ import annotations

import json
import logging
import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

CLAUDE_CLI = Path.home() / ".local" / "bin" / "claude"
PROJECT_ROOT = Path(__file__).parent.parent

logger = logging.getLogger(__name__)


@dataclass
class AgentRun:
    agent_name: str
    success: bool
    output: str
    duration: float
    timestamp: datetime


class Agent:
    def __init__(
        self,
        name: str,
        prompt_path: Path,
        interval_seconds: int = 3600,
        working_dir: Path = PROJECT_ROOT,
        timeout_seconds: int = 600,
        model: str | None = None,
        allowed_tools: list[str] | None = None,
    ):
        self.name = name
        self.prompt_path = prompt_path
        self.interval_seconds = interval_seconds
        self.working_dir = working_dir
        self.timeout_seconds = timeout_seconds
        self.model = model
        self.allowed_tools = allowed_tools
        self.last_run: datetime | None = None
        self.run_count = 0

    def is_due(self) -> bool:
        if self.last_run is None:
            return True
        elapsed = (datetime.now() - self.last_run).total_seconds()
        return elapsed >= self.interval_seconds

    def _build_command(self, prompt: str) -> list[str]:
        cmd = [
            str(CLAUDE_CLI),
            "-p",
            prompt,
            "--dangerously-skip-permissions",
            "--verbose",
            "--output-format", "stream-json",
        ]
        if self.model:
            cmd.extend(["--model", self.model])
        if self.allowed_tools:
            cmd.extend(["--allowedTools", *self.allowed_tools])
        return cmd

    def run(self) -> AgentRun:
        logger.info(f"[{self.name}] Starting cycle #{self.run_count + 1}")
        start = datetime.now()

        prompt = self.prompt_path.read_text()
        cmd = self._build_command(prompt)

        try:
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                cwd=str(self.working_dir),
            )

            result_text = ""
            assert process.stdout is not None
            for line in process.stdout:
                line = line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                    self._log_event(event)
                    if event.get("type") == "result":
                        result_text = event.get("result", "")
                except json.JSONDecodeError:
                    logger.info(f"[{self.name}] {line}")

            process.wait(timeout=self.timeout_seconds)

            duration = (datetime.now() - start).total_seconds()
            self.last_run = datetime.now()
            self.run_count += 1

            success = process.returncode == 0
            level = logging.INFO if success else logging.ERROR
            logger.log(level, f"[{self.name}] Cycle #{self.run_count} {'OK' if success else 'FAILED'} in {duration:.1f}s")

            return AgentRun(
                agent_name=self.name,
                success=success,
                output=result_text,
                duration=duration,
                timestamp=start,
            )

        except subprocess.TimeoutExpired:
            process.kill()
            duration = (datetime.now() - start).total_seconds()
            self.last_run = datetime.now()
            self.run_count += 1
            logger.error(f"[{self.name}] Timed out after {duration:.1f}s")
            return AgentRun(
                agent_name=self.name,
                success=False,
                output="Process timed out",
                duration=duration,
                timestamp=start,
            )

    def _log_event(self, event: dict) -> None:
        """Log a stream-json event in a human-readable way."""
        event_type = event.get("type", "")

        if event_type == "assistant":
            # Assistant text output
            for block in event.get("message", {}).get("content", []):
                if block.get("type") == "text":
                    for text_line in block["text"].split("\n"):
                        logger.info(f"[{self.name}] {text_line}")
                elif block.get("type") == "tool_use":
                    tool_name = block.get("name", "?")
                    logger.info(f"[{self.name}] [tool] {tool_name}")

        elif event_type == "result":
            for text_line in event.get("result", "").split("\n"):
                logger.info(f"[{self.name}] {text_line}")
