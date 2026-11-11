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
| `known_cases` | `quiz_check`      | path                                   | The known cases file, relative to the experiment file. |
| `case_set`    | `quiz_check`      | `development` or `test`, required      | Which known cases to run on (FR-026).                  |

Variants override configuration as before: `llm.model` for the writer, and `generation.quiz.check.*`
for the checker.

## `kind: quiz`

For each variant and target, it prepares the quiz through the workspace's `QuizService`, timing it.
Then the writer answers each question without its passage. Rows follow `data-model.md` §
Measurement. `summarize` averages these per variant, and per book:
- `delivered_share`, `seconds`, `first_question_seconds`;
- `key_is_longest` and `key_is_shortest`;
- `closed_book_correct`, which leaves out the answers it can't read and counts them as
  `closed_book_unreadable`.

`benchmark-report` adds:
- the letter spread: the share of keys on each letter, balanced by construction (SC-001);
- where questions come from: the share in each third of their chapter;
- refusals by FR-010's kinds, passages skipped and passed over, and check verdicts that couldn't
  be read;
- `closed_book_correct`, shown without a target (FR-019);
- once `reading.csv` holds marks, the share of sound keys over the marked rows. It says how many
  rows are unmarked, counts the flawed ones by reason (FR-020), and counts the rows noted
  `refers_to_passage` (SC-015).

These are FR-019's measures, one for one.

Rows pair across variants by `question` (`book:chapter:position`). With the same seed and targets,
`--baseline` compares question by question.

**`reading.csv`** has one row per question (`data-model.md` § Reading row), with the passage's
text. It stays in the results directory, out of the repository.

## `kind: quiz_check`

It loads `known_cases`, keeps the cases of the experiment's `case_set` (`development` or
`test`), and locates each case's passage in the workspace by its quote. A quote found nowhere is
reported, and the case is left out and counted. For each variant:
- the check runs on each case (`contracts/model-replies.md` § The checker);
- the shipped writer answers each case with its passage (§ The comparator).

**Rows** follow `data-model.md` § Check row. The **summary**, per variant:
- `flawed_caught`, `flawed_cases`, `sound_rejected`, `sound_cases`, `unreadable`;
- the comparator's `flawed_caught` and `comparator_unreadable`;
- on the `test` set only, `rule_passes`:
  - (a) the paired difference, check caught minus comparator caught, over the flawed cases whose
    comparator answer could be read, from `paired_difference` (4,000 resamples, 95%), has an
    interval above zero;
  - (b) `sound_rejected/sound_cases` ≤ 0.10 (FR-027).

On the `development` set, `rule_passes` is always null: those runs choose a wording, and decide
nothing. On the `test` set, a run with fewer than 10 flawed or 30 sound cases located states no
verdict either: `rule_passes` is null, with the reason (FR-026).

`case_set` is a new field of `Experiment`, for this kind, and has no default.

## `key_cases.yaml`

A YAML list of known cases (`data-model.md` § Known case). It is read from beside the experiment
file, so `quickstart.md` § 8 copies both into the container. Its comment header says:
- how cases are labeled;
- that quotes are at most 30 words, verbatim;
- that no passage text is stored.

It starts from the 24 questions of `.specify/assessments/chapter-quiz/probe/results.json`, labeled
as that reading did, as development cases:
- **4 flawed**: Q16 `key_not_stated`, Q17 `wrong_key`, Q18 `two_defensible`, Q22
  `two_defensible`;
- **20 sound**: Q2, Q7, Q9 and Q13 with a note on their wording.

Cases are added from marked `reading.csv` files, with their run's name as `source`. A run read
before the check's final wording was fixed gives development cases; a run read afterwards gives
test cases (FR-026).
