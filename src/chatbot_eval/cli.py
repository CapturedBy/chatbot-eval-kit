"""Command-line interface.

Examples:
    chatbot-eval run examples/cases/triage_nl.yaml --bot examples.bots:echo_bot
    chatbot-eval run cases.yaml --bot mybot:answer --judge keyword --judge llm --json out.json
    chatbot-eval compare baseline.json out.json
"""

from __future__ import annotations

import argparse
import importlib
import sys
from pathlib import Path

from chatbot_eval.cases import load_cases
from chatbot_eval.judges import Judge, KeywordJudge, LLMJudge
from chatbot_eval.report import compare_runs, to_json, to_markdown
from chatbot_eval.runner import BotFn, run_eval


def load_bot(spec: str) -> BotFn:
    """Import ``module.path:function`` and return the callable."""
    if ":" not in spec:
        raise SystemExit(f"--bot must look like 'package.module:function', got {spec!r}")
    module_name, func_name = spec.split(":", 1)
    sys.path.insert(0, str(Path.cwd()))
    module = importlib.import_module(module_name)
    try:
        fn = getattr(module, func_name)
    except AttributeError as exc:
        raise SystemExit(f"{module_name} has no attribute {func_name!r}") from exc
    if not callable(fn):
        raise SystemExit(f"{spec} is not callable")
    return fn


def build_judges(names: list[str], model: str) -> list[Judge]:
    judges: list[Judge] = []
    for name in names:
        if name == "keyword":
            judges.append(KeywordJudge())
        elif name == "llm":
            judges.append(LLMJudge(model=model))
        else:
            raise SystemExit(f"Unknown judge {name!r}; choose from: keyword, llm")
    return judges


def cmd_run(args: argparse.Namespace) -> int:
    tags = set(args.tag) if args.tag else None
    cases = load_cases(args.cases, tags=tags)
    if not cases:
        print("No cases matched.", file=sys.stderr)
        return 2

    bot = load_bot(args.bot)
    judges = build_judges(args.judge or ["keyword"], args.model)

    def progress(result):
        mark = "PASS" if result.passed else "FAIL"
        print(f"[{mark}] {result.case.id}  ({result.latency_s:.2f}s)", file=sys.stderr)

    run = run_eval(cases, bot, judges, on_result=progress)

    if args.json:
        Path(args.json).write_text(to_json(run), encoding="utf-8")
    markdown = to_markdown(run)
    if args.markdown:
        Path(args.markdown).write_text(markdown, encoding="utf-8")
    else:
        print(markdown)

    threshold = args.fail_under
    if threshold is not None and run.pass_rate < threshold:
        print(
            f"\nPass rate {run.pass_rate:.0%} is below threshold {threshold:.0%}.",
            file=sys.stderr,
        )
        return 1
    return 0


def cmd_compare(args: argparse.Namespace) -> int:
    diff = compare_runs(args.baseline, args.current)
    print(f"Baseline pass rate: {diff['baseline_pass_rate']:.0%}")
    print(f"Current pass rate:  {diff['current_pass_rate']:.0%}")
    for key in ("regressions", "fixes", "new_cases", "removed_cases"):
        items = diff[key]
        print(f"{key.replace('_', ' ').capitalize()} ({len(items)}): {', '.join(items) or '-'}")
    return 1 if diff["regressions"] else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="chatbot-eval", description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="Run cases against a bot")
    run.add_argument("cases", help="Path to YAML cases file")
    run.add_argument("--bot", required=True, help="Bot callable as module:function")
    run.add_argument(
        "--judge", action="append", choices=["keyword", "llm"], help="Judge(s) to use; repeatable"
    )
    run.add_argument("--model", default="claude-sonnet-4-5", help="Model for the LLM judge")
    run.add_argument("--tag", action="append", help="Only run cases with this tag; repeatable")
    run.add_argument("--json", help="Write JSON report to this path")
    run.add_argument("--markdown", help="Write Markdown report to this path (default: stdout)")
    run.add_argument(
        "--fail-under", type=float, help="Exit 1 if pass rate is below this fraction (e.g. 0.9)"
    )
    run.set_defaults(func=cmd_run)

    cmp_ = sub.add_parser("compare", help="Compare two JSON reports for regressions")
    cmp_.add_argument("baseline")
    cmp_.add_argument("current")
    cmp_.set_defaults(func=cmd_compare)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
