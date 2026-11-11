# Feature Specification: A quiz on a chapter or a book

**Feature Branch**: `feat/chapter-quiz`

**Created**: 2026-11-10

**Status**: Draft

**Input**: User description: "A chapter quiz tab, as handed off in
.specify/assessments/chapter-quiz/decision.md (Option B of concept.md)"

The handoff is the `go` verdict of the assessment in `.specify/assessments/chapter-quiz/`, with
its Option B: a quiz the application vouches for.

## Context

The owner studies with this application and wants to "simulate graded quizes about the book and
its topics", on one chapter or on the whole book, and to know where they went wrong. Their second
purpose is to compare how models do this task as models and hardware change (`intake.md`, the
owner's answers).

The assessment's probe had gpt-oss:20b write 24 questions on three chapters of *História econômica
global*, and read each one against its passage (`research.md`). A quiz written by the model as is
would mislead its reader:

| Measure                                               | Probe        |
| ----------------------------------------------------- | ------------ |
| Keys right, with one defensible answer                | 20 of 24     |
| Flawed keys the model's own check caught              | 1 of 4       |
| Score from always answering B                         | 54%          |
| Score from always taking the longest option           | 62%          |
| Questions from the first 3 passages of a batch        | 14 of 18     |
| Questions delivered against asked                     | 24 of 30     |
| Questions whose named passage holds their subject     | 24 of 24     |
| Time to write a chapter's questions                   | 15–34 s      |

So the application owns what the model did badly: which passages questions come from, which letter
is right, the score, and replies it can't read. What only the model can do, a sound question and
key, is made visible through its passage and measured. A check that rejects flawed keys is an
experiment, kept only by the rule this spec fixes (FR-027).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - A quiz on one chapter, with a score that can be trusted (Priority: P1)

The reader picks a book and one of its chapters, and a number of questions, which has a default
they can change. The application prepares the quiz, showing its progress. The reader answers each
question by choosing one of five options, A to E, and submits. They see their score as a
percentage. For each question they missed, they see their answer, the right one, why it is right,
and the passage it came from, with its pages, so they can check the key themselves.

**Why this priority**: It is the feature: practice on a chapter, graded, and the way back to the
text for every mistake. Everything else builds on it.

**Independent Test**: Prepare a quiz on Capítulo 1 of *História econômica global*, answer it,
submit, and check the score against the answers given. Every missed question shows its passage
and pages, and the right answers fall on every letter.

**Acceptance Scenarios**:

1. **Given** an indexed book and one of its chapters, **When** the reader asks for a quiz of N
   questions, **Then** they get N questions, each with five options, A to E. Each question
   appears in its place as soon as it is ready, while the rest are prepared, with the number
   ready out of N shown. The quiz can be submitted only once every question is ready.
2. **Given** a quiz of 5 or more questions, **When** it is shown, **Then** each letter holds the
   right answer as often as any other, give or take one.
3. **Given** a quiz of 3 or more questions on one chapter, **When** it is prepared, **Then**
   questions come from each third of the chapter, from its start to its end.
4. **Given** the reader has answered some or all questions, **When** they submit, **Then** the
   score is the share of questions answered right, as a percentage, and a question left
   unanswered counts as wrong and is shown as "not answered".
5. **Given** a submitted quiz, **When** the reader looks at a question they missed, **Then** they
   see their answer, the right answer, why it is right, and the passage with its book, chapter,
   section and pages.
6. **Given** the model's reply can't be read for some question, **When** the quiz is prepared,
   **Then** that question is written again, and if the quiz still ends up shorter than asked, the
   reader is told how many questions it has.
7. **Given** a quiz of 2 or more questions, **When** it is shown, **Then** the questions are in a
   random order, not in the order of their passages in the text.
8. **Given** a chapter of 3,115 words, **When** the reader chooses it, **Then** the number of
   questions defaults to 10, which they can change.

---

### User Story 2 - A quiz on the whole book, and the chapters to reread (Priority: P2)

The reader picks a book and "the whole book". The questions are spread over its chapters by their
length, and none comes from passages with nothing to ask about, such as references, lists of
tables or acknowledgements. After submitting, the reader sees, besides what User Story 1 shows,
the chapters ranked by how many questions they missed in each.

**Why this priority**: It is the owner's other way to study a book, and the only one that can
point to the chapters to reread.

**Independent Test**: Prepare a 20-question quiz on the whole of *História econômica global*,
submit it with some wrong answers, and check the spread of questions over the chapters, the
absence of questions from its references and lists, and the ranking against the answers.

**Acceptance Scenarios**:

1. **Given** a book, **When** the reader asks for a whole-book quiz of N questions, **Then** each
   chapter gets questions in proportion to its share of the book's text, give or take one.
2. **Given** a book whose catalog chapters include references, further reading, lists of
   illustrations or tables, or acknowledgements, **When** a whole-book quiz is prepared, **Then**
   no question comes from those passages.
3. **Given** a submitted whole-book quiz, **When** the result is shown, **Then** the chapters are
   ranked by questions missed, each with how many it had and how many were missed.
4. **Given** a one-chapter quiz, **When** the result is shown, **Then** there is no chapter
   ranking: the score and the missed questions are the result.

---

### User Story 3 - The result, downloaded (Priority: P3)

After submitting, the reader downloads the result as a document. It records when the quiz was
taken, the book, the chapter when there is one, the score, and every question with the reader's
answer, the right answer, why, and where it is in the book. Nothing is kept in the application.

**Why this priority**: It is the only record of a quiz, by the owner's choice: the application
keeps nothing.

**Independent Test**: Submit a quiz, download the result, and find every element listed above in
it. Restart the application and find no trace of the quiz in it.

**Acceptance Scenarios**:

1. **Given** a submitted quiz, **When** the reader downloads the result, **Then** the document
   holds the date and time, the book, the chapter when the quiz is on one, the language, the models
   that wrote and checked the questions, the score, the chapter ranking for a whole-book quiz, and
   for each question its text, options, the reader's answer, the right answer, the explanation and
   the passage's pages.
2. **Given** a quiz prepared or submitted, **When** the reader prepares another quiz, **Then**
   nothing of the earlier quiz remains in the application's state. **When** the application is
   restarted, **Then** nothing of it remains anywhere in the application.

---

### User Story 4 - Comparing models on writing questions (Priority: P4)

The owner runs a repeatable measurement of how the configured model writes questions, on fixed
chapters. It reports what can be computed without a judge, and lists the questions with their
passages for reading by hand. Run again after switching the model in the configuration, it reports
the same measures for the new model.

**Why this priority**: It is the owner's second purpose, and the only way to know whether a prompt
change or a new model made the questions better. User Story 1's quality claims are checked with
it.

**Independent Test**: Run the measurement with the default model on its fixed chapters, then with
another configured model, and compare the two reports. No code changes between the runs.

**Acceptance Scenarios**:

1. **Given** the configured model and the measurement's chapters, **When** the measurement runs,
   **Then** it reports:
   - how often each letter holds the right answer;
   - how often the right answer is the longest option;
   - how many questions the model answers right without the passages;
   - where in each chapter the questions come from;
   - questions delivered against asked;
   - the time to prepare;
   - the replies it couldn't read.
2. **Given** a finished measurement, **When** its questions have been marked sound or flawed by a
   reader, **Then** the share of sound keys is computed from those marks.
3. **Given** another model named in the configuration, **When** the measurement runs again,
   **Then** it reports the same measures, and nothing in the code changed.
4. **Given** any run, **When** its result is recorded, **Then** it records the model's digest and
   quantization, the model server's and the packages' versions, the hardware, the full
   configuration, the commit, and the checksums of its books.

---

### User Story 5 - Fewer flawed keys reach the reader (Priority: P5)

Before a question is shown, a check reads it against its passage, and rejects it if its key is
wrong, unsupported or not the only defensible answer. A rejected question is replaced. The check
stays on only if it proves itself on questions whose soundness is known, by the rule in FR-027.

**Why this priority**: The probe's flawed keys are the largest risk to the score's meaning, and
the model's own check caught 1 of 4 of them. It comes last because its value is unknown, and the
feature ships with or without it.

**Independent Test**: Run the check over the known cases, apply FR-027's rule, and record whether
the check stays on, with its catch rate and false rejections.

**Acceptance Scenarios**:

1. **Given** the known cases, **When** the check runs over them, **Then** the flawed questions it
   rejects and the sound questions it rejects are counted.
2. **Given** those counts, **When** FR-027's rule is applied, **Then** the check is switched on
   by default if the rule passes, and off if it fails, and either way the result and the remaining
   rate of flawed keys are recorded.
3. **Given** the check is on and rejects a question, **When** the quiz is prepared, **Then** the
   question is replaced, and the reader gets the number of questions asked, or is told how many
   the quiz has.

---

### Edge Cases

- **A chapter shorter than the number asked.** A chapter can't yield more questions than it has
  passages. The reader is told the most it can hold, and a quiz is never padded with two
  questions from one passage. *Agradecimentos*, a single passage, holds one.
- **A book that isn't indexed.** A book that failed or is still being added can't be quizzed. The
  reader is told why, as the other tabs do.
- **The model can't be reached.** The preparation stops with a notification that stays until
  dismissed, as in the other tabs. The questions already shown stay visible, but the quiz can't
  be submitted, and the reader can prepare it again.
- **Options that point at each other.** "All of the above", "both A and B" or "none of the above"
  would become wrong once the application moves the right answer. A question with such an option
  isn't accepted, and is written again.
- **A reply cut off by its length limit.** It counts as unreadable, and the question is written
  again.
- **A passage that holds nothing to ask about inside a chapter.** A figure caption, a table of
  numbers or a list of references within a chapter is passed over for another passage.
- **The book changes during a quiz.** If the book is replaced, removed or reindexed after the quiz
  was prepared, the quiz and its result keep the passages they were written from, and the
  download still works.
- **A book whose language isn't known.** The questions are written in the language the reader
  chooses, as summaries are.
- **The reader prepares a new quiz before submitting.** The current quiz is discarded without
  being graded. If it is still being prepared, the reader stops it first. Its questions stay
  visible but can't be submitted.
- **Two questions about the same fact.** Questions come from different passages, so two questions
  can still overlap on a point a passage repeats. This isn't checked. Two questions on one point
  make a weaker quiz, not a wrong one, and checking every pair would cost a model call per pair.

## Clarifications

### Session 2026-11-10 (specify)

- Q: Must questions stay within what the book says, or may they reach into the book's topics
  beyond its text? → A: Within the book. Every right option is stated by its passage
  (constitution VII). Questions may ask about arguments, explanations and evidence (FR-005).
- Q: How is the default number of questions set? → A: From the text's length, one question per
  300 words, at most 20 by default, changeable up to the limit (FR-002). This replaces the idea's
  "recommended by the LLM". The owner added that the questions must be mixed up, not in the
  text's order: "question 1 of 10 could be from the start of the chapter/book, question 9 from the
  biggining of the chapter/book and question 10 from the middle" (FR-006, SC-014).
- Q: What share of questions must have a sound key? → A: At least 90% (SC-003).

### Session 2026-11-10

- Q: How long is the owner willing to wait for a 20-question quiz to be ready? → A: No limit:
  quality comes before speed, as long as progress is shown. At the owner's suggestion, each
  question appears as soon as it is ready and can be answered while the rest are prepared. The
  quiz can be submitted only once all are ready (FR-012, SC-008).
- Q: Which model runs the key check: the writing model, or another local model? → A: A setting
  that defaults to the writing model, and may name another configured local model (FR-025,
  FR-027). The owner may later want a cloud model to help with such evaluations. That belongs to
  the cloud providers change, which constitution I requires to amend the constitution first.
- Q: Which books and chapters does the measurement use? → A: The probe's three chapters of
  *História econômica global*, plus one chapter from each benchmark book: *Think Python*, *On
  Liberty* and *Quincas Borba* (FR-019).
- Q: In what file format is the quiz result downloaded? → A: Markdown (`.md`), the format of a
  saved summary (FR-017).
- Q: After seeing the result, can the reader retake the same quiz? → A: No. Practicing again
  means preparing a new quiz, with questions written anew (FR-018).

### Corrections during planning, 2026-11-10

Each one came from checking the spec against the code. `research.md` gives the reasons.

- **FR-002's limit counts every passage of the chosen text.** "Usable" passages can't be known
  before the model reads them (R5). Passages with nothing to ask about can leave a quiz shorter,
  which the reader is told.
- **A preparation is stopped, then a new one prepared.** Gradio queues a second Prepare behind
  the running one rather than replacing it (R9). The edge case now says so.
- **The download's copy in temporary storage.** Gradio serves a download from its cache. FR-018
  and SC-012 now say that this copy goes on a restart and within the hour, while the
  application's state keeps nothing (R9).
- **The commit is given to each measurement run** (FR-023). The app container holds no `.git`.

### Corrections from the requirements checklist, 2026-11-10

`checklists/model-and-measurement.md` found these gaps, and the owner asked for them to be closed:
- **The explanation**: it is held to the passage like the key, and the wrong options to the right
  one's length and form (FR-004).
- **The meaning of "stated by its passage"**: following the passage's reasoning is allowed, and
  across two languages it is judged by meaning (FR-005).
- **Nothing to ask about**: defined by what a passage does, with a chapter-level rule for a quiz
  on a chapter that has nothing to ask about (FR-007).
- **Option rules**: stated generally, beyond examples (FR-009).
- **Refusals**: given kinds, including a reply in the wrong language. The stale "passage other
  than the one given" is gone (FR-010).
- **The measurement**: its chapters, counts, meaning of "repeatable", configuration and reported
  measures (FR-019), and a rubric for marking (FR-020).
- **The key check**: an unreadable verdict, the reasoning setting, development and test cases
  kept apart, a paired interval, a bounded number of attempts, and how the remaining rate is
  measured (FR-024 to FR-027).
- **The records**: `docs/benchmark-results.md` added (FR-031).
- **The success criteria**: how each one is judged, and reasons for SC-002's and SC-004's
  thresholds.

### The owner's request after the checklist, 2026-11-10

- **No pointers to where the answer is.** The owner, reading the probe's questions, wrote
  (translated from Portuguese): "We need to avoid these references to passages, and simply refer
  to the chapter or the book more generically, not giving the user hints about where they can find
  the answer by looking in the book." Their examples were "segundo o trecho", "de acordo com o
  trecho" and "trecho N". 20 of the probe's 24 questions did this.
- **Where it landed**:
  - FR-004 now forbids references to the passage, its section or pages, and, in a whole-book quiz,
    to the chapter;
  - FR-010 refuses the forms it recognizes;
  - FR-020 notes the rest;
  - SC-015 counts them.

### Corrections from the analysis, 2026-11-10

`/speckit-analyze` compared the spec, plan and tasks with each other and with the constitution,
and the owner asked for its findings to be fixed:
- **The chapter rule** follows research R5. A chapter is ruled out only when the first two
  passages tried in it are both skipped, before any of its questions is ready. Read as "any two
  in a row", it would have ended a one-chapter quiz short over two captions in a row, after the
  chapter had already given questions (FR-007).
- **Shares after a chapter is ruled out** are among the chapters still in play (FR-006, SC-006).
- **Rules and writes stay in the service** (constitution IV). The service writes the download's
  file and empties its directory, and refuses to grade a quiz twice (FR-018). The tab only shows
  what it returns.
- **Model replies.** The comparator answers in JSON: a search for a letter would read the article
  in "A resposta é C" as the answer. The checker gets a model provider of its own, so its
  reasoning setting takes effect (FR-025).
- **A second model is measured** before the feature is done, as SC-010 asks.

A second run, on 2026-11-11, found only text that predated these corrections:
- **FR-018 names the download's two copies**: the service's file, kept until another quiz is
  prepared or the application restarts, and the copy the interface serves, removed on a restart
  and within the hour.
- **FR-027 (a)** says that a case whose comparator answer can't be read is left out and counted.

## Requirements *(mandatory)*

### Functional Requirements

#### Choosing what to be quizzed on

- **FR-001**: The application MUST offer a Quiz tab where the reader chooses one book, then either
  one of its chapters or the whole book. A quiz covers one book.
- **FR-002**: The reader MUST be able to set the number of questions. The default is derived from
  the chosen text's length: one question per 300 words, rounded to the nearest whole number, at
  least 1, and at most 20. That gives 10 for Capítulo 1 of *História econômica global*, 17 for
  Capítulo 3, and 20 for Capítulo 6 or the whole book. The reader can change it up to the limit:
  the number of passages in the chosen text, and never more than 50. The default never exceeds
  the limit. Passages with nothing to ask about (FR-007) can leave fewer; the quiz then says how
  many it has (FR-010).
- **FR-003**: The reader MUST be able to choose the language of the questions: the book's
  language by default, or one of the configured response languages, as for summaries. The
  language is named to the model, not described.

#### Preparing the quiz

- **FR-004**: Each question MUST have its text, five options labeled A to E, exactly one right
  option, an explanation of why it is right, and the one passage it was written from.
  - **The explanation** MUST be stated by the passage, as the key is (FR-005). It may restate or
    quote the passage, and adds nothing the passage doesn't say.
  - **The four wrong options** MUST be of about the same length and form as the right one, so
    that length gives the answer away no more than chance does (SC-002).
  - **The question and its options** MUST read like an exam question about the book, giving no
    hint of where in the book the answer is. They may refer to the author or to the book, and in
    a one-chapter quiz to "the chapter", generically.
    - They MUST NOT refer to the passage they were written from ("o trecho", "de acordo com a
      passagem 2", "the passage"), nor to its section or pages.
    - In a whole-book quiz, they MUST NOT name the chapter a question comes from.
    - The explanation, shown after submission next to the passage, may refer to it.
- **FR-005**: Every question MUST stay within what the book says: its right option is stated by
  its passage, and answering it needs nothing the book doesn't give (constitution VII).
  - **Arguments, not only facts.** Questions may ask about the author's arguments, explanations
    and evidence: why something happened, how one claim leads to another, what the author
    concludes.
  - **Following the reasoning is allowed.** A question may ask the reader to follow the passage's
    reasoning, as long as the passage itself states the answer, or the steps that lead to it. It
    may not need an inference the passage doesn't support, nor any knowledge from outside it.
  - **Across languages, by meaning.** When the questions are in another language than the book
    (FR-003), "stated by its passage" is judged by meaning, across the two languages.
- **FR-006**: The application, not the model, MUST choose the passages questions are written from,
  one passage per question:
  - **One chapter**: spread from the chapter's start to its end. With 3 or more questions, each
    third of the chapter has at least one.
  - **The whole book**: each chapter's number of questions MUST be within one of its share of the
    book's text. If a chapter is ruled out (FR-007), the shares are among the chapters still in
    play.
  - **The order**: the questions MUST be shown in a random order, never in the order of their
    passages. A question's place in the quiz says nothing about where in the chapter or book it
    comes from. Question 1 may come from the start, question 9 from the start too, and question
    10 from the middle. If a draw happens to match the text's order, it is drawn again.
- **FR-007**: Passages with nothing to ask about MUST NOT be used. Such passages are recognized by
  their content, not by a chapter's title, whether they are whole catalog chapters or passages
  within one.
  - **What has nothing to ask about.** A passage that only points elsewhere or names things,
    without saying anything about the book's subject: references, bibliographies, further
    reading, lists of illustrations or tables, acknowledgements, indexes, and a caption that only
    names its figure.
  - **What is asked about.** A passage that states something about the subject, in any form: a
    table of figures, a list of events, an epigraph, a chapter's own summary, or a caption that
    says what its figure shows.
  - **A chapter with nothing to ask about.** When the first two passages tried in a chapter both
    have nothing to ask about, before any question from it is ready, the chapter is treated as
    having none. A skip after that is replaced like any other. In a whole-book quiz, its
    questions go to the other chapters (FR-006), as do those of a chapter whose passages run out.
    In a one-chapter quiz, the preparation ends and says the chapter has nothing to ask about.
- **FR-008**: The application, not the model, MUST decide which letter holds the right option.
  Over a quiz of N questions, each letter holds it between ⌊N/5⌋ and ⌈N/5⌉ times.
- **FR-009**: Every option MUST be readable on its own, whatever its letter and whatever the other
  options say. No option may refer to other options by letter or by position, or be right or
  wrong according to them, as "all of the above", "both A and B" and "none of the above" are. The
  application refuses the forms it can recognize (FR-010). The reading marks any that get through
  as flawed (FR-020).
- **FR-010**: A reply the application can't read, or a question not in the required form, MUST be
  written again. Each refusal is counted by kind (FR-019):
  - `unreadable`: the reply can't be read;
  - `cut_off`: it stopped at its length limit;
  - `blank_field`: the question, the right answer or the explanation is missing or blank;
  - `wrong_count`: there aren't exactly four wrong answers;
  - `repeated_option`: two options have the same text, ignoring case, spacing and final
    punctuation. Options that say the same thing in other words aren't detected; the reading marks
    them flawed;
  - `cross_reference`: an option depends on the others (FR-009);
  - `passage_reference`: the question or an option refers to its passage, its section or its pages,
    or, in a whole-book quiz, names its chapter (FR-004). Recognized by the forms the application
    knows, in the six interface languages. The reading notes any that get through (FR-020);
  - `wrong_language`: the question, its options and its explanation are identified, with
    confidence, as another language than the one named (FR-003). An identification without
    confidence is accepted.

  After 3 failed attempts on a passage, another passage is used. If the quiz still has fewer
  questions than asked, the reader MUST be told how many it has. A question is never dropped
  silently.
- **FR-011**: A question MUST be written only from a passage the model received whole. Nothing the
  model is given may be cut off for lack of room. A passage too long to fit with its instructions
  is passed over for another and counted (FR-019). With today's chunk size of 500 tokens, in an
  8,192-token window, this doesn't happen. A change to the chunking or the window keeps the rule.
- **FR-012**: Preparation has no time limit. It MUST show its progress: the number of questions
  ready out of the number asked. Each question MUST appear in its place in the quiz as soon as it
  is ready, after any check (FR-024). The reader can answer it while the rest are prepared.
  Submission MUST be possible only once preparation has finished. If preparation stops on an
  error, the questions shown stay visible but can't be submitted, and the reader is told why.

#### Taking the quiz and the result

- **FR-013**: The reader MUST be able to choose one option per question and change it until
  submitting. Right answers, explanations and passages MUST NOT be shown before submission.
- **FR-014**: On submission, the score MUST be the number of questions answered right divided by
  the number of questions in the quiz, as a percentage. It is counted by comparing letters, never
  judged by a model. An unanswered question counts as wrong and is shown as "not answered".
- **FR-015**: After submission, each question MUST show whether it was answered right. Each missed
  question MUST show:
  - the reader's answer;
  - the right answer;
  - the explanation;
  - the passage's text, with its book, chapter, section and pages.
- **FR-016**: For a whole-book quiz, the result MUST rank the chapters by questions missed, most
  first, each with its number of questions and of misses. Ties go to the higher share missed,
  then to book order. A one-chapter quiz has no ranking.

#### The record

- **FR-017**: After submission, the reader MUST be able to download the result as a Markdown
  document (`.md`), the format of a saved summary. It holds:
  - the date and time of submission;
  - the book's title;
  - the chapter, when the quiz is on one;
  - the language;
  - the model that wrote the questions, and the one that checked them when the check is on;
  - the score;
  - the chapter ranking, for a whole-book quiz;
  - for each question: its text, its options, the reader's answer, the right answer, the
    explanation, and the passage's chapter, section and pages.
- **FR-018**: The application MUST NOT keep any quiz, answer or result: not after the reader
  prepares another quiz, and not after a restart. The downloaded document is the only record.
  A graded quiz can't be retaken. To practice again, the reader prepares a new quiz, whose
  questions are written anew. Its passages may repeat earlier ones, since nothing is kept to
  avoid them. To serve the download, the application writes the file into a directory of its
  own, emptied when another quiz is prepared and at each start, and the interface serves a copy
  of it from temporary storage, removed on a restart and within the hour. Neither holds anything
  the downloaded file doesn't.

#### The measurement

- **FR-019**: A command MUST run a repeatable measurement of question writing with the configured
  model, on chapters named in its own configuration with their numbers of questions. Its chapters
  are six:
  - **The probe's three**, so the baseline compares: Capítulo 1, 3 and 6 of *História econômica
    global*, at 10, 17 and 20 questions (FR-002's defaults).
  - **One from each benchmark book**: *Inheritance* of *Think Python*, *CHAPTER V. APPLICATIONS*
    of *On Liberty*, and *CAPITULO L* of *Quincas Borba*, each at FR-002's default. They are
    chapters the summarization benchmark already uses, and cover a programming book, philosophy
    and a novel, in English and Portuguese.

  **Repeatable** means that a run given the same seed uses the same passages, in the same order,
  with the same letters. The questions themselves may differ between runs, since the model
  samples.

  The measurement runs in the configuration it is given, and records it (FR-023). SC-002 to
  SC-004 are judged on a run in the configuration that ships: the key check is on only if
  FR-027's rule passed.

  It reports, computed without a judge:
  - the share of right options on each letter;
  - the share of questions whose right option is the longest;
  - the share the model answers right without the passages. This has no target. A book's subject
    can be known without reading it, and a question within the book can still be answered from
    knowledge; the share shows how much a score may owe to that;
  - the share of each chapter's questions in each third of the chapter;
  - questions delivered against asked;
  - refusals by the kinds of FR-010, passages skipped (FR-007), passages passed over (FR-011), and
    check verdicts that couldn't be read (FR-024);
  - the time to prepare each quiz, and to its first question.
- **FR-020**: The measurement MUST list every question with its options, key, explanation and
  passage, in a form a reader can mark, with reasons:
  - **Sound**: the key is right according to the passage, it is the only defensible option, and
    the explanation says nothing the passage doesn't.
  - **Flawed**, with one or more reasons:
    - a wrong key;
    - a key the passage doesn't state;
    - two defensible options;
    - an explanation beyond the passage;
    - an option that depends on the others (FR-009);
    - a question about a passage with nothing to ask about (FR-007).
  - **Weak wording with a sound key** is marked sound, with a note: for example, a question that
    gives its answer away. The probe's reading counted Q2, Q7, Q9 and Q13 this way. A question or
    option that points to its passage, section, pages or, in a whole-book quiz, its chapter
    (FR-004) gets the note `refers_to_passage`, which SC-015 counts.

  The share of sound keys MUST be computed from the marked questions only, saying how many are
  unmarked. An unmarked question is never counted as sound or as flawed. The listing holds the
  passages' text, so it stays with the results, out of the repository: no passage text of a book
  that isn't public may enter the repository (FR-026).
- **FR-021**: The measurement MUST run on its own copies of its books, apart from the library, and
  MUST NOT read or change the library's books, catalog or index (constitution II).
- **FR-022**: Measuring another model MUST need only a configuration change (constitution I).
- **FR-023**: Each measurement result MUST record:
  - each model's digest and quantization;
  - the model server's and the packages' versions;
  - the hardware;
  - the full configuration;
  - the commit, given to the run, since the app container holds no repository;
  - the checksums of its books;
  - whether the run was complete (constitution VI).

#### The key check

- **FR-024**: The application MUST be able to run a check on each question before it is shown.
  The check reads the question with its passage, and rejects it if its key is wrong, isn't stated
  by the passage, or isn't the only defensible option. A rejected question is replaced as in
  FR-010.
  - **An unreadable verdict** is asked for a second time. If the second can't be read either, the
    question is shown, and the event is logged and counted (FR-019). The passage shown after
    submission stays the reader's safeguard, as the abstention check never costs the reader an
    answer.
- **FR-025**: The check MUST be a setting that can be switched on or off without a code change.
  - **The model** that runs it MUST be a setting too. It defaults to the model that wrote the
    questions, and may name any other configured local model (constitution I).
  - **The reasoning level** MUST be a setting as well, replacing the checker's profile setting for
    the check. FR-027's rule is applied at the level that ships.
- **FR-026**: The known cases MUST be questions read against their passages and marked as FR-020
  says, with the reasons. They are of two kinds, kept apart so that the check isn't tuned to its
  own test:
  - **Development cases**: wordings of the check may be tried on them. They are the probe's 24 (4
    flawed), and any marked before the check's final wording is fixed.
  - **Test cases**: marked afterwards, from measurement runs no wording was tried on. They MUST
    include at least 10 flawed and 30 sound questions. If one run doesn't yield 10 flawed keys,
    another run, with another seed, is read.

  A known case locates its passage by a verbatim quote of at most 30 words. No passage text of a
  book that isn't public is stored with it.
- **FR-027**: The check is switched on by default only if, on the test cases, both of these hold:
  - **(a) It catches more flawed questions than the comparator does.**
    - The comparator is the shipped writer model answering each case with its passage. A flawed
      case is caught when its answer isn't the key. A case whose answer can't be read is left
      out of the comparison and counted (constitution VI). The probe's equivalent caught 1 of 4.
    - Compared case by case, the difference counts only when its paired bootstrap interval (4,000
      resamples, 95%) excludes zero (constitution VI). A tie fails.
  - **(b) It rejects no more than 10% of the sound questions.**

  The rule is fixed before the check is first run on any known case. It applies the same way to
  any checker model tried, and each try is recorded with its model.
  - **Attempts**: at most three wordings of the check are tried on the development cases, each
    with the writer model and with at most one other configured model. The rule is then applied
    once, on the test cases, to the try that did best on the development cases. If it fails, the
    check ships switched off.
  - **The remaining rate**: either way, the share of flawed keys in the marked reading of a
    measurement run in the shipped configuration (SC-003) is recorded in
    `docs/benchmark-results.md` and `docs/decisions.md`.

#### Constraints from the constitution

- **FR-028**: Preparation and grading MUST live in the service layer. The Quiz tab and any command
  only read input and show output (constitution IV).
- **FR-029**: Every setting the feature adds MUST be validated when the application starts, and
  an unknown or invalid one MUST stop it (constitution I).
- **FR-030**: The prompt, the parsing of its replies and the key check MUST be verified on the real
  default model and on a real book, through integration tests or the measurement, not only with
  fake models (constitution V).
- **FR-031**: `README.md` MUST describe the Quiz tab and the measurement. `docs/decisions.md` MUST
  record each choice this feature makes and why, including the key check's verdict.
  `docs/benchmark-results.md` MUST record the measurement runs and the check's proof
  (constitution VIII).

### Key Entities

- **Quiz**: one book, and one chapter or the whole book. It also records the language, the model
  that wrote it, the model that checked it when the check is on, when it was prepared, its
  questions, and how many were asked against prepared.
  It lives only until the next quiz or a restart.
- **Question**: its text, five options A to E, the right letter, the explanation, and its source
  passage, with the book, chapter, section, pages and text.
- **Result**: the reader's letter or "not answered" for each question, which ones were right, the
  score, the chapter ranking for a whole-book quiz, and when it was submitted. It is downloadable,
  never kept.
- **Measurement run**: the model and its environment (FR-023), the chapters, the computed measures
  (FR-019), its questions for reading by hand, and their marks once read.
- **Known case**: a question with its passage, marked sound or flawed by a reader, with the
  reasons. It is either a development case or a test case (FR-026), and locates its passage by a
  quote of at most 30 words. It is used to decide the key check.

## Success Criteria *(mandatory)*

### Measurable Outcomes

Baselines are the probe's: gpt-oss:20b, a first prompt, 24 questions on chapters 1, 3 and 6 of
*História econômica global*.

How each criterion is judged:
- **By construction, for every quiz.** SC-001, SC-005, SC-009, SC-014, and SC-006's spread. The
  unit tests pin them, and the measurement's rows show them.
- **On one full measurement run** in the configuration that ships, with its experiment's seed
  (FR-019). SC-002, SC-003, SC-004 and SC-015, reported with their counts. A target missed is
  recorded as missed, not rounded up.
- **On the quickstart's whole-book quiz.** SC-006's absence of questions from references and
  lists, which depends on the model.
- **By the owner after use.** SC-013, which doesn't block delivery.

- **SC-001**: In every quiz of 5 or more questions, each letter holds the right answer between
  ⌊N/5⌋ and ⌈N/5⌉ times. Baseline: never D or E, and always answering B scored 54%.
- **SC-002**: On the measurement, always taking the longest option scores at most 35%, against 20%
  by chance. A reader who always takes the longest then gains at most 15 points over guessing.
  Baseline: 62%.
- **SC-003**: On the measurement, at least 90% of the questions are marked sound (FR-020). Every
  question of the run, about 85, is read. Baseline: 20 of 24, 83%.
- **SC-004**: On the measurement, at least 95% of the questions asked are delivered, and every
  shortfall is reported to the reader. That is about one question in 20 missing after retries,
  where the probe's batches lost one in five. Baseline: 24 of 30, two replies lost silently.
- **SC-005**: In one-chapter quizzes of 3 or more questions, every third of the chapter has a
  question. Baseline: 14 of 18 questions came from the first 3 passages of 9–10.
- **SC-006**: In a 20-question whole-book quiz on *História econômica global*, each chapter's
  number of questions is within one of its share of the text, among the chapters still in play
  (FR-006). No question comes from its
  acknowledgements, references, further reading, or lists of illustrations and tables.
- **SC-007**: Every question in every result shows its passage, with chapter, section and pages.
  Baseline: 24 of 24.
- **SC-008**: Preparation has no time limit; quality comes before speed. In every quiz, the reader
  sees how many questions are ready out of how many were asked. The first question can be
  answered before the last is ready. The measurement records each quiz's preparation time and the
  time to its first question (FR-019). Baseline: 15–34 s per chapter for 6 to 12 questions,
  without checks.
- **SC-009**: For every submission, the score equals right answers over questions, exactly.
- **SC-010**: The measurement runs for a second configured model with no code change, and reports
  every measure of FR-019 for it.
- **SC-011**: Every downloaded result holds every element FR-017 lists.
- **SC-012**: After preparing another quiz, no earlier quiz, answer or result can be found in the
  application's state. After a restart, none can be found anywhere in the application, including
  the interface's temporary storage.
- **SC-013** (qualitative): Studying with it, the owner finds that the passage shown for a missed
  question is the one to reread. It is reported by the owner after use, and isn't a gate.
- **SC-014**: No quiz of 2 or more questions is shown in the order of its passages in the text.
- **SC-015**: On the measurement, no question or option points to where its answer is. That means
  no reference to its passage, its section or its pages, and no chapter named in a whole-book
  quiz: the application refuses the forms it knows (FR-010), and the reading notes the rest
  (FR-020). Baseline: 20 of 24 questions in the probe said "segundo o trecho", "de acordo com a
  passagem 2" or the like.

## Assumptions

- **One reader, on their own machine.** There are no accounts, no sharing, and no use beyond the
  owner's own study.
- **No timer for answering.** A "graded quiz" here means answers hidden until submission and a
  counted score. Nothing in the owner's answers asked for a timer.
- **50 questions at most per quiz** keeps the preparation and the page manageable.
- **Passages with nothing to ask about can be recognized from their content.** The catalog keeps
  only a chapter's number and title, so recognition by title would be guesswork in every
  language.
- **The measurement's books come from two places.**
  - **The benchmark books** are fetched with their checksums, as the benchmarks already do.
  - ***História econômica global*** isn't public. The owner's copy has to be brought into the
    measurement's own workspace, apart from the library. Its checksum identifies it in each
    result.

  If the benchmarks restored from `c7bb785` or the owner's copy are missing, or the copy's
  checksum differs, a run stops before any work and says which.
- **Who reads.** The readings are marked and the known cases labeled by the agent that implements
  the feature, as the probe was. Before FR-027's rule is applied, the owner reviews every flawed
  label and a sample of the sound ones.
- **The key check is a judge** (constitution VI), and FR-027 is how it proves itself. A judge of
  quiz quality, for scores beyond the check's own rejections, is out of scope.
- **Out of scope**, inherited from the assessment:
  - quizzes on several books at once. They are left for a later change, which nothing here should
    make harder;
  - hand-picked sets of chapters;
  - keeping anything in the application;
  - formats other than five options with one right answer;
  - grading by a model;
  - difficulty and topic settings;
  - more than one user;
  - models outside this machine.
