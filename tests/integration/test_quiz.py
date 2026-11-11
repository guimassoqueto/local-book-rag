"""Runs the configured LLM for real on the quiz's prompts and readers (constitution V, research R14).

The passages are written into this file, from John Stuart Mill's *On Liberty* (Project Gutenberg,
public domain), so that the test needs no book in the library. These tests check formats; the
`quiz` experiment checks quality, on whole chapters.
"""

import os
from dataclasses import replace

import pytest

from app.config.loader import load_settings
from app.config.settings import EnvironmentSettings
from app.generation.factory import create_llm_provider
from app.generation.prompts import QuizSource
from app.generation.quiz import Draft, QuizWriter, Skip
from app.ingestion.language import confident_reply_language
from app.utils.ollama_runtime import OllamaRuntime
from tests.fakes import make_chunk

pytestmark = pytest.mark.integration

MAXIMS = """The maxims are, first, that the individual is not accountable to society
for his actions, in so far as these concern the interests of no person
but himself. Advice, instruction, persuasion, and avoidance by other
people if thought necessary by them for their own good, are the only
measures by which society can justifiably express its dislike or
disapprobation of his conduct. Secondly, that for such actions as are
prejudicial to the interests of others, the individual is accountable
and may be subjected either to social or to legal punishments, if
society is of opinion that the one or the other is requisite for its
protection.

In the first place, it must by no means be supposed, because damage, or
probability of damage, to the interests of others, can alone justify the
interference of society, that therefore it always does justify such
interference. In many cases, an individual, in pursuing a legitimate
object, necessarily and therefore legitimately causes pain or loss to
others, or intercepts a good which they had a reasonable hope of
obtaining. Such oppositions of interest between individuals often arise
from bad social institutions, but are unavoidable while those
institutions last; and some would be unavoidable under any institutions.
Whoever succeeds in an overcrowded profession, or in a competitive
examination; whoever is preferred to another in any contest for an
object which both desire, reaps benefit from the loss of others, from
their wasted exertion and their disappointment."""

# A list of references, as a book's back matter holds: nothing about the book's subject to ask.
BIBLIOGRAPHY = """Further reading

Mill, John Stuart. A System of Logic, Ratiocinative and Inductive. London: John W. Parker, 1843.
Mill, John Stuart. Principles of Political Economy. London: John W. Parker, 1848.
Mill, John Stuart. Considerations on Representative Government. London: Parker, Son, and Bourn, 1861.
Humboldt, Wilhelm von. The Sphere and Duties of Government. Trans. Joseph Coulthard. London: John Chapman, 1854.
Tocqueville, Alexis de. Democracy in America. Trans. Henry Reeve. 2 vols. London: Saunders and Otley, 1835-1840.
Comte, Auguste. Système de politique positive. 4 vols. Paris: Carilian-Goeury, 1851-1854.
Bentham, Jeremy. An Introduction to the Principles of Morals and Legislation. London: T. Payne, 1789."""

SOURCE = QuizSource(book_title="On Liberty", author="John Stuart Mill", chapter_title="CHAPTER V. APPLICATIONS")


@pytest.fixture
def settings():
    return load_settings(EnvironmentSettings().config_dir)


@pytest.fixture
def writer(settings, monkeypatch):
    monkeypatch.setenv("OLLAMA_BASE_URL", os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434"))
    runtime = OllamaRuntime(EnvironmentSettings().ollama_base_url, settings.ollama.request_timeout_seconds)
    quiz = settings.generation.quiz
    return QuizWriter(quiz, settings.generation.context.safety_margin, create_llm_provider(settings, runtime))


def passage(text):
    return replace(make_chunk(text, book_id="on_liberty", section=None, page_start=None), book_title="On Liberty")


def test_an_english_passage_gives_a_question_in_the_language_named(writer, settings):
    results = []
    for seed in range(settings.generation.quiz.attempts_per_passage):
        result = writer.write(passage(MAXIMS), SOURCE, "Portuguese", seed=seed)
        results.append(result)
        if isinstance(result, Draft):
            break

    draft = results[-1]
    assert isinstance(draft, Draft), f"no question in {len(results)} attempts: {results}"
    assert len(draft.wrong) == 4
    text = " ".join((draft.question, draft.correct, *draft.wrong, draft.explanation))
    assert confident_reply_language(text) == "pt"


def test_a_bibliography_is_skipped(writer):
    assert isinstance(writer.write(passage(BIBLIOGRAPHY), SOURCE, "English", seed=0), Skip)


# The key check and the comparator (FR-030): two cases on the passage above, one sound, one with a
# deliberately wrong key.

QUESTION = "According to the author, when may society punish an individual for his actions?"
OPTIONS = (
    "When his actions are prejudicial to the interests of others.",
    "Whenever society dislikes or disapproves of his conduct.",
    "Only when his actions concern no one's interests but his own.",
    "Whenever he refuses advice, instruction or persuasion from others.",
    "Only when he succeeds in a competitive examination at another's loss.",
)
SOUND_KEY = "A"
WRONG_KEY = "B"


@pytest.fixture
def checker(settings, monkeypatch):
    monkeypatch.setenv("OLLAMA_BASE_URL", os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434"))
    runtime = OllamaRuntime(EnvironmentSettings().ollama_base_url, settings.ollama.request_timeout_seconds)
    quiz = settings.generation.quiz
    return QuizWriter(
        quiz,
        settings.generation.context.safety_margin,
        create_llm_provider(settings, runtime),
        checker=create_llm_provider(
            settings, runtime, model=quiz.check.model or settings.llm.model, reasoning=quiz.check.reasoning
        ),
    )


@pytest.mark.parametrize(("key", "accepted"), [(SOUND_KEY, True), (WRONG_KEY, False)])
def test_the_checks_verdict_is_readable_on_a_sound_and_a_flawed_key(checker, key, accepted):
    verdict = checker.check(QUESTION, OPTIONS, key, passage(MAXIMS), SOURCE, seed=0)

    assert verdict.readable
    assert verdict.accepted is accepted


@pytest.mark.parametrize("with_passage", [True, False])
def test_the_comparators_answer_is_readable_with_and_without_the_passage(checker, with_passage):
    answer = checker.answer(QUESTION, OPTIONS, passage(MAXIMS) if with_passage else None, SOURCE, seed=0)

    assert answer in tuple("ABCDE")
    if with_passage:
        assert answer == SOUND_KEY
