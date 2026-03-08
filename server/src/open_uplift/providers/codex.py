"""Codex CLI session provider.

Reads rollout JSONL files from ~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl
"""

import json
import re
from collections import Counter
from pathlib import Path
from typing import Iterator

from open_uplift.config import CODEX_HOME
from open_uplift.models import MessageData, SessionData
from open_uplift.providers.base import SessionProvider

CODEX_SESSIONS_DIR = CODEX_HOME / "sessions"

# Rollout filename pattern: rollout-<timestamp>-<uuid>.jsonl
ROLLOUT_FILE_RE = re.compile(
    r"^rollout-[\dT\-]+-([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\.jsonl$"
)


def _extract_session_id(filename: str) -> str | None:
    """Extract the UUID portion from a rollout filename."""
    m = ROLLOUT_FILE_RE.match(filename)
    return m.group(1) if m else None


class CodexProvider(SessionProvider):
    @property
    def tool_name(self) -> str:
        return "codex"

    def discover_session_files(self) -> Iterator[Path]:
        if not CODEX_SESSIONS_DIR.exists():
            return
        # Rollout files are date-sharded: sessions/YYYY/MM/DD/rollout-*.jsonl
        for jsonl_file in CODEX_SESSIONS_DIR.rglob("rollout-*.jsonl"):
            if ROLLOUT_FILE_RE.match(jsonl_file.name):
                yield jsonl_file

    def parse_session(
        self, file_path: Path, from_offset: int = 0
    ) -> tuple[SessionData, list[MessageData], int]:
        session_id = _extract_session_id(file_path.name) or file_path.stem

        messages: list[MessageData] = []
        first_timestamp: str | None = None
        last_timestamp: str | None = None
        cwd: str | None = None
        model_counter: Counter[str] = Counter()
        total_tool_calls = 0

        # Track per-turn token accumulation
        current_turn_items: list[dict] = []

        with open(file_path, "r") as f:
            f.seek(from_offset)
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue

                event_type = event.get("type", "")
                timestamp = event.get("timestamp", "")

                if timestamp:
                    if first_timestamp is None:
                        first_timestamp = timestamp
                    last_timestamp = timestamp

                # thread.started — may carry thread_id
                if event_type == "thread.started":
                    thread_id = event.get("thread_id")
                    if thread_id:
                        session_id = thread_id

                # item.completed — extract messages and tool calls
                elif event_type == "item.completed":
                    item = event.get("item", {})
                    item_type = item.get("type", "")

                    if item_type == "userMessage":
                        messages.append(
                            MessageData(
                                session_id=session_id,
                                timestamp=timestamp,
                                role="user",
                            )
                        )

                    elif item_type == "agentMessage":
                        current_turn_items.append(item)

                    elif item_type in (
                        "commandExecution",
                        "fileChange",
                        "mcpToolCall",
                        "webSearch",
                    ):
                        total_tool_calls += 1
                        # Extract cwd from command executions
                        if item_type == "commandExecution" and cwd is None:
                            cwd = item.get("cwd")
                        current_turn_items.append(item)

                # turn.completed — flush accumulated items as a single assistant message
                elif event_type == "turn.completed":
                    usage = event.get("usage", {})
                    input_tokens = usage.get("input_tokens", 0)
                    cached_input = usage.get("cached_input_tokens", 0)
                    output_tokens = usage.get("output_tokens", 0)

                    # Extract tool names from accumulated items
                    tool_names_list = []
                    for item in current_turn_items:
                        itype = item.get("type", "")
                        if itype == "commandExecution":
                            tool_names_list.append("bash")
                        elif itype == "fileChange":
                            tool_names_list.append("file_change")
                        elif itype == "mcpToolCall":
                            tool_name = item.get("tool", "mcp_tool")
                            tool_names_list.append(tool_name)
                        elif itype == "webSearch":
                            tool_names_list.append("web_search")

                    # Try to get model from the event or items
                    model = event.get("model", "")
                    if model:
                        model_counter[model] += 1

                    messages.append(
                        MessageData(
                            session_id=session_id,
                            timestamp=timestamp,
                            role="assistant",
                            model=model or None,
                            input_tokens=input_tokens,
                            output_tokens=output_tokens,
                            cache_read_tokens=cached_input,
                            cache_create_tokens=0,
                            tool_names=",".join(tool_names_list) if tool_names_list else None,
                        )
                    )
                    current_turn_items = []

                # turn.failed — still record the turn
                elif event_type == "turn.failed":
                    current_turn_items = []

            new_offset = f.tell()

        model_primary = model_counter.most_common(1)[0][0] if model_counter else None
        project_name = Path(cwd).name if cwd else None

        session = SessionData(
            session_id=session_id,
            tool_source="codex",
            project_path=cwd,
            project_name=project_name,
            started_at=first_timestamp or "",
            ended_at=last_timestamp,
            message_count=len(messages),
            tool_call_count=total_tool_calls,
            model_primary=model_primary,
        )

        return session, messages, new_offset
