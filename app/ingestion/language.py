"""Language identification, for documents that don't declare theirs, and for questions."""

from functools import cache

import py3langid
from py3langid.langid import MODEL_FILE, LanguageIdentifier

_SAMPLE_CHARACTERS = 20_000

_NAMES = {"en": "English", "pt": "Portuguese", "es": "Spanish", "fr": "French", "de": "German", "it": "Italian"}

# A reply's language is refused only when it is identified this surely: a short or mixed text, such
# as a quiz question listing names, can read as anything. Full drafts read at 0.9999 or more.
_MIN_REPLY_CONFIDENCE = 0.9

# A short text is often ambiguous: "Explain recursion." reads as French at 0.17, and an English
# question quoting Portuguese as Portuguese at 0.27. Below this, no language is named at all.
_MIN_QUESTION_CONFIDENCE = 0.5


def normalize_language(code: str) -> str:
    """Reduce a language tag to its ISO 639-1 code: pt-BR and pt_PT are both pt."""
    return code.replace("_", "-").split("-")[0].strip().lower()


def language_name(code: str) -> str | None:
    """Name a language for a prompt. Told "Write in pt", gpt-oss summarized Portuguese in English."""
    return _NAMES.get(normalize_language(code))


def detect_language(text: str) -> str:
    """Identify the language of a text, from a sample of it. The result is deterministic."""
    return py3langid.classify(text[:_SAMPLE_CHARACTERS])[0]


def question_language(text: str) -> str | None:
    """Name the language of a question, or None when it can't be told with confidence."""
    code, confidence = _identifier().classify(text)
    return _NAMES.get(code) if confidence >= _MIN_QUESTION_CONFIDENCE else None


def reply_language(text: str) -> str:
    """Identify the language of a reply, among the ones a reply is asked for in.

    Unrestricted, a Portuguese answer quoting a 19th-century novel can read as Galician.
    """
    return _identifier(restricted=True).classify(text)[0]


def confident_reply_language(text: str) -> str | None:
    """Identify a reply's language as reply_language does, or None when it can't be told surely."""
    code, confidence = _identifier(restricted=True).classify(text)
    return code if confidence >= _MIN_REPLY_CONFIDENCE else None


@cache
def _identifier(restricted: bool = False) -> LanguageIdentifier:
    """Unrestricted for questions: limited to the names above, a Dutch question reads as German."""
    identifier = LanguageIdentifier.from_model_file(MODEL_FILE, norm_probs=True)
    if restricted:
        identifier.set_languages(list(_NAMES))
    return identifier
