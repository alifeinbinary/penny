"""Base agent class for Penny's autonomous agent system.

Each agent wraps Claude CLI, running with a specific prompt on a schedule.
The orchestrator manages agent lifecycles and scheduling.
"""

from __future__ import annotations

import logging
import subprocess
import time
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
                cwd=str(self.working_dir),
            )

            output_lines = []
            assert process.stdout is not None
            for line in process.stdout:
                line = line.rstrip("\n")
                logger.info(f"[{self.name}] {line}")
                output_lines.append(line)

            process.wait(timeout=self.timeout_seconds)

            duration = (datetime.now() - start).total_seconds()
            self.last_run = datetime.now()
            self.run_count += 1

            success = process.returncode == 0
            output = "\n".join(output_lines)

            level = logging.INFO if success else logging.ERROR
            logger.log(level, f"[{self.name}] Cycle #{self.run_count} {'OK' if success else 'FAILED'} in {duration:.1f}s")

            return AgentRun(
                agent_name=self.name,
                success=success,
                output=output,
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
