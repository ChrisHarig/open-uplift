"""Judge evaluator: estimate time-without-AI from transcripts."""

import json
import logging
import sqlite3
from datetime import datetime, timezone

from open_uplift import scripts as _scripts
from open_uplift.evaluators.base import Evaluator, EvaluatorResult
from open_uplift.llm_client import LLMClient
from open_uplift.surveys import _get_config
from open_uplift.time_measurement import compute_time_with_ai

logger = logging.getLogger(__name__)


def _store_judge_outputs(
    db: sqlite3.Connection,
    session_id: str,
    judge_result: dict,
    prompt_id: str,
    schema: list[dict] | None,
) -> None:
    """Extract schema-defined fields from the judge result and store in judge_outputs."""
    now = datetime.now(timezone.utc).isoformat()

    # If no schema, use default field list
    if not schema:
        schema = [
            {"name": "success", "type": "boolean"},
            {"name": "total_minutes_without_ai", "type": "numeric"},
            {"name": "tasks", "type": "array"},
            {"name": "confidence", "type": "string"},
            {"name": "reasoning", "type": "string"},
        ]

    for field in schema:
        field_name = field["name"]
        value_type = field["type"]
        value = judge_result.get(field_name)
        if value is None:
            continue

        if value_type == "boolean":
            value_text = "true" if value else "false"
            value_numeric = 1.0 if value else 0.0
        elif value_type == "numeric":
            value_text = str(value)
            try:
                value_numeric = float(value)
            except (ValueError, TypeError):
                value_numeric = None
        elif value_type == "array":
            value_text = json.dumps(value)
            value_numeric = None
        else:  # string
            value_text = str(value)
            value_numeric = None

        db.execute(
            """INSERT OR REPLACE INTO judge_outputs
               (session_id, field_name, value_text, value_numeric, value_type, prompt_id, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (session_id, field_name, value_text, value_numeric, value_type, prompt_id, now),
        )


class JudgeEvaluator(Evaluator):
    evaluator_id = "llm-time-estimate"
    name = "LLM Time Estimate"
    category = "builtin"
    description = "Estimate how long tasks would take without AI assistance"
    requires_llm = True
    requires_transcript = True
    depends_on = ["transcript-compact"]

    def run(self, db: sqlite3.Connection, session_id: str) -> EvaluatorResult:
        started_at = datetime.now(timezone.utc).isoformat()
        config = _scripts._get_script_config(db)
        judge = config.get("judge", {})
        prompt_id = judge.get("prompt_id", "judge-default")

        # Try compacted transcript first
        compaction = db.execute(
            "SELECT result FROM script_results WHERE session_id = ? AND script_id = 'transcript-compact' AND status = 'completed'",
            (session_id,),
        ).fetchone()

        if compaction and compaction["result"]:
            result_data = json.loads(compaction["result"])
            user_prompt = result_data.get("compacted_transcript", "")
        else:
            # Fall back to raw preprocessed transcript
            path = _scripts._get_transcript_path(db, session_id)
            if not path:
                error = "Transcript file not found"
                _scripts._store_result(db, session_id, self.evaluator_id, "error", None,
                                       error, 0, 0, 0.0, prompt_id, started_at)
                return EvaluatorResult(
                    evaluator_id=self.evaluator_id, value=None,
                    value_type="numeric", error=error,
                )
            from open_uplift.transcript import parse_transcript

            transcript_data = parse_transcript(path)
            user_prompt = _scripts._preprocess_transcript(transcript_data)

        if not user_prompt.strip():
            error = "No transcript content available"
            _scripts._store_result(db, session_id, self.evaluator_id, "error", None,
                                   error, 0, 0, 0.0, prompt_id, started_at)
            return EvaluatorResult(
                evaluator_id=self.evaluator_id, value=None,
                value_type="numeric", error=error,
            )

        # Tool-use prompts (Amy methodology) are sent verbatim — no profile or
        # continuation-context injection. Legacy text prompts keep both.
        is_tool_prompt = bool(_scripts._get_tool_config(db, prompt_id))

        if not is_tool_prompt:
            if judge.get("include_profile", True):
                profile = _get_config(db, "user_profile")
                if profile and profile.get("experience_description"):
                    profile_text = f"The developer completing this task describes themselves as:\n{profile['experience_description']}\n"
                    user_prompt = profile_text + "\n---\n\n" + user_prompt
            context = _scripts._build_continuation_context(db, session_id)
            if context:
                user_prompt = context + "\n\n" + user_prompt

        provider = judge.get("provider", "anthropic")
        model = judge.get("model", "claude-sonnet-4-6")

        try:
            output_schema = _scripts._get_output_schema(db, prompt_id)
            if is_tool_prompt:
                system_prompt = _scripts._get_prompt(db, prompt_id)
            else:
                system_prompt = _scripts._build_prompt_with_schema(db, prompt_id)
        except Exception as e:
            error = f"Failed to build prompt: {e}"
            _scripts._store_result(db, session_id, self.evaluator_id, "error", None,
                                   error, 0, 0, 0.0, prompt_id, started_at)
            return EvaluatorResult(
                evaluator_id=self.evaluator_id, value=None,
                value_type="numeric", error=error,
            )

        api_key = _scripts.get_api_key(db, provider)
        if not api_key:
            error = f"No API key configured for {provider}"
            _scripts._store_result(db, session_id, self.evaluator_id, "error", None,
                                   error, 0, 0, 0.0, prompt_id, started_at)
            return EvaluatorResult(
                evaluator_id=self.evaluator_id, value=None,
                value_type="numeric", error=error,
            )

        try:
            client = LLMClient(provider, model, api_key)
            tool_config = _scripts._get_tool_config(db, prompt_id)

            if tool_config:
                # Send the full template as the user message with the placeholder
                # filled, system prompt empty — model sees the prompt verbatim as
                # printed in METR's Appendix A.
                filled = system_prompt.replace("{compressed_transcript}", user_prompt)
                response = client.complete_with_tool(
                    system_prompt="",
                    user_prompt=filled,
                    tool_name=tool_config["tool_name"],
                    tool_description=tool_config.get("tool_description", ""),
                    tool_schema=tool_config["input_schema"],
                    max_tokens=4096,
                    temperature=0.0,
                )
                # Tool-use returns the tool input as JSON in content; parse directly.
                try:
                    judge_result = json.loads(response.content)
                except json.JSONDecodeError:
                    judge_result = {"raw_response": response.content.strip(), "parse_error": True}
            else:
                response = client.complete(system_prompt, user_prompt, max_tokens=4096, temperature=0.0)
                content = response.content.strip()
                import re
                fence_match = re.search(r"```(?:json)?\s*\n(.*?)```", content, re.DOTALL)
                if fence_match:
                    content = fence_match.group(1).strip()
                elif not content.startswith("{"):
                    first_brace = content.find("{")
                    last_brace = content.rfind("}")
                    if first_brace != -1 and last_brace > first_brace:
                        content = content[first_brace:last_brace + 1]
                try:
                    judge_result = json.loads(content)
                except json.JSONDecodeError:
                    judge_result = {"raw_response": response.content.strip(), "parse_error": True}

            result = {
                **judge_result,
                "minutes": judge_result.get("total_minutes_without_ai"),
                "input_tokens": response.input_tokens,
                "output_tokens": response.output_tokens,
                "cost_usd": response.cost_usd,
                "model": response.model,
            }
            _scripts._store_result(db, session_id, self.evaluator_id, "completed", result, None,
                                   response.input_tokens, response.output_tokens, response.cost_usd,
                                   prompt_id, started_at)

            # Store judge outputs into EAV table
            if not judge_result.get("parse_error"):
                try:
                    _store_judge_outputs(db, session_id, judge_result, prompt_id, output_schema)
                except Exception:
                    logger.warning("Failed to store judge outputs for session %s", session_id, exc_info=True)

            # Auto-generate uplift output
            minutes_without_ai = judge_result.get("total_minutes_without_ai")
            if minutes_without_ai and minutes_without_ai > 0:
                try:
                    time_data = compute_time_with_ai(db, session_id)
                    active_minutes = time_data.get("active_minutes", 0)
                    if active_minutes > 0:
                        uplift_factor = round(minutes_without_ai / active_minutes, 2)
                    else:
                        logger.warning("active_minutes=0 for session %s, storing uplift_factor=0", session_id)
                        uplift_factor = 0.0
                    now = datetime.now(timezone.utc).isoformat()
                    db.execute(
                        """INSERT OR REPLACE INTO uplift_outputs
                           (session_id, survey_response_id, output_id, uplift_factor, metadata, timestamp)
                           VALUES (?, NULL, 'llm-judge', ?, ?, ?)""",
                        (session_id, uplift_factor, json.dumps({
                            "minutes_without_ai": minutes_without_ai,
                            "active_minutes": active_minutes,
                        }), now),
                    )
                except Exception:
                    logger.warning("Failed to store uplift output for session %s", session_id, exc_info=True)

            minutes = judge_result.get("total_minutes_without_ai")
            return EvaluatorResult(
                evaluator_id=self.evaluator_id,
                value=minutes,
                value_type="numeric",
                answer=f"{minutes} minutes" if minutes else None,
                explanation=judge_result.get("reasoning"),
                confidence=judge_result.get("confidence"),
                metadata=result,
            )
        except Exception as e:
            error = str(e)
            _scripts._store_result(db, session_id, self.evaluator_id, "error", None,
                                   error, 0, 0, 0.0, prompt_id, started_at)
            return EvaluatorResult(
                evaluator_id=self.evaluator_id, value=None,
                value_type="numeric", error=error,
            )
