"""Exact, prefixed commands only; unknown speech has no side effects."""

import re

COMMANDS = {
    "cogni who is this": "identify",
    "cogni tell me more": "context",
    "cogni when did i last see them": "history",
    "cogni repeat": "repeat",
    "cogni stop": "stop",
    "cogni pause recognition": "pause",
    "cogni resume recognition": "resume",
}


def parse_command(text):
    if not isinstance(text, str) or "[unk]" in text.lower():
        return None
    phrase = " ".join(re.sub(r"[^a-z ]", " ", text.lower()).split())
    if phrase.startswith("computer "):
        phrase = "cogni " + phrase[len("computer ") :]
    return COMMANDS.get(phrase)
