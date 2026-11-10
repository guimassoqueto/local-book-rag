# Idea Intake: a multiple-choice quiz on chosen chapters

- **Slug**: chapter-quiz
- **Created**: 2026-11-10
- **Source**: pasted text; related repo paths: `app/interface/` (the Gradio tabs),
  `app/services/book_service.py` (`chapters`), `app/generation/summarization.py` (the other
  feature that reads whole chapters)
- **Type**: new-capability

## Idea (as captured)

> "Create a tab where we select a chapter (or multiple chapters), and the system generates an
> questionnaire with N questions (defined by the user and a number recommended by the LLM by
> default based on chapters lenght and content), with options from A to E, where only one is
> right. After the user submit the answers the LLM evaluate the answers and give the user a score
> (right answers percentual), and suggest improvements on specific chapters (where the user made
> the most mistakes)."

## Restated

A new tab where the reader picks one or more chapters and gets a multiple-choice questionnaire
written by the LLM: N questions, each with five options, A to E, exactly one of them correct. N
defaults to a number the LLM recommends from the chapters' length and content, and the reader can
change it. After the reader submits their answers, they get the share they got right, as a
percentage, and suggestions on which chapters to improve, by where the mistakes were.

## Origin & Context

- **Raised by**: the repository owner, through `/speckit-assess-intake` on 2026-11-10.
- **Trigger**: given as the owner's next planned implementation, after v0.2.1. No triggering
  event (a failure, a request) was stated. What the quiz is for is in the owner's answers below.
- **Current state, as found** (facts, not assessment):
  - The interface has four tabs: Library, Chat, Summarization and Research.
  - Nothing in `app/`, `config/`, `README.md` or `docs/` generates questions for the reader, or
    keeps a reader's answers or scores.
  - Chapters are listed per book from the catalog (`BookService.chapters`), as number and title.
  - The Summarization tab works on one chapter of one book. A summary goes through the whole
    chapter by map-reduce, so that each prompt fits the context, and cites by lookup: each
    statement is matched with the closest chunk of the chapter
    (`RetrievalService.closest_chunk`).
  - The Chat tab can scope a question to one chapter of one book, or to all of them, but not to a
    set of chapters.
  - Answers can be written in the book's language or in one of six configured languages
    (`generation.response_languages`).

## Owner's Answers (2026-11-10)

Given after research, before `/speckit-assess-define`, to four questions with suggested options.
The owner's own words are quoted.

- **What the quiz is for**: all three options offered (study a book, check one's reading, compare
  the models), and: "Mostly to personal study and simulate graded quizes about the book and its
  topics, but in future, i could upgrade my hardware (add RAM and GPU power, and CPU), i could
  change the models over time to improve the quality of the RAG system."
- **Which chapters**: "Just one book for now (make sure to make easy to improve the system to
  consider multiple books in future, but for now, one is enough). One chapter or the entire book
  (similar to what the other tabs do)." This replaces "a chapter (or multiple chapters)" in the
  idea as captured.
- **What is kept**: "Let me download the results, with little information about when the test was
  taken, the book and the chapter (if the test is about a specific chapter). Do not save nothing
  (at least for this app version, since it is running only in my machine to help me to study)."
- **What the feedback contains**: the options "Chapters to reread" (ranked by questions missed),
  "Why each was wrong" (the right answer explained from its passage) and "The score only". Read
  together, the last is taken as "the score" too, not as "nothing more".

## First-Glance Unknowns

- [NEEDS CLARIFICATION: Can the chosen chapters come from more than one book, or only from one?]
- [NEEDS CLARIFICATION: Who sets the recommended N? The idea says the LLM recommends it from the
  chapters' length and content. What are the bounds: a minimum, a maximum, a cap on how many
  chapters can be chosen at once?]
- [NEEDS CLARIFICATION: "The LLM evaluate the answers": is the score meant to come from the LLM,
  or from comparing the reader's letters with the answer key? What is the LLM asked to judge
  beyond that?]
- [NEEDS CLARIFICATION: What is a "suggested improvement" on a chapter: the chapter's name, the
  sections or pages to reread, an explanation of each wrong answer, the correct answer?]
- [NEEDS CLARIFICATION: How is "only one option is right" ensured? A question whose key is wrong,
  or that has two defensible answers, would mark the reader wrong for a right answer. What happens
  when the model doesn't write five options, or marks no key, or two?]
- [NEEDS CLARIFICATION: Does each question have to point back to the passage it was written from,
  as answers and summaries do (constitution VII)?]
- [NEEDS CLARIFICATION: What kind of questions: recall of facts, comprehension of arguments,
  vocabulary? Any difficulty setting?]
- [NEEDS CLARIFICATION: In which language are the questions written: the book's, or a chosen
  one?]
- [NEEDS CLARIFICATION: Are questionnaires, answers or scores kept after the session, so that
  progress over time can be seen? Or is each quiz used once and forgotten?]
- [NEEDS CLARIFICATION: How long may generating a questionnaire take? With gpt-oss, a summary of
  one chapter took 48.6 s to 104 s on average across the benchmark runs
  (`docs/benchmark-results.md`), and up to 272 s for one chapter
  (`.specify/assessments/gemma4-default-llm/research.md`). Several chapters hold more text.]
- [NEEDS CLARIFICATION: How would the quality of the questions be measured: which real books,
  which models, which benchmark or check (constitution V and VI)?]
- [NEEDS CLARIFICATION: Does the idea need a commands counterpart (`app/main.py`), or only the
  Gradio tab? Constitution IV puts the logic in a service either way.]
