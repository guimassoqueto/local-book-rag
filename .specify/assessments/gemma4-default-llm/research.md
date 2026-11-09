# Idea Research: gemma4:12b as the default LLM

- **Slug**: gemma4-default-llm
- **Created**: 2026-11-09
- **Evidence confidence (overall)**: medium

The evidence is this project's own: the six benchmark runs that compared the models (result
files in `benchmarks/results/`, kept out of the repository), re-read and re-analysed here, and two
small read-only probes run for this research against the live stack. Nothing was fetched from the
web. The constitution has this project's benchmarks decide a default (principle VI), and external
model reports wouldn't be measured on these books, prompts or hardware.

Probes, both run through the app's own services in the `app` container, with `llm.model`
overridden in memory (no file in `config/` or `data/` changed):

- **Probe A**: `QuestionAnsweringService.stream` with no filters (the whole library), 3 runs per
  model, on two questions. One is the benchmark's trap `quincas_borba_unanswerable_04` ("Que nome
  recebeu a filha de Maria Benedita e Carlos Maria?"). The other is
  `think_python_multi_section_04`, on `*` and `**`.
- **Probe B**: the LLM provider's `count_tokens` against Ollama's `prompt_eval_count`, net of a
  one-character baseline, on 8 chunks spread through each book's `data/processed/*/r2/chunks.jsonl`.
  One reply token was requested per call.

## Users & Demand

- The only user is the repository owner, who runs it as a personal research platform on one
  machine. The demand is the owner's own: the first suggestion in the Recommendations section of
  `docs/benchmark-results.md`, which also says "The defaults stay as they are" — [source:
  `docs/benchmark-results.md` § Recommendations; `intake.md`] (confidence: high)
- No record of real use (questions asked, summaries made) was found to tell which task matters
  more, answers or summaries, or how often whole-library questions are asked. `data/` holds
  `metadata`, `original_books`, `processed` and `summaries` only — [source: `ls data/`]
  (confidence: medium; see Gaps)
- The idea is "stated" in the sense the template uses: it comes from benchmark scores and reading
  their output, not from a complaint about a failure in use. One observed failure in use exists:
  asked of the whole library, gpt-oss named Maria Benedicta's daughter "D. Fernanda" with a
  citation of a chapter that doesn't say so — [source: `docs/benchmark-results.md` § Known
  limitations; commit `ffb8bbe`] (confidence: high)

## Prior Art

- **How gpt-oss became the default.** It has been `llm.model` since milestone 1 (`3b93cce`,
  2026-11-06), before any model was benchmarked. The commit gives no reason, and
  `docs/decisions.md` records none. The v0.1 spec, `.TASK/task.md`, isn't in this checkout, so
  whether it named gpt-oss couldn't be checked — [source: `git log -S'gpt-oss:20b' --
  config/models.yaml`; `git show 3b93cce`; `grep` of `docs/decisions.md`] (confidence: high that
  no reason is recorded)
- **Most model-specific handling came from gpt-oss's failures.** Normalizing `【3】` citations,
  matching the marker with any dash, naming the answer's language, naming the summary's language,
  halving merges that don't condense, the judge's JSON repair. gemma4 needed one fix: it
  translated the no-evidence marker as `[NO-EVIDÊNCIA]`, recognized since `c7dd6ac` —
  [source: `docs/decisions.md` § Generation, § Evaluation; `docs/benchmark-results.md` § Changes
  these benchmarks led to] (confidence: high)
- **A precedent for "within noise".** The historical spelling feature was benchmarked, gained
  within noise, and shipped switched off (`af10c0f`). The project has declined a change whose
  measured gain didn't clear the bootstrap before — [source: `docs/benchmark-results.md` §
  Historical spelling; `git log`] (confidence: high)
- **The runs still describe current `main`.** Since the generation run's commit (`f90a1b0`), the
  question-answering prompt is unchanged. `prompts.py` changed only in its summary prompts
  (`9f90a13`, before the summarization run), and `question_answering.py` only for the translated
  marker (`c7dd6ac`), which would raise gemma4's abstention quality, not lower it. The rest of
  `app/` since then is the historical spelling in BM25, shipped off — [source: `git diff --stat
  f90a1b0 HEAD -- app config`; `git log f90a1b0..HEAD -- app/generation/prompts.py
  app/generation/question_answering.py`] (confidence: high)
- **External prior art**: not gathered. Model cards and leaderboards live on hosts outside the
  fetch allowlist (`ollama.com`, `huggingface.co`), and wouldn't measure this workload — [source:
  ASSUMPTION about relevance] (confidence: low)

## Market & Context

- **One model does every task.** `llm.model` serves answers and summaries. The tasks in
  `config/generation.yaml` override only temperature and token limits — [source:
  `config/models.yaml`; `config/generation.yaml`] (confidence: high)
- **The judge doesn't move with the default.** The generation and summarization experiments name
  `judge.model: gpt-oss:20b` on their own — [source: `benchmarks/experiments/generation.yaml`,
  `summarization.yaml`] (confidence: high)
- **The judge has to be pulled.** `pull-models` pulls `llm.model` and `embedding.model`, and with
  `--all` every model that has a profile. gpt-oss keeps its profile, so `--all` still brings it,
  and plain `pull-models` wouldn't — [source: `app/main.py:133-140`] (confidence: high)
- **The cost of doing nothing**, by what is recorded and re-measured here:
  - gpt-oss abstains with evidence in front of it: 3 wrong abstentions in the full run and 5 in
    the interrupted one, all on *Quincas Borba*. gemma4 had 0 in both — [source:
    `benchmarks/results/generation_20261108T175100527075Z`,
    `generation_20261107T133931058188Z`, re-analysed] (confidence: high)
  - gpt-oss summarizes the novel badly: 0.211 coverage against gemma4's 0.578, and a summary that
    gives Palha what Sophia says — [source: `docs/benchmark-results.md` § Summarization]
    (confidence: medium: coverage judge, six chapters)
  - Summaries take three times as long with gpt-oss, and its step count is unstable: 104 s and
    9.8 steps a chapter on average, up to 272 s and 24 steps for On Liberty V in the latest run
    and 13 steps for Inheritance in the one before. gemma4 took 1 to 8 steps — [source:
    `summarization_20261108T213459590645Z`, `summarization_20261108T170744515174Z` rows]
    (confidence: high)
  - The whole-library trap still catches gpt-oss: in Probe A it answered "D. Fernanda" with a
    citation of CAPITULO CXX in 1 of 3 runs, and abstained in the other two. gemma4 abstained in
    3 of 3 — [source: Probe A] (confidence: medium, n = 3)
  - In Probe A, gpt-oss gave one of its three answers to the `*`/`**` question with no citation
    at all. gemma4 cited in all three — [source: Probe A] (confidence: low, n = 3)

## Data & Constraints

- **Generation scores, paired against gpt-oss, full run** (90 questions, gpt-oss judging):
  faithfulness +0.090 (+0.012 to +0.174), correctness +0.005 (−0.041 to +0.050), relevance
  −0.008 (−0.043 to +0.023), citation accuracy +0.042 (+0.000 to +0.097), abstention quality
  +0.022 (−0.022 to +0.067) — [source: `book-rag benchmark-report --baseline gpt_oss_20b
  generation_20261108T175100527075Z`] (confidence: high that these are the numbers; see
  Evidence Against for what they mean)
- **Determinism**: gemma4 gave the same 90 answers byte for byte in both generation runs. gpt-oss
  repeated 3 of its 90. Score changes between runs for gemma4 are therefore the judge's alone,
  and gpt-oss's mix its own variation with the judge's — [source: both generation runs'
  `rows.jsonl`, compared] (confidence: high)
- **Latency in use**: Probe A timed the app's own path. Retrieval took 12 to 20 s per
  whole-library question, before the LLM started. The LLM then read a 1,600 to 2,100-token prompt.
  Uncached, at about 2,100 tokens, gemma4 read it in 0.97 s and gpt-oss in 0.41 s, so the gap was
  0.56 s against 12 s or more of retrieval. In the benchmark's per-book answers the median LLM
  time was 2.42 s for gemma4 and 2.54 s for gpt-oss, gemma4 writing slightly fewer words (93.5
  against 98.5). gpt-oss's `low` reasoning was short in Probe A, 51 to 129 characters, so it
  delays its first visible token little — [source: Probe A; generation run `rows.jsonl`
  `total_seconds`] (confidence: medium)
- **Memory**: 9,158 MB of VRAM over idle against 12,546 MB at 8K, but 4,364 MB of RAM over idle
  against 793 MB. The machine has 16 GB of VRAM and 60 GB of RAM. The current device choices,
  with the reranker and query embeddings on the CPU, were made so the LLM could keep the GPU —
  [source: `docs/benchmark-results.md` § Performance; `config/models.yaml` comments] (confidence:
  high)
- **The tokenizer approximation stays inside the margin.** Probe B compared gemma4's
  `o200k_base` estimate with Ollama's count on 24 real chunks. Medians by book were 1.011 (On
  Liberty), 0.949 (Think Python) and 0.961 (Quincas Borba), from 0.941 to 1.043 overall, so the
  estimate undercounts by up to about 6%. `safety_margin` is 0.1 of the window. gpt-oss's
  `o200k_harmony` matched exactly, 1.000 on every chunk — [source: Probe B;
  `config/generation.yaml:49-51`] (confidence: medium: 24 chunks, three books)
- **Answer prompts are far from the window.** At the default 5 reranked passages, a prompt was
  1,600 to 2,100 tokens of 8,192, so passage fitting rarely binds for answers. Where the
  approximation matters more is summary batches, sized to the window — [source: Probe A
  `prompt_tokens`; `app/generation/question_answering.py:207-222`;
  `app/generation/summarization.py:262`] (confidence: medium)
- **An integration test assumes an exact tokenizer.**
  `tests/integration/test_generation.py::test_the_token_estimate_matches_the_runtime_count`
  checks the configured LLM's estimate within 2 tokens. On its text of about 350 tokens, a 5%
  error is about 17 tokens, so with gemma4 configured it would likely fail as written — [source: the
  test; inferred from Probe B, not run] (confidence: medium)
- **Constitution checks this idea meets as stated**: a model switch named only in configuration,
  with a profile already present (I), and a default change compared with a baseline in a
  benchmark run (VI). No prompt or parser change is proposed (V) — [source:
  `.specify/memory/constitution.md`] (confidence: high that the rules say this; whether the
  evidence suffices is the decide stage's call)

## Evidence Against the Idea

- **The faithfulness lead rests on the novel, where the judge is weakest, and it flipped sign.**
  Paired by book, gemma4's faithfulness lead in the full run was +0.221 (+0.032 to +0.419) on
  *Quincas Borba*, +0.008 on *Think Python* and +0.058 on *On Liberty*. In the interrupted run
  the novel's was −0.035 (−0.136 to +0.075), and the overall lead +0.024 (−0.041 to +0.088).
  gemma4's novel answers were the same in both runs. gpt-oss's novel faithfulness went from
  0.882 to 0.662. The doc lists "the judge resolves names badly in the novel" as a known
  limitation. The one generation difference that excluded zero is therefore mostly gpt-oss's
  variation plus the judge's, on the book it scores least reliably — [source: both generation
  runs, paired bootstrap re-computed here, 4,000 resamples; `docs/benchmark-results.md` § Known
  limitations] (confidence: high for the numbers, medium for the reading)
- **Multi-section correctness is lower, in both runs.** gemma4 −0.100 (−0.214 to +0.015) and
  −0.095 (−0.195 to +0.028) against gpt-oss, over 13 paired questions. The intervals touch zero,
  but the direction repeated. Relevance was also slightly lower in both runs (0.758 vs 0.783,
  0.771 vs 0.783). Read closely, the widest gaps aren't clearly worse answers: on
  `on_liberty_multi_section_01` gemma4 said the passages don't hold the answer (0.11) while
  gpt-oss answered beyond them (0.38). That still leaves "the judge prefers gpt-oss's fuller
  answers" and "gemma4 is weaker across sections" both open — [source: both generation runs,
  re-computed; answers read in `rows.jsonl`] (confidence: medium)
- **The summary rubric puts gemma4 below gpt-oss on factual consistency and coherence, in both
  comparable runs.** Consistency: −0.125 (−0.208 to −0.042) in the run of 2026-11-08T17:07Z,
  which excludes zero, and −0.042 (−0.250 to +0.125) in the latest. Coherence: −0.125 (−0.250 to
  +0.042) and −0.083 (−0.167 to +0.000). gemma4 got 0.5 for consistency on *Think Python*'s
  "Inheritance" in both runs, and on "Fruitful functions" in the latest. The rubric rates
  consistency against the chapter's passages, not the key points (`summary_metrics.py:35`), so
  the key-point rewrite between runs doesn't explain it. `docs/benchmark-results.md` reports the
  latest run only, and doesn't mention the earlier consistency result — [source: `book-rag
  benchmark-report --baseline gpt_oss_20b` on `summarization_20261108T170744515174Z` and
  `summarization_20261108T213459590645Z`; their rows] (confidence: medium: six chapters, steps of
  0.04, and the doc itself says the rubric "separates little")
- **gemma4 copies footnote markers as citations.** Its 3 invented citations in the full run were
  all in one answer, `[1, 7]`, `[1, 8]`, `[1, 9]` on `on_liberty_factual_04`. The passage holds
  *On Liberty*'s own footnote `[7]`. gpt-oss had 1, also on *On Liberty*. Both runs counted 3
  against 1. The interface flags invented numbers (`app/interface/formatting.py:96`), so it shows
  rather than misleads. It is still a citation failure on any book with bracketed footnotes —
  [source: both generation runs; the passage in
  `benchmarks/workspace/71026d902d/processed/book_003/r1/chunks.jsonl`]
  (confidence: high)
- **gemma4 "answered" one more unanswerable question.** 2 of 15 against 1 of 15. One of the two
  was the translated marker, which `c7dd6ac` now recognizes. The other said honestly that the
  text names no one, without the marker, which gpt-oss also did on the same question — [source:
  full generation run rows] (confidence: high)
- **Slower prompt reading, more RAM.** 2.4× slower prompt reading, 0.67 s against 0.31 s to the
  first token on four passages, and 4.3 GB of RAM over idle against 0.8 GB. Probe A suggests the
  first matters little next to retrieval, but long summary batches read more — [source:
  `docs/benchmark-results.md` § Performance; Probe A] (confidence: medium)
- **gemma4 has been seen on little.** 90 questions in English and Portuguese, six `standard`
  summaries, and Probe A. The `brief`, `comprehensive` and `analytical` summary types, the other
  interface languages and long whole-library sessions are unobserved. Every format fix so far was
  found by running a model at length — [source: `docs/benchmark-results.md` § Generation, §
  Summarization; `config/generation.yaml` summary types] (confidence: high that it is untested;
  ASSUMPTION that it hides failures)
- **The judge is also a candidate.** gpt-oss scores its own answers. That would favor gpt-oss,
  which makes gemma4's parity, if anything, conservative. It also means no score here is
  independent of one of the two models compared — [source: `docs/benchmark-results.md` § How far
  to trust these numbers] (confidence: medium)

## Gaps & Open Questions

- [NEEDS CLARIFICATION: Why was gpt-oss:20b the first default? Did `.TASK/task.md` name it, and
  for a reason that still holds? Nothing in the repository says.]
- [NEEDS CLARIFICATION: Does the faithfulness lead survive a second full generation run on
  current `main` (with `c7dd6ac`)? `docs/benchmark-results.md` recommends two runs before
  trusting a faithfulness difference. Re-analysed here, the two runs disagree on the novel.]
- [NEEDS CLARIFICATION: Is gemma4 weaker on multi-section questions, or does the judge prefer
  gpt-oss's fuller answers? Reading all 13 pairs, not just the three widest, would tell.]
- [NEEDS CLARIFICATION: What did the judge object to in gemma4's *Think Python* summaries (0.5
  consistency in 3 of 4 chapter-runs)? The rubric stores no reasons. Reading the summaries
  against their chapters would settle whether gemma4 goes beyond the passages.]
- [NEEDS CLARIFICATION: How does gemma4 do on the `brief`, `comprehensive` and `analytical`
  summary types, and on whole-library questions beyond Probe A's two?]
- [NEEDS CLARIFICATION: Do the summary batches sized to the window stay inside it with gemma4's
  ~6% undercount? Probe B says the margin covers it on 24 chunks. No run compared the estimate
  with Ollama's count on a full batch.]
- [NEEDS CLARIFICATION: Which matters more in this owner's use, answers or summaries? The
  summary evidence favors gemma4 more clearly than the answer evidence does.]
- [NEEDS CLARIFICATION: Does `make test-integration` pass with gemma4 configured? The tokenizer
  test likely won't as written.]
- [NEEDS CLARIFICATION: Do 3.4 GB of freed VRAM change anything else, such as the reranker or
  query embedding staying on the CPU? Out of this idea's scope unless the owner wants it in.]

## Sources

No URLs were fetched. All sources are local:

- `docs/benchmark-results.md` (§ How far to trust these numbers, Generation, Summarization,
  Performance, Recommendations, Known limitations, Changes these benchmarks led to)
- `docs/decisions.md` (§ Configuration, Generation, Evaluation)
- `.specify/memory/constitution.md` (principles I, V, VI, VII)
- `config/models.yaml`, `config/generation.yaml`, `config/retrieval.yaml`
- `benchmarks/experiments/generation.yaml`, `summarization.yaml`, `performance.yaml`
- `benchmarks/results/generation_20261107T133931058188Z/rows.jsonl` (interrupted run)
- `benchmarks/results/generation_20261108T175100527075Z/` (full run, Ollama 0.40.15; digests
  gemma4:12b `6114515d63c1…`, gpt-oss:20b `f38aa0c53da5…`)
- `benchmarks/results/summarization_20261107T125425283621Z/` (gpt-oss finished 4 of 6
  chapters, before the merge fix, so not comparable),
  `summarization_20261108T170744515174Z/`, `summarization_20261108T213459590645Z/`
- `book-rag benchmark-report --baseline gpt_oss_20b` on the runs above
- `app/main.py:133-150`, `app/generation/question_answering.py`,
  `app/generation/summarization.py`, `app/evaluation/benchmark.py`,
  `app/evaluation/summary_metrics.py`, `app/interface/formatting.py`,
  `tests/integration/test_generation.py`
- Git history: `3b93cce`, `f90a1b0`, `9f90a13`, `826c977`, `c7dd6ac`, `ffb8bbe`, `af10c0f`
- Probe A and Probe B, run on 2026-11-08 against the live stack (Ollama in Compose, library of
  three indexed books). Scripts and raw output were kept in this session's scratchpad, not in the
  repository.
