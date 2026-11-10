# Contract: `QuizService` (`app/services/quiz_service.py`)

The Quiz tab and the `quiz` experiment call this service, and nothing else holds a quiz rule
(constitution IV). The types are those of `data-model.md`. Every error is a `BookRagError`
subclass, which the tab shows as a lasting notification (`reports_errors`).

## `limit(book_id: str, chapter: int | None) -> int`

The most questions the chosen text can hold: its number of passages, capped at
`generation.quiz.max_questions` (FR-002, research R5).

Raises:
- `BookNotFoundError`: no such book.
- `ChapterNotFoundError`: no such chapter in the book.
- A `BookRagError` when the book isn't indexed: the one the other tabs raise for such a book,
  saying why and what to do.

## `default_count(book_id: str, chapter: int | None) -> int`

`⌊words / words_per_question + 0.5⌋`, clamped to at least 1, at most `default_max`, and at most
`limit()` (FR-002, R8). It raises what `limit()` raises.

Examples, on the probe's book: Capítulo 1 → 10, Capítulo 3 → 17, Capítulo 6 → 20, the whole
book → 20.

## `prepare(book_id, chapter, count, language=None, seed=None) -> Iterator[QuizEvent]`

Prepares a quiz, yielding `QuizStarted`, then one `QuestionReady` per question, then `QuizReady`.

Arguments:
- `count`: 1 ≤ count ≤ `limit()`. Otherwise `ConfigurationError`, naming the bounds.
- `language`: a name from `generation.response_languages`. None means the book's, named. A book
  without a known language needs one given; otherwise `ConfigurationError`.
- `seed`: fixes the passages, letters and order, for the measurement (R6). None in use.

Guarantees:
- **Passages.** Questions come one per passage, chosen by R6:
  - in a one-chapter quiz of 3 or more questions, every third of the chapter has one (SC-005);
  - in a whole-book quiz, each chapter is within one of its share (SC-006).
- **Letters.** They are balanced (SC-001).
- **Order.** It is never the text's order when there are 2 or more questions (SC-014).
- **Each `QuestionReady` is final.** It has been written, read, checked for form, and checked for
  its key when the check is on. It never changes afterwards.
- **Retries.** A refused draft is written again, up to `attempts_per_passage` times. Then another
  passage of the same stratum is used, then of the nearest ones.
- **Skips.** A skipped passage is replaced the same way. Two skips in a row from one chapter rule
  the chapter out, and in a whole-book quiz its questions move to the others (R5).
- **Shortfall.** When passages run out, `QuizReady.shortfall` says how many questions are
  missing (FR-010). Nothing is dropped without being counted.
- **Reads only.** It reads the book's chunks once at the start, and nothing in the library
  changes (constitution II). A book replaced or removed afterwards doesn't affect the quiz.
- **Logging.** It runs inside `operation(logger, "prepare_quiz", book_id=…, chapter=…, model=…)`.

Raises, besides those of `limit()`:
- `ServiceUnavailableError` or `ModelNotFoundError`, from the provider. The stream ends; the
  questions already yielded stay valid but make no quiz (state `failed`).

Closing the generator, which Gradio does on Stop, ends the preparation at once (state `stopped`).

## `grade(quiz: Quiz, answers: Sequence[str | None]) -> Result`

Counts the score and builds the ranking (FR-014, FR-016). It is pure and makes no model call.

- `answers` has one entry per question, in position order. Otherwise `ConfigurationError`.
- `score = 100 × right / len(quiz.questions)`. An unanswered question (None) is wrong.
- `ranking` is empty for a one-chapter quiz.

## `result_document(result: Result) -> tuple[str, str]`

Returns `(file name, Markdown)`, in the layout of `contracts/quiz-tab.md` § Download. The file
name is `quiz-<book_id>[-ch<NN>]-<YYYYMMDDTHHMMSSZ>.md`. It writes nothing; the tab writes the
temporary file.
