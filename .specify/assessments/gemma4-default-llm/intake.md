# Idea Intake: gemma4:12b as the default LLM

- **Slug**: gemma4-default-llm
- **Created**: 2026-11-08
- **Source**: pasted text, pointing to `docs/benchmark-results.md` (sections Generation,
  Summarization, Performance, Recommendations); related repo paths: `config/models.yaml`,
  `benchmarks/experiments/generation.yaml`, `benchmarks/experiments/summarization.yaml`
- **Type**: improvement

## Idea (as captured)

> "Make gemma4:12b the default LLM instead of gpt-oss:20b, keeping gpt-oss as the benchmark judge.
> Evidence is in docs/benchmark-results.md (Generation, Summarization, Performance,
> Recommendations)."

The Recommendations section it points to reads, in part:

> **gemma4:12b as the default LLM.** It matched gpt-oss's correctness and relevance, never
> abstained with evidence in front of it, was ahead on faithfulness in both runs, summarized the
> novel far better (0.578 against 0.211), and summarized three times as fast. It writes slightly
> faster, and needs 3.4 GB less VRAM. Against it: gpt-oss reads prompts 2.4 times as fast, so its
> first token comes in 0.31 s against 0.67 s. gpt-oss should stay the judge either way: a new
> judge would have to pass the known-answer checks again.

The same section opens with "The defaults stay as they are": the benchmark write-up suggested the
change and didn't make it.

## Restated

Switch the application's default answering and summarizing model (`llm.model` in
`config/models.yaml`) from gpt-oss:20b to gemma4:12b. The benchmark judge stays gpt-oss:20b.

## Origin & Context

- **Raised by**: the repository owner, through `/speckit-assess-intake` on 2026-11-08.
- **Trigger**: the benchmark runs recorded in `docs/benchmark-results.md` (generation on
  `f90a1b0`, summarization on `826c977`, performance on `4fcd1cb`), whose Recommendations section
  names this change first.
- **Current state, as found** (facts, not assessment):
  - `config/models.yaml` sets `llm.model: gpt-oss:20b`. Both models already have an entry in
    `llm_profiles`: gemma4:12b uses an approximate tokenizer (`tiktoken` `o200k_base`, since
    Gemma's own needs a Hugging Face login) and `reasoning: false`.
  - The generation and summarization experiments name their judge on their own
    (`judge.model: gpt-oss:20b`), apart from `llm.model`.
  - `scripts/pull_models.sh` pulls the models named in `config/models.yaml`, and with `--all`
    every candidate that has a profile.
  - Most of the output-format handling in `app/` (citation normalization, the marker's dash
    variants, the language naming in prompts) came from gpt-oss's failures. gemma4's one recorded
    format failure, a translated no-evidence marker, was handled in `c7dd6ac`.

## First-Glance Unknowns

- [NEEDS CLARIFICATION: Is one generation run enough? `docs/benchmark-results.md` itself
  recommends two runs before trusting a faithfulness difference. gemma4's faithfulness lead was
  +0.090 in the full run and +0.011 in the interrupted one, and the judge is also a candidate that
  may prefer its own writing.]
- [NEEDS CLARIFICATION: Do the runs still hold on current `main`? Generation and summarization
  ran on `f90a1b0` and `826c977`. Commits since then include `c7dd6ac` (the translated marker)
  and the historical spelling work (`608e9a4`, `1228aeb`, shipped off).]
- [NEEDS CLARIFICATION: Does the slower prompt reading matter in use? First token is 0.67 s
  against 0.31 s on four passages, at 2,150 against 5,160 prompt tokens per second. How does
  that grow with a full 8K context, a whole-library question or a summary's map-reduce?]
- [NEEDS CLARIFICATION: Does the approximate tokenizer for gemma4 hold up as the default? Today
  `generation.context.safety_margin` absorbs it, but that was only exercised in benchmarks.]
- [NEEDS CLARIFICATION: Does gemma4's output have failure modes that haven't been seen yet in
  citations, the marker or language, outside the benchmark's 90 questions and six chapters?
  Which real-model checks (`make test-integration`, a benchmark) would cover them?]
- [NEEDS CLARIFICATION: The rubric scored gemma4 slightly lower than gpt-oss on consistency,
  coherence and completeness (0.792 / 0.750 / 0.708 against 0.833 / 0.833 / 0.792). The write-up
  reads most rubric differences as noise. Does that matter for the decision?]
- [NEEDS CLARIFICATION: With gpt-oss no longer the default, how does the judge model get onto a
  machine? Today `pull-models` pulls it because it is `llm.model`.]
- [NEEDS CLARIFICATION: Does `docs/decisions.md` record why gpt-oss:20b was the first default?
  The constitution asks for that reason to be found before a default changes.]
- [NEEDS CLARIFICATION: Should the other gemma4 settings (temperature, `max_tokens`, the
  per-task overrides in `config/generation.yaml`) stay as tuned for gpt-oss, or be revisited with
  the switch?]
