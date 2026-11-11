"""Every prompt the application sends. Chat templates are the runtime's job: these are only messages."""

from collections.abc import Sequence
from dataclasses import dataclass

from app.generation.base import Message
from app.ingestion.chunker import Chunk
from app.ingestion.language import language_name, question_language

NO_EVIDENCE_MARKER = "[NO-EVIDENCE]"

_QUESTION_ANSWERING_SYSTEM = f"""You answer questions about books, using numbered passages retrieved from them.

Follow these rules:
- Base every factual statement on the passages. Never add facts from memory, even well-known ones.
- Cite the passages you rely on, with their numbers in square brackets, like [1] or [2][3].
- Keep what the author states apart from what you infer. Introduce an inference as such, for example with "this suggests".
- Preserve the author's meaning: don't strengthen, soften or generalize a claim.
- If the passages answer only part of the question, answer that part and say what is missing.
- If the passages don't answer the question at all, begin your reply with {NO_EVIDENCE_MARKER}, then say that the source doesn't contain enough information. Don't guess, and don't answer from general knowledge.
- {{language_rule}}"""  # noqa: E501

_ABSTENTION_CHECK_SYSTEM = "You read replies to questions about books, and say whether each one informs its reader."

# The passages aren't sent: the check reads what the reply gives, not whether the passages support
# it. Asked to weigh the evidence, gpt-oss abstained on questions its passages answer. Asked to
# classify replies as answers or abstentions, gemma4 and qwen3.5 took partial answers that say
# what is missing for abstentions (.specify/bugs/unmarked-abstentions).
_ABSTENTION_CHECK_INSTRUCTIONS = """A reader asked the question below about a book, and got the reply below, written from passages of the book.

Does the reply give the reader any of the information the question asks for?
- YES if it gives what was asked, or some of it, even when it also says that something else is missing. An answer can be a negation, such as "No, he rejects it".
- NO if it only says that the passages don't contain what was asked, perhaps with what they say around it. A vague stand-in, such as "someone" for who, gives nothing.

Reply with one word: YES or NO.

Question: {question}

Reply:
{reply}"""  # noqa: E501

_SUMMARY_SYSTEM = """You write faithful summaries of book chapters, for a reader who needs to rely on them.

Follow these rules:
- Report only what the text says. Never add facts, opinions or context from memory.
- Preserve the author's meaning and argument structure: don't strengthen, soften or generalize a claim.
- Attribute claims to the author, rather than presenting them as established facts.
- {language_rule}"""  # noqa: E501

_MAP_INSTRUCTIONS = """Summarize the passages below, which are consecutive parts of the chapter "{chapter}".

Capture every argument, definition, example and conclusion: another step will combine this
with the rest of the chapter, and whatever you leave out is lost. Write continuous prose, not one
section per passage, in at most {max_words} words. Cover all the passages, up to the last one.

{sources}"""

_COLLAPSE_INSTRUCTIONS = """Merge the partial summaries below, which cover consecutive parts of the chapter "{chapter}",
into one summary of at most {max_words} words. Together they are too long for the next step, so
the limit comes first: keep every argument and conclusion, from the first part to the last, and
cut examples and details until it fits.

{summaries}"""

_FINAL_INSTRUCTIONS = """Write the final summary of the chapter "{chapter}" of "{book}", from the material below.

{sections}

{style}

Aim for about {target_words} words. Draw on the whole material, from its first part to its
last. If the material has nothing for a section, say so in one line. Don't add references or
citations: they are generated afterwards.

{material}"""

_VERIFICATION_INSTRUCTIONS = """Check the summary below against the source passages.

List each claim in the summary that the passages don't support, or that they contradict,
quoting the claim and saying why. If every claim is supported, reply only with: All claims are
supported.

Summary:

{summary}

Source passages:

{sources}"""


def _language_rule(language: str | None) -> str:
    if language:
        return f"Write your reply in {language}, whatever the language of the passages."
    return "Write your reply in the language of the question, whatever the language of the passages."


def _summary_language(language: str | None, book_language: str | None) -> str | None:
    """The language chosen, or the book's. A book stores its language as a code, to be named."""
    return language or (language_name(book_language) if book_language else None)


def _summary_language_rule(language: str | None, book_language: str | None) -> str:
    if target := _summary_language(language, book_language):
        return f"Write in {target}, whatever the language of the text."
    return "Write in the language of the text."


# Shown in the reply's language: asked to translate them, qwen3.5 copied the English headings
# into Portuguese summaries, even with the language named.
_SECTIONS = {
    "English": (
        "Chapter overview",
        "Main thesis",
        "Main arguments",
        "Important concepts and definitions",
        "Supporting examples",
        "Relationships between concepts",
        "Important conclusions",
    ),
    "Portuguese": (
        "Visão geral do capítulo",
        "Tese principal",
        "Argumentos principais",
        "Conceitos e definições importantes",
        "Exemplos de apoio",
        "Relações entre conceitos",
        "Conclusões importantes",
    ),
    "Spanish": (
        "Visión general del capítulo",
        "Tesis principal",
        "Argumentos principales",
        "Conceptos y definiciones importantes",
        "Ejemplos de apoyo",
        "Relaciones entre conceptos",
        "Conclusiones importantes",
    ),
    "French": (
        "Vue d'ensemble du chapitre",
        "Thèse principale",
        "Arguments principaux",
        "Concepts et définitions importants",
        "Exemples à l'appui",
        "Relations entre les concepts",
        "Conclusions importantes",
    ),
    "German": (
        "Überblick über das Kapitel",
        "Hauptthese",
        "Hauptargumente",
        "Wichtige Begriffe und Definitionen",
        "Belegende Beispiele",
        "Beziehungen zwischen den Begriffen",
        "Wichtige Schlussfolgerungen",
    ),
    "Italian": (
        "Panoramica del capitolo",
        "Tesi principale",
        "Argomenti principali",
        "Concetti e definizioni importanti",
        "Esempi a sostegno",
        "Relazioni tra i concetti",
        "Conclusioni importanti",
    ),
}


def _sections(language: str | None) -> str:
    """The required sections, in the reply's language when they are known in it."""
    if language in _SECTIONS:
        headings = "\n".join(f"## {heading}" for heading in _SECTIONS[language])
        return f"Use exactly these sections, as Markdown headings:\n\n{headings}"
    headings = "\n".join(f"## {heading}" for heading in _SECTIONS["English"])
    instruction = "Use exactly these sections, as Markdown headings, translated into the language of your reply"
    return f"{instruction}:\n\n{headings}"


def _describe(chunk: Chunk) -> str:
    parts = [f"Book: {chunk.book_title}", f"Chapter: {chunk.chapter_title}"]
    if chunk.section_title:
        parts.append(f"Section: {chunk.section_title}")
    if chunk.page_start is not None:
        parts.append(f"Pages: {chunk.page_start}-{chunk.page_end}")
    return " | ".join(parts)


def format_passage(number: int, chunk: Chunk) -> str:
    return f"[{number}] {_describe(chunk)}\n{chunk.text}"


def question_answering_messages(question: str, passages: Sequence[Chunk], language: str | None) -> list[Message]:
    """Build the messages for a question.

    Args:
        question: what the user asked.
        passages: the context, numbered from 1 in this order.
        language: the language to answer in. None means the question's, named when it can be
            identified: told only "the language of the question", gpt-oss answered some English
            questions in Spanish.
    """
    context = "\n\n".join(format_passage(number, chunk) for number, chunk in enumerate(passages, start=1))
    system = _QUESTION_ANSWERING_SYSTEM.format(language_rule=_language_rule(language or question_language(question)))
    return [
        Message("system", system),
        Message("user", f"Passages:\n\n{context}\n\nQuestion: {question}"),
    ]


def abstention_check_messages(question: str, reply: str) -> list[Message]:
    """Ask whether a finished reply answers its question, or says the passages can't."""
    return [
        Message("system", _ABSTENTION_CHECK_SYSTEM),
        Message("user", _ABSTENTION_CHECK_INSTRUCTIONS.format(question=question, reply=reply)),
    ]


def map_messages(
    chapter: str, sources: str, max_words: int, language: str | None, book_language: str | None
) -> list[Message]:
    system = _SUMMARY_SYSTEM.format(language_rule=_summary_language_rule(language, book_language))
    user = _MAP_INSTRUCTIONS.format(chapter=chapter, sources=sources, max_words=max_words)
    return [Message("system", system), Message("user", user)]


def collapse_messages(
    chapter: str, summaries: str, max_words: int, language: str | None, book_language: str | None
) -> list[Message]:
    system = _SUMMARY_SYSTEM.format(language_rule=_summary_language_rule(language, book_language))
    user = _COLLAPSE_INSTRUCTIONS.format(chapter=chapter, summaries=summaries, max_words=max_words)
    return [Message("system", system), Message("user", user)]


def final_summary_messages(
    book: str,
    chapter: str,
    material: str,
    target_words: int,
    style: str,
    language: str | None,
    book_language: str | None,
) -> list[Message]:
    system = _SUMMARY_SYSTEM.format(language_rule=_summary_language_rule(language, book_language))
    user = _FINAL_INSTRUCTIONS.format(
        book=book,
        chapter=chapter,
        material=material,
        target_words=target_words,
        style=style,
        sections=_sections(_summary_language(language, book_language)),
    )
    return [Message("system", system), Message("user", user)]


def verification_messages(summary: str, sources: str) -> list[Message]:
    system = "You check summaries against their sources, and report only what the sources fail to support."
    return [
        Message("system", system),
        Message("user", _VERIFICATION_INSTRUCTIONS.format(summary=summary, sources=sources)),
    ]


# Quizzes (specs/003-chapter-quiz, contracts/model-replies.md). The passage comes without a number,
# a section or pages: in the assessment's probe, numbered passages under such headers led 20 of 24
# questions to say "segundo o trecho 7". The reply formats name their keys, with no sample values,
# which a judge once copied instead of reading.

QUIZ_LETTERS = "ABCDE"


@dataclass(frozen=True)
class QuizSource:
    """What a quiz's passage is shown under.

    Attributes:
        book_title: the book.
        author: its author, if known.
        chapter_title: the chapter, in a one-chapter quiz. None in a whole-book quiz, where
            questions mustn't name their chapter.
    """

    book_title: str
    author: str | None
    chapter_title: str | None


_QUIZ_WRITER_SYSTEM = (
    "You write multiple-choice questions for a reader who is studying a book and wants to be graded "
    "on what it says. You write one question at a time, from an excerpt of the book."
)

_QUIZ_WRITER_RULES = """Write one multiple-choice question about what this excerpt says.

Follow these rules:
- The question can be answered from this excerpt alone. Ask about the author's arguments, explanations and evidence: what happened and why, how one claim leads to another, what the author concludes. Don't ask about page numbers, or about anything the excerpt doesn't say.
- Write one right answer, which the excerpt states, or reaches by steps it states.
- Write four wrong answers. Each is wrong according to the excerpt, yet plausible to someone who hasn't read the book.
- Make the five answers alike, so that only knowing the book tells the right one apart: about the same number of words, the same form, and the same amount of detail. The right answer must not be the longest or the most detailed of the five. Say it as briefly as it can be said, and give the wrong ones as much detail.
- Write an explanation of why the right answer is right, saying only what the excerpt says.
- Write the question and the answers as an exam would ask about the book. They may say "the author" or "the book"{chapter_rule}. They must never mention "the excerpt", "the passage" or "the text", and never a number, a section or a page of the book.
- Every answer must make sense on its own. None may refer to the others, as "all of the above", "none of the above" or "both A and B" do.
- Write the question, the answers and the explanation in {language}.

If the excerpt says nothing about the book's subject, as with references, a bibliography, further reading, a list of illustrations or tables, acknowledgements, an index, or a caption that only names its figure, don't write a question.

Reply with only a JSON object. For a question, its keys are "question", "correct" for the right answer, "wrong" for the list of the four wrong answers, and "explanation". When there is nothing to ask about, its only key is "skip", saying why."""  # noqa: E501

_QUIZ_CHAPTER_RULE = ', or "the chapter"'
_QUIZ_WHOLE_BOOK_RULE = ". They never name the chapter the excerpt comes from"

_QUIZ_CHECK_SYSTEM = "You check multiple-choice questions against the excerpt of a book they were written from."

_QUIZ_CHECK_INSTRUCTIONS = """{heading}

{passage}

Question: {question}
{options}

Judging only from the excerpt above, which options does it support as an answer to the question? An option is supported when the excerpt states it, or states the steps that lead to it. There may be none, one or several.

Reply with only a JSON object, whose only key is "supported": the list of the letters of the supported options."""  # noqa: E501

_QUIZ_ANSWER_SYSTEM = "You answer multiple-choice questions about books."

_QUIZ_ANSWER_WITH_PASSAGE = """{heading}

{passage}

Answer this question from the excerpt above.

Question: {question}
{options}

Reply with only a JSON object, whose only key is "answer": the letter of the right option."""

_QUIZ_ANSWER_WITHOUT_PASSAGE = """Answer this question about the book "{book}"{author}.

Question: {question}
{options}

Reply with only a JSON object, whose only key is "answer": the letter of the right option."""


def _quiz_heading(source: QuizSource) -> str:
    author = f", by {source.author}" if source.author else ""
    chapter = f', chapter "{source.chapter_title}"' if source.chapter_title else ""
    return f'An excerpt from "{source.book_title}"{author}{chapter}:'


def lettered_options(options: Sequence[str]) -> str:
    """The options as the reader sees them, A) to E)."""
    return "\n".join(f"{letter}) {option}" for letter, option in zip(QUIZ_LETTERS, options, strict=True))


def quiz_question_messages(passage: str, source: QuizSource, language: str) -> list[Message]:
    """Ask for one question from one passage, or a skip (contracts/model-replies.md § The writer).

    Args:
        passage: the passage's text, alone.
        source: the book, and the chapter in a one-chapter quiz.
        language: the language to write in, by name.
    """
    chapter_rule = _QUIZ_CHAPTER_RULE if source.chapter_title else _QUIZ_WHOLE_BOOK_RULE
    rules = _QUIZ_WRITER_RULES.format(chapter_rule=chapter_rule, language=language)
    return [
        Message("system", _QUIZ_WRITER_SYSTEM),
        Message("user", f"{_quiz_heading(source)}\n\n{passage}\n\n{rules}"),
    ]


def quiz_check_messages(passage: str, source: QuizSource, question: str, options: Sequence[str]) -> list[Message]:
    """Ask which options the passage supports (contracts/model-replies.md § The checker)."""
    user = _QUIZ_CHECK_INSTRUCTIONS.format(
        heading=_quiz_heading(source), passage=passage, question=question, options=lettered_options(options)
    )
    return [Message("system", _QUIZ_CHECK_SYSTEM), Message("user", user)]


def quiz_answer_messages(
    question: str, options: Sequence[str], passage: str | None, source: QuizSource
) -> list[Message]:
    """Ask for the right option's letter, with the passage or without it (§ The comparator)."""
    if passage is None:
        author = f", by {source.author}" if source.author else ""
        user = _QUIZ_ANSWER_WITHOUT_PASSAGE.format(
            book=source.book_title, author=author, question=question, options=lettered_options(options)
        )
    else:
        user = _QUIZ_ANSWER_WITH_PASSAGE.format(
            heading=_quiz_heading(source), passage=passage, question=question, options=lettered_options(options)
        )
    return [Message("system", _QUIZ_ANSWER_SYSTEM), Message("user", user)]
