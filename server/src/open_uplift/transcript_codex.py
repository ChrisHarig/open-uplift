"""Parse Codex CLI rollout JSONL files into structured conversation data."""

import json
from pathlib import Path


def parse_codex_transcript(file_path: Path) -> dict:
    """Read a Codex rollout JSONL file and return structured conversation entries.

    Returns dict with:
        transcript: list of message entries (user, assistant with tool_use)
        stats: {user_messages, assistant_messages, tool_calls}
    """
    events = []
    for line in file_path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            continue

    transcript = []
    tool_call_count = 0

    # Accumulate items per turn, then flush on turn.completed
    current_blocks: list[dict] = []
    current_timestamp: str | None = None

    for event in events:
        event_type = event.get("type", "")
        timestamp = event.get("timestamp", "")

        if event_type == "item.completed":
            item = event.get("item", {})
            item_type = item.get("type", "")

            if item_type == "userMessage":
                # Flush any pending assistant blocks
                if current_blocks:
                    transcript.append({
                        "role": "assistant",
                        "timestamp": current_timestamp,
                        "blocks": current_blocks,
                    })
                    current_blocks = []

                # Extract user text
                content = item.get("content", [])
                text = ""
                if isinstance(content, list):
                    text_parts = [
                        c.get("text", "")
                        for c in content
                        if isinstance(c, dict) and c.get("type") == "text"
                    ]
                    text = "\n".join(text_parts)
                elif isinstance(content, str):
                    text = content

                if text:
                    transcript.append({
                        "role": "user",
                        "timestamp": timestamp,
                        "blocks": [{"type": "text", "text": text}],
                    })

            elif item_type == "agentMessage":
                current_timestamp = current_timestamp or timestamp
                text = item.get("text", "")
                if text:
                    current_blocks.append({"type": "text", "text": text})

            elif item_type == "reasoning":
                current_timestamp = current_timestamp or timestamp
                summary = item.get("summary", "")
                if summary:
                    current_blocks.append({"type": "thinking", "text": summary})

            elif item_type == "commandExecution":
                current_timestamp = current_timestamp or timestamp
                tool_call_count += 1
                current_blocks.append({
                    "type": "tool_use",
                    "tool_name": "bash",
                    "input": {"command": item.get("command", "")},
                    "result": item.get("aggregatedOutput", ""),
                    "is_error": item.get("exitCode", 0) != 0,
                })

            elif item_type == "fileChange":
                current_timestamp = current_timestamp or timestamp
                tool_call_count += 1
                changes = item.get("changes", [])
                diff_text = "\n".join(
                    f"{c.get('path', '')}: {c.get('kind', 'modify')}\n{c.get('diff', '')}"
                    for c in changes
                )
                current_blocks.append({
                    "type": "tool_use",
                    "tool_name": "file_change",
                    "input": {"changes": changes},
                    "result": diff_text,
                    "is_error": item.get("status") == "failed",
                })

            elif item_type == "mcpToolCall":
                current_timestamp = current_timestamp or timestamp
                tool_call_count += 1
                current_blocks.append({
                    "type": "tool_use",
                    "tool_name": item.get("tool", "mcp_tool"),
                    "input": item.get("arguments", {}),
                    "result": item.get("result", ""),
                    "is_error": bool(item.get("error")),
                })

            elif item_type == "webSearch":
                current_timestamp = current_timestamp or timestamp
                tool_call_count += 1
                current_blocks.append({
                    "type": "tool_use",
                    "tool_name": "web_search",
                    "input": {"query": item.get("query", ""), "action": item.get("action", "")},
                    "result": None,
                    "is_error": False,
                })

        elif event_type == "turn.completed":
            # Flush accumulated blocks as an assistant message
            if current_blocks:
                transcript.append({
                    "role": "assistant",
                    "timestamp": current_timestamp or timestamp,
                    "blocks": current_blocks,
                })
                current_blocks = []
                current_timestamp = None

        elif event_type == "turn.failed":
            current_blocks = []
            current_timestamp = None

    # Flush any remaining blocks
    if current_blocks:
        transcript.append({
            "role": "assistant",
            "timestamp": current_timestamp,
            "blocks": current_blocks,
        })

    user_messages = sum(1 for t in transcript if t["role"] == "user")
    assistant_messages = sum(1 for t in transcript if t["role"] == "assistant")

    return {
        "transcript": transcript,
        "stats": {
            "user_messages": user_messages,
            "assistant_messages": assistant_messages,
            "tool_calls": tool_call_count,
        },
    }
