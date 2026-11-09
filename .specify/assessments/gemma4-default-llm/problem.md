# Problem Definition: the default LLM fails the library's own tasks in known ways

- **Slug**: gemma4-default-llm
- **Created**: 2026-11-09
- **Inputs used**: intake.md, research.md

The idea arrived as a solution: "make gemma4:12b the default". This file states the problem that
switch is meant to solve, so the options in `/speckit-assess-shape` can be weighed against it.
Every figure below comes from `research.md`.

## Problem Statement

The model that answers questions and summarizes chapters by default was chosen before anything was
measured, and no reason for it is recorded. Measured since, it fails the platform's own tasks in
repeatable ways, worst on the Portuguese novel:

- It abstains when the passages hold the answer.
- It summarizes the novel poorly, and once misattributed who said what.
- Its summaries take long, and how long varies widely.
- Asked over the whole library, it sometimes answers a question the books can't answer, with a
  false citation.

These undercut what a reader relies on most here: that every answer and summary is traceable to
the book and faithful to it. They matter now because the benchmarks have only just made the
failures visible, and the measurements that would justify any default are now available.

## Affected Users & Stakeholders

- **Users**:
  - **The owner as a reader**, asking questions of the books and summarizing chapters in English
    and Portuguese. A wrong abstention hides an answer the passages hold. A misattributed summary
    or a false citation misleads them while looking traceable. A slow summary keeps them waiting
    (`research.md` § Market & Context).
  - **The owner as a researcher**, for whom this is a platform for comparing open-weight models.
    The default is the configuration everything else is measured on, and it has no recorded
    justification (`research.md` § Prior Art).
- **Stakeholders**:
  - **The owner as maintainer and sole decider**. They keep the constitution's rules:
    measurements decide a default (VI), every answer is traceable (VII), decisions are recorded
    (VIII). They also keep code, tests and documents that were tuned around the current default:
    an integration test assumes the default's tokenizer is exact (`research.md` § Data &
    Constraints).
  - **The benchmark judge**, which isn't a person but has a stake. Its scores mean something only
    because it proved itself on known-answer cases. Anything that changed it would have to prove
    it again (`docs/benchmark-results.md` § Recommendations).
- [NEEDS CLARIFICATION: Does anyone else use or read this library, or the benchmark record, such
  as readers of the published repository? `research.md` found only the owner.]

## Goals

- Answers in use don't abstain when the passages in front of the model hold the answer.
- Answers and summaries stay traceable: no citation of a passage that doesn't say what is
  claimed, and no answer to a question the books can't answer, whether one book or the whole
  library is searched.
- Chapter summaries say what the chapter claims, and attribute it to the right character or
  author, including for the Portuguese novel.
- A chapter summary takes a predictable and shorter time.
- Answer quality doesn't fall where it is good today: correctness, relevance, multi-section
  questions, summary consistency and coherence.
- Whatever the default ends up being, the measurement and the reason that chose it are recorded,
  so the next comparison starts from a justified baseline.

## Non-Goals

- **Changing the benchmark judge**, its prompts or its reasoning. It stays as it is, so that its
  known-answer checks still hold (`intake.md`).
- **Changing prompts or how model output is parsed**, including the footnote markers some books
  carry. Doing so would change what the existing benchmarks measured.
- **Retrieval speed**, which dominates the time to an answer (12 to 20 s over the whole library),
  and where the reranker and query embeddings run.
- **Uses for freed VRAM.**
- **Making the judge less noisy**, or adding summary chapters so the rubric separates models
  better. These limit the evidence, but are problems of their own.
- **Candidate models beyond the four already benchmarked**: gpt-oss:20b, gemma4:12b, qwen3.5:9b,
  qwen3:14b. [NEEDS CLARIFICATION: Confirm this bound, or say the problem is open to any model.]
- **Embedding, chunking and the index.** Nothing here touches what is stored.

## Success Metrics

All are read through the project's own benchmarks. A change counts only when its paired
bootstrap interval excludes zero (constitution VI). "Not worse" means no difference whose interval
excludes zero downward. The answers and summaries in `rows.csv` are read before concluding.

- **Wrong abstentions** on the 75 answerable questions. Baseline: 3 in the full run, 5 in the
  interrupted one, all on *Quincas Borba*.
- **Abstention quality**, with the marker recognized since `c7dd6ac`. Baseline: 0.956.
- **Citation accuracy**. Baseline: 0.944 (full run), 0.914 (interrupted).
- **Whole-library trap answered** (`quincas_borba_unanswerable_04`, no book filter). Baseline: 1
  in 3 runs, with a false citation. Qualitative, small n.
- **Invented citations**. Baseline: 1 in 90 answers, in both runs.
- **Faithfulness, overall and by book.** Baseline: 0.813 overall in the full run. On the novel,
  0.633 in the full run and 0.882 in the interrupted one, so a single run doesn't establish it.
- **Answer correctness and relevance not worse.** Baseline: 0.706 and 0.783.
  Multi-section correctness: 0.585 over 13 questions.
- **Summary argument coverage**. Baseline: 0.543 overall, 0.211 on the novel's two chapters.
- **Summary consistency and coherence not worse.** Baseline: 0.833 and 0.833 in the latest run,
  0.958 and 0.917 in the run before.
- **Summary time and steps per chapter**. Baseline: 104 s and 9.8 steps on average, up to 272 s
  and 24 steps.
- **Time to the first visible word of an answer**, measured in the app's own path, whole library.
  Baseline: about 0.4 s of prompt reading on a ~2,100-token prompt, after 12 to 20 s of
  retrieval. [NEEDS CLARIFICATION: How much slower is acceptable?]
- **Repeatability of answers between runs.** Baseline: 3 of 90 answers identical between the two
  generation runs. Qualitative. It matters to a research platform, but no rule asks for it.
- **The default's reason is recorded** in `docs/decisions.md`, with the run it rests on. Baseline:
  no reason recorded. Qualitative, yes/no.

## Cost of Inaction

Nothing breaks if nothing changes. The application works, the judge is unaffected, and no code,
test or document has to move. What stays:

- Answers on the novel keep abstaining with evidence in front of them, 3 to 5 times in 75
  answerable questions.
- Novel summaries keep missing most of what the chapters claim (0.211 coverage), with
  misattribution seen in one.
- Summaries keep taking 104 s a chapter on average, and up to 272 s.
- Whole-library questions keep a demonstrated path to a confident, falsely cited answer, the
  failure constitution VII exists to prevent.
- The default keeps resting on no measurement, while the platform's stated purpose is to choose
  by measurement.
- 12.5 GB of the 16 GB GPU stays taken by the LLM.

Against that, inaction carries no risk of new, unobserved failures from a less-exercised model.
Any change has to weigh this. gpt-oss's failure modes are known and handled, and an alternative's
are only partly known (`research.md` § Evidence Against the Idea).

## Open Questions

- [NEEDS CLARIFICATION: Why was gpt-oss:20b the first default? Did `.TASK/task.md` name it, and
  for a reason that still holds? Nothing in the repository says.]
- [NEEDS CLARIFICATION: Which matters more in the owner's own use, answers or summaries, and
  whole-library questions or single-book ones? The evidence favors an alternative more clearly
  for summaries than for answers.]
- [NEEDS CLARIFICATION: Is one full generation run enough evidence, or does a second run on
  current `main` have to agree first? `docs/benchmark-results.md` itself recommends two before
  trusting a faithfulness difference, and the two runs disagree on the novel.]
- [NEEDS CLARIFICATION: How much slower to the first visible word is acceptable? Measured in use,
  the gap between candidates is about half a second, against 12 s or more of retrieval.]
- [NEEDS CLARIFICATION: Is the lower multi-section correctness, about −0.10 in both runs with
  intervals touching zero, a real weakness or the judge preferring fuller answers? Reading all 13
  pairs would tell.]
- [NEEDS CLARIFICATION: What did the judge object to in the *Think Python* summaries scored 0.5 on
  consistency? Reading them against their chapters would show whether they go beyond the
  passages.]
- [NEEDS CLARIFICATION: Do the unbenchmarked uses count toward the decision? These are the
  `brief`, `comprehensive` and `analytical` summary types, the other interface languages, and
  long whole-library sessions. Or are they risks to accept and watch?]
- [NEEDS CLARIFICATION: Are the candidates bounded to the four already benchmarked?]
- [NEEDS CLARIFICATION: Does anyone besides the owner rely on the defaults or the benchmark
  record?]
