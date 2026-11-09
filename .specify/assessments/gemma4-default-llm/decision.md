# Decision: choosing the default LLM by measurement

- **Slug**: gemma4-default-llm
- **Decided**: 2026-11-09
- **Verdict**: go
- **Artifacts reviewed**: intake.md, research.md, problem.md, concept.md

## Scorecard

| Criterion | Rating | Justification |
|-----------|--------|---------------|
| Problem validity | strong | The failures repeat across runs and were reproduced in use: gpt-oss made 3 and 5 wrong abstentions in 75 answerable questions, all on the novel. It covered 0.211 of the novel summaries' key points. Summaries took 104 s a chapter, up to 272 s. It answered the whole-library trap with a false citation in 1 of 3 runs. The default rests on no recorded reason (`research.md`). |
| Evidence strength | adequate | The wins that motivate a switch repeated in both runs, or are measured rather than judged: abstentions, summary time and steps, novel coverage, the trap, repeatable answers. The one answer-score difference that excluded zero, faithfulness, reverses on the novel between runs. Multi-section correctness and summary consistency lean against gemma4 in both runs. There is one judge, which is also a candidate, on a small dataset (`research.md` § Evidence Against). |
| Value vs. inaction | adequate | Inaction breaks nothing and risks nothing new. But it keeps the observed failures, and a default that the platform's own rule (VI) says should rest on a measurement. The recommended option costs days, mostly machine time (`problem.md` § Cost of Inaction, `concept.md`). |
| Feasibility / appetite | strong | The switch is a configuration change. The profile already exists, the judge is configured separately, and no code branches on a model name. The surrounding work is documents, how the judge gets pulled, and one integration test. Option C is small: days, most of them runs (`concept.md`). |
| Strategic fit | strong | It serves principle VI (a default chosen by benchmark, with intervals and reading), VII (fewer false citations and wrong abstentions) and VIII (the reason recorded). It also keeps I: one line of configuration, a profile already validated at startup. It touches no prompt, parser, judge or index (`concept.md` § Recommendation). |
| Risk posture | adequate | The main risks are named, and the confirmation either checks them or the decision rule gates them: an unrecognized marker in French or German, footnote markers taken as citations, the tokenizer approximation on whole summary batches, the untested summary types, and the doubtful score differences. One risk can't be removed: with gpt-oss judging, its preference for its own writing can't be checked, only seen to repeat or not (`concept.md` § Assumptions). |

## Verdict & Rationale

**Go, with Option C (confirm on current `main`, then switch or keep by a rule set in advance).**

The problem is real and measured, and the switch is cheap and inside the constitution. That alone
would support a switch now, but the evidence is only adequate: the wins in abstentions, summary
speed, novel coverage and the trap are robust, while the score differences that would be quoted
for a switch are doubtful, and two point the other way.

Option C is the honest response to that mix. It costs days, mostly runs, and it applies the
project's own rule of two runs before trusting a faithfulness difference. It reads what the scores
can't settle, and its outcome is fixed in advance. If the confirmation fails the rule, the feature
ships Option A instead: gpt-oss stays, with the reason recorded. This repository has done that
before, when historical spelling shipped switched off (`af10c0f`).

No criterion is `weak` or `unknown`. The open questions below shape the spec, and none blocks
writing it.

## If needs-clarification

Not applicable.

## If go — Handoff to `/speckit-specify`

Input for `/speckit-specify`, on a `feat/gemma4-default-llm` branch created from an up-to-date
`main`:

- **Problem**: The default LLM, gpt-oss:20b, was chosen before any measurement, and no reason for
  it is recorded. Measured since, it fails the platform's own tasks in repeatable ways:
  - it abstains with the evidence in front of it (3 and 5 times in 75 answerable questions, all
    on *Quincas Borba*);
  - it covers 0.211 of the novel summaries' key points, and once gave one character's words to
    another;
  - its summaries take 104 s a chapter on average, up to 272 s;
  - over the whole library, it answered a trap the books can't answer, with a false citation, in
    1 of 3 runs.
- **Chosen approach**: Option C of `concept.md`, in four parts.
  1. **A decision rule, written into the spec before any run.** The starting point to refine:
     switch to gemma4:12b only if
     - (a) in the confirmation runs, no answer or summary metric is worse than gpt-oss with a
       paired interval excluding zero;
     - (b) the wins that motivated it repeat: fewer wrong abstentions, fewer seconds and steps per
       summary, higher novel coverage;
     - (c) the reading finds no systematic weakness.

     Otherwise keep gpt-oss:20b, and record why.
  2. **Confirmation on current `main`.** One full generation run and one summarization run, with
     the same dataset checksum, the same judge, the same model digests and Ollama 0.40.15. Verify
     all of these before the runs.
  3. **Reading.** All 13 multi-section answer pairs, and the *Think Python* summaries scored 0.5
     on consistency, against their passages.
  4. **A probe of what the benchmark doesn't cover.** The whole-library trap, the no-evidence
     marker in Spanish, French, German and Italian, and one `comprehensive` or `analytical`
     summary.

  **If the rule says switch**: `llm.model` becomes gemma4:12b, and gpt-oss:20b stays the judge.
  The README and `docs/decisions.md` record the default and its reason, and
  `docs/benchmark-results.md` records the confirmation runs and moves its "(default)" labels and
  Recommendations. Getting the judge model onto a machine is made deliberate: `pull-models`
  brings it today only because it is the default. The integration test that assumes an exact
  tokenizer accounts for an approximate one.

  **If the rule says keep**: only the records change.
- **In scope / out of scope**:
  - **In**: the rule, the confirmation runs, the reading, the probe, and either the switch with
    its surroundings or the recorded reason to keep.
  - **Out**:
    - changing the judge;
    - changing prompts or output parsing, including recognizing the marker in other languages
      and footnote markers taken as citations. Findings become their own bug or feature;
    - retrieval speed, device placement, and uses for freed VRAM;
    - the judge's noise, and growing the dataset;
    - candidates beyond the four benchmarked, and re-opening the comparison with the qwen models;
    - a model per task;
    - tuning gemma4's temperature, token limits or reasoning;
    - embedding, chunking and the index.
- **Success metrics** (`problem.md` § Success Metrics), each read as a paired difference with gpt-oss:
  - **Wrong abstentions**: baseline 3 and 5 in 75.
  - **Abstention quality**: baseline 0.956.
  - **Citation accuracy**: baseline 0.944.
  - **Invented citations**: baseline 1 in 90.
  - **Faithfulness**: baseline 0.813 overall, and by book.
  - **Correctness and relevance not worse**: baseline 0.706 and 0.783. Multi-section correctness:
    0.585.
  - **Summary coverage**: baseline 0.543, and 0.211 on the novel.
  - **Summary consistency and coherence not worse**: baseline 0.833 and 0.833.
  - **Seconds and steps per summary**: baseline 104 s and 9.8 steps.
  - **The trap**: baseline 1 of 3 answered.
  - **Time to the first visible word in use**: baseline about 0.4 s of prompt reading, after 12 to
    20 s of retrieval.
  - **The default's reason recorded**.
- **Carried-forward open questions**:
  - [NEEDS CLARIFICATION: Why was gpt-oss:20b the first default? Did `.TASK/task.md` name it, and
    for a reason that still holds?]
  - [NEEDS CLARIFICATION: Which matters more in the owner's use, answers or summaries? It decides
    how a mixed result is read, such as summaries better and multi-section answers worse.]
  - [NEEDS CLARIFICATION: How much slower to the first visible word is acceptable?]
  - [NEEDS CLARIFICATION: Does the rule judge on the confirmation runs alone, or pool them with
    the earlier runs?]
  - [NEEDS CLARIFICATION: Does a probe finding block the switch, such as an abstention
    unrecognized in French or German, or a footnote cited as a source? Or does it become a bug
    filed alongside?]
  - [NEEDS CLARIFICATION: Does anyone besides the owner rely on the defaults or the benchmark
    record?]
  - The assumptions to validate in `concept.md`:
    - the reruns are comparable (digests, Ollama, dataset);
    - gemma4 stays deterministic;
    - the safety margin covers whole summary batches;
    - nothing in `app/` or `tests/` depends on the default being gpt-oss;
    - the benchmarks keep working with gpt-oss as judge only;
    - prompt reading stays negligible in use;
    - the judge's self-preference doesn't reverse the picture.

  Per `AGENTS.md`, the feature touches no prompt, parser, judge or metric, so `/speckit-clarify`,
  `/speckit-checklist` and `/speckit-analyze` aren't required. `/speckit-clarify` would still be
  the natural place to settle the questions above before the plan.
