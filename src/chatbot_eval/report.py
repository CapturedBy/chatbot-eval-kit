"""Render an EvalRun as Markdown or JSON, and compare two runs for regressions."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from chatbot_eval.runner import EvalRun


def to_json(run: EvalRun) -> str:
    payload = {
        "summary": {
            "total": run.total,
            "passed": run.passed,
            "failed": run.failed,
            "pass_rate": round(run.pass_rate, 4),
            "mean_score": round(run.mean_score, 4),
            "started_at": run.started_at,
            "finished_at": run.finished_at,
        },
        "by_tag": {tag: {"passed": p, "total": t} for tag, (p, t) in run.by_tag().items()},
        "results": [
            {
                "id": r.case.id,
                "tags": list(r.case.tags),
                "passed": r.passed,
                "score": round(r.score, 4),
                "latency_s": round(r.latency_s, 3),
                "error": r.error,
                "response": r.response,
                "verdicts": [asdict(v) for v in r.verdicts],
            }
            for r in run.results
        ],
    }
    return json.dumps(payload, indent=2, ensure_ascii=False)


def _truncate(text: str, limit: int = 240) -> str:
    text = text.replace("\n", " ").strip()
    return text if len(text) <= limit else text[: limit - 1] + "…"


def to_markdown(run: EvalRun, title: str = "Chatbot evaluation report") -> str:
    lines = [f"# {title}", ""]
    lines.append(
        f"**{run.passed}/{run.total} passed** ({run.pass_rate:.0%}) · "
        f"mean score {run.mean_score:.2f}"
    )
    lines.append("")

    if run.by_tag():
        lines += ["## By tag", "", "| Tag | Passed | Total | Rate |", "|---|---:|---:|---:|"]
        for tag, (p, t) in run.by_tag().items():
            lines.append(f"| {tag} | {p} | {t} | {p / t:.0%} |")
        lines.append("")

    lines += [
        "## Results",
        "",
        "| Case | Status | Score | Latency | Notes |",
        "|---|---|---:|---:|---|",
    ]
    for r in run.results:
        status = "✅ pass" if r.passed else "❌ fail"
        if r.error:
            note = f"error: {_truncate(r.error, 120)}"
        else:
            note = "; ".join(
                f"{v.judge}: {_truncate(v.reason, 90)}" for v in r.verdicts if not v.passed
            )
        lines.append(f"| `{r.case.id}` | {status} | {r.score:.2f} | {r.latency_s:.2f}s | {note} |")
    lines.append("")

    failures = run.failures()
    if failures:
        lines += ["## Failure details", ""]
        for r in failures:
            lines.append(f"### `{r.case.id}`")
            lines.append("")
            lines.append(f"**Input:** {_truncate(r.case.last_user_message)}")
            lines.append("")
            if r.error:
                lines.append(f"**Error:** `{r.error}`")
            else:
                lines.append(f"**Response:** {_truncate(r.response, 600)}")
                lines.append("")
                for v in r.verdicts:
                    mark = "✅" if v.passed else "❌"
                    lines.append(f"- {mark} **{v.judge}** ({v.score:.2f}): {v.reason}")
            lines.append("")
    return "\n".join(lines)


def compare_runs(baseline_json: str | Path, current_json: str | Path) -> dict:
    """Diff two saved JSON reports. Returns regressions, fixes and unchanged counts."""
    base = json.loads(Path(baseline_json).read_text(encoding="utf-8"))
    curr = json.loads(Path(current_json).read_text(encoding="utf-8"))
    base_map = {r["id"]: r["passed"] for r in base["results"]}
    curr_map = {r["id"]: r["passed"] for r in curr["results"]}

    regressions = sorted(i for i in curr_map if base_map.get(i) is True and not curr_map[i])
    fixes = sorted(i for i in curr_map if base_map.get(i) is False and curr_map[i])
    new = sorted(i for i in curr_map if i not in base_map)
    removed = sorted(i for i in base_map if i not in curr_map)
    return {
        "regressions": regressions,
        "fixes": fixes,
        "new_cases": new,
        "removed_cases": removed,
        "baseline_pass_rate": base["summary"]["pass_rate"],
        "current_pass_rate": curr["summary"]["pass_rate"],
    }
