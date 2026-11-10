# Data Model: A quiz on a chapter or a book

Nothing here is stored by the application. Quizzes and results live in memory for one session
(FR-018), and only the measurement writes files, in `benchmarks/results` and the experiment's
workspace. The types below are frozen dataclasses, like the rest of the code.

## Quiz settings (`generation.quiz`, in `config/generation.yaml`)

| Key                     | Type                                | Default  | Rule                                               |
| ----------------------- | ----------------------------------- | -------- | -------------------------------------------------- |
| `temperature`           | float ≥ 0                           | 0.2      | Writing a question.                                |
| `max_tokens`            | int > 0                             | 1500     | Reasoning included. Leaves room in the window.     |
| `words_per_question`    | int > 0                             | 300      | FR-002's rate.                                     |
| `default_max`           | int > 0                             | 20       | At most `max_questions`.                           |
| `max_questions`         | int > 0                             | 50       | FR-002's cap, and the number of slots in the tab.  |
| `attempts_per_passage`  | int > 0                             | 3        | FR-010.                                            |
| `check.enabled`         | bool                                | false    | The shipped value is set by FR-027's rule.         |
| `check.model`           | string or null                      | null     | Null means the writer. Needs an `llm_profiles` entry. |
| `check.reasoning`       | `low`, `medium`, `high` or null     | `medium` | Replaces the checker's profile setting.            |
| `check.max_tokens`      | int > 0                             | 2000     | Leaves room in the window.                         |

An unknown or invalid key stops the application at startup (FR-029).

## Scope

What a quiz is about.

| Field            | Type        | Rule                                                                  |
| ---------------- | ----------- | --------------------------------------------------------------------- |
| `book_id`        | str         | A book in the catalog, in status `INDEXED`. Otherwise refused, saying why. |
| `chapter_number` | int or None | A chapter of the book. None means the whole book.                     |

The structure stays a book and an optional chapter. A later change could widen it to several
books without changing any of the rules below.

## Draft

A writer reply, as read (`contracts/model-replies.md`). It is either a question draft or a skip.

| Field         | Type            | Rule                                                        |
| ------------- | --------------- | ----------------------------------------------------------- |
| `question`    | str             | Not blank.                                                  |
| `correct`     | str             | Not blank.                                                  |
| `wrong`       | tuple of 4 str  | Exactly four. Each is distinct from the others and from `correct` (casefolded, trimmed). |
| `explanation` | str             | Not blank.                                                  |

A **skip** carries `reason`, a string: the passage has nothing to ask about (FR-007).

A reply that can't be read, or a draft that fails a rule, is a **refusal**. Each has a kind:
- `unreadable`
- `cut_off`
- `blank_field`
- `wrong_count`
- `repeated_option`
- `cross_reference`

## Question

A draft placed in the quiz.

| Field         | Type                    | Rule                                                      |
| ------------- | ----------------------- | --------------------------------------------------------- |
| `position`    | int, 1..N               | Its place in the quiz, from a random permutation (R7).    |
| `text`        | str                     | The draft's question.                                     |
| `options`     | tuple of 5 str          | Shown as A to E. The right answer sits at `key`.          |
| `key`         | `A`..`E`                | From the quiz's balanced letter set (R7).                 |
| `explanation` | str                     | The draft's explanation.                                  |
| `passage`     | `Chunk`                 | The one passage it was written from, whole (FR-004, FR-011). |

## Quiz

| Field            | Type                         | Notes                                                       |
| ---------------- | ---------------------------- | ----------------------------------------------------------- |
| `scope`          | Scope                        |                                                             |
| `book_title`     | str                          |                                                             |
| `chapter_title`  | str or None                  | None for a whole-book quiz.                                 |
| `language`       | str                          | Named, as given to the model.                               |
| `writer`         | str                          | The model that wrote the questions.                         |
| `checker`        | str or None                  | The model that checked them, when the check is on.          |
| `asked`          | int                          | 1 ≤ asked ≤ limit (FR-002).                                 |
| `questions`      | tuple of Question            | In position order. Fewer than `asked` only with a shortfall. |
| `prepared_at`    | datetime (UTC)               |                                                             |
| `state`          | see below                    |                                                             |

**State**:

```text
            prepare
 (none) ──────────────► preparing ──┬── all asked ready ───────────────► ready
                                    ├── passages ran out ─(shortfall)──► ready
                                    ├── Stop ──────────────────────────► stopped
                                    └── error ─────────────────────────► failed
 ready ── submit ──► graded
 any ── new quiz or restart ──► discarded (nothing remains)
```

Only `ready` can be submitted (FR-012). `stopped` and `failed` keep their shown questions visible,
but can't be submitted.

## Preparation events

`QuizService.prepare` yields these, in order:

| Event           | Fields                                    | When                                          |
| --------------- | ----------------------------------------- | --------------------------------------------- |
| `QuizStarted`   | `asked`, `limit`, `book_title`, `chapter_title` | Before the first call.                  |
| `QuestionReady` | `question`, `ready` (count)               | Each time a question is ready, checked if the check is on. |
| `QuizReady`     | `quiz`, `shortfall` (int, 0 if none)      | Last, when preparation finishes.              |

A stop or an error ends the stream without `QuizReady`. An error is raised as a `BookRagError`.

## Answers and result

**Answers**: one entry per position, holding a letter or None for "not answered".

**Result**:

| Field          | Type                        | Rule                                                        |
| -------------- | --------------------------- | ----------------------------------------------------------- |
| `quiz`         | Quiz                        | In state `graded`.                                          |
| `answers`      | tuple of letter or None     | In position order.                                          |
| `right`        | tuple of bool               | An unanswered question is wrong (FR-014).                   |
| `score`        | float, 0..100               | right ÷ questions in the quiz × 100, by counting (SC-009).  |
| `ranking`      | tuple of ChapterTally       | Whole-book quizzes only. Otherwise empty (FR-016).          |
| `submitted_at` | datetime (UTC)              |                                                             |

**ChapterTally** holds `chapter_number`, `chapter_title`, `questions` and `missed`. The ranking is
ordered by `missed`, highest first. Ties go to the higher `missed / questions`, then to book order.

**The result document** is the Markdown of `contracts/quiz-tab.md` § Download. It is built from the
result on demand.

## Check verdict

| Field        | Type                 | Rule                                                            |
| ------------ | -------------------- | --------------------------------------------------------------- |
| `supported`  | tuple of letters     | The options the checker found the passage supports.             |
| `accepted`   | bool                 | True only when `supported` is exactly the key.                  |
| `readable`   | bool                 | False after a retry that still couldn't be read. The question is then shown, and the event logged. |

## Measurement

**Question row** (`kind: quiz`):
- `variant`, `book`, `chapter`, `question`: the pairing ID, `book:chapter:position`;
- `relative_position`, from 0 to 1 within its chapter;
- `letter`, `model_order_letter` (the letter the right answer would have had in the model's
  order);
- `key_is_longest`, `closed_book_correct`;
- `seconds`, `attempts`, `refusals` (by kind), `checked`, `check_accepted`.

**Quiz row** (`kind: quiz`):
- `variant`, `book`, `chapter`;
- `asked`, `delivered`, `delivered_share`;
- `seconds`, `first_question_seconds`;
- `skipped_passages`, `ruled_out_chapters`.

**Reading row** (`reading.csv`, results directory only):
- `question` (the pairing ID), `book`, `chapter`, `pages`, `passage`;
- `text`, the options A to E, `key`, `explanation`;
- `mark`: `sound`, `flawed` or empty;
- `reason`.

**Known case** (`specs/003-chapter-quiz/key_cases.yaml`):

| Field         | Type                  | Rule                                                    |
| ------------- | --------------------- | ------------------------------------------------------- |
| `id`          | str                   | Unique.                                                 |
| `source`      | str                   | Where it came from: the probe, or a measurement run.    |
| `book`        | str                   | A dataset key, or a `local_books` key.                  |
| `chapter`     | str                   | The chapter's title.                                    |
| `quote`       | str, ≤ 30 words       | Verbatim from the passage. It locates the passage under any chunking. |
| `question`    | str                   |                                                         |
| `options`     | map `A`..`E` → str    |                                                         |
| `key`         | `A`..`E`              |                                                         |
| `label`       | `sound` or `flawed`   |                                                         |
| `reason`      | str                   | Why it was labeled so. Required for `flawed`.           |

**Check row** (`kind: quiz_check`): `variant`, `case`, `label`, `rejected`, `supported`,
`readable`, `open_book_answer` and `open_book_caught`. The last two come from the comparator: the
writer answering with the passage.
