import pytest

from chatbot_eval.cases import CaseValidationError, load_cases, parse_case


def test_parse_minimal_case():
    case = parse_case({"id": "a", "input": "hi", "must_include": "hello"})
    assert case.id == "a"
    assert case.must_include == ("hello",)
    assert case.last_user_message == "hi"


def test_multi_turn_last_user_message():
    case = parse_case(
        {
            "id": "mt",
            "input": [
                {"role": "user", "content": "first"},
                {"role": "assistant", "content": "reply"},
                {"role": "user", "content": "second"},
            ],
            "rubric": "anything",
        }
    )
    assert case.last_user_message == "second"


@pytest.mark.parametrize(
    "raw, message",
    [
        ({"input": "x", "rubric": "r"}, "non-empty string 'id'"),
        ({"id": "x"}, "missing 'input'"),
        ({"id": "x", "input": "y"}, "at least one of"),
        ({"id": "x", "input": 5, "rubric": "r"}, "must be a string or message list"),
        ({"id": "x", "input": [{"role": "user"}], "rubric": "r"}, "role/content"),
        ({"id": "x", "input": "y", "must_include": 3}, "must be a string or list"),
    ],
)
def test_validation_errors(raw, message):
    with pytest.raises(CaseValidationError, match=message):
        parse_case(raw)


def test_load_cases_from_yaml(tmp_path):
    f = tmp_path / "cases.yaml"
    f.write_text(
        """
cases:
  - id: one
    input: hi
    must_include: [a]
    tags: [safety]
  - id: two
    input: hi
    rubric: be nice
    tags: [tone]
""",
        encoding="utf-8",
    )
    assert [c.id for c in load_cases(f)] == ["one", "two"]
    assert [c.id for c in load_cases(f, tags={"safety"})] == ["one"]


def test_load_cases_rejects_duplicate_ids(tmp_path):
    f = tmp_path / "dup.yaml"
    f.write_text("- {id: a, input: x, rubric: r}\n- {id: a, input: y, rubric: r}\n")
    with pytest.raises(CaseValidationError, match="duplicate"):
        load_cases(f)


def test_example_cases_file_is_valid():
    from pathlib import Path

    path = Path(__file__).resolve().parents[1] / "examples" / "cases" / "triage_nl.yaml"
    cases = load_cases(path)
    assert len(cases) >= 5
    assert all(c.rubric for c in cases)
