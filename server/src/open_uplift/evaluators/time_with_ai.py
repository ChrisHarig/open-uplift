"""Time-with-AI evaluator: deterministic time measurement (no LLM needed)."""

import sqlite3
from datetime import datetime, timezone

from open_uplift.evaluators.base import Evaluator, EvaluatorResult
from open_uplift import scripts as _scripts
from open_uplift.time_measurement import compute_concurrency_adjustment, compute_time_with_ai


class TimeWithAIEvaluator(Evaluator):
    evaluator_id = "time-with-ai"
    name = "Time With AI"
    category = "builtin"
    description = "Deterministic active-time measurement using 10-minute windows with concurrency adjustment"
    requires_llm = False
    requires_transcript = False
    depends_on = []

    def run(self, db: sqlite3.Connection, session_id: str) -> EvaluatorResult:
        started_at = datetime.now(timezone.utc).isoformat()

        try:
            time_data = compute_time_with_ai(db, session_id)
            concurrency = compute_concurrency_adjustment(db, session_id)

            result = {
                **time_data,
                "adjusted_minutes": concurrency["adjusted_minutes"],
                "concurrent_sessions": concurrency["concurrent_sessions"],
            }

            _scripts._store_result(
                db, session_id, self.evaluator_id, "completed", result, None,
                0, 0, 0.0, None, started_at,
            )

            return EvaluatorResult(
                evaluator_id=self.evaluator_id,
                value=concurrency["adjusted_minutes"],
                value_type="numeric",
                answer=f"{concurrency['adjusted_minutes']} min (adjusted)",
                explanation=(
                    f"{time_data['active_minutes']} active min across "
                    f"{time_data['active_windows']}/{time_data['total_windows']} windows, "
                    f"{concurrency['concurrent_sessions']} concurrent sessions"
                ),
                metadata=result,
            )
        except Exception as e:
            error = str(e)
            _scripts._store_result(
                db, session_id, self.evaluator_id, "error", None,
                error, 0, 0, 0.0, None, started_at,
            )
            return EvaluatorResult(
                evaluator_id=self.evaluator_id, value=None,
                value_type="numeric", error=error,
            )
