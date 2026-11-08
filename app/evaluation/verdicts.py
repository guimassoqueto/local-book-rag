"""Getting a verdict out of a judge."""

import json
import re
from dataclasses import replace

from app.generation.base import GenerationParameters

JUDGE_ATTEMPTS = 3

# Judges run at temperature 0, where decoding is greedy: a new seed alone repeats the reply.
_RETRY_TEMPERATURE = 0.5

_JSON_OBJECT = re.compile(r"\{.*\}", re.DOTALL)


def attempt_parameters(parameters: GenerationParameters, attempt: int) -> GenerationParameters:
    """The first attempt as configured. A retry samples, or it would get the same malformed reply."""
    if attempt == 0:
        return parameters
    return replace(
        parameters,
        temperature=max(parameters.temperature, _RETRY_TEMPERATURE),
        seed=(parameters.seed or 0) + attempt,
    )


def read_verdict(reply: str) -> dict[str, object]:
    """Find the JSON object in a reply, which can come with text around it. Empty if there is none."""
    match = _JSON_OBJECT.search(reply)
    if match is None:
        return {}
    for candidate in (match.group(), _close_lists(match.group())):
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _close_lists(text: str) -> str:
    """Close the lists left open when the object around them closes.

    gpt-oss can end a list of statements with `"...last."}`, without its `]`. Nothing else is
    repaired: a reply cut off at its limit stays invalid, instead of becoming a shorter verdict.
    """
    repaired: list[str] = []
    closers: list[str] = []
    in_string = escaped = False
    for character in text:
        if in_string:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == '"':
                in_string = False
        elif character == '"':
            in_string = True
        elif character in "[{":
            closers.append("]" if character == "[" else "}")
        elif character in "]}":
            while character == "}" and closers and closers[-1] == "]":
                repaired.append(closers.pop())
            if closers and closers[-1] == character:
                closers.pop()
        repaired.append(character)
    return "".join(repaired)
