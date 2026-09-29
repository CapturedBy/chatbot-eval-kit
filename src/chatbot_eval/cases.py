"""Test case model and YAML loader."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


class CaseValidationError(ValueError):
    """Raised when a test case file is malformed."""


@dataclass(frozen=True)
class TestCase:
    """One evaluation scenario for a chatbot.

    Attributes:
        id: Unique identifier, used in reports and for tracking regressions.
        input: The user message (or list of messages for multi-turn) sent to the bot.
        must_include: Substrings/phrases the answer must contain (case-insensitive).
        must_not_include: Substrings that must be absent (e.g. hallucinated facts, unsafe advice).
        rubric: Free-text criteria for an LLM judge. Optional when only keyword checks are used.
        tags: Labels for filtering (e.g. "safety", "triage", "tone").
        system: Optional per-case system prompt override for the bot under test.
    """

    __test__ = False  # keep pytest from collecting this dataclass

    id: str
    input: str | list[dict[str, str]]
    must_include: tuple[str, ...] = ()
    must_not_include: tuple[str, ...] = ()
    rubric: str | None = None
    tags: tuple[str, ...] = ()
    system: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def last_user_message(self) -> str:
        if isinstance(self.input, str):
            return self.input
        for msg in reversed(self.input):
            if msg.get("role") == "user":
                return msg.get("content", "")
        return ""


def _as_tuple(value: Any, key: str, case_id: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    if isinstance(value, list) and all(isinstance(v, str) for v in value):
        return tuple(value)
    raise CaseValidationError(f"Case '{case_id}': '{key}' must be a string or list of strings")


def parse_case(raw: dict[str, Any]) -> TestCase:
    if not isinstance(raw, dict):
        raise CaseValidationError(f"Each case must be a mapping, got {type(raw).__name__}")
    case_id = raw.get("id")
    if not case_id or not isinstance(case_id, str):
        raise CaseValidationError("Each case needs a non-empty string 'id'")
    if "input" not in raw:
        raise CaseValidationError(f"Case '{case_id}': missing 'input'")

    raw_input = raw["input"]
    if isinstance(raw_input, list):
        for msg in raw_input:
            if not isinstance(msg, dict) or "role" not in msg or "content" not in msg:
                raise CaseValidationError(
                    f"Case '{case_id}': multi-turn input needs role/content per message"
                )
    elif not isinstance(raw_input, str):
        raise CaseValidationError(f"Case '{case_id}': 'input' must be a string or message list")

    must_include = _as_tuple(raw.get("must_include"), "must_include", case_id)
    must_not_include = _as_tuple(raw.get("must_not_include"), "must_not_include", case_id)
    rubric = raw.get("rubric")
    if not (must_include or must_not_include or rubric):
        raise CaseValidationError(
            f"Case '{case_id}': needs at least one of must_include, must_not_include, rubric"
        )

    return TestCase(
        id=case_id,
        input=raw_input,
        must_include=must_include,
        must_not_include=must_not_include,
        rubric=rubric,
        tags=_as_tuple(raw.get("tags"), "tags", case_id),
        system=raw.get("system"),
        metadata=raw.get("metadata") or {},
    )


def load_cases(path: str | Path, tags: set[str] | None = None) -> list[TestCase]:
    """Load test cases from a YAML file.

    The file may be a list of cases, or a mapping with a top-level ``cases`` key.
    Duplicate ids raise ``CaseValidationError``.
    """
    path = Path(path)
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if isinstance(data, dict):
        data = data.get("cases", [])
    if not isinstance(data, list):
        raise CaseValidationError(f"{path}: expected a list of cases")

    cases = [parse_case(raw) for raw in data]
    seen: set[str] = set()
    for case in cases:
        if case.id in seen:
            raise CaseValidationError(f"{path}: duplicate case id '{case.id}'")
        seen.add(case.id)

    if tags:
        cases = [c for c in cases if tags.intersection(c.tags)]
    return cases
