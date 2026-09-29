import json

from chatbot_eval import KeywordJudge, TestCase, run_eval, to_json, to_markdown
from chatbot_eval.cli import main
from chatbot_eval.report import compare_runs

CASES = [
    TestCase(id="ok", input="hi", must_include=("hello",), tags=("greet",)),
    TestCase(id="bad", input="dose?", must_not_include=("500 mg",), tags=("safety",)),
    TestCase(id="boom", input="crash", must_include=("x",), tags=("safety",)),
]


def bot(message, system=None):
    if message == "hi":
        return "Hello there"
    if message == "dose?":
        return "Take 500 mg"
    raise RuntimeError("bot exploded")


def test_run_eval_collects_results_and_survives_errors():
    run = run_eval(CASES, bot, [KeywordJudge()])
    assert run.total == 3 and run.passed == 1 and run.failed == 2
    by_id = {r.case.id: r for r in run.results}
    assert by_id["ok"].passed
    assert not by_id["bad"].passed
    assert by_id["boom"].error and "bot exploded" in by_id["boom"].error
    assert run.by_tag() == {"greet": (1, 1), "safety": (0, 2)}


def test_reports_render(tmp_path):
    run = run_eval(CASES, bot, [KeywordJudge()])
    md = to_markdown(run)
    assert "1/3 passed" in md and "`boom`" in md and "Failure details" in md
    data = json.loads(to_json(run))
    assert data["summary"]["failed"] == 2
    assert data["by_tag"]["safety"] == {"passed": 0, "total": 2}


def test_compare_runs_detects_regressions(tmp_path):
    good = run_eval(CASES[:1], lambda m, s: "hello", [KeywordJudge()])
    worse = run_eval(CASES[:1], lambda m, s: "bye", [KeywordJudge()])
    base = tmp_path / "base.json"
    curr = tmp_path / "curr.json"
    base.write_text(to_json(good))
    curr.write_text(to_json(worse))
    diff = compare_runs(base, curr)
    assert diff["regressions"] == ["ok"] and diff["fixes"] == []


def test_cli_run_with_example_bot(tmp_path, monkeypatch):
    import pathlib

    repo = pathlib.Path(__file__).resolve().parents[1]
    monkeypatch.chdir(repo)
    out_json = tmp_path / "out.json"
    code = main(
        [
            "run",
            "examples/cases/triage_nl.yaml",
            "--bot",
            "examples.bots:rule_based_bot",
            "--judge",
            "keyword",
            "--json",
            str(out_json),
            "--markdown",
            str(tmp_path / "out.md"),
        ]
    )
    assert code == 0
    data = json.loads(out_json.read_text())
    ids = {r["id"]: r["passed"] for r in data["results"]}
    assert ids["chest-pain-escalates"] is True
    assert ids["no-dosing-advice"] is False  # the demo bot deliberately fails this


def test_cli_fail_under_exit_code(tmp_path, monkeypatch):
    import pathlib

    monkeypatch.chdir(pathlib.Path(__file__).resolve().parents[1])
    code = main(
        [
            "run",
            "examples/cases/triage_nl.yaml",
            "--bot",
            "examples.bots:rule_based_bot",
            "--fail-under",
            "1.0",
            "--markdown",
            str(tmp_path / "x.md"),
        ]
    )
    assert code == 1
