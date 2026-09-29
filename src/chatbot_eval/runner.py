"""Run test cases against a bot and collect verdicts."""

from __future__ import annotations

import time
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field

from chatbot_eval.cases import TestCase
from chatbot_eval.judges import Judge, Verdict

# A bot is any callable taking (input, system) and returning the response text.
# `input` is a string or a list of {"role", "content"} messages.
BotFn = Callable[[str | list[dict[str, str]], str | None], str]


@dataclass
class CaseResult:
    case: TestCase
    response: str
    verdicts: list[Verdict]
    latency_s: float
    error: str | None = None

    @property
    def passed(self) -> bool:
        return self.error is None and all(v.passed for v in self.verdicts)

    @property
    def score(self) -> float:
        scored = [v for v in self.verdicts if not v.details.get("skipped")]
        if not scored:
            return 1.0 if self.error is None else 0.0
        return sum(v.score for v in scored) / len(scored)


@dataclass
class EvalRun:
    results: list[CaseResult] = field(default_factory=list)
    started_at: float = field(default_factory=time.time)
    finished_at: float | None = None

    @property
    def total(self) -> int:
        return len(self.results)

    @property
    def passed(self) -> int:
        return sum(1 for r in self.results if r.passed)

    @property
    def failed(self) -> int:
        return self.total - self.passed

    @property
    def pass_rate(self) -> float:
        return self.passed / self.total if self.total else 0.0

    @property
    def mean_score(self) -> float:
        return sum(r.score for r in self.results) / self.total if self.total else 0.0

    def by_tag(self) -> dict[str, tuple[int, int]]:
        """Return {tag: (passed, total)}."""
        stats: dict[str, list[int]] = {}
        for r in self.results:
            for tag in r.case.tags or ("untagged",):
                entry = stats.setdefault(tag, [0, 0])
                entry[1] += 1
                if r.passed:
                    entry[0] += 1
        return {k: (v[0], v[1]) for k, v in sorted(stats.items())}

    def failures(self) -> list[CaseResult]:
        return [r for r in self.results if not r.passed]


def run_eval(
    cases: Iterable[TestCase],
    bot: BotFn,
    judges: Sequence[Judge],
    on_result: Callable[[CaseResult], None] | None = None,
) -> EvalRun:
    """Run every case through ``bot`` and score it with every judge.

    Bot exceptions are captured per case (the run continues) and count as failures.
    """
    run = EvalRun()
    for case in cases:
        start = time.perf_counter()
        try:
            response = bot(case.input, case.system)
            latency = time.perf_counter() - start
            verdicts = [judge.evaluate(case, response) for judge in judges]
            result = CaseResult(case, response, verdicts, latency)
        except Exception as exc:  # noqa: BLE001 - we want to keep the run alive
            latency = time.perf_counter() - start
            result = CaseResult(case, "", [], latency, error=f"{type(exc).__name__}: {exc}")
        run.results.append(result)
        if on_result:
            on_result(result)
    run.finished_at = time.time()
    return run
