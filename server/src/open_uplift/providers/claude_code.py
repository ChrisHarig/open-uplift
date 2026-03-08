import json
import re
from collections import Counter
from pathlib import Path
from typing import Iterator

from open_uplift.config import CLAUDE_PROJECTS_DIR
from open_uplift.models import MessageData, SessionData
from open_uplift.providers.base import SessionProvider

# UUID pattern for session JSONL files
SESSION_FILE_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\.jsonl$"
)


class ClaudeCodeProvider(SessionProvider):
    @property
    def tool_name(self) -> str:
        return "claude_code"

    def discover_session_files(self) -> Iterator[Path]:
        if not CLAUDE_PROJECTS_DIR.exists():
            return
        for project_dir in CLAUDE_PROJECTS_DIR.iterdir():
            if not project_dir.is_dir() or project_dir.name.startswith("."):
                continue
            for jsonl_file in project_dir.iterdir():
                if jsonl_file.is_file() and SESSION_FILE_RE.match(jsonl_file.name):
                    yield jsonl_file

    def parse_session(
        self, file_path: Path, from_offset: int = 0
    ) -> tuple[SessionData, list[MessageData], int]:
        session_id = file_path.stem

        messages: list[MessageData] = []
        first_timestamp = None
        last_timestamp = None
        git_branch = None
        version = None
        cwd = None
        model_counter: Counter[str] = Counter()
        total_tool_calls = 0

        with open(file_path, "r") as f:
            f.seek(from_offset)
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue

                entry_type = entry.get("type")
                timestamp = entry.get("timestamp", "")

                if timestamp:
                    if first_timestamp is None:
                        first_timestamp = timestamp
                    last_timestamp = timestamp

                if cwd is None:
                    cwd = entry.get("cwd")
                if git_branch is None:
                    git_branch = entry.get("gitBranch")
                if version is None:
                    version = entry.get("version")

                if entry_type == "assistant":
                    msg = entry.get("message", {})
                    usage = msg.get("usage", {})
                    model = msg.get("model", "")

                    input_tokens = usage.get("input_tokens", 0)
                    output_tokens = usage.get("output_tokens", 0)
                    cache_read = usage.get("cache_read_input_tokens", 0)
                    cache_create = usage.get("cache_creation_input_tokens", 0)

                    # Extract tool names from content
                    tool_names_list = []
                    content = msg.get("content", [])
                    if isinstance(content, list):
                        for block in content:
                            if isinstance(block, dict) and block.get("type") == "tool_use":
                                name = block.get("name", "")
                                if name:
                                    tool_names_list.append(name)
                                    total_tool_calls += 1

                    if model:
                        model_counter[model] += 1

                    messages.append(
                        MessageData(
                            session_id=session_id,
                            request_id=entry.get("requestId"),
                            timestamp=timestamp,
                            role="assistant",
                            model=model or None,
                            input_tokens=input_tokens,
                            output_tokens=output_tokens,
                            cache_read_tokens=cache_read,
                            cache_create_tokens=cache_create,
                            tool_names=",".join(tool_names_list) if tool_names_list else None,
                        )
                    )

                elif entry_type == "user":
                    messages.append(
                        MessageData(
                            session_id=session_id,
                            timestamp=timestamp,
                            role="user",
                        )
                    )

            new_offset = f.tell()

        # Determine primary model
        model_primary = model_counter.most_common(1)[0][0] if model_counter else None

        project_name = Path(cwd).name if cwd else None

        session = SessionData(
            session_id=session_id,
            tool_source="claude_code",
            project_path=cwd,
            project_name=project_name,
            git_branch=git_branch,
            started_at=first_timestamp or "",
            ended_at=last_timestamp,
            message_count=len(messages),
            tool_call_count=total_tool_calls,
            model_primary=model_primary,
        )

        return session, messages, new_offset
