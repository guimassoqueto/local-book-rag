"""Writing quiz questions, one from each passage, and reading what the model replies.

The application owns everything the assessment's probe saw the model do badly: which passages,
which letter is right, the order and the score live in app/services/quiz_service.py. The model only
writes a question with one right answer and four wrong ones, and never sees a letter. This module
sends it the passage, reads its reply, and refuses a question that isn't in form, by kind, so the
service can write it again and the measurement can count why (contracts/model-replies.md).
"""

import json
import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Literal

from app.config.settings import QuizConfig
from app.generation.base import FINISHED_BY_LENGTH, Generation, GenerationParameters, LLMProvider, Message
from app.generation.prompts import (
    QUIZ_LETTERS,
    QuizSource,
    quiz_answer_messages,
    quiz_check_messages,
    quiz_question_messages,
)
from app.ingestion.chunker import Chunk
from app.ingestion.language import confident_reply_language, language_name

RefusalKind = Literal[
    "unreadable",
    "cut_off",
    "blank_field",
    "wrong_count",
    "repeated_option",
    "cross_reference",
    "passage_reference",
    "wrong_language",
]
REFUSAL_KINDS: tuple[RefusalKind, ...] = RefusalKind.__args__  # type: ignore[attr-defined]

_WRONG_ANSWERS = 4
_CHECK_RETRY_TEMPERATURE = 0.5
_CHECK_RETRY_SEED_STEP = 7919  # a new seed for the retry, away from the ones a run uses per attempt


@dataclass(frozen=True)
class Draft:
    """A question as the model wrote it, in form. It has no letters yet."""

    question: str
    correct: str
    wrong: tuple[str, ...]
    explanation: str


@dataclass(frozen=True)
class Skip:
    """The model found nothing to ask about in the passage (FR-007)."""

    reason: str


@dataclass(frozen=True)
class Refusal:
    """A reply that can't be read, or a question not in form (FR-010)."""

    kind: RefusalKind


@dataclass(frozen=True)
class PassedOver:
    """The passage doesn't fit in the window with its instructions, so it was never sent (FR-011)."""

    tokens: int


@dataclass(frozen=True)
class CheckVerdict:
    """The key check's reading of a question.

    Attributes:
        supported: the letters of the options the checker found the passage supports.
        accepted: True only when that is exactly the key.
        readable: False when the reply couldn't be read, even asked again. The question is then
            shown anyway: the passage shown after submission stays the reader's safeguard.
    """

    supported: tuple[str, ...]
    accepted: bool
    readable: bool


UNREADABLE_VERDICT = CheckVerdict(supported=(), accepted=False, readable=False)


class QuizWriter:
    """Talks to the models for a quiz: the writer, the checker, and the comparator.

    Args:
        config: generation.quiz.
        safety_margin: generation.context.safety_margin.
        llm: the writer, which also answers as the comparator.
        checker: the key check's provider, with its own reasoning setting. None when the check
            has none.
    """

    def __init__(
        self, config: QuizConfig, safety_margin: float, llm: LLMProvider, checker: LLMProvider | None = None
    ) -> None:
        self._config = config
        self._safety_margin = safety_margin
        self._llm = llm
        self._checker = checker

    @property
    def model(self) -> str:
        return self._llm.model

    @property
    def checker_model(self) -> str | None:
        return self._checker.model if self._checker is not None else None

    def write(
        self,
        chunk: Chunk,
        source: QuizSource,
        language: str,
        forbidden_titles: Sequence[str] = (),
        seed: int | None = None,
    ) -> Draft | Skip | Refusal | PassedOver:
        """Make one attempt at a question from a passage.

        Args:
            chunk: the passage.
            source: what it is shown under.
            language: the language to write in, by name.
            forbidden_titles: titles the question mustn't name, besides the passage's section:
                the chapter's, in a whole-book quiz.
            seed: fixes the sampling, for the measurement.

        Raises:
            ServiceUnavailableError, ModelNotFoundError: from the provider.
        """
        messages = quiz_question_messages(chunk.text, source, language)
        tokens = sum(self._llm.count_tokens(message.content) for message in messages)
        if tokens > self._budget(self._llm, self._config.max_tokens):
            return PassedOver(tokens)
        parameters = GenerationParameters(self._config.temperature, self._config.max_tokens, seed)
        generation = self._llm.generate(messages, parameters)
        titles = [*forbidden_titles, *([chunk.section_title] if chunk.section_title else [])]
        return read_draft(generation, language, titles)

    def check(
        self,
        question: str,
        options: Sequence[str],
        key: str,
        chunk: Chunk,
        source: QuizSource,
        seed: int | None = None,
    ) -> CheckVerdict:
        """Ask the checker which options the passage supports (contracts/model-replies.md).

        A reply that can't be read is asked again once, sampling, with a new seed.
        """
        if self._checker is None:
            raise AssertionError("the key check needs a checker's provider")
        messages = quiz_check_messages(chunk.text, source, question, options)
        verdict = self._ask_checker(messages, key, 0, seed)
        if verdict.readable:
            return verdict
        retry_seed = None if seed is None else seed + _CHECK_RETRY_SEED_STEP
        return self._ask_checker(messages, key, _CHECK_RETRY_TEMPERATURE, retry_seed)

    def answer(
        self,
        question: str,
        options: Sequence[str],
        chunk: Chunk | None,
        source: QuizSource,
        seed: int | None = None,
    ) -> str | None:
        """Have the writer answer a question, with its passage or without it (the comparator).

        Returns:
            The letter it chose, or None when its reply can't be read.
        """
        messages = quiz_answer_messages(question, options, chunk.text if chunk else None, source)
        generation = self._llm.generate(messages, GenerationParameters(0, self._config.max_tokens, seed))
        return read_answer(generation.text)

    def _ask_checker(self, messages: list[Message], key: str, temperature: float, seed: int | None) -> CheckVerdict:
        assert self._checker is not None
        parameters = GenerationParameters(temperature, self._config.check.max_tokens, seed)
        return read_check(self._checker.generate(messages, parameters).text, key)

    def _budget(self, llm: LLMProvider, max_tokens: int) -> int:
        return int(llm.context_size() * (1 - self._safety_margin)) - max_tokens


# Reading replies


def first_object(text: str) -> dict[str, Any] | None:
    """The first JSON object in a reply, which may come in code fences or among text."""
    decoder = json.JSONDecoder()
    for match in re.finditer(r"\{", text):
        try:
            parsed, _ = decoder.raw_decode(text, match.start())
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    return None


def read_draft(
    generation: Generation, named_language: str, forbidden_titles: Sequence[str] = ()
) -> Draft | Skip | Refusal:
    """Read a writer's reply, and check the question's form (FR-010).

    Args:
        generation: the reply.
        named_language: the language the question was asked for, by name.
        forbidden_titles: section and chapter titles the question and options mustn't name.
    """
    if generation.stats.finish_reason == FINISHED_BY_LENGTH:
        return Refusal("cut_off")
    content = first_object(generation.text)
    if content is None:
        return Refusal("unreadable")
    if "skip" in content:
        return Skip(str(content["skip"]).strip())

    fields = {name: content.get(name) for name in ("question", "correct", "explanation")}
    if any(value is not None and not isinstance(value, str) for value in fields.values()):
        return Refusal("unreadable")
    if any(not value or not value.strip() for value in fields.values()):
        return Refusal("blank_field")
    wrong = content.get("wrong")
    if not isinstance(wrong, list):
        return Refusal("wrong_count")
    if not all(isinstance(answer, str) for answer in wrong):
        return Refusal("unreadable")
    # gpt-oss:20b ends the list with an empty fifth string in most replies: an empty string is no
    # answer, so only the written ones are counted.
    wrong = [answer for answer in wrong if answer.strip()]
    if len(wrong) != _WRONG_ANSWERS:
        return Refusal("wrong_count")

    draft = Draft(
        question=fields["question"].strip(),  # type: ignore[union-attr]
        correct=fields["correct"].strip(),  # type: ignore[union-attr]
        wrong=tuple(answer.strip() for answer in wrong),
        explanation=fields["explanation"].strip(),  # type: ignore[union-attr]
    )
    options = (draft.correct, *draft.wrong)
    if len({_comparable(option) for option in options}) < len(options):
        return Refusal("repeated_option")
    if any(refers_to_other_options(option) for option in options):
        return Refusal("cross_reference")
    if any(points_to_passage(text, forbidden_titles) for text in (draft.question, *options)):
        return Refusal("passage_reference")
    if _in_another_language(draft, named_language):
        return Refusal("wrong_language")
    return draft


def read_check(text: str, key: str) -> CheckVerdict:
    """Read a checker's reply: the question is accepted only when the list is exactly its key."""
    content = first_object(text)
    supported = content.get("supported") if content is not None else None
    if not isinstance(supported, list):
        return UNREADABLE_VERDICT
    letters: list[str] = []
    for item in supported:
        letter = item.strip().upper() if isinstance(item, str) else ""
        if len(letter) == 1 and letter in QUIZ_LETTERS and letter not in letters:
            letters.append(letter)
    return CheckVerdict(supported=tuple(letters), accepted=letters == [key], readable=True)


def read_answer(text: str) -> str | None:
    """Read a comparator's reply: one letter, A to E, from its JSON object, or None.

    The letter isn't searched for in free text, which would misread Portuguese: "A resposta é C"
    starts with the article "A".
    """
    content = first_object(text)
    answer = content.get("answer") if content is not None else None
    if not isinstance(answer, str):
        return None
    letter = answer.strip().upper()
    return letter if len(letter) == 1 and letter in QUIZ_LETTERS else None


def _comparable(option: str) -> str:
    """An option's text as compared for repeats: casefolded, spacing collapsed, final punctuation off."""
    return " ".join(option.casefold().split()).rstrip(" .;:!?…")


def _in_another_language(draft: Draft, named_language: str) -> bool:
    """Whether the draft is identified with confidence as another of the interface languages.

    A language outside them can't be identified, and isn't checked.
    """
    text = " ".join((draft.question, draft.correct, *draft.wrong, draft.explanation))
    found = confident_reply_language(text)
    return found is not None and language_name(found) != named_language and named_language in _KNOWN_NAMES


_KNOWN_NAMES = {name for code in ("en", "pt", "es", "fr", "de", "it") if (name := language_name(code))}


# Options that depend on the others (FR-009). The lists grow from what the measurement finds.

_CROSS_REFERENCE_PHRASES = re.compile(
    r"\b(?:"
    r"all of the above|none of the above|all the above|both of the above|neither of the above"
    r"|all of these|none of these|all the options|all of the options|none of the options"
    r"|todas as anteriores|nenhuma das anteriores|todas as alternativas|nenhuma das alternativas"
    r"|todas as op[çc][õo]es|nenhuma das op[çc][õo]es|todas as respostas|nenhuma das respostas"
    r"|ambas as anteriores|todas acima|nenhuma das acima|todas as acima"
    r"|todas las anteriores|ninguna de las anteriores|todas las opciones|ninguna de las opciones"
    r"|todas las respuestas|ninguna de las respuestas|ambas anteriores"
    r"|toutes les r[ée]ponses|aucune des r[ée]ponses|toutes les propositions|aucune des propositions"
    r"|toutes les options|aucune des options|toutes les pr[ée]c[ée]dentes|aucune des pr[ée]c[ée]dentes"
    r"|keine der (?:oben|obigen|genannten|anderen|vorherigen|vorigen|antworten|optionen|aussagen|m[öo]glichkeiten)"
    r"|alle (?:oben|obigen|genannten|vorherigen|antworten|optionen|aussagen|m[öo]glichkeiten)"
    r"|nessuna delle (?:precedenti|risposte|opzioni|alternative|altre|sopra)"
    r"|tutte le (?:precedenti|risposte|opzioni|alternative)"
    r")\b",
    re.IGNORECASE,
)
_OPTION_WORDS = (
    r"op[çc][ãa]o|alternativa|resposta|letra|option|answer|choice|letter|opci[óo]n|respuesta"
    r"|r[ée]ponse|proposition|antwort|m[öo]glichkeit|opzione|risposta|lettera"
)
# A capital letter alone counts only next to a word for "option", or joined to another: "vitamin A"
# and Portuguese's article "a" don't.
_LETTER_AFTER_OPTION_WORD = re.compile(rf"\b(?i:{_OPTION_WORDS})\s+\(?[A-E]\)?(?![\w-])")
_LETTERS_JOINED = re.compile(
    r"(?<![\w-])\(?[A-E]\)?\s*(?:,|e|and|y|et|und|ed|ou|or|o|oder|nor|né)\s+\(?[A-E]\)?(?![\w-])"
)
_LOWERCASE_LETTERS_JOINED = re.compile(r"(?<![\w-])[a-e]\)\s*(?:,|e|and|y|et|und|ed|ou|or|o|oder)\s+[a-e]\)")


def refers_to_other_options(option: str) -> bool:
    """Whether an option is right or wrong according to the others (FR-009)."""
    return bool(
        _CROSS_REFERENCE_PHRASES.search(option)
        or _LETTER_AFTER_OPTION_WORD.search(option)
        or _LETTERS_JOINED.search(option)
        or _LOWERCASE_LETTERS_JOINED.search(option)
    )


# Questions that point to where their answer is (FR-004). "Trecho" is also a stretch of road or
# railway in Portuguese, and "the passage of" an act is its passing in English, so a word for the
# passage counts only with a number or a pointer.

_PASSAGE_WORDS = (
    r"trecho|passagem|excerto|fragmento|passage|excerpt|extract|pasaje|extracto|extrait"
    r"|abschnitt|auszug|textstelle|brano|estratto"
)
_PASSAGE_WITH_NUMBER = re.compile(
    rf"\b(?:{_PASSAGE_WORDS}|texto|text|texte|testo)\s+(?:n[º°.o]?\s*)?\d+", re.IGNORECASE
)
_POINTED_PASSAGE = re.compile(
    r"\b(?:"
    # Portuguese: "segundo o trecho", "de acordo com a passagem", "no excerto", "neste texto"
    r"(?:segundo|conforme|de acordo com)\s+(?:[oa]s?|este|esta|esse|essa)\s+"
    r"(?:trechos?|passagens?|excertos?|fragmentos?|textos?)"
    r"|(?:com base|baseado|apresentad[oa])\s+n(?:[oa]s?|este|esta|esse|essa)\s+"
    r"(?:trechos?|passagens?|excertos?|fragmentos?|textos?)"
    r"|(?:no|na|nos|nas|neste|nesta|nesse|nessa|deste|desta|desse|dessa|este|esta|esse|essa)\s+"
    r"(?:(?:trechos?|passagens?|textos?)(?!\s+(?:d[aoe]s?|entre)\b)|excertos?|fragmentos?)"
    r"|(?:trechos?|passagens?|excertos?|fragmentos?|textos?)\s+(?:acima|anterior|citad[oa]|apresentad[oa]|lid[oa])"
    # "ao fim do trecho", found by the measurement's reading
    r"|(?:fim|final|início|inicio|começo|meio)\s+d[oa]s?\s+(?:trechos?|passagens?|excertos?|fragmentos?|textos?)"
    # English: "according to the passage", "in this excerpt", "the text above"
    r"|(?:the|this|that|above|following|given)\s+(?:passage|excerpt|extract|text)(?!\s+of\b)"
    # Spanish: "según el fragmento", "en este pasaje", "el texto anterior"
    r"|(?:según|de acuerdo con|conforme a)\s+(?:el|la|este|esta)?\s*(?:pasaje|fragmento|extracto|texto)"
    r"|(?:en el|en este|en esta|este|esta|del)\s+(?:pasaje|fragmento|extracto|texto)(?!\s+de\b)"
    # French: "selon le passage", "dans cet extrait", "le texte ci-dessus"
    r"|(?:selon|d'après|dans)\s+(?:le|la|l'|ce|cet|cette)\s*(?:passage|extrait|texte)"
    r"|(?:passage|extrait|texte)\s+ci-dessus"
    # German: "laut dem Abschnitt", "in diesem Auszug", "im Text"
    r"|(?:laut|gemäß|nach|in)\s+(?:dem|diesem|der|dieser)\s+(?:abschnitt|auszug|textstelle|text)"
    r"|im\s+(?:abschnitt|auszug|text)\b"
    # Italian: "secondo il brano", "nel passo", "in questo estratto"
    r"|(?:secondo|in)\s+(?:il|lo|la|questo|questa)\s+(?:brano|passo|estratto|testo)"
    r"|(?:nel|nello|nella|del)\s+(?:brano|passo|estratto|testo)"
    r")\b",
    re.IGNORECASE,
)
_PAGE_NUMBER = re.compile(r"(?:\b(?:p[áa]ginas?|pages?|p[áa]g|pp?|seiten?)\.?|\bS\.)\s*\d+", re.IGNORECASE)
# Words for a chapter or a section, before a title. "Parte" and "part" count only with a number:
# "a maior parte do Japão" names no part of the book.
_STRUCTURE_WORDS = (
    r"cap[íi]tulos?|se[çc][ãa]o|se[çc][õo]es|chapters?|sections?|secci[óo]n|apartado|chapitre"
    r"|kapitel|capitolo|sezione"
)
_NUMBERED_TITLE = re.compile(
    rf"^(?P<prefix>(?:{_STRUCTURE_WORDS}|parte|part|partie|teil)\s+(?:\d+|[ivxlcdm]+)\b)[\s.:\-–—]*(?P<name>.*)$",
    re.IGNORECASE,
)
_TITLE_CONNECTORS = (
    r"intitulad[oa]|chamad[oa]|denominad[oa]|titled|entitled|called|named|sobre|about|on|de|da|do|of|"
    r"o|a|the|el|la|le|der|die|das|il|lo"
)
_OPEN_QUOTES = "\"“«‘'„"
_CLOSE_QUOTES = "\"”»’'“"


def points_to_passage(text: str, forbidden_titles: Sequence[str] = ()) -> bool:
    """Whether a question or an option points to where its answer is (FR-004)."""
    if _PASSAGE_WITH_NUMBER.search(text) or _POINTED_PASSAGE.search(text) or _PAGE_NUMBER.search(text):
        return True
    return any(_names_title(text, title) for title in forbidden_titles if title and title.strip())


def _names_title(text: str, title: str) -> bool:
    """Whether a text names a section or chapter, rather than only its subject.

    Titles are mostly subjects, such as "Japão" or "A Revolução Industrial", which a question may
    well ask about. A title counts when it is quoted, follows a word for a chapter or section, or
    comes with its number, as "Capítulo 3" does.
    """
    title = " ".join(title.split())
    numbered = _NUMBERED_TITLE.match(title)
    names = [title]
    if numbered:
        prefix = re.escape(numbered.group("prefix")).replace(r"\ ", r"\s+")
        if re.search(rf"(?<!\w){prefix}(?!\w)", text, re.IGNORECASE):
            return True
        if numbered.group("name").strip():
            names.append(numbered.group("name").strip())
    for name in names:
        escaped = re.escape(name).replace(r"\ ", r"\s+")
        quoted = rf"[{_OPEN_QUOTES}]\s*{escaped}\s*[{_CLOSE_QUOTES}]"
        after_word = (
            rf"\b(?:{_STRUCTURE_WORDS})\s+(?:(?:{_TITLE_CONNECTORS})\s+){{0,2}}[{_OPEN_QUOTES}]?\s*{escaped}(?!\w)"
        )
        if re.search(quoted, text, re.IGNORECASE) or re.search(after_word, text, re.IGNORECASE):
            return True
    return False
