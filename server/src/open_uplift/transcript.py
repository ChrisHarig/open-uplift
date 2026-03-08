"""Parse Claude Code JSONL transcript files into structured conversation data."""

import json
from pathlib import Path


def parse_transcript(file_path: Path) -> dict:
    """Read a JSONL transcript file and return structured conversation entries.

    Returns dict with:
        transcript: list of message entries (user, assistant with tool_use/thinking)
        stats: {user_messages, assistant_messages, tool_calls}
    """
    entries = []
    for line in file_path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            continue

    # Filter out noise: file-history-snapshot, progress, isMeta entries
    filtered = []
    for entry in entries:
        if entry.get("type") == "file-history-snapshot":
            continue
        if entry.get("type") == "progress":
            continue
        if entry.get("isMeta"):
            continue
        if "message" not in entry:
            continue
        filtered.append(entry)

    # Build transcript: collect assistant and user messages
    # Track tool_use blocks so we can attach tool_result to them
    transcript = []
    tool_use_map: dict[str, dict] = {}  # tool_use_id -> tool_use block in transcript

    for entry in filtered:
        msg = entry["message"]
        role = msg.get("role")
        content = msg.get("content")
        timestamp = entry.get("timestamp")

        if role == "assistant":
            blocks = _extract_assistant_blocks(content, tool_use_map)
            if blocks:
                transcript.append({
                    "role": "assistant",
                    "timestamp": timestamp,
                    "blocks": blocks,
                })

        elif role == "user":
            # Could be plain user text or tool_result
            if isinstance(content, str):
                transcript.append({
                    "role": "user",
                    "timestamp": timestamp,
                    "blocks": [{"type": "text", "text": content}],
                })
            elif isinstance(content, list):
                # Check if it's a tool_result (attach to preceding tool_use)
                user_blocks = []
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "tool_result":
                        tool_use_id = block.get("tool_use_id")
                        result_content = block.get("content", "")
                        if isinstance(result_content, list):
                            # Extract text from content blocks
                            parts = []
                            for part in result_content:
                                if isinstance(part, dict) and part.get("type") == "text":
                                    parts.append(part.get("text", ""))
                            result_content = "\n".join(parts)
                        if tool_use_id and tool_use_id in tool_use_map:
                            tool_use_map[tool_use_id]["result"] = str(result_content)
                            tool_use_map[tool_use_id]["is_error"] = block.get("is_error", False)
                        # Don't add tool_result as a standalone message
                    elif isinstance(block, dict) and block.get("type") == "text":
                        user_blocks.append({"type": "text", "text": block.get("text", "")})
                if user_blocks:
                    transcript.append({
                        "role": "user",
                        "timestamp": timestamp,
                        "blocks": user_blocks,
                    })

    # Compute stats
    user_messages = sum(1 for t in transcript if t["role"] == "user")
    assistant_messages = sum(1 for t in transcript if t["role"] == "assistant")
    tool_calls = len(tool_use_map)

    return {
        "transcript": transcript,
        "stats": {
            "user_messages": user_messages,
            "assistant_messages": assistant_messages,
            "tool_calls": tool_calls,
        },
    }


def detect_session_end_type(transcript_data: dict) -> str | None:
    """Check the last tool call in a transcript. Returns 'plan' if ExitPlanMode, else None."""
    entries = transcript_data.get("transcript", [])
    # Walk backwards to find the last assistant message with a tool_use block
    for entry in reversed(entries):
        if entry.get("role") != "assistant":
            continue
        for block in reversed(entry.get("blocks", [])):
            if block.get("type") == "tool_use":
                if block.get("tool_name") == "ExitPlanMode":
                    return "plan"
                return None
    return None


def _extract_assistant_blocks(content, tool_use_map: dict) -> list[dict]:
    """Extract structured blocks from assistant message content."""
    if isinstance(content, str):
        return [{"type": "text", "text": content}]

    if not isinstance(content, list):
        return []

    blocks = []
    for block in content:
        if not isinstance(block, dict):
            continue

        block_type = block.get("type")

        if block_type == "text":
            text = block.get("text", "").strip()
            if text:
                blocks.append({"type": "text", "text": text})

        elif block_type == "thinking":
            thinking = block.get("thinking", "").strip()
            if thinking:
                blocks.append({"type": "thinking", "text": thinking})

        elif block_type == "tool_use":
            tool_block = {
                "type": "tool_use",
                "tool_name": block.get("name", "unknown"),
                "input": block.get("input", {}),
                "result": None,
                "is_error": False,
            }
            tool_use_id = block.get("id")
            if tool_use_id:
                tool_use_map[tool_use_id] = tool_block
            blocks.append(tool_block)

    return blocks
