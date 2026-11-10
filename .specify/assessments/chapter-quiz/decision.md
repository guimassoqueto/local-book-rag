# Decision: a multiple-choice quiz on chosen chapters

- **Slug**: chapter-quiz
- **Decided**: 2026-11-10
- **Verdict**: go
- **Artifacts reviewed**: intake.md (with the owner's answers), research.md (with the probe in
  `probe/`), problem.md, concept.md

## Scorecard

| Criterion | Rating | Justification |
|-----------|--------|---------------|
| Problem validity | adequate | The need is real but small: one user, stated, not observed. The owner studies with the application and has no way to practice graded or to find weak chapters, and the reviews found support for practice tests, multiple choice included. The second purpose, comparing models on a new task over time, ties to the constitution's own (`problem.md`; `research.md` § Users & Demand). |
| Evidence strength | adequate | The decisive facts were measured on the live stack, with the default model and a real book, and every question was read against its passage: speed, failure modes, cue scores, coverage and lost replies. The literature agrees on the same failure kinds. Against it: one book, one model, one seed, a first prompt, one reader, 24 questions, web sources read as search results only. Demand is the owner's word (`research.md`). |
| Value vs. inaction | adequate | Inaction risks nothing and costs only opportunity. The owner keeps studying without practice questions, or uploads the book to a cloud tool. The project keeps no measure of how local models do this task. Option B serves both of the owner's purposes for weeks of work (`problem.md` § Cost of Inaction, `concept.md`). |
| Feasibility / appetite | adequate | gpt-oss wrote usable questions at 5 to 9 s a call: 20 of 24 keys sound, every passage pointer right. Option B's application-side parts are days of known work. Its appetite, a few weeks, is uncertain because of prompt rounds on real models and the key-check experiment, which `concept.md` time-boxes behind a rule fixed in advance. |
| Strategic fit | adequate | The idea meets the constitution as shaped: local models only (I), one service (IV), real-model checks (V), a repeatable measurement and a check that must prove itself (VI), and questions tied to passages (VII). A study quiz serves the reader more than the research platform's stated purpose. The repeatable measurement is what ties it back (`concept.md` § Recommendation). |
| Risk posture | adequate | The measured risks are named and each has a response. Letter skew is removed by construction, lost replies by retries, bunched questions by passages the application picks, and wrong keys are made visible through the passage. Two remain partly open: the length cue (prompt only, unmeasured) and the flawed keys that remain if the check fails, which the owner hasn't said they accept. Scope risks are named with bounds: the key check, a quality judge, front and back matter, multi-book generality. |

## Verdict & Rationale

**Go, with Option B: a quiz the application vouches for.**

Every criterion is adequate, and none is weak or unknown. That is enough for a go, and not more.

The idea would be a kill as first described, which is Option A of `concept.md`. The probe showed
what A would deliver:
- about 1 question in 6 marking a defensible answer wrong, or rewarding one the book doesn't give;
- 54% for always answering B;
- most of each batch never asked about;
- 2 replies in 10 lost without a sign.

A study tool with those properties would mislead the one person it serves.

Option B survives because the probe also showed where the failures live. The letter, the passages,
the score and the lost replies are all things the application can own, by construction rather than
by hoping for a better model. What only the model can do, a sound key, becomes visible to the
reader through its passage and measurable through a repeatable probe. That probe is also what the
owner's second purpose needs. The one part whose worth is unknown, the key check, doesn't hold the
feature hostage: a rule fixed in advance keeps it or drops it, and B ships either way. This
repository has done the same before: `specs/002-gemma4-default-llm` set its rule before the runs,
and historical spelling shipped switched off.

**Not a "needs-clarification".** Three of the problem's open questions are still unanswered by the
owner:
- whether questions may reach beyond the book;
- what share of flawed keys is acceptable;
- how long preparation may take.

None decides whether to build. Each shapes what to build, and `/speckit-specify` and
`/speckit-clarify` exist to ask them:
- **Beyond the book.** Constitution VII largely settles it: keys trace to passages.
- **Flawed keys.** The rule for the key check and the visible passage answer the risk, whatever the
  target turns out to be.
- **Preparation time.** Option B's estimate is about a minute, against the 48 to 104 s the owner
  already waits for a chapter's summary.

They go to the spec as its first clarifications, not as reasons to wait.

## If needs-clarification

Not applicable.

## If go — Handoff to `/speckit-specify`

Input for `/speckit-specify`, on a `feat/chapter-quiz` branch created from an up-to-date `main`
after this assessment merges:

- **Problem**: A reader studying a book from their library can't practice on it under graded
  conditions, or learn which chapters they have yet to master. A quiz written by the model as is
  can't be trusted. In the probe, about 1 question in 6 marked a defensible answer wrong or
  rewarded one the book doesn't give, and always answering B scored 54%.
- **Chosen approach**: Option B of `concept.md`.

  **What the reader sees:**
  - **A Quiz tab.** One book, then one chapter or the whole book, like the other tabs, and a
    number of questions with a default the reader can change.
  - **The questions.** Each has five options, A to E, with one right answer. The reader answers,
    then submits.
  - **The result.** The score counted as a percentage, the chapters ranked by questions missed,
    and, for each missed question, the right answer, why, from its passage, and its pages.
  - **A download** of the result, with the date and time, the book, and the chapter when the
    quiz is on one.

  **What the application owns:**
  1. Which passages the questions come from, spread over the chosen text.
  2. Which letter holds the right answer, so letters are balanced.
  3. The score, by counting.
  4. Replies that can't be read, or questions not in the asked form, written again, never dropped
     silently.
  5. The default number of questions, derived from the text's length. This departs from the
     idea's "recommended by the LLM", whose recommendations varied from 18 to 25 for one chapter,
     and the owner should confirm it.

  **The key check**, an experiment under a rule fixed in the spec before it is tried. A check
  that reads each question against its passage, before it is shown, is kept only if, on known
  cases, it catches more flawed keys than the model's own open-book check: 1 of the probe's 4. It
  also must not drop too many sound questions, a threshold the spec sets. The known cases start
  from the 24 questions read in `probe/results.json`. If it fails, the feature ships without it,
  and the remaining rate is recorded. Constitution VI applies: it is a judge, and proves itself
  first.

  **The repeatable measurement**, possibly built first. The probe, turned into a measurement any
  configured model can run on fixed chapters with no code change. Computed:
  - the letter spread;
  - how often the key is the longest option;
  - how many the model answers without the passages;
  - where the questions come from;
  - questions delivered against asked;
  - time.

  Key soundness is read by hand on a sample. The baseline is `research.md`'s.
- **In scope / out of scope**:
  - **In**: the tab and its service, the question prompt and its parser, everything the
    application owns above, the explanations, the download, the key-check experiment and its
    rule, the repeatable measurement, and `README.md` and `docs/decisions.md`.
  - **Out**:
    - quizzes on several books, kept easy to add later;
    - hand-picked sets of chapters;
    - anything kept in the application: no history, the download being the record;
    - formats other than five options with one right answer;
    - grading by the model;
    - a quiz-quality judge or a benchmark dataset beyond the key check;
    - difficulty and topic settings;
    - more than one user;
    - models outside this machine.
- **Success metrics** (`problem.md` § Success Metrics, baselines from the probe):
  - **Sound keys**: 20 of 24 (83%). Target to be set by the owner.
  - **Answer patterns**: the most frequent letter scores 54% (B) and the longest option 62%,
    against 20% by chance. The letters reach chance by construction; the length cue is to be
    measured.
  - **Answerable without the passages**: 18 of 24 (75%). It is read according to the
    within-the-book question below.
  - **Coverage**: 14 of 18 questions from the first 3 passages of a batch, and Capítulo 6 asked
    about in 4 page ranges of 79–110.
  - **Delivered against asked**: 24 of 30.
  - **Traceable questions**: 24 of 24.
  - **Time to a quiz**: 15–34 s per chapter, without checks. A whole book hasn't been timed.
  - **The download** holds the date, book, chapter and result.
  - **The measurement** runs for another configured model with no code change.
- **Carried-forward open questions**, in order of impact:
  - [NEEDS CLARIFICATION: Do questions stay within what the book says, as constitution VII
    suggests, or may they cover "the book and its topics" more broadly?]
  - [NEEDS CLARIFICATION: What share of flawed keys does the owner accept, when each question
    shows its passage? The probe had 4 in 24.]
  - [NEEDS CLARIFICATION: How long may preparing a quiz take, for one chapter and for the whole
    book?]
  - [NEEDS CLARIFICATION: Is a default number derived from length acceptable, in place of the
    model's recommendation the idea asked for? Within what bounds?]
  - [NEEDS CLARIFICATION: In a whole-book quiz, how are questions spread across chapters, and are
    front and back matter left out? The catalog can't tell them from chapters.]
  - [NEEDS CLARIFICATION: In a one-chapter quiz, the chapter ranking has one entry. Is the
    feedback the score and the explanations alone?]
  - [NEEDS CLARIFICATION: What does the download hold besides the date, book and chapter, and in
    what format? A saved summary is the precedent.]
  - [NEEDS CLARIFICATION: In which language are the questions written: the book's, or a chosen
    one, as for summaries?]
  - [NEEDS CLARIFICATION: Does a "graded quiz" include a time limit?]
  - [NEEDS CLARIFICATION: The key check's rule: which known cases, which threshold for sound
    questions dropped, and what time box?]
  - The assumptions to validate in `concept.md`:
    - the application can place the right answer without breaking options that refer to each
      other;
    - questions from passages the application picks are as sound as the model's own picks;
    - a second attempt at an unreadable reply usually succeeds;
    - the prompt can bring the length cue down;
    - front and back matter can be left to the reader or a simple rule.

  Per `AGENTS.md`, the feature adds a prompt, parses model output and adds a check that acts as a
  judge, so it runs `/speckit-clarify` before the plan, `/speckit-checklist` after it, and
  `/speckit-analyze` after the tasks. Constitution V asks for the prompt, the parser and the check
  to be verified on real models and real books, not only by unit tests.
