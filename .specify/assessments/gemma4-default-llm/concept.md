# Concept: choosing the default LLM by measurement

- **Slug**: gemma4-default-llm
- **Created**: 2026-11-09
- **Recommended option**: Option C — confirm, then switch

The options below answer `problem.md`. All of them keep gpt-oss:20b as the benchmark judge, and
none changes a prompt, a parser or the index. Figures come from `research.md`.

## Options

### Option A — Keep gpt-oss:20b, and record why

- **Sketch**: The default stays gpt-oss:20b. What changes is the record: `docs/decisions.md`
  states the comparison, what favored each model, and why the evidence didn't clear the bar for a
  switch. The Recommendations in `docs/benchmark-results.md` then point to that reason, not to an
  open suggestion. The reader sees no difference in use.
- **Appetite**: small (hours).
- **Trade-offs**: Meets one goal, the recorded reason, and none of the others.
  - The failures it leaves were observed in both runs: wrong abstentions on the novel (3 and 5 in
    75), novel summaries at 0.211 coverage, summaries at 104 s a chapter (up to 272 s), and the
    whole-library trap answered in 1 of 3 runs.
  - It risks nothing new: gpt-oss's failure modes are known and handled.
  - The recorded reason would be weak. The one advantage gpt-oss showed, faster prompt reading, is
    about half a second in use, against 12 s or more of retrieval.
- **Rabbit holes**: Few. The record could turn into an argument for gpt-oss the data doesn't
  make. Measured, it wins on prompt reading, summary consistency and coherence, and multi-section
  correctness, and only consistency ever excluded zero, in one run.

### Option B — Switch to gemma4:12b now, on the existing runs

- **Sketch**: `llm.model` becomes gemma4:12b on the evidence already gathered, and gpt-oss stays
  the judge. The surroundings follow:
  - the README and `docs/decisions.md` say what the default is and why;
  - the benchmark write-up's "(default)" labels and Recommendations move;
  - getting the judge onto a machine no longer happens by accident, since `pull-models` brings
    gpt-oss today only because it is the default;
  - the integration test that assumes the default's tokenizer is exact accounts for an
    approximate one.

  In use, answers stop abstaining with evidence present, summaries come about three times
  faster, and the first word of an answer arrives about half a second later.
- **Appetite**: small (a day or two).
- **Trade-offs**: It is the fastest route to the goals the robust evidence supports. That
  evidence doesn't depend on a single judge score:
  - 0 wrong abstentions in both runs;
  - summary time and step counts, which are measured, not judged;
  - novel coverage;
  - the trap refused 3 of 3 times;
  - gemma4's answers repeating byte for byte.

  It sacrifices the project's own rule that a single faithfulness run isn't trusted. It also
  ships with three concerns unresolved:
  - multi-section correctness about 0.10 lower in both runs (interval touching zero);
  - summary consistency lower in both runs (excluding zero once);
  - *Think Python* summaries scored 0.5 on consistency in 3 of 4 chapter-runs, never read.

  The faithfulness lead it would be credited with is mostly the judge and gpt-oss varying on the
  novel.
- **Rabbit holes**:
  - **Failures found in use.** If gemma4 shows a new failure once it is the default, the tempting
    fix is a prompt or parser patch. Each needs real-model checks and benchmark reruns (V, VI),
    and the switch grows into prompt work.
  - **Footnote markers.** gemma4 copies a book's footnote markers, `[7]`, as citations. Fixing
    that is a parser change, a non-goal.
  - **The marker in other languages.** The no-evidence marker is recognized only as
    `[NO-EVID…]`. gemma4 translated it into Portuguese once, and the interface also offers
    Spanish, French, German and Italian. A French or German translation wouldn't be recognized,
    and an abstention would show as an answer.

### Option C — Confirm on current `main`, then switch or keep by a rule set in advance

- **Sketch**: Before the default changes, the doubtful parts of the evidence are checked, against
  a decision rule written down before any number comes in:
  - **Reruns.** One more full generation run and one more summarization run, on current `main`,
    with the same dataset, judge, models and Ollama version as before. gemma4's answers are
    deterministic, so on its side the rerun resamples only the judge. On gpt-oss's side it
    resamples both answers and judge.
  - **Reading.** The 13 multi-section answer pairs, and the *Think Python* summaries scored 0.5,
    read against their passages, as constitution VI asks before concluding.
  - **A small probe** of what the benchmark doesn't cover:
    - the whole-library trap again;
    - the no-evidence marker in the four response languages the benchmark never uses;
    - one `comprehensive` or `analytical` summary.

  **The rule**: switch if the confirmation repeats the wins that motivated it and shows no metric
  worse with an interval excluding zero, and the reading finds no systematic weakness. Otherwise,
  keep gpt-oss and record why, which is Option A. Switching then carries Option B's
  surroundings.
- **Appetite**: small (days), most of it machine time. The last full generation run took 3 h 43
  min. The summarization run's total isn't recorded in `research.md`. Writing the six summaries
  alone took about 4 min for gemma4 and 10 min for gpt-oss, and judging comes on top. The
  reading and the probe are hours.
- **Trade-offs**:
  - It meets every goal the problem sets, through the project's own rules: two runs before a
    faithfulness claim, intervals that exclude zero, outputs read before conclusions.
  - It spends a few days and a run's worth of GPU time, and keeps the current failures a few
    days longer.
  - It can still end in "keep gpt-oss". That isn't a failure of the option: it is Option A with a
    better reason.
  - The judge's noise doesn't go away with one more run. The rule has to accept that, not chase
    certainty.
- **Rabbit holes**:
  - **Running until the noise settles.** It never fully does. The rule allows one confirmation
    run, not a series.
  - **Growing the benchmark.** The probe could become new dataset work: whole-library questions,
    more chapters, the other summary types, the other languages, `validate-benchmark`. Those are
    their own changes. The probe here only looks.
  - **Widening the candidates.** qwen3.5:9b led summary coverage (+0.167, excluding zero), but its
    answer correctness was lower (−0.054, excluding zero). Re-opening the field turns a
    confirmation into a new comparison.
  - **Tuning gemma4's temperature or token limits** while confirming. Every setting changed needs
    its own baseline.
  - **The marker or footnote findings.** If the probe finds an unrecognized marker in a language,
    or footnotes cited, the fix is a parser change. That gets its own bug or feature. The rule
    decides whether it blocks the switch.

## Recommendation

**Option C.** The problem's metrics only count a difference whose interval excludes zero.
Re-analysed, the evidence splits in two:

- **Robust, and enough to motivate a switch**: no wrong abstentions (both runs), summary speed and
  stability (measured, not judged), novel coverage, the trap refused 3 of 3 times, and
  repeatable answers.
- **Doubtful**: the faithfulness lead, the only answer difference that excluded zero, which
  reverses on the novel between runs. Against gemma4, the lower multi-section correctness and
  summary consistency, which repeated in direction across runs.

Option B would ship on the robust part while ignoring the doubtful part, against a rule the
project wrote for exactly this case: two runs before trusting a faithfulness difference
(`docs/benchmark-results.md` § Recommendations). Option A would keep known failures to avoid a
risk the evidence mostly doesn't show. Option C costs days, mostly machine time. It turns the
open questions in `problem.md` into answers, and whichever way it comes out, it leaves the
recorded reason the problem asks for.

The rule should be written into the spec before the runs start, so that the result can't be
fitted to it afterwards.

If it ends in a switch, it becomes a feature (`feat/…`, `/speckit-specify` onward). It touches
no prompt, parser, judge or metric, so the extra clarify, checklist and analyze steps in
`AGENTS.md` don't apply. Constitution VI and VIII do: the benchmark comparison, and the README
and `docs/decisions.md`.

## Out of Scope (for the recommended option)

- Changing the judge, its prompts or reasoning (inherited).
- Changing prompts or output parsing, including marker recognition in other languages and
  footnote markers taken as citations (inherited). Findings go to their own bug or feature.
- Retrieval speed, device placement, and uses for freed VRAM (inherited).
- Reducing the judge's noise, or growing the dataset: more chapters, whole-library questions,
  other summary types, other languages (inherited and newly excluded). The probe only looks.
- Candidates beyond the four benchmarked, and re-opening the comparison with qwen3.5:9b or
  qwen3:14b (newly excluded).
- **A model per task**, such as one for summaries and another for answers. The summary evidence
  favors gemma4 more clearly than the answer evidence does, which points that way. It needs a new
  setting, and two models that can't share the 16 GB GPU (9.2 + 12.5 GB). Revisit only if the
  confirmation shows answers favoring gpt-oss while summaries favor gemma4 (newly excluded).
- Tuning gemma4's temperature, token limits or reasoning (newly excluded).
- Embedding, chunking and the index (inherited).

## Assumptions to Validate

- **The rerun is comparable.** Same dataset checksum, Ollama 0.40.15, and the same digests for
  gemma4:12b (`6114515d63c1…`), gpt-oss:20b (`f38aa0c53da5…`) and the embedding model. A model
  pulled again can bring new weights under the same tag.
- **gemma4 stays deterministic** on the benchmark's settings, so its side of the rerun samples
  only the judge.
- **The 10% safety margin covers gemma4's tokenizer on whole summary batches**, not only on the
  24 single chunks of Probe B, whose worst undercount was about 6%.
- **No code depends on the default being gpt-oss.** Constitution I forbids branching on a model
  name, and unit tests use `gpt-oss:20b` only as fixture data. A search of `app/` and `tests/`
  should confirm it.
- **The benchmarks keep working with gemma4 as default and gpt-oss as judge.** The judge is named
  on its own in the experiments, and `pull-models --all` brings it.
- **The slower prompt reading stays negligible in use**, as Probe A showed on two questions with
  12 to 20 s of retrieval in front of it, including on long summary batches.
- **The benchmark's balance of answers and summaries matches the owner's use**, closely enough
  for its scores to decide. `problem.md` leaves this open.
- **The judge's preference for its own writing doesn't reverse the picture.** It can't be fully
  checked with gpt-oss judging. The confirmation can only show whether the differences repeat.
- **A translated marker in Spanish or Italian would still be recognized** (`[NO-EVIDENCIA]`,
  `[NO-EVIDENZA]` start with `[NO-EVID`), and French or German wouldn't. The probe should show
  what gemma4 actually writes.
