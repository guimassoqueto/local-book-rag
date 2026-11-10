"""Probe for the chapter-quiz assessment: can the default LLM write A-E questions from real chapters?

Read-only: loads chunks and calls the model, writes only to /tmp/quiz_probe in the app container.
Run inside the app container: python /tmp/quiz_probe.py
"""

import json
import re
import sys
import time
from pathlib import Path

import ollama

from app.container import build_container
from app.generation.base import GenerationParameters, Message
from app.generation.prompts import format_passage

BOOK_ID = "book_001"
CHAPTERS = [int(x) for x in sys.argv[1].split(",")] if len(sys.argv) > 1 else [2, 4, 7]
QUESTIONS_PER_BATCH = 3
MAX_TOKENS = 3000
SEED = 0
LETTERS = "ABCDE"
OUT = Path("/tmp/quiz_probe")
OUT.mkdir(exist_ok=True)

SYSTEM = "You write multiple-choice questions that test whether a reader understood a book."

INSTRUCTIONS = """Write {k} multiple-choice questions about the passages below, which are consecutive parts of the chapter "{chapter}" of "{book}".

Rules:
- Each question has exactly five options, A to E, and exactly one of them is correct according to the passages.
- The other four options are wrong according to the passages, yet plausible to someone who hasn't read them.
- Ask about what the passages say: the author's arguments, explanations and evidence. Don't ask about page numbers, and don't ask what can be answered from general knowledge alone.
- Each question is answered by a single passage: give its number.
- Write the questions, options and explanations in {language}.

Reply with JSON only, no other text, in this form:
{{"questions": [{{"question": "...", "options": {{"A": "...", "B": "...", "C": "...", "D": "...", "E": "..."}}, "answer": "C", "passage": 2, "explanation": "why the answer is right, from the passage"}}]}}

Passages:

{passages}"""  # noqa: E501

SCHEMA = {
    "type": "object",
    "properties": {
        "questions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "question": {"type": "string"},
                    "options": {
                        "type": "object",
                        "properties": {letter: {"type": "string"} for letter in LETTERS},
                        "required": list(LETTERS),
                    },
                    "answer": {"type": "string", "enum": list(LETTERS)},
                    "passage": {"type": "integer"},
                    "explanation": {"type": "string"},
                },
                "required": ["question", "options", "answer", "passage", "explanation"],
            },
        }
    },
    "required": ["questions"],
}

c = build_container()
llm = c.summaries._llm
book = c.books.get_book(BOOK_ID)
chunks = c.books.chunks(BOOK_ID)
budget = int(llm.context_size() * 0.9) - MAX_TOKENS
frame = llm.count_tokens(SYSTEM + INSTRUCTIONS)
print(f"model={llm.model} context={llm.context_size()} prompt budget={budget} frame~{frame}", flush=True)


def batches(items):
    """Consecutive chunks whose formatted passages fit the prompt budget."""
    out, current, used = [], [], 0
    for chunk in items:
        size = llm.count_tokens(format_passage(len(current) + 1, chunk)) + 2
        if current and used + size > budget - frame:
            out.append(current)
            current, used = [], 0
        current.append(chunk)
        used += size
    if current:
        out.append(current)
    return out


def parse(text):
    """The questions in a reply, and what is wrong with each, judged by format only."""
    body = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())
    try:
        data = json.loads(body)
    except json.JSONDecodeError as error:
        return None, [f"invalid JSON: {error}"]
    questions = data.get("questions") if isinstance(data, dict) else None
    if not isinstance(questions, list):
        return None, ["no questions list"]
    problems = []
    for i, q in enumerate(questions):
        opts = q.get("options") if isinstance(q, dict) else None
        if not isinstance(opts, dict) or sorted(opts) != list(LETTERS):
            problems.append(f"q{i}: options keys {sorted(opts) if isinstance(opts, dict) else opts}")
        elif len({str(v).strip().lower() for v in opts.values()}) < 5:
            problems.append(f"q{i}: repeated option text")
        if q.get("answer") not in LETTERS:
            problems.append(f"q{i}: answer {q.get('answer')!r}")
        if not isinstance(q.get("passage"), int):
            problems.append(f"q{i}: passage {q.get('passage')!r}")
    return questions, problems


def letter(text):
    match = re.search(r"\b([A-E])\b", text.strip())
    return match.group(1) if match else None


def ask(question, passages_text):
    """The model answers a question, with the passages (open book) or without them (closed book)."""
    options = "\n".join(f"{k}) {v}" for k, v in question["options"].items())
    if passages_text:
        prompt = f"Using only the passages below, answer the multiple-choice question. Reply with the letter of the correct option only.\n\nQuestion: {question['question']}\n{options}\n\nPassages:\n\n{passages_text}"  # noqa: E501
    else:
        prompt = f"Answer the multiple-choice question from what you know. Reply with the letter of the correct option only.\n\nQuestion: {question['question']}\n{options}"  # noqa: E501
    result = llm.generate([Message("user", prompt)], GenerationParameters(temperature=0.0, max_tokens=1500, seed=SEED))
    return letter(result.text), result.text.strip()[:80]


results = {"model": llm.model, "context": llm.context_size(), "seed": SEED, "chapters": []}
for number in CHAPTERS:
    items = [ch for ch in chunks if ch.chapter_number == number]
    title = items[0].chapter_title
    chapter = {"number": number, "title": title, "chunks": len(items), "batches": []}
    started = time.perf_counter()
    for b_index, batch in enumerate(batches(items)):
        passages = [format_passage(i + 1, ch) for i, ch in enumerate(batch)]
        passages_text = "\n\n".join(passages)
        prompt = INSTRUCTIONS.format(
            k=QUESTIONS_PER_BATCH, chapter=title, book=book.title, language="Portuguese", passages=passages_text
        )
        messages = [Message("system", SYSTEM), Message("user", prompt)]
        gen = llm.generate(messages, GenerationParameters(temperature=0.2, max_tokens=MAX_TOKENS, seed=SEED))
        questions, problems = parse(gen.text)
        record = {
            "batch": b_index,
            "chunks": len(batch),
            "pages": f"{batch[0].page_start}-{batch[-1].page_end}",
            "prompt_tokens": gen.stats.prompt_tokens,
            "completion_tokens": gen.stats.completion_tokens,
            "thinking_chars": len(gen.thinking),
            "seconds": round(gen.stats.total_seconds, 1),
            "finish_reason": gen.stats.finish_reason,
            "format_problems": problems,
            "raw": gen.text if questions is None else None,
            "questions": [],
        }
        for q in questions or []:
            n = q.get("passage")
            source = passages[n - 1] if isinstance(n, int) and 1 <= n <= len(passages) else None
            entry = dict(q, source=source)
            if not problems or all(not p.startswith(f"q{questions.index(q)}:") for p in problems):
                entry["open_book"] = ask(q, passages_text)
                entry["closed_book"] = ask(q, None)
            record["questions"].append(entry)
        chapter["batches"].append(record)
        print(
            f"ch{number} batch {b_index}: {len(batch)} chunks, {gen.stats.prompt_tokens} prompt tok, "
            f"{gen.stats.completion_tokens} out tok, {gen.stats.total_seconds:.1f}s, finish={gen.stats.finish_reason}, "
            f"questions={len(questions or [])}, problems={problems}",
            flush=True,
        )
    chapter["generation_seconds"] = round(sum(b["seconds"] for b in chapter["batches"]), 1)
    chapter["wall_seconds_with_checks"] = round(time.perf_counter() - started, 1)

    # How many questions would the model recommend for this chapter?
    sections = list(dict.fromkeys(ch.section_title for ch in items if ch.section_title))
    words = sum(len(ch.text.split()) for ch in items)
    recommend = (
        f'A reader wants a multiple-choice quiz on the chapter "{title}" of "{book.title}". The chapter has '
        f"{words} words, in these sections: {'; '.join(sections)}. How many questions would test it well? "
        "Reply with a number only."
    )
    chapter["recommended_n"] = [
        llm.generate([Message("user", recommend)], GenerationParameters(temperature=0.2, max_tokens=800)).text.strip()
        for _ in range(3)
    ]
    chapter["words"] = words
    results["chapters"].append(chapter)
    print(f"ch{number}: recommended N {chapter['recommended_n']}", flush=True)

# Structured output: the first chapter's first batch again, through Ollama's JSON-schema format.
first = [ch for ch in chunks if ch.chapter_number == CHAPTERS[0]]
batch = batches(first)[0]
passages_text = "\n\n".join(format_passage(i + 1, ch) for i, ch in enumerate(batch))
prompt = INSTRUCTIONS.format(
    k=QUESTIONS_PER_BATCH,
    chapter=batch[0].chapter_title,
    book=book.title,
    language="Portuguese",
    passages=passages_text,
)
client = ollama.Client(host=c.environment.ollama_base_url)
structured = []
for attempt in range(2):
    t0 = time.perf_counter()
    try:
        reply = client.chat(
            model=llm.model,
            messages=[{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}],
            format=SCHEMA,
            think="low",
            options={"num_ctx": llm.context_size(), "temperature": 0.2, "num_predict": MAX_TOKENS, "seed": attempt},
        )
        content = reply.message.content or ""
        questions, problems = parse(content)
        structured.append(
            {
                "seconds": round(time.perf_counter() - t0, 1),
                "thinking_chars": len(reply.message.thinking or ""),
                "done_reason": reply.done_reason,
                "questions": len(questions or []),
                "problems": problems,
                "head": content[:300],
            }
        )
    except Exception as error:  # noqa: BLE001 - a probe records whatever happens
        structured.append({"error": repr(error)})
    print(f"structured attempt {attempt}: {structured[-1]}", flush=True)
results["structured_output"] = structured

(OUT / "results.json").write_text(json.dumps(results, ensure_ascii=False, indent=2))
print("written", OUT / "results.json")
