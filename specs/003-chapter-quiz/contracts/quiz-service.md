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
- **Skips.** A skipped passage is replaced the same way. When the first two passages tried in a
  chapter are both skipped, before any of its questions is ready, the chapter is ruled out. In a
  whole-book quiz its questions move to the others, as do those of a chapter whose passages run
  out (R5). In a one-chapter quiz, `NothingToAskError` is raised.
- **Counts.** Each `QuestionReady` carries its attempts, its refusals by kind and its check
  verdict. `QuizReady` carries the passages skipped and passed over, the chapters ruled out, and
  the check verdicts that couldn't be read (`data-model.md` § Preparation events). The tab
  ignores them; the measurement's rows come from them.
- **Shortfall.** When passages run out, `QuizReady.shortfall` says how many questions are
  missing (FR-010). Nothing is dropped without being counted.
- **Reads only.** It reads the book's chunks once at the start, and nothing in the library
  changes (constitution II). A book replaced or removed afterwards doesn't affect the quiz.
  Besides emptying the download directory (§ `export`), it writes nothing.
- **Logging.** It runs inside `operation(logger, "prepare_quiz", book_id=…, chapter=…, model=…)`.

Raises, besides those of `limit()`:
- `NothingToAskError`: a one-chapter quiz whose chapter is ruled out (FR-007).
- `ServiceUnavailableError` or `ModelNotFoundError`, from the provider. The stream ends; the
  questions already yielded stay valid but make no quiz (state `failed`).

Closing the generator, which Gradio does on Stop, ends the preparation at once (state `stopped`).

## `grade(quiz: Quiz, answers: Sequence[str | None]) -> Result`

Counts the score and builds the ranking (FR-014, FR-016). It is pure and makes no model call.

- A quiz not in state `ready` raises `QuizAlreadyGradedError`, which says to prepare a new quiz
  to practice again. The Result holds a copy of the quiz in state `graded`, so a graded quiz
  can't be graded again (FR-018).
- `answers` has one entry per question, in position order. Otherwise `ConfigurationError`.
- `score = 100 × right / len(quiz.questions)`. An unanswered question (None) is wrong.
- `ranking` is empty for a one-chapter quiz.

## `result_document(result: Result) -> tuple[str, str]`

Returns `(file name, Markdown)`, in the layout of `contracts/quiz-tab.md` § Download. The file
name is `quiz-<book_id>[-ch<NN>]-<YYYYMMDDTHHMMSSZ>.md`. It writes nothing.

## `export(result: Result) -> Path`

Writes `result_document()` into the service's download directory, and returns the file's path
for the tab's download button. The container gives the directory: `quiz_downloads` in the data
directory, so a benchmark workspace has its own. The service empties it when it is built, at
each start of the application, and when `prepare()` begins, so it holds at most the current
result (FR-018). The tab writes nothing (constitution IV).
