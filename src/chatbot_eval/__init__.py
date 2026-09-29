"""chatbot-eval-kit: evaluate LLM chatbots with YAML test cases and pluggable judges."""

from chatbot_eval.cases import TestCase, load_cases
from chatbot_eval.judges import Judge, KeywordJudge, LLMJudge, Verdict
from chatbot_eval.report import to_json, to_markdown
from chatbot_eval.runner import CaseResult, EvalRun, run_eval

__all__ = [
    "CaseResult",
    "EvalRun",
    "Judge",
    "KeywordJudge",
    "LLMJudge",
    "TestCase",
    "Verdict",
    "load_cases",
    "run_eval",
    "to_json",
    "to_markdown",
]

__version__ = "0.1.0"
