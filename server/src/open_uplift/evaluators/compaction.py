"""Compaction evaluator: summarize transcripts via LLM.

Two modes, selected by the prompt's tool_config:
  - Tool-use (Amy methodology): per-turn summarization. Iterate over user/assistant
    segments, call complete_with_tool once per assistant turn with the prompt's
    summarize_turn tool, concatenate verbatim user messages with the structured
    per-turn summaries. Aggregates tokens and cost across all calls. Anthropic
    and OpenAI only.
  - Text (legacy): single LLM call over the whole preprocessed transcript.
"""

import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from open_uplift.evaluators.base import Evaluator, EvaluatorResult
from open_uplift.llm_client import LLMClient
from open_uplift import scripts as _scripts


_MAX_PARALLEL_TURNS = 5
_PER_TURN_MAX_TOKENS = 1024


class CompactionEvaluator(Evaluator):
    evaluator_id = "transcript-compact"
    name = "Transcript Compaction"
    category = "builtin"
    description = "Summarize a session transcript into a structured compact form using an LLM"
    requires_llm = True
    requires_transcript = True
    depends_on = []

    def run(self, db: sqlite3.Connection, session_id: str) -> EvaluatorResult:
        started_at = datetime.now(timezone.utc).isoformat()
        config = _scripts._get_script_config(db)
        compaction = config.get("compaction", {})
        prompt_id = compaction.get("prompt_id", "compaction-default")

        path = _scripts._get_transcript_path(db, session_id)
        if not path:
            return self._fail(db, session_id, prompt_id, started_at, "Transcript file not found")

        from open_uplift.transcript import parse_transcript

        transcript_data = parse_transcript(path)

        provider = compaction.get("provider", "anthropic")
        model = compaction.get("model", "claude-haiku-4-5-20251001")
        system_prompt = _scripts._get_prompt(db, prompt_id)
        tool_config = _scripts._get_tool_config(db, prompt_id)
        api_key = _scripts.get_api_key(db, provider)

        if not api_key:
            return self._fail(db, session_id, prompt_id, started_at, f"No API key configured for {provider}")

        try:
            client = LLMClient(provider, model, api_key)

            if tool_config:
                content, in_tok, out_tok, cost = self._compact_per_turn(
                    db, session_id, client, system_prompt, tool_config, transcript_data,
                )
            else:
                content, in_tok, out_tok, cost = self._compact_single_call(
                    db, session_id, client, system_prompt, transcript_data,
                )

            result = {
                "compacted_transcript": content,
                "input_tokens": in_tok,
                "output_tokens": out_tok,
                "cost_usd": cost,
                "model": model,
            }
            _scripts._store_result(db, session_id, self.evaluator_id, "completed", result, None,
                                   in_tok, out_tok, cost, prompt_id, started_at)
            return EvaluatorResult(
                evaluator_id=self.evaluator_id,
                value=content,
                value_type="string",
                answer=f"Compacted ({out_tok} tokens)",
                metadata=result,
            )
        except Exception as e:
            return self._fail(db, session_id, prompt_id, started_at, str(e))

    def _fail(self, db, session_id, prompt_id, started_at, error: str) -> EvaluatorResult:
        _scripts._store_result(db, session_id, self.evaluator_id, "error", None,
                               error, 0, 0, 0.0, prompt_id, started_at)
        return EvaluatorResult(
            evaluator_id=self.evaluator_id, value=None,
            value_type="structured", error=error,
        )

    def _compact_per_turn(
        self,
        db: sqlite3.Connection,
        session_id: str,
        client: LLMClient,
        system_prompt: str,
        tool_config: dict,
        transcript_data: dict,
    ) -> tuple[str, int, int, float]:
        """Per-turn compaction (METR Amy-Deng methodology).

        Sends each assistant turn to the summarizer using the FULL prompt template
        as the user message (with {assistant_turn_content} substituted) and an
        empty system prompt — so the model sees exactly what's printed in METR's
        Appendix A. Continuation context and developer profiles are NOT injected.
        Code diffs are preserved verbatim in the final output.
        """
        chunks = _scripts._segment_transcript_by_turn(transcript_data)

        to_summarize: list[tuple[int, str]] = [
            (i, c["assistant_text"]) for i, c in enumerate(chunks) if c["assistant_text"]
        ]

        summaries: dict[int, dict] = {}
        total_in = 0
        total_out = 0
        total_cost = 0.0

        def call_one(idx_text: tuple[int, str]) -> tuple[int, dict, int, int, float]:
            idx, assistant_text = idx_text
            filled = system_prompt.replace("{assistant_turn_content}", assistant_text)
            resp = client.complete_with_tool(
                system_prompt="",
                user_prompt=filled,
                tool_name=tool_config["tool_name"],
                tool_description=tool_config.get("tool_description", ""),
                tool_schema=tool_config["input_schema"],
                max_tokens=_PER_TURN_MAX_TOKENS,
                temperature=0.0,
            )
            try:
                parsed = json.loads(resp.content)
            except json.JSONDecodeError:
                parsed = {"actions": resp.content, "outcome": ""}
            return idx, parsed, resp.input_tokens, resp.output_tokens, resp.cost_usd

        if to_summarize:
            with ThreadPoolExecutor(max_workers=_MAX_PARALLEL_TURNS) as pool:
                for idx, parsed, in_t, out_t, cost in pool.map(call_one, to_summarize):
                    summaries[idx] = parsed
                    total_in += in_t
                    total_out += out_t
                    total_cost += cost

        out_lines: list[str] = []
        for i, chunk in enumerate(chunks):
            if chunk["user_text"]:
                out_lines.append(chunk["user_text"])
            if i in summaries:
                s = summaries[i]
                actions = s.get("actions", "").strip()
                outcome = s.get("outcome", "").strip()
                out_lines.append("ASSISTANT TURN SUMMARY:")
                if actions:
                    out_lines.append(f"  ACTIONS: {actions}")
                if outcome:
                    out_lines.append(f"  OUTCOME: {outcome}")
            elif chunk["assistant_text"] is None:
                out_lines.append("(no assistant response — session ended after this user message)")
            for diff in chunk.get("code_diffs", []):
                out_lines.append("CODE DIFF:")
                out_lines.append(diff)
            out_lines.append("")

        return "\n".join(out_lines).rstrip(), total_in, total_out, round(total_cost, 6)

    def _compact_single_call(
        self,
        db: sqlite3.Connection,
        session_id: str,
        client: LLMClient,
        system_prompt: str,
        transcript_data: dict,
    ) -> tuple[str, int, int, float]:
        """Legacy single-call compaction for non-tool-using prompts."""
        preprocessed = _scripts._preprocess_transcript(transcript_data)
        context = _scripts._build_continuation_context(db, session_id)
        if context:
            preprocessed = context + "\n\n" + preprocessed
        if not preprocessed.strip():
            raise RuntimeError("Empty transcript")
        response = client.complete(system_prompt, preprocessed, max_tokens=4096, temperature=0.0)
        return response.content, response.input_tokens, response.output_tokens, response.cost_usd
