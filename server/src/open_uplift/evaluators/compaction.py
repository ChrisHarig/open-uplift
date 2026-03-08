"""Compaction evaluator: summarize transcripts via LLM."""

import sqlite3
from datetime import datetime, timezone

from open_uplift.evaluators.base import Evaluator, EvaluatorResult
from open_uplift.llm_client import LLMClient
from open_uplift import scripts as _scripts


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

        # Get transcript
        path = _scripts._get_transcript_path(db, session_id)
        if not path:
            error = "Transcript file not found"
            _scripts._store_result(db, session_id, self.evaluator_id, "error", None,
                                   error, 0, 0, 0.0, prompt_id, started_at)
            return EvaluatorResult(
                evaluator_id=self.evaluator_id, value=None,
                value_type="structured", error=error,
            )

        from open_uplift.transcript import parse_transcript

        transcript_data = parse_transcript(path)
        preprocessed = _scripts._preprocess_transcript(transcript_data)

        # Prepend continuation context if this is a continuation session
        context = _scripts._build_continuation_context(db, session_id)
        if context:
            preprocessed = context + "\n\n" + preprocessed

        if not preprocessed.strip():
            error = "Empty transcript"
            _scripts._store_result(db, session_id, self.evaluator_id, "error", None,
                                   error, 0, 0, 0.0, prompt_id, started_at)
            return EvaluatorResult(
                evaluator_id=self.evaluator_id, value=None,
                value_type="structured", error=error,
            )

        provider = compaction.get("provider", "anthropic")
        model = compaction.get("model", "claude-haiku-4-5-20251001")
        system_prompt = _scripts._get_prompt(db, prompt_id)
        api_key = _scripts.get_api_key(db, provider)

        if not api_key:
            error = f"No API key configured for {provider}"
            _scripts._store_result(db, session_id, self.evaluator_id, "error", None,
                                   error, 0, 0, 0.0, prompt_id, started_at)
            return EvaluatorResult(
                evaluator_id=self.evaluator_id, value=None,
                value_type="structured", error=error,
            )

        try:
            client = LLMClient(provider, model, api_key)
            response = client.complete(system_prompt, preprocessed, max_tokens=4096, temperature=0.0)

            result = {
                "compacted_transcript": response.content,
                "input_tokens": response.input_tokens,
                "output_tokens": response.output_tokens,
                "cost_usd": response.cost_usd,
                "model": response.model,
            }
            _scripts._store_result(db, session_id, self.evaluator_id, "completed", result, None,
                                   response.input_tokens, response.output_tokens, response.cost_usd,
                                   prompt_id, started_at)
            return EvaluatorResult(
                evaluator_id=self.evaluator_id,
                value=response.content,
                value_type="string",
                answer=f"Compacted ({response.output_tokens} tokens)",
                metadata=result,
            )
        except Exception as e:
            error = str(e)
            _scripts._store_result(db, session_id, self.evaluator_id, "error", None,
                                   error, 0, 0, 0.0, prompt_id, started_at)
            return EvaluatorResult(
                evaluator_id=self.evaluator_id, value=None,
                value_type="structured", error=error,
            )
