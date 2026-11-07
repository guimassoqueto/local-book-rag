"""Every prompt the application sends. Chat templates are the runtime's job: these are only messages."""

from collections.abc import Sequence

from app.generation.base import Message
from app.ingestion.chunker import Chunk
from app.ingestion.language import question_language

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
into one summary of at most {max_words} words. Keep every argument, definition, example and
conclusion, from the first part to the last.

{summaries}"""

_FINAL_INSTRUCTIONS = """Write the final summary of the chapter "{chapter}" of "{book}", from the material below.

Use exactly these sections, as Markdown headings, translated into the language of your reply:

## Chapter overview
## Main thesis
## Main arguments
## Important concepts and definitions
## Supporting examples
## Relationships between concepts
## Important conclusions

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


def _summary_language_rule(language: str | None, book_language: str | None) -> str:
    target = language or book_language
    if target:
        return f"Write in {target}."
    return "Write in the language of the text."


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
        book=book, chapter=chapter, material=material, target_words=target_words, style=style
    )
    return [Message("system", system), Message("user", user)]


def verification_messages(summary: str, sources: str) -> list[Message]:
    system = "You check summaries against their sources, and report only what the sources fail to support."
    return [
        Message("system", system),
        Message("user", _VERIFICATION_INSTRUCTIONS.format(summary=summary, sources=sources)),
    ]
