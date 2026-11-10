# Problem Definition: a multiple-choice quiz on chosen chapters

- **Slug**: chapter-quiz
- **Created**: 2026-11-10
- **Inputs used**: intake.md (with the owner's answers of 2026-11-10), research.md (with the probe)

## Problem Statement

A reader studying a book from their library has no way to practice on it under graded conditions,
or to learn which chapters they have yet to master. The application answers their questions and
summarizes chapters, but never asks them anything or measures what they retained. A quiz written by
a model would have to be trustworthy to help. In the probe, about 1 question in 6 would have marked
a defensible answer wrong, or rewarded one the book doesn't give, and always answering B would have
scored 54% without reading.

## Affected Users & Stakeholders

- **Users**:
  - **The owner, as a reader studying a book.** They want to "simulate graded quizes about the
    book and its topics", on one chapter or on the whole book, and to know where they went wrong.
    The app runs only on their machine, "to help me to study" — [source: intake, owner's answers]
  - **The owner, as a researcher.** As hardware and models change, they "could change the models
    over time to improve the quality of the RAG system", and want to see how models compare on
    this task too — [source: intake, owner's answers; constitution I]
- **Stakeholders**:
  - **The project, through its constitution.** Whatever is built stays local (I), puts its logic
    in one service layer (IV), and gets checked on real models (V). It is measured, with any judge
    proving itself first (VI), and every claim traces to a passage (VII). These shape any solution
    — [source: constitution; research § Data & Constraints]
  - The owner is also the only maintainer, and decides.

## Goals

- **Practice under graded conditions** on one chapter, or on the whole book, of one book at a time,
  with multiple-choice questions of five options, A to E, with one right answer each.
- **A score the reader can trust.** A question marked wrong is wrong because of the reader's answer,
  not because of a wrong or ambiguous key. Each question can be checked against the passage it came
  from.
- **A score that reflects knowing the book.** Answer patterns, such as the letter or the length of
  the right option, give no advantage over chance.
- **Learn where the weak points are**: the score, the chapters ranked by questions missed, and, for
  each missed question, why the right answer is right, from the book.
- **A record outside the application**: the result can be downloaded, with when the quiz was taken,
  the book, and the chapter when the quiz is on one.
- **Comparable across models**: how well a model writes the questions can be compared with another
  model, after a configuration change and without code changes.

## Non-Goals

- **Quizzes on several books at once.** "Just one book for now". The owner wants that to be easy
  to add later, so it is out of scope, not ruled out — [source: owner's answers]
- **Hand-picked sets of chapters.** A quiz covers one chapter or the whole book, "similar to what
  the other tabs do" — [source: owner's answers]
- **Anything kept in the application**: no quiz, answer, score or history is saved, "at least for
  this app version". The downloaded result is the only record — [source: owner's answers]
- **Other question formats**: open answers, true or false, flashcards — [source: the idea, A to E
  only]
- **More than one user**: the application runs only on the owner's machine — [source: owner's
  answers]
- **Models outside this machine**, for writing, checking or grading — [source: constitution I]

## Success Metrics

Each baseline is the probe's: gpt-oss:20b, a first untuned prompt, 3 questions per batch, 24
questions read, on chapters 1, 3 and 6 of *História econômica global*.

- **Sound keys**: the share of questions whose key is right and is the only defensible answer,
  read against the passage. Baseline: 20 of 24 (83%). Target: [NEEDS CLARIFICATION: what share
  the owner accepts].
- **No advantage from answer patterns**: the score of always answering the most frequent letter,
  and of always taking the longest option. Baseline: 54% (B) and 62%. By chance, both would be
  20%.
- **Answerable without the book**: the share the generating model answers correctly without the
  passages. Baseline: 18 of 24 (75%). Target: [NEEDS CLARIFICATION: it depends on whether
  questions may cover "the book and its topics" beyond what the book says].
- **Coverage of the chosen text**: where in the chapter the questions come from. Baseline: in
  batches of 9–10 passages, 14 of 18 questions came from the first 3. Capítulo 6's questions came
  from 4 page ranges of its 79–110. Target: [NEEDS CLARIFICATION: how even the spread should be].
- **Questions delivered as asked**: usable questions per question requested. Baseline: 24 of 30,
  since 2 of 10 replies were unreadable.
- **Traceable questions**: the share whose passage, with its pages, can be shown and holds the
  question's subject. Baseline: 24 of 24.
- **Time to a quiz**: from asking to answering, for one chapter and for the whole book. Baseline:
  15–34 s per chapter, without checks. A whole-book quiz hasn't been timed. For reference, a
  chapter's summary takes 48–104 s. Target: [NEEDS CLARIFICATION: the owner's tolerance].
- **Comparable across models**: the measures above can be repeated for another configured model,
  on the same chapters, with no code change. Baseline: no such measurement exists.
- **The downloaded record** holds the date and time, the book, the chapter when there is one, and
  the result. Baseline: none (binary).
- **Use** (qualitative): the owner studies with it, and finds the chapters it sends them back to
  worth rereading. Baseline: none.

## Cost of Inaction

Nothing breaks, and nothing is at risk. The owner keeps studying without practice questions, or
writes them by hand, or uses a cloud service such as NotebookLM, which means uploading the book
this project keeps local. The project also keeps no measure of how local models write questions,
so changing models or hardware tells the owner nothing about this task. The cost is opportunity,
not damage.

## Open Questions

- [NEEDS CLARIFICATION: Do questions stay within what the book says, or may they cover "the book
  and its topics" more broadly, as an exam would? Constitution VII ties claims to passages, and the
  answer decides what the "answerable without the book" metric should be.]
- [NEEDS CLARIFICATION: What share of flawed keys can the owner accept, given that each question
  can show its passage? The probe had 4 in 24.]
- [NEEDS CLARIFICATION: How long may a quiz take to prepare, for one chapter and for the whole
  book?]
- [NEEDS CLARIFICATION: In a whole-book quiz, how are questions spread across chapters, and are
  front and back matter (acknowledgements, references, lists of tables) left out?]
- [NEEDS CLARIFICATION: In a one-chapter quiz, the chapter ranking has a single entry. Is the
  feedback then the score and the explanations alone? The owner didn't choose "sections and
  pages".]
- [NEEDS CLARIFICATION: Does a "graded quiz" include anything beyond the score, such as a time
  limit, or answers hidden until submission?]
- [NEEDS CLARIFICATION: What does the downloaded result hold besides the date, book and chapter:
  the questions, the reader's answers, the keys, the explanations? In what format?]
- [NEEDS CLARIFICATION: Are the probe's problems (wrong keys, letter skew, length cue, questions
  bunched at the start) properties of gpt-oss, or of the first prompt? Untested: other prompts,
  other seeds, other models.]
- [NEEDS CLARIFICATION: How can question quality be measured across models, given that a judge
  has to prove itself first (constitution VI), and the model's own check caught 1 of 4 flawed
  keys?]
- [NEEDS CLARIFICATION: In which language are the questions written: the book's, or a chosen one,
  as summaries allow?]
- [NEEDS CLARIFICATION: How is the recommended number of questions set, and within what bounds?
  The model's own recommendations varied from 18 to 25 for the same chapter.]
