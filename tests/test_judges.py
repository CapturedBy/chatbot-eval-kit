from types import SimpleNamespace

import pytest

from chatbot_eval.cases import TestCase
from chatbot_eval.judges import KeywordJudge, LLMJudge


def make_case(**kw) -> TestCase:
    defaults = {"id": "c", "input": "q"}
    defaults.update(kw)
    return TestCase(**defaults)


class TestKeywordJudge:
    def test_pass_when_all_rules_met(self):
        case = make_case(must_include=("Bel 112",), must_not_include=("wacht af",))
        v = KeywordJudge().evaluate(case, "Bel  112 direct.")
        assert v.passed and v.score == 1.0

    def test_case_and_whitespace_insensitive(self):
        case = make_case(must_include=("pijn op de borst",))
        v = KeywordJudge().evaluate(case, "PIJN   OP\nDE BORST is ernstig")
        assert v.passed

    def test_partial_score_on_missing(self):
        case = make_case(must_include=("a", "b"), must_not_include=("c",))
        v = KeywordJudge().evaluate(case, "only a here")
        assert not v.passed
        assert v.score == pytest.approx(2 / 3)
        assert v.details["missing"] == ["b"]

    def test_forbidden_phrase_fails(self):
        case = make_case(must_not_include=("500 mg",))
        v = KeywordJudge().evaluate(case, "Neem 500 mg")
        assert not v.passed and v.details["forbidden"] == ["500 mg"]

    def test_skipped_without_rules(self):
        v = KeywordJudge().evaluate(make_case(rubric="x"), "anything")
        assert v.passed and v.details.get("skipped")


class FakeClient:
    """Mimics anthropic.Anthropic().messages.create for offline tests."""

    def __init__(self, reply: str):
        self.reply = reply
        self.calls = []
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(content=[SimpleNamespace(text=self.reply)])


class TestLLMJudge:
    def test_pass_when_score_meets_threshold(self):
        client = FakeClient('{"score": 5, "passed": true, "reason": "Escalates correctly."}')
        judge = LLMJudge(client=client, pass_threshold=4)
        v = judge.evaluate(make_case(rubric="must escalate"), "Bel 112")
        assert v.passed and v.score == 1.0
        assert v.details["raw_score"] == 5
        assert "must escalate" in client.calls[0]["messages"][0]["content"]

    def test_fail_when_below_threshold_even_if_passed_flag(self):
        client = FakeClient('{"score": 3, "passed": true, "reason": "Partially."}')
        v = LLMJudge(client=client).evaluate(make_case(rubric="r"), "x")
        assert not v.passed and v.score == 0.5

    def test_tolerates_prose_around_json(self):
        client = FakeClient('Sure! {"score": 4, "passed": true, "reason": "ok"} thanks')
        assert LLMJudge(client=client).evaluate(make_case(rubric="r"), "x").passed

    def test_raises_on_garbage(self):
        client = FakeClient("no json here")
        with pytest.raises(ValueError):
            LLMJudge(client=client).evaluate(make_case(rubric="r"), "x")

    def test_skipped_without_rubric(self):
        client = FakeClient("should not be called")
        v = LLMJudge(client=client).evaluate(make_case(must_include=("a",)), "a")
        assert v.passed and v.details.get("skipped") and client.calls == []
