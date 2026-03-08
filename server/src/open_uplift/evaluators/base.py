"""Base classes for the evaluator system."""

from __future__ import annotations

import sqlite3
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class EvaluatorResult:
    """Standardized output from any evaluator."""

    evaluator_id: str
    value: Any  # Primary output (number, bool, string, dict)
    value_type: str  # "numeric" | "boolean" | "string" | "structured"
    answer: str | None = None  # Human-readable short answer
    explanation: str | None = None  # Reasoning or summary
    confidence: str | None = None  # "low" | "medium" | "high"
    metadata: dict = field(default_factory=dict)  # Evaluator-specific data
    error: str | None = None  # Set when the evaluator failed

    @property
    def success(self) -> bool:
        return self.error is None


class Evaluator(ABC):
    """Abstract base class for all evaluators.

    An evaluator reads a transcript (or session data) and produces
    a structured result that can be stored and combined with other results.
    """

    evaluator_id: str
    name: str
    category: str  # "builtin" | "scout" | "inspect"
    description: str
    requires_llm: bool = False
    requires_transcript: bool = True
    depends_on: list[str] = []

    @abstractmethod
    def run(self, db: sqlite3.Connection, session_id: str) -> EvaluatorResult:
        """Execute the evaluator for a session. Returns an EvaluatorResult."""
        ...

    def get_config_section(self) -> str:
        """Config key used in evaluator_config. Defaults to evaluator_id."""
        return self.evaluator_id

    def to_dict(self) -> dict:
        """Serialize evaluator metadata for API responses."""
        return {
            "evaluator_id": self.evaluator_id,
            "name": self.name,
            "category": self.category,
            "description": self.description,
            "requires_llm": self.requires_llm,
            "requires_transcript": self.requires_transcript,
            "depends_on": self.depends_on,
        }
