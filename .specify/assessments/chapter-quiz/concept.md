# Concept: a multiple-choice quiz on chosen chapters

- **Slug**: chapter-quiz
- **Created**: 2026-11-10
- **Recommended option**: Option B — a quiz the application vouches for

The options below answer `problem.md`. Figures come from `research.md` and its probe: gpt-oss:20b
wrote 24 questions on three chapters of *História econômica global*. Three of the problem's open
questions weren't answered before this stage, so the recommendation takes a position on each,
listed under Assumptions to Validate:
- whether questions may go beyond what the book says;
- what share of flawed keys is acceptable;
- how long a quiz may take to prepare.

## Options

### Option A — The model's quiz, as written

- **Sketch**: A Quiz tab. The reader picks a book, then one chapter or the whole book, and a
  number of questions, defaulting to one the model recommends. The model reads the chosen text,
  batch by batch, and writes the questions, their keys and an explanation of each key. The reader
  answers and submits. The application compares letters and shows:
  - the score;
  - the chapters ranked by questions missed;
  - for each missed question, the right answer and the model's explanation.

  The result can be downloaded, with the date, the book and the chapter.
- **Appetite**: small (days).
- **Trade-offs**: It is the shortest way to a working tab. It meets the practice, feedback and
  record goals, and fails the three the probe measured, by the probe's own numbers:
  - **Trust**: 4 questions in 24 had a wrong, unsupported or ambiguous key, and nothing in this
    option catches them. The explanations inherit them: Q16's invented the reason the passage
    doesn't give.
  - **Answer patterns**: the key was never D or E. Always answering B would score 54%, and always
    taking the longest option 62%.
  - **Coverage**: 14 of 18 questions came from the first 3 passages of their batch, and 2 replies
    in 10 couldn't be read, losing their questions without a sign.
  - **Recommended number**: the model's varied between asks: 18, 25 and 20 for the same chapter.

  It also leaves the model-comparison goal unmet, and a whole-book quiz has the model read all of
  it. Batched as in the probe, that is about 26 calls for this book's 9 core chapters, some 2 to 4
  minutes at the probe's 5 to 9 s a call, before any check.
- **Rabbit holes**: Few in the building. The risk is after: a score the reader learns not to
  trust, and a "chapter to reread" chosen by a wrong key.

### Option B — A quiz the application vouches for

- **Sketch**: The same tab and the same experience, the result downloadable the same way. What
  changes is who decides what. The model writes the questions, and the application takes over what
  the probe showed the model doing badly:
  - **Where questions come from.** The application picks the passages, spread over the chosen
    chapter or book, and the model writes each question from the ones it is given. The time to
    prepare a quiz then grows with the number of questions, not with the book's length.
  - **Which letter is right.** The application places the right answer, so every letter is right
    about as often as the others.
  - **The score.** It is counted, not judged.
  - **Lost questions.** A reply that can't be read, or a question not in the asked form, is
    written again. It is never dropped silently.
  - **The default number of questions.** The application derives it from the chosen text's
    length, and the reader can change it. This departs from the idea's "recommended by the LLM":
    the model's own recommendations weren't stable.
  - **Traceability.** Every question keeps its passage and pages. After submission, each missed
    question shows the right answer, why, from its passage, and where it is in the book. The
    reader can see for themselves when a key is wrong.
  - **A key check.** Before a question is shown, a check reads it against its passage and drops a
    question whose key it rejects. It is kept only if it proves itself on known cases. The
    probe's 24 questions, 4 of them flawed, are a first set. The model's own check, which caught 1
    of the 4, is the bar to beat. If it doesn't beat that bar, the feature ships without it, and
    the remaining rate is recorded.
  - **Model comparison.** The probe becomes a repeatable measurement on fixed chapters, run for
    any configured model with no code change. Most of what it measures is computed:
    - which letters hold the keys;
    - how often the key is the longest option;
    - how many the model answers without the passages;
    - where in the text the questions come from;
    - questions delivered against questions asked;
    - time.

    Key soundness is read by hand on a sample, as in the probe.
- **Appetite**: medium (a few weeks). Uncertain. The application-side parts are days of work: the
  passages, the letters, the counted score, retries, traceability and the download. The rest is
  open-ended: rounds of prompt changes measured on real models (constitution V), and the key-check
  experiment.
- **Trade-offs**: It meets every goal the problem sets, or measures how far it falls short:
  - **Letter skew**: removed by construction.
  - **Lost batches**: replaced by retries.
  - **Bunched questions**: replaced by passages the application picks.
  - **Wrong keys**: become visible through the passage, and fewer if the check proves itself.

  It sacrifices speed to a first tab, and some preparation time if a check runs: the probe's
  checks added about 70%. Three risks:
  - **The length cue** has no application-side fix. Only the prompt can address it, and that is
    unmeasured.
  - **Questions from passages the model would have skipped** may be worse: dense lists, tables,
    figure captions.
  - **The key check** may never clear its bar, which leaves trust resting on transparency alone.
- **Rabbit holes**:
  - **The key check.** Building enough known cases, and finding a check that catches Q16-, Q18-
    and Q22-type keys, could take as long as the rest. It needs a time box and a rule fixed
    before it starts, as `specs/002-gemma4-default-llm` did.
  - **A quiz-quality judge or benchmark.** A judge has to prove itself first (constitution VI), and
    the benchmark's dataset and experiments are out of the repository now. Hand reading on a
    sample keeps this feature from turning into a benchmark project.
  - **Front and back matter.** The catalog keeps only each chapter's number and title. This book's
    acknowledgements, references and lists came in as ordinary chapters, so telling them apart
    automatically would be guesswork by title, in every language.
  - **"Easy to extend to several books."** It can pull the design toward generality now. The owner
    asked only that it stay easy.
  - **Prompt rounds.** Each change to the prompt or to the parser needs real-model checks, and on
    this project a single-passage test has failed to predict benchmark behavior before.

### Option C — Don't build: an outside tool, or questions written by hand

- **Sketch**: Nothing changes in the application. The owner studies with NotebookLM's quizzes,
  which offer chosen sources, difficulty, an "explain" per wrong answer and a study guide from the
  questions missed. Or they write their own questions while reading.
- **Appetite**: none.
- **Trade-offs**:
  - **NotebookLM matches most of the experience asked for**, but it is a cloud service: the book
    leaves the machine, which this project exists to avoid.
  - **Hand-written questions are trustworthy**, but they cost the time the idea wants to save,
    and they can't simulate an unseen exam.
  - **Neither serves the model-comparison goal.**
  - **Nothing is at risk**, and nothing in the application needs maintaining.
- **Rabbit holes**: None in the application.

## Recommendation

**Option B, with its key check as a time-boxed experiment under a rule fixed in advance.**

Option A builds the experience the idea describes, but the probe measured where it breaks.
- **About 1 question in 6** marks a defensible answer wrong, or rewards one the book doesn't give.
- **Letter position alone scores 54%.**
- **Most of each batch goes unasked.**

A study quiz that answers by letter position, or sends the reader back to the wrong chapter, fails
the problem's central goal: a score that can be trusted. Option C keeps the book local only by
giving up the feature, and it doesn't serve the owner's second purpose, comparing models over
time.

Option B keeps the experience and moves the measured failures out of the model's hands, where the
application can own them:
- which passages the questions come from;
- which letter is right;
- the score;
- what happens to an unreadable reply.

What only the model can do, writing a sound question and key, becomes visible through the passage,
and measurable through the repeatable probe. That is also what the owner's research purpose needs:
the same measurement, for the next model or the next machine. The key check is the one part whose
value is unknown. A rule set before it is tried decides it, as this repository did with gemma4 and
with historical spelling. If it fails, B still ships, with the remaining rate recorded.

The spec can order the work measurement-first. The repeatable probe, with its baseline from
`research.md`, comes before the tab, so that each prompt round is measured against it.

## Out of Scope (for the recommended option)

- Quizzes on several books at once, which stay easy to add later (owner).
- Hand-picked sets of chapters: one chapter or the whole book (owner).
- Keeping quizzes, answers, scores or history in the application. The download is the record
  (owner).
- Formats other than five options with one right answer (the idea).
- Grading by the model: the score is counted.
- A quiz-quality judge or benchmark dataset. Measurement is computed or read by hand, until a
  judge proves itself in a later change (constitution VI).
- Difficulty and topic settings, of the kind NotebookLM offers: not asked for.
- More than one user, and models outside this machine (owner, constitution I).

## Assumptions to Validate

- **Questions stay within what the book says**, so every key traces to a passage (constitution
  VII). The owner's "the book and its topics" could mean more. If it does, the
  answerable-without-the-book measure changes meaning, and so does traceability.
- **The owner accepts the flawed keys that remain, when each question shows its passage.** The
  probe's rate was 4 in 24. The owner hasn't set a target.
- **A quiz may take about a minute or two to prepare.** With the application picking passages, 20
  questions at 3 per call would take about 7 calls, roughly 50 s at the probe's speed. That rises
  to about 85 s if the checks cost what the probe's did. The owner's tolerance is unknown.
- **The application can place the right answer without breaking a question.** Options that refer to
  each other, such as "both A and B" or "none of the above", would break when moved.
- **Questions written from passages the application picks are as sound as the ones the model
  chose.**
- **A second attempt at an unreadable reply usually succeeds.** The two failures in the probe were
  different malformations, at temperature 0.2.
- **The prompt can bring the length cue down**, from 15 of 24 keys being the longest option.
- **A key check that beats the model's own check exists, within the time box.** Unknown.
- **Leaving front and back matter out of a whole-book quiz can be left to the reader**, by
  choosing a chapter, or settled by a simple rule. Detecting them is out of reach.
- **A length-derived default number is acceptable** in place of the model's recommendation, which
  the idea asked for.
