"""Judges score a bot response against a test case.

Two implementations ship out of the box:

* ``KeywordJudge`` — deterministic, offline. Checks ``must_include`` / ``must_not_include``.
  Use it for hard requirements (safety phrases, forbidden claims) and in CI.
* ``LLMJudge`` — LLM-as-judge via the Anthropic API. Grades against the free-text ``rubric``.
  Use it for qualities keywords can't capture (tone, completeness, reasoning).

Combine them: a case passes only when every judge passes.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Protocol

from chatbot_eval.cases import TestCase


@dataclass(frozen=True)
class Verdict:
    judge: str
    passed: bool
    score: float  # 0.0–1.0
    reason: str
    details: dict = field(default_factory=dict)


class Judge(Protocol):
    name: str

    def evaluate(self, case: TestCase, response: str) -> Verdict: ...


class KeywordJudge:
    """Deterministic substring checks. Case-insensitive, whitespace-normalised."""

    name = "keyword"

    @staticmethod
    def _norm(text: str) -> str:
        return re.sub(r"\s+", " ", text).strip().lower()

    def evaluate(self, case: TestCase, response: str) -> Verdict:
        body = self._norm(response)
        missing = [p for p in case.must_include if self._norm(p) not in body]
        forbidden = [p for p in case.must_not_include if self._norm(p) in body]

        total = len(case.must_include) + len(case.must_not_include)
        if total == 0:
            return Verdict(self.name, True, 1.0, "No keyword rules; skipped.", {"skipped": True})

        failures = len(missing) + len(forbidden)
        score = (total - failures) / total
        reasons = []
        if missing:
            reasons.append(f"missing: {missing}")
        if forbidden:
            reasons.append(f"forbidden present: {forbidden}")
        return Verdict(
            judge=self.name,
            passed=failures == 0,
            score=score,
            reason="; ".join(reasons) if reasons else "All keyword rules satisfied.",
            details={"missing": missing, "forbidden": forbidden},
        )


JUDGE_SYSTEM_PROMPT = """You are a strict, impartial evaluator of chatbot responses.
You will receive the user's message, the chatbot's response, and a rubric.
Grade ONLY against the rubric. Do not reward length or politeness unless the rubric asks for it.
Respond with a single JSON object and nothing else:
{"score": <integer 1-5>, "passed": <true|false>, "reason": "<one or two sentences>"}
Use passed=true only if the response meets every requirement in the rubric."""


class LLMJudge:
    """Grades a response against ``case.rubric`` using Claude.

    Requires the ``anthropic`` package (``pip install chatbot-eval-kit[llm]``) and
    ``ANTHROPIC_API_KEY`` in the environment. A ``client`` can be injected for testing.
    """

    name = "llm"

    def __init__(
        self,
        model: str = "claude-sonnet-4-5",
        pass_threshold: int = 4,
        client=None,
        max_tokens: int = 300,
    ) -> None:
        self.model = model
        self.pass_threshold = pass_threshold
        self.max_tokens = max_tokens
        self._client = client

    @property
    def client(self):
        if self._client is None:
            try:
                import anthropic
            except ImportError as exc:  # pragma: no cover
                raise ImportError(
                    "LLMJudge needs the 'anthropic' package: pip install 'chatbot-eval-kit[llm]'"
                ) from exc
            self._client = anthropic.Anthropic()
        return self._client

    def _build_prompt(self, case: TestCase, response: str) -> str:
        return (
            f"<user_message>\n{case.last_user_message}\n</user_message>\n\n"
            f"<chatbot_response>\n{response}\n</chatbot_response>\n\n"
            f"<rubric>\n{case.rubric}\n</rubric>"
        )

    @staticmethod
    def _parse(text: str) -> dict:
        match = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if not match:
            raise ValueError(f"Judge returned no JSON: {text!r}")
        data = json.loads(match.group(0))
        score = int(data["score"])
        if not 1 <= score <= 5:
            raise ValueError(f"Judge score out of range: {score}")
        return {
            "score": score,
            "passed": bool(data.get("passed")),
            "reason": str(data.get("reason", "")),
        }

    def evaluate(self, case: TestCase, response: str) -> Verdict:
        if not case.rubric:
            return Verdict(self.name, True, 1.0, "No rubric; skipped.", {"skipped": True})

        message = self.client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            system=JUDGE_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": self._build_prompt(case, response)}],
        )
        text = "".join(getattr(block, "text", "") for block in message.content)
        parsed = self._parse(text)
        passed = parsed["passed"] and parsed["score"] >= self.pass_threshold
        return Verdict(
            judge=self.name,
            passed=passed,
            score=(parsed["score"] - 1) / 4,
            reason=parsed["reason"],
            details={"raw_score": parsed["score"], "model": self.model},
        )
