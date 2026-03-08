"""Evaluator registry: registration, discovery, and dispatch."""

from __future__ import annotations

import logging
import sqlite3

from open_uplift.evaluators.base import Evaluator, EvaluatorResult

logger = logging.getLogger(__name__)


class EvaluatorRegistry:
    """Central registry for all evaluators (built-in and extensions)."""

    def __init__(self) -> None:
        self._evaluators: dict[str, Evaluator] = {}

    def register(self, evaluator: Evaluator) -> None:
        """Register an evaluator instance."""
        self._evaluators[evaluator.evaluator_id] = evaluator

    def get(self, evaluator_id: str) -> Evaluator | None:
        """Look up an evaluator by ID."""
        return self._evaluators.get(evaluator_id)

    def list(self) -> list[Evaluator]:
        """Return all registered evaluators."""
        return list(self._evaluators.values())

    def list_available(self) -> list[dict]:
        """Return serialized metadata for all registered evaluators."""
        return [e.to_dict() for e in self._evaluators.values()]

    def run(self, db: sqlite3.Connection, evaluator_id: str, session_id: str) -> EvaluatorResult:
        """Run an evaluator by ID. Raises ValueError if not found."""
        evaluator = self._evaluators.get(evaluator_id)
        if evaluator is None:
            raise ValueError(f"Unknown evaluator: {evaluator_id}")
        return evaluator.run(db, session_id)

    def has(self, evaluator_id: str) -> bool:
        return evaluator_id in self._evaluators


# Global registry instance
_registry = EvaluatorRegistry()


def get_registry() -> EvaluatorRegistry:
    """Get the global evaluator registry, initializing if needed."""
    if not _registry._evaluators:
        _init_registry()
    return _registry


def _init_registry() -> None:
    """Register built-in evaluators."""
    from open_uplift.evaluators.compaction import CompactionEvaluator
    from open_uplift.evaluators.judge import JudgeEvaluator
    from open_uplift.evaluators.time_with_ai import TimeWithAIEvaluator

    _registry.register(CompactionEvaluator())
    _registry.register(JudgeEvaluator())
    _registry.register(TimeWithAIEvaluator())
