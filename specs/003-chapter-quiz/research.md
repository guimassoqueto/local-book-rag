# Research: A quiz on a chapter or a book

Phase 0 of `/speckit-plan`. Each decision resolves a question the spec leaves to the plan, or one
the code raised. The figures come from the assessment's probe
(`.specify/assessments/chapter-quiz/research.md`), unless a decision names another source.

## R1. Where the quiz lives

- **Decision**: The quiz is split in two.
  - **`app/generation/quiz.py`** talks to the model. `QuizWriter` writes one question from one
    passage, reads the reply and checks its form, and runs the key check.
  - **`app/services/quiz_service.py`** holds the rules the application owns. `QuizService`
    covers:
    - the default count and the limit;
    - which passages, which letters, and what order;
    - preparing a quiz as a stream of events;
    - grading, and the result document.

  The Quiz tab and the benchmark both call `QuizService`.
- **Rationale**:
  - Constitution IV puts the service in `app/services`.
  - Constitution V sends every model call through the provider in `app/generation`, where the
    prompts and the other readers of replies live.
  - The split keeps the rules that unit tests must pin down (FR-006, FR-008, FR-014, FR-016) apart
    from model I/O, which the integration tests and the measurement check.
- **Alternatives considered**: One class in `app/generation`, like `ChapterSummarizer`, was
  rejected. It would mix the passage, letter and grading rules with prompt work, so every test of
  a rule would need a scripted fake model.

## R2. One question per call

- **Decision**: Each call writes one question from one passage, in the order the questions will be
  shown.
- **Rationale**:
  - **The probe's failures came from batching.** In batches of 9–10 passages, 14 of 18 questions
    came from the first 3. A batch's unreadable reply lost all of its questions: 6 of 30 lost.
  - **One passage per call** lets the application choose the passage (FR-006), retry or replace one
    question at a time (FR-010), and show each question as soon as it is ready (FR-012).
  - **It fits easily (FR-011).** A chunk targets 500 tokens (`chunking.target_size`), so one passage
    plus the instructions takes about 900 tokens of the 8,192-token window, leaving the reply its
    whole limit.
  - **Cost**: the probe wrote 3 questions in 5 to 9 s, with 42 to 112 characters of reasoning. One
    question per call should take 3 to 5 s, so 20 questions take one to two minutes, plus the check
    when it is on. The spec sets no time limit (SC-008), and the measurement records the real
    figure.
- **Alternatives considered**: Several passages per call, as in the probe, was rejected. It costs
  fewer calls, but brings back the bunching and the lost batches, and nothing can be shown until a
  batch is done.

## R3. The model never chooses a letter

- **Decision**: The writer replies with a JSON object holding:
  - `question`: the question;
  - `correct`: the right answer;
  - `wrong`: four wrong answers;
  - `explanation`: why the right answer is right.

  The model never sees letters and never picks a position. The application places the right
  answer on the letter it chose (R7), and shuffles the wrong ones into the rest. A passage with
  nothing to ask about gets `{"skip": "<why>"}` instead (R5). `contracts/model-replies.md` gives the
  exact format.
- **Rationale**:
  - **Position bias is removed at its source.** In the probe, the key was never D or E. The
    literature finds position preferences in nearly every model, even without letter labels
    (`research.md` of the assessment, arXiv 2605.01846).
  - **It removes a failure kind.** A letter key that doesn't match the options can't happen.
  - **Cross-references become rarer.** Options like "both A and B" are less likely when the model
    has no letters to point at. Some, such as "all of the above", are still caught (R4).
- **Alternatives considered**:
  - **Ask for lettered options with a key, then re-letter them.** This keeps the model's planning
    of a position, and its letter skew could still leak into how options are worded.
  - **Ollama's JSON-schema mode.** Rejected for now. The provider passes no schema; adding one
    changes the provider for every model. And the probe's two schema calls still returned the
    wrong number of items once. With one question per reply and retries (FR-010), plain JSON is
    enough if delivery reaches 95% (SC-004), which the measurement checks. If it misses, the
    provider's `json_mode` is the next step, in its own change.

## R4. Reading a reply and checking its form

- **Decision**:
  - **Reading.** The reader takes the first JSON object in the reply, with or without code fences
    or text around it. It is the same tolerance as `read_verdict`, but local to `app/generation`,
    which can't import from `app/evaluation`. Nothing is repaired: a reply that can't be read is
    written again.
  - **Form checks.** A question is refused when:
    - the question, the right answer or the explanation is missing or blank;
    - there aren't exactly four wrong answers;
    - two options are the same, compared casefolded and trimmed;
    - an option refers to the others (FR-009);
    - the reply hit its length limit.
  - **Cross-references.** An option is refused when it says "all of the above" or "none of the
    above", in any of the six interface languages, or names another option by letter, such as
    "A and B" or "option C".

  Each refusal is recorded by kind. The tab doesn't show them; the measurement reports them
  (FR-019).
- **Rationale**: Constitution V asks to parse what models really write. The probe's two unreadable
  replies were different malformations: an object closed early, and an empty extra option. Neither
  is worth repairing, since a retry costs seconds.
- **Alternatives considered**: Repairing JSON as the judge's reader does was rejected. That repair
  handles one recurring gpt-oss defect in long lists of verdicts. Here a fresh attempt is cheaper,
  and safer than guessing.

## R5. Passages with nothing to ask about, and the limit

- **Decision**:
  - **The model skips them.** The writer is told to reply `{"skip": …}` when its passage holds
    nothing about the book's subject: references, bibliographies, further reading, lists of
    illustrations or tables, acknowledgements, indexes, or a bare caption (FR-007). The
    application then tries another passage.
  - **A chapter can be ruled out.** When the first two passages tried in a chapter are both
    skipped, the chapter is treated as having nothing to ask about. In a whole-book quiz, its
    questions move to the other chapters (R6).
  - **The limit counts every passage.** The limit in FR-002 is the number of passages in the chosen
    text, capped at 50. If skipped passages leave too few, the quiz comes out shorter, and the
    reader is told how many it has (FR-010). This settles the point `/speckit-clarify` left open:
    FR-002 can't count "usable" passages before the model has read them. The spec is corrected
    accordingly.
- **Rationale**: The catalog keeps only a chapter's number and title, and *História econômica
  global*'s references and lists came in as ordinary chapters. Judging content needs reading it,
  and the model is already reading each passage.
- **Alternatives considered**:
  - **A title list per language.** Guesswork in every language, and it misses references inside a
    chapter.
  - **A share-of-digits heuristic.** It would also drop tables of real data, which are worth asking
    about.

## R6. Choosing passages

- **Decision**:
  - **One chapter.** Its passages, in book order, are cut into N contiguous strata of nearly equal
    size, and one passage is drawn from each. With N = 3, the strata are the thirds. With N ≥ 6,
    every third holds at least one whole stratum. For N = 4 or 5, a draw that leaves a third
    without a question is drawn again (FR-006, SC-005). A replacement comes from the same stratum
    first, then from the nearest strata.
  - **The whole book.** Each chapter's share is its share of the book's words. N is divided by
    largest remainder, which keeps each chapter within one of its share (FR-006, SC-006). Each
    chapter's questions are then drawn as above.
  - **A ruled-out chapter (R5).** Its questions are divided again among the chapters still in play,
    by the same method.
  - **Randomness.** Use is random. The measurement sets a seed, so that every model and every
    prompt round writes on the same passages, and their rows pair up for `benchmark-report
    --baseline` (constitution VI).
- **Rationale**: This spreads the questions by construction, instead of hoping the model spreads
  them. Largest remainder is the standard way to divide a whole number by shares while keeping each
  part within one of its share.
- **Alternatives considered**:
  - **Uniform random passages.** It can bunch, and fails SC-005 on short quizzes.
  - **Evenly spaced passages.** It is deterministic, so the same chapter always gives the same
    quiz.

## R7. Letters and order

- **Decision**:
  - **Letters.** For N questions, the letters are a balanced set, each letter used ⌊N/5⌋ or ⌈N/5⌉
    times, with the extra letters drawn at random. The set is shuffled over the positions. Each
    question's right answer goes on its position's letter, and the wrong ones are shuffled into
    the other four (FR-008, SC-001).
  - **Order.** The chosen passages get positions by a random permutation, drawn again if it
    matches the text's order (FR-006, SC-014). Questions are written in position order, so they
    appear in place, one after another (FR-012). A replacement keeps its position and letter.
- **Rationale**: Balance is by construction, so SC-001 holds for every quiz, not on average.
- **Alternatives considered**: An independent random letter per question was rejected. It is fair
  on average, but a 10-question quiz could still put the key on B four times.

## R8. The default count

- **Decision**: The default is `⌊words / 300 + 0.5⌋`, at least 1, at most 20 and at most the
  limit. The words are counted over the chosen text's chunks.
  - Chunks overlap by 80 tokens, so the count runs about 15% above the plain text. That is the
    count behind the spec's examples: 3,115 words, so 10 questions, for Capítulo 1.
  - The rounding is half-up, written out, because Python's `round` rounds half to even.
- **Rationale**: FR-002 as clarified. Counting the same way as the examples keeps them true.
- **Alternatives considered**: De-duplicating the overlaps. Chunks don't record where an overlap
  starts, and the difference doesn't matter for a default the reader can change.

## R9. The Quiz tab in Gradio 6.31

- **Decision**:
  - **Pre-built slots.** The tab builds `max_questions` question slots up front, each a Markdown
    with a Radio, hidden until filled. The preparing handler is a generator. Each time it yields,
    it fills the slot whose question is ready, updates the "7 of 20 ready" line, and leaves every
    other slot alone with `gr.skip()`, so answers already chosen stay.
  - **Submit** becomes active only when preparation finishes (FR-012).
  - **Stop.** A Stop button cancels a running preparation through Gradio's `cancels`, and Prepare
    is inactive meanwhile. By default, Gradio runs one call of an event at a time, so a second
    Prepare would wait behind the first instead of replacing it. The spec's edge case is corrected
    to "stop, then prepare".
  - **After submission** each slot shows right or wrong. A missed one also shows the reader's
    answer, the right one, the explanation and the passage (FR-015). A result block shows the
    score and, for a whole book, the ranking (FR-016).
  - **The download** is a `gr.DownloadButton` whose file is written to a temporary directory the
    tab owns. The directory is emptied when a new quiz is prepared and when the application
    starts. Gradio serves its own copy from its cache. The Blocks set `delete_cache`, which
    empties that cache on restart and removes stale copies hourly; `quickstart.md` checks both.
    The spec's FR-018 and SC-012 are corrected to say so.
  - **The book list.** `gradio_app.refresh` also refreshes the Quiz tab's book list.
- **Rationale**: `gr.render` was considered for the variable number of questions. It rebuilds its
  components on every change, which would clear answers while later questions arrive. A
  dynamically sized list has the same problem.
- **Alternatives considered**:
  - **Showing the quiz only when complete.** Simpler, but the owner asked for questions to appear
    as they are ready.
  - **A download built on click.** Gradio's download button serves a file that has to exist
    already.

## R10. Language

- **Decision**: As for summaries:
  - **The choice.** "Same as the book" is the default, or one of `generation.response_languages`.
  - **Naming.** The book's language code is turned into a name (`language_name`), and the prompt
    names the language: "Write in Portuguese" (FR-003).
  - **Unknown language.** A book whose language isn't known needs a language chosen.
- **Rationale**: `docs/decisions.md` § Generation. Told "Write in pt", gpt-oss summarized
  Portuguese chapters in English. Named, the language came out right. In the probe, all 24
  questions came in Portuguese with the language named.

## R11. The key check

- **Decision**:
  - **The verdict.** The checker reads the passage and the question with its options as they will
    be shown, lettered. It replies `{"supported": [<letters>]}`: the letters of every option the
    passage supports as an answer. The question is rejected unless the list holds exactly its key.
    An empty list means the key isn't stated by the passage; another letter means a wrong key or a
    second defensible answer. `contracts/model-replies.md` gives the format.
  - **A rejected question** is replaced from another passage of its stratum (R6), and keeps its
    position and letter.
  - **The settings.** The checker's model is `generation.quiz.check.model`, by default the writer.
    Its reasoning is `generation.quiz.check.reasoning`, which replaces the model's profile setting
    as the judge's `reasoning` does. The first wording runs at `medium`.
  - **A verdict that can't be read** is asked again once, sampling. If it still can't be read, the
    question is shown, and the event is logged and counted. The passage shown after submission
    remains the reader's safeguard, as the abstention check never costs the reader an answer.
  - **The proof (FR-026, FR-027).** The experiment kind `quiz_check` (R12) runs the check over the
    known cases, and computes the rule's comparator in the same run: the writer's own open-book
    answer, as in the probe. Each wording and each checker model is a variant, recorded with its
    result. The rule picks whether the shipped default is `check.enabled: true`.
- **Rationale**:
  - **One list covers all three flaws** the reading found: a wrong key (Q17), a key not in the
    passage (Q16), and two defensible answers (Q18, Q22).
  - **Reasoning matters for judges.** At `low`, the summary judge copied its prompt's sample values
    without reading (`docs/decisions.md` § Evaluation). The check gets `medium` to start, and the
    proof decides.
  - **The same model reads by default.** A second model can't stay loaded beside gpt-oss on the
    16 GB card, and the abstention check made the same choice. The setting lets the experiment try
    another model under the same rule (`spec.md` § Clarifications).
- **Alternatives considered**:
  - **Ask the checker to answer the question, and compare with the key.** That is the comparator
    itself, which caught 1 of 4.
  - **A yes/no "is the key right"**, which invites agreement.

## R12. The measurement and the proof

- **Decision**: Two experiment kinds join `BenchmarkRunner`.
  - **`quiz` (FR-019 to FR-023)**: for each variant and each target (a book, a chapter or the whole
    book, and a number of questions, by default the rule of R8), it prepares the quiz through
    `QuizService` in the workspace, with the seed set (R6). Then the writer answers each question
    without its passage, at temperature 0.

    Rows:
    - **One per question.** Its pairing ID is `book:chapter:position`, plus the passage's relative
      position, the letter, `key_is_longest`, `closed_book_correct`, the seconds, and the
      refusals by kind.
    - **One per quiz.** `delivered_share`, the seconds, `first_question_seconds`, and the skips.

    The letter spread and where questions come from are computed from the rows and shown by
    `benchmark-report`.
  - **The reading.** The run writes `reading.csv` next to `results.json`. Each row holds a
    question, its options, the key, the explanation, the passage with its pages, and empty `mark`
    and `reason` columns. Once marked, `benchmark-report` computes the share of sound keys
    (FR-020, SC-003). The file holds book text, so it stays with the results, out of the
    repository.
  - **`quiz_check` (FR-026, FR-027)**: for each variant (a checker model and wording), it runs the
    check and the writer's open-book answer over the known cases. It reports the share of flawed
    cases each catches and the share of sound ones each rejects, and states whether FR-027's rule
    passes.
  - **The known cases.** They are kept in `specs/003-chapter-quiz/key_cases.yaml`: each holds the
    question, the options, the key, the label, the reason, the book key and the chapter.
    - **The passage** is located by a verbatim quote of at most 30 words, the dataset's convention
      for evidence. No passage of the owner's book is committed.
    - **The set** starts from the probe's 24, and grows from the marked readings until it holds at
      least 10 flawed and 30 sound.
  - **The owner's book in the workspace.** An experiment can list `local_books` by key, title,
    language, file name and checksum. The owner copies the file into `benchmarks/books`; the runner
    verifies its checksum, never fetches it, and indexes it in the workspace beside the dataset's
    books. The library is never read (FR-021).
  - **The experiment files.** `specs/003-chapter-quiz/benchmarks/quiz.yaml` and `quiz_check.yaml`
    are copied into the container with the benchmarks restored from `c7bb785` (README,
    Benchmarks).
  - **The targets** (FR-019):
    - Capítulo 1, 3 and 6 of *História econômica global*;
    - *Inheritance* from *Think Python*;
    - *CHAPTER V. APPLICATIONS* from *On Liberty*;
    - *CAPITULO L* from *Quincas Borba*.

    The last three are chapters the summarization benchmark already uses.
- **Rationale**:
  - **The runner already does what constitution VI asks.** It isolates the workspace, records the
    environment (digests, versions, hardware, configuration, checksum), flags sampled runs, and
    provides `benchmark-report --baseline`.
  - **Seeded passages make variants pair up**, so prompt rounds and models compare question by
    question.
  - **Why the spec directory.** `docs/decisions.md` records that `benchmarks/` left the repository.
    The spec directory holds this feature's records, as `specs/002-gemma4-default-llm/reading.yaml`
    did.
  - **Why CAPITULO L.** *Quincas Borba*'s median chapter runs 300 words, too short for a
    measurement, but L runs 1,878 words. That was counted on the Gutenberg EPUB, whose checksum
    matches the dataset's.
- **Alternatives considered**:
  - **A devtool piped into the container, as for spec 002.** That suits a one-off decision. The
    owner wants this measurement again for each new model or machine, which is what the benchmarks
    are for.
  - **Putting the experiments back in `benchmarks/` in the repository.** That would reverse a
    recorded decision, which isn't this feature's call.
  - **Integration tests for the proof.** They can't reach a workspace holding the owner's book.

## R13. Configuration

- **Decision**: `config/generation.yaml` gains `generation.quiz`, validated like the rest
  (FR-029):
  - `temperature: 0.2` and `max_tokens: 1500`, for writing;
  - `words_per_question: 300`, `default_max: 20` and `max_questions: 50`;
  - `attempts_per_passage: 3`;
  - `check`: `enabled: false`, `model: null` (meaning the writer), `reasoning: medium` and
    `max_tokens: 2000`.

  Cross-file rules:
  - `check.model` has an `llm_profiles` entry;
  - each `max_tokens` leaves room in `llm.context_size`;
  - `default_max` is at most `max_questions`.

  `create_llm_provider` takes an optional model name, so the container can build the checker's
  provider from that model's profile.
- **Rationale**: Constitution I keeps model names in configuration, and validates all of
  `config/` at startup. None of these settings shapes the index, so the fingerprint is untouched
  (constitution III).
- **Alternatives considered**: Putting the check's model in the writer's profile. A profile
  describes a model; which model checks is a choice about the task.

## R14. Verified on real models

- **Decision**: Two kinds of check, at two levels.
  - **`tests/integration/test_quiz.py`** runs the configured model on public-domain passages
    written into the test, from *On Liberty*:
    - a question comes back readable and in form;
    - a bibliography passage is skipped;
    - the language named is the one written;
    - the check's verdict is readable on a sound case and a flawed one.
  - **The measurement and the proof**, on the six chapters (R12), decide the quality targets:
    SC-002 to SC-006, and FR-027.
- **Rationale**: Constitution V. Unit tests with fake models check the rules; only real output
  shows the formats and the failures. On this project, single-passage tests have failed to predict
  benchmark behavior before (`docs/decisions.md`, the marker rule), so the integration tests check
  format, and the measurement checks quality.
