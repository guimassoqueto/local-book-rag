"""Language identification, for documents that don't declare theirs."""

import py3langid

_SAMPLE_CHARACTERS = 20_000


def normalize_language(code: str) -> str:
    """Reduce a language tag to its ISO 639-1 code: pt-BR and pt_PT are both pt."""
    return code.replace("_", "-").split("-")[0].strip().lower()


def detect_language(text: str) -> str:
    """Identify the language of a text, from a sample of it. The result is deterministic."""
    return py3langid.classify(text[:_SAMPLE_CHARACTERS])[0]
