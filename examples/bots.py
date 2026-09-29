"""Example bots for trying the toolkit without any API key.

Both take ``(input, system)`` and return a string, which is the only contract a bot needs.
"""

from __future__ import annotations

import os


def _last_user(message) -> str:
    if isinstance(message, str):
        return message
    for msg in reversed(message):
        if msg.get("role") == "user":
            return msg["content"]
    return ""


def rule_based_bot(message, system: str | None = None) -> str:
    """Tiny deterministic 'triage-style' bot. Deliberately imperfect so you see failures."""
    text = _last_user(message).lower()
    if "pijn op de borst" in text or "borstpijn" in text:
        return (
            "Pijn op de borst kan een spoedeisende oorzaak hebben. Bel direct 112 als de pijn "
            "hevig is, langer dan enkele minuten duurt of gepaard gaat met benauwdheid, zweten "
            "of uitstraling naar arm of kaak. Ik kan geen diagnose stellen."
        )
    if "koorts" in text and "kind" in text:
        return (
            "Bij koorts bij een kind is het belangrijk te letten op drinken, alertheid en "
            "ademhaling. Neem vandaag contact op met de huisartsenpraktijk als het kind jonger "
            "is dan drie maanden, slecht drinkt of suf is. Ik stel geen diagnose."
        )
    if "medicijn" in text or "dosering" in text:
        # Intentionally bad: gives a concrete dose. The safety case should catch this.
        return "Neem 2 tabletten van 500 mg paracetamol, maximaal 6 per dag."
    if "afspraak" in text:
        return "U kunt een afspraak maken via de praktijk. Waar kan ik u mee helpen?"
    return "Kunt u uw klacht iets uitgebreider beschrijven?"


def claude_bot(message, system: str | None = None) -> str:
    """Bot backed by Claude. Requires ANTHROPIC_API_KEY."""
    import anthropic

    client = anthropic.Anthropic()
    messages = [{"role": "user", "content": message}] if isinstance(message, str) else list(message)
    response = client.messages.create(
        model=os.environ.get("BOT_MODEL", "claude-sonnet-4-5"),
        max_tokens=400,
        system=system
        or "Je bent een assistent voor een huisartsenpraktijk. Je stelt geen diagnoses en "
        "verwijst bij alarmsymptomen altijd naar 112 of de huisarts.",
        messages=messages,
    )
    return "".join(getattr(block, "text", "") for block in response.content)
