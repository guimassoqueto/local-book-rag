# Contract: the quiz experiments

Two experiment kinds join `book-rag benchmark` (`app/evaluation/benchmark.py`). Everything runs in
`benchmarks/workspace`, on its own copies of the books, and never reads the library (constitution
II, FR-021). Results go to `benchmarks/results/<name>_<stamp>/`, with the environment the runner
already records: date, configuration and its checksum, model digests and quantization, Ollama and
package versions, hardware, and `complete` (FR-023). Two things are added:
- **the commit**, from `--commit`, as the devtools of spec 002 recorded it;
- **every book file's checksum.**

The experiment files are `specs/003-chapter-quiz/benchmarks/quiz.yaml` and `quiz_check.yaml`.

## New fields on `Experiment`

| Field         | Kinds             | Type                                   | Rule                                                   |
| ------------- | ----------------- | -------------------------------------- | ------------------------------------------------------ |
| `kind`        | all               | adds `quiz`, `quiz_check`              |                                                        |
| `local_books` | all               | list of `{key, title, language, filename, sha256}` | Read from `benchmarks/books/<filename>`, never fetched. A missing file or a different checksum stops the run before any work. Indexed in the workspace beside the dataset's books. |
| `targets`     | `quiz`            | list of `{book, chapter, questions}`   | `book` is a dataset or local key. `chapter` is a title, or null for the whole book. `questions` is null for the default rule. |
| `seed`        | `quiz`            | int, default 0                         | Passed to `QuizService.prepare` (research R6).         |
| `known_cases` | `quiz_check`      | path                                   | The known cases file.                                  |

Variants override configuration as before: `llm.model` for the writer, and `generation.quiz.check.*`
for the checker.

## `kind: quiz`

For each variant and target, it prepares the quiz through the workspace's `QuizService`, timing it.
Then the writer answers each question without its passage. Rows follow `data-model.md` §
Measurement. `summarize` averages these per variant, and per book:
- `delivered_share`, `seconds`, `first_question_seconds`;
- `key_is_longest`, `closed_book_correct`.

`benchmark-report` adds:
- the letter spread: the share of keys on each letter, which should be balanced by construction,
  beside the model's own order (`model_order_letter`);
- where questions come from: the share in each third of their chapter;
- refusals and skips by kind;
- once `reading.csv` holds marks, the share of sound keys, with how many were marked.

Rows pair across variants by `question` (`book:chapter:position`). With the same seed and targets,
`--baseline` compares question by question.

**`reading.csv`** has one row per question (`data-model.md` § Reading row), with the passage's
text. It stays in the results directory, out of the repository.

## `kind: quiz_check`

It loads `known_cases` and locates each case's passage in the workspace by its quote. A quote
found nowhere is reported, and the case is left out and counted. For each variant:
- the check runs on each case (`contracts/model-replies.md` § The checker);
- the writer answers each case with its passage (§ The comparator).

**Rows** follow `data-model.md` § Check row. The **summary**, per variant:
- `flawed_caught`, `flawed_cases`, `sound_rejected`, `sound_cases`, `unreadable`;
- the comparator's `flawed_caught`;
- `rule_passes`: `flawed_caught/flawed_cases` above the comparator's, and
  `sound_rejected/sound_cases` ≤ 0.10 (FR-027).

The run refuses to state a verdict with fewer than 10 flawed or 30 sound cases located (FR-026):
`rule_passes` is null, with the reason.

## `key_cases.yaml`

A YAML list of known cases (`data-model.md` § Known case). Its comment header says:
- how cases are labeled;
- that quotes are at most 30 words, verbatim;
- that no passage text is stored.

It starts from the 24 questions of `.specify/assessments/chapter-quiz/probe/results.json`, labeled
as that reading did: 4 flawed (Q16, Q17, Q18, Q22) and 20 sound. Cases are added from marked
`reading.csv` files, with their run's name as `source`.
