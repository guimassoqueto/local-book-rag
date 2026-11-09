# Feature Specification: Choosing the default LLM by measurement

**Feature Branch**: `feat/gemma4-default-llm`

**Created**: 2026-11-09

**Status**: Draft

**Input**: User description: "per the handoff in .specify/assessments/gemma4-default-llm/decision.md"

The handoff is the `go` verdict of the assessment in `.specify/assessments/gemma4-default-llm/`,
with its Option C: confirm the evidence on current `main`, then switch the default LLM to
gemma4:12b or keep gpt-oss:20b, by a rule written into this spec before any run.

## Context

The default LLM answers every question and writes every summary. It has been gpt-oss:20b since
milestone 1 (`3b93cce`, 2026-11-06), before any model was measured. The repository doesn't say
why, but the first version's spec, `.TASK/task.md`, does, in its § 3.1:

- It lists four "initial evaluation candidates": gpt-oss:20b, gemma4:12b, qwen3.5:9b and qwen3:14b.
- It names gpt-oss:20b the "Initial recommended model", for "Reasoning and summarization".
- It names gemma4:12b the "Alternative", for "General-purpose generation".

It gives no other reason. Its § 15.3 asks for the four candidates to be compared on identical
retrieved contexts, with "automated evaluation as an initial signal and manual review for final
conclusions". So the first default was a recommendation made before the evaluation the same spec
asked for. Summarization, one of its two stated purposes, is where it fell furthest behind
gemma4:12b: on the novel's coverage, and on time.

The benchmarks have measured it since, against gemma4:12b among others, with gpt-oss:20b judging.
These are the figures the decision starts from, all from the assessment's `research.md`:

| Measure | gpt-oss:20b | gemma4:12b | Where |
| --- | --- | --- | --- |
| Wrong abstentions, of 75 answerable questions | 3, and 5 | 0, and 0 | full and interrupted generation runs, all on *Quincas Borba* |
| Faithfulness | 0.813 | 0.894 (+0.090, +0.012 to +0.174) | full run; +0.024 (−0.041 to +0.088) in the interrupted one |
| Correctness, relevance | 0.706, 0.783 | 0.702, 0.771 | full run, within noise |
| Multi-section correctness, 13 questions | 0.585 | −0.100 (−0.214 to +0.015) | full run; −0.095 in the interrupted one |
| Citation accuracy, abstention quality | 0.944, 0.956 | 0.987, 0.978 | full run, within noise |
| Invented citations, of 90 answers | 1 | 3, in one answer copying the book's footnote `[7]` | both runs |
| Summary argument coverage | 0.543; 0.211 on the novel | 0.665; 0.578 on the novel | latest summarization run |
| Summary consistency | 0.833 | 0.792; −0.125 (−0.208 to −0.042) in the run before | both summarization runs |
| Summary coherence | 0.833 | 0.750 | latest summarization run, within noise |
| Seconds and steps per chapter summary | 104 s, 9.8 steps, up to 272 s and 24 | 35 s, 3.5 steps | latest summarization run |
| Whole-library trap answered, with a false citation | 1 of 3 | 0 of 3 | Probe A, n = 3 |
| First token, four passages | 0.31 s | 0.67 s | performance run; about 0.56 s behind 12 to 20 s of retrieval in use |

The wins that would motivate a switch repeated in both runs, or are measured rather than judged:
the abstentions, the summary time and steps, the novel's coverage, the trap. The answer-score
differences are doubtful. The one that excluded zero, faithfulness, reverses on the novel between
runs, and is mostly gpt-oss's own variation plus the judge's. Multi-section correctness and summary
consistency lean against gemma4 in both runs. gemma4 has also been seen on little: 90 questions in
English and Portuguese, and six `standard` summaries.

The earlier runs were made with Ollama 0.40.15 and the digests gemma4:12b `6114515d63c1…`,
gpt-oss:20b `f38aa0c53da5…` and qwen3-embedding:0.6b `ac6da0dfba84…`. The generation run used
dataset `f69da2332857…`, and the latest summarization run `767e4cceb315…`, which is today's. They
differ only in the chapter key points, rewritten in `826c977`: the generation experiment doesn't
read them, and the questions and books haven't changed since `bce8124`.

This feature confirms the evidence once more, against a rule fixed below, and ships whichever
outcome the rule gives. The repository has shipped a "keep" before: historical spelling was
benchmarked, gained within noise, and shipped switched off (`af10c0f`).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - A verdict the numbers can't be fitted to (Priority: P1)

The owner, as a researcher, runs the confirmation: one generation run and one summarization run
comparing gpt-oss:20b and gemma4:12b, a reading of the outputs the scores can't settle, and a small
probe of what the benchmark doesn't cover. They apply the rule written in this spec before any of
it ran, and get one verdict: switch to gemma4:12b, or keep gpt-oss:20b.

**Why this priority**: it is the decision itself, and both outcomes depend on it. A default chosen
after seeing the numbers, by a rule shaped to them, would be the unmeasured choice this feature
replaces.

**Independent Test**: check that the commit adding the rule to this spec is older than every
confirmation run's start, then apply the rule to the recorded results, and check that each
condition has a pass or fail backed by a number or a reading, and that the verdict follows from
them alone.

**Acceptance Scenarios**:

1. **Given** this spec with its rule committed, **When** a confirmation run is about to start,
   **Then** its dataset checksum, Ollama version and model digests are checked against the ones FR-004
   names, and the run doesn't start until they match or the spec is amended.
2. **Given** the confirmation's results, the reading and the probe, **When** the rule is applied,
   **Then** every condition of FR-002 is recorded as passed or failed, with what decided it.
3. **Given** any condition failed, **When** the verdict is drawn, **Then** it is "keep gpt-oss:20b",
   whatever the other conditions show.
4. **Given** every condition passed, **When** the verdict is drawn, **Then** it is "switch to
   gemma4:12b".

---

### User Story 2 - The default's reason, on record (Priority: P2)

A researcher, the owner or whoever reads the repository next, opens `docs/decisions.md` and finds
what the default LLM is, the run it rests on, the rule that chose it, and how each condition came
out. `docs/benchmark-results.md` holds the confirmation runs next to the earlier ones.

**Why this priority**: it is delivered whichever way the rule goes, and it is the only thing the
"keep" outcome delivers. The next comparison of models then starts from a justified baseline
instead of an accident of milestone 1.

**Independent Test**: read `docs/decisions.md` and `docs/benchmark-results.md` after the feature,
and check that they name the default, the confirmation runs, each condition's outcome, and the
reason, without the reader having to open the result files.

**Acceptance Scenarios**:

1. **Given** the verdict is "keep", **When** the feature is done, **Then** only records have
   changed: no configuration, code or test, and the benchmark write-up's Recommendations point to
   the recorded reason instead of an open suggestion.
2. **Given** the verdict is "switch", **When** the feature is done, **Then** the write-up's
   "(default)" labels are on gemma4:12b, and its Recommendations no longer suggest the switch as
   pending.
3. **Given** either verdict, **When** the reading or the probe found a failure that only a prompt
   or parser change would fix, **Then** it is recorded as a follow-up for its own bug or feature,
   and not fixed here.

---

### User Story 3 - Answers and summaries from gemma4:12b (Priority: P3)

Only if the rule says switch. A reader asks questions and summarizes chapters as before, and
gemma4:12b writes the replies. The benchmarks keep gpt-oss:20b as their judge, and a machine set up
by the README gets that judge deliberately, not because it happens to be the default.

**Why this priority**: it is the reader's gain, fewer wrong abstentions and summaries about three
times as fast, but it happens only on one of the two outcomes.

**Independent Test**: on a machine set up by the README, ask a question and summarize a chapter,
and check that gemma4:12b wrote them. Run `make test-integration`, and start a generation benchmark
with `--limit 1`.

**Acceptance Scenarios**:

1. **Given** the switch, **When** a reader asks a question the passages answer, **Then** gemma4:12b
   answers it with numbered citations that resolve to their passages, as before.
2. **Given** the switch, **When** a reader asks a question the passages don't answer, **Then** the
   application shows an abstention, as before.
3. **Given** the switch and a machine set up for benchmarks as the README says, **When** a
   generation or summarization benchmark starts, **Then** gpt-oss:20b is there to judge.
4. **Given** the switch and a machine without the judge model, **When** a benchmark that needs it
   starts, **Then** it stops before any work, naming the missing model.
5. **Given** the switch, **When** `make test-integration` runs, **Then** it passes, with the
   token-count check accepting gemma4's approximate tokenizer within what the safety margin absorbs.

### Edge Cases

- **A model was pulled again, with new weights under the same tag.** The digest check before the
  run catches it. The registry serves only the newest weights for a tag, so the old digest may be
  out of reach. Then the spec is amended with the digests actually used before the run starts,
  never after, and the record says that the confirmation ran on different weights from the
  earlier runs.
- **A run is interrupted, sampled, or fails part way.** It decides nothing, and is replaced by one
  full run. That is the same confirmation run, not a second one.
- **The judge can't score some answers or summaries.** They are left out of the metric and counted,
  as everywhere in the benchmarks. The rule applies to what was scored, and the record gives the
  counts.
- **gpt-oss also has no wrong abstentions this time.** The win didn't repeat, so condition (b)
  fails and the verdict is "keep", however the other conditions came out. The rule says which wins
  motivated the switch, and it holds them to repeating.
- **gemma4's answers differ from the earlier runs.** They were the same byte for byte in both
  earlier runs. If they differ now, the record says so: the rerun then resamples gemma4 as well as
  the judge.
- **A score and the reading disagree**, such as a rubric criterion worse with an interval that
  excludes zero, while the reading finds gemma4's summaries fine. The score decides, and the
  verdict is "keep" (FR-002 (a)). The reading is still recorded, and the record says the two
  disagreed.
- **Answers favor gpt-oss while summaries favor gemma4.** The rule doesn't weigh one against the
  other: a gated answer metric worse fails it. The record notes the split, since a model per task
  would be the change to consider then, as its own feature.
- **The switch reveals a test or document that assumes gpt-oss is the default.** It is updated, if
  the assumption is only about which model is the default. If it shows a gemma4 failure that only
  a prompt or parser change would fix, condition (e) of FR-002 fails, the verdict is "keep", and
  the failure is filed as its own bug or feature.

## Clarifications

### Session 2026-11-09

- Q: Why was gpt-oss:20b the first default? → A: The first version's spec, `.TASK/task.md` § 3.1,
  named it the "Initial recommended model", for "Reasoning and summarization", with gemma4:12b as
  the "Alternative". It gave no other reason, and asked for the four candidates to be compared
  (§ 15.3). A switch is recorded as a departure from it (FR-014).
- Q: If a gated metric comes out worse for gemma4 with an interval that excludes zero, does it block
  the switch outright, or may the reading overrule it? → A: It blocks outright. The rule's lean
  towards keeping is accepted (Assumptions).
- Q: Which probe findings block the switch? → A: Only failures where gemma4:12b does worse than
  gpt-oss:20b. A failure both share is filed as its own bug or feature, and doesn't block (FR-008).

## Requirements *(mandatory)*

### Functional Requirements

#### The rule

- **FR-001**: The decision rule in FR-002 MUST be committed to this spec before the first
  confirmation run starts. A change to it after a run has started needs a new confirmation run,
  under a new spec.
- **FR-002**: The default MUST switch to gemma4:12b only if every condition below holds in the
  confirmation. Otherwise it MUST stay gpt-oss:20b, and the record MUST say which conditions failed.
  - **(a) Nothing gated is worse.** No gated metric is lower for gemma4:12b than for gpt-oss:20b
    with a paired bootstrap interval (4,000 resamples, 95%) that excludes zero. Such a result
    blocks the switch outright: the reading can't overrule it, even where it suggests the judge
    caused the difference. The gated metrics are:
    - from the generation run, over all 90 questions: faithfulness, answer correctness, answer
      relevance, citation accuracy, language consistency and abstention quality;
    - from the same run, answer correctness on the 13 multi-section questions;
    - from the summarization run, over its six chapters: argument coverage, concept preservation,
      factual consistency, coherence, completeness and citation traceability.

    These are the metrics the first version's spec asks the candidates to be compared on (§ 15.3),
    plus the one category where gemma4 leaned lower in both runs. Differences by book, and in the
    other categories, are reported and read, not gated.
  - **(b) The wins that motivated the switch repeat.**
    - **Wrong abstentions**: gemma4:12b abstains on fewer of the 75 answerable questions than
      gpt-oss:20b.
    - **Summary time and steps**: gemma4:12b takes fewer seconds and fewer steps per chapter than
      gpt-oss:20b on average, each with a paired interval that excludes zero, computed like the
      report's. Re-computed for this spec on the latest run, they were about −69 s (−143 to −5) and
      −6.3 steps (−12.7 to −0.3).
    - **The novel's coverage**: gemma4:12b's argument coverage, averaged over *Quincas Borba*'s two
      chapters, is higher than gpt-oss:20b's. Two chapters are too few for an interval, so only
      the direction counts, and the record doesn't call it a measured improvement on its own.
  - **(c) The reading finds no systematic weakness**, as FR-006 defines it.
  - **(d) The probe finds nothing that blocks**, as FR-008 defines it.
  - **(e) The real-model checks pass with gemma4:12b configured**, as `make test-integration`
    runs them. A failure that comes only from assuming gpt-oss:20b is the default is fixed in the
    check (FR-011, FR-012). Any other failure fails this condition.
- **FR-003**: The rule MUST judge on the confirmation runs alone. The earlier runs are context:
  "repeat" in (b) means the win, seen in them, is seen again in the confirmation.

#### The confirmation

- **FR-004**: The confirmation MUST be one full generation run and one full summarization run, with
  the code that answers, summarizes and judges as it is on `main` at `a647e1a`. Whatever this
  feature adds before the runs only measures. Each run MUST have:
  - only two variants, gpt-oss:20b and gemma4:12b, each with its profile and settings as they are;
  - the judge as configured today: gpt-oss:20b, with its embedding model, token limit and
    reasoning (`low` for generation, `medium` for summarization);
  - dataset `767e4cceb315…`;
  - Ollama 0.40.15;
  - gemma4:12b `6114515d63c1…`, gpt-oss:20b `f38aa0c53da5…` and qwen3-embedding:0.6b
    `ac6da0dfba84…`.

  These MUST be checked before each run starts, and recorded with its results.
- **FR-005**: There MUST be one confirmation of each kind. A run is repeated only when it didn't
  complete, and never to settle the judge's noise.

#### The reading

- **FR-006**: The confirmation's outputs MUST be read against their passages:
  - **the 13 multi-section questions**: both models' answers to each, against the passages they
    were given and the expected answer;
  - **the summaries**: every gemma4:12b summary the confirmation scores 0.5 or lower on factual
    consistency, and *Think Python*'s "Inheritance" and "Fruitful functions" as summarized in the
    earlier runs, where gemma4 scored 0.5 in 3 of 4 chapter-runs, each next to gpt-oss:20b's summary
    of the same chapter.

  Each answer and summary read MUST be recorded with the errors it has, by kind:
  - a claim the passages don't support;
  - something said, done or argued, attributed to the wrong person;
  - part of the question left unanswered, though the passages answer it;
  - an abstention with the evidence in the passages;
  - a citation of a passage that doesn't say what is claimed.

  A **systematic weakness** is one kind of error that gemma4:12b makes and gpt-oss:20b doesn't on
  the same item, in 3 or more of the 13 multi-section answers, or in 2 or more of the summaries
  read, the probe's included.
- **FR-007**: The reading MUST be recorded case by case, in this feature's directory, and
  summarized in `docs/benchmark-results.md`.

#### The probe

- **FR-008**: The probe MUST look at what the benchmark doesn't cover, with both models, through
  the application's own services. It only reads: it MUST NOT save a summary, change the library or
  its configuration files, or change the dataset. The model it uses is chosen for the probe alone.
  It looks at:
  - **The whole-library trap**: `quincas_borba_unanswerable_04`, asked with no book filter, 3 times
    per model.
  - **The no-evidence marker in the other answer languages**: the 15 unanswerable questions, each
    asked of its book with the answer language set to Spanish, French, German and Italian, which
    makes 60 replies per model. A reply that says the passages don't hold the answer, but that
    the application shows as an answer, is an unrecognized abstention.
  - **A long summary**: one `analytical` summary of *Think Python*'s "Inheritance" per model, read
    as FR-006 says, and counted with the summaries there.
  - **Whole prompts against the tokenizer**: for every summary prompt in the confirmation's
    summarization run and the probe's `analytical` summaries, the model's own count of the prompt
    compared with the estimate it was fitted by.
  - **The first visible word in use**: the two questions of the assessment's Probe A, asked of the
    whole library, 3 times each per model. It times the wait from the prompt being sent to the
    first word of the answer the reader sees, after any reasoning.

  A probe finding blocks the switch only where gemma4:12b does worse than gpt-oss:20b, the
  default it would replace. These block it:
  - gemma4:12b answers the trap in more runs than gpt-oss:20b;
  - gemma4:12b has more unrecognized abstentions than gpt-oss:20b;
  - gemma4:12b's `analytical` summary doesn't finish, or isn't in the book's language, while
    gpt-oss:20b's does and is;
  - the estimate undercounts one of gemma4:12b's whole prompts by more than the safety margin, so
    Ollama could have cut it silently;
  - gemma4:12b's median wait for the first visible word is more than 1 s longer than
    gpt-oss:20b's.

  A failure both models share doesn't block: it is the status quo already. It is recorded, and
  filed alongside as its own bug or feature, like anything else the probe finds that a prompt or
  parser change would fix.

#### If the rule says switch

- **FR-009**: The configured default LLM MUST become gemma4:12b, with its profile and settings as
  they are. The benchmark experiments' judge MUST stay gpt-oss:20b, with its settings unchanged.
- **FR-010**: Getting the judge model onto a machine MUST be a deliberate, documented step, so that
  it doesn't depend on the judge being the default: the README's benchmark setup brings every model
  the experiments judge with. A benchmark started without its judge MUST stop before any work,
  naming the missing model.
- **FR-011**: The real-model check of token counts MUST hold an exact tokenizer to its current
  tolerance, and an approximate one to what the safety margin absorbs. It MUST tell them apart by
  what the model's profile says, never by its name.
- **FR-012**: The application and its tests MUST NOT depend on the default being gpt-oss:20b, apart
  from tests that use the name as fixture data. A search MUST confirm it before the switch.
- **FR-013**: The README MUST say which model is the default, and why, and what holds for its token
  counts, wherever it now describes gpt-oss:20b as the model in use.

#### Either way

- **FR-014**: `docs/decisions.md` MUST record:
  - the default and the confirmation runs it rests on;
  - the rule, and how each of its conditions came out;
  - why gpt-oss:20b was the first default: the first version's spec recommended it, before the
    evaluation that spec asked for, as the Context says.

  If the verdict is "switch", it MUST also be recorded as a departure from the first version's
  spec, which recommended gpt-oss:20b and named gemma4:12b as the alternative.
- **FR-015**: `docs/benchmark-results.md` MUST record:
  - the confirmation runs, with their commit, date, versions, numbers and paired differences;
  - the reading's summary, and the probe's results.

  Its "(default)" labels and Recommendations MUST follow the verdict.
- **FR-016**: If the verdict is "keep", the feature MUST NOT change any configuration, code or test.
- **FR-017**: Whatever the verdict, the feature MUST NOT change the embedding model, chunking or the
  index, and MUST NOT need a reindex.

### Key Entities

- **Decision rule**: the conditions of FR-002, fixed before any run. Each condition comes out
  passed or failed, and all of them passing is the only way to switch.
- **Confirmation run**: one benchmark run, generation or summarization, comparing the two models
  with gpt-oss:20b judging. It records the versions FR-004 names.
- **Reading record**: for each answer or summary read, its item, its model, and the errors found in
  it by kind.
- **Probe result**: each probe's replies, with what the application showed and the counts and
  times the blocking findings are judged by.
- **Verdict**: "switch to gemma4:12b" or "keep gpt-oss:20b", with the conditions that decided it.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: The rule was committed before the first confirmation run started. Every condition of
  FR-002 is recorded as passed or failed, with the number or reading behind it, and the verdict
  follows from them alone.
- **SC-002**: Both confirmation runs are complete, and record the dataset, Ollama version and
  digests that FR-004 names, or the amendment that replaced them before the run.
- **SC-003**: The confirmation took one run of each kind, plus at most one replacement for a run
  that didn't complete.
- **SC-004**: All 13 multi-section answer pairs, every summary FR-006 names, and every probe in
  FR-008 are recorded, each with its result.
- **SC-005**: A reader of `docs/decisions.md` alone can say what the default LLM is, which runs
  chose it, and why, without opening a result file.
- **SC-006**: Every failure the reading or the probe found that needs a prompt or parser change is
  listed as a follow-up, and none is fixed in this feature.
- **SC-007**: If the verdict is "switch", a reader on a machine set up by the README gets gemma4:12b
  answers and summaries, and both of these pass with no step the README doesn't list:
  - `make test-integration`;
  - a generation and a summarization benchmark at `--limit 1`, judged by gpt-oss:20b.
- **SC-008**: If the verdict is "switch", the confirmation shows, for the reader:
  - fewer wrong abstentions on the 75 answerable questions;
  - summaries taking fewer seconds and fewer steps per chapter, with intervals that exclude zero;
  - no gated metric worse with an interval that excludes zero.

## Assumptions

- **The owner is the only one who relies on the default or the benchmark record**, as the research
  found. Readers of the published repository learn the default from the README.
- **The rule weighs neither answers nor summaries above the other.** It is a conjunction, so a mixed
  result keeps gpt-oss, and the question of which task matters more doesn't arise.
- **The rule leans towards keeping**, which is accepted. With 13 gated metrics, a model no worse than
  gpt-oss could still show one of them worse by chance, roughly once in four confirmations. Keeping
  is the outcome that risks nothing new, and its reason gets recorded.
- **1 s is the acceptable extra wait for the first visible word.** The measured gap was about
  0.56 s, behind 12 to 20 s of retrieval over the whole library.
- **gemma4:12b stays deterministic** at the benchmark's settings, so its side of the generation
  rerun resamples only the judge. If it doesn't, the record says so.
- **The judge's preference for its own writing can't be checked** while gpt-oss:20b judges. The
  confirmation only shows whether the differences repeat.
- **The safety margin, 10% of the window, covers gemma4's tokenizer.** Its worst undercount on 24
  single chunks was about 6%. The probe checks whole prompts.
- **The confirmation is mostly machine time.** The last full generation run took 3 h 43 min with
  four models, and this one has two. Writing the six summaries took about 4 min for gemma4 and
  10 min for gpt-oss, before judging. The reading and the probe take hours.
- **Out of scope**, each its own change if it is ever wanted:
  - changing the judge, its prompts or its reasoning;
  - changing prompts or output parsing, including the marker in other languages and footnote
    markers taken as citations;
  - retrieval speed, where the reranker and query embeddings run, and uses for freed VRAM;
  - the judge's noise, and growing the dataset, which includes more chapters, whole-library
    questions, the other summary types and the other languages; the probe only looks;
  - models beyond gpt-oss:20b and gemma4:12b, and re-opening the comparison with the qwen models;
  - a model per task;
  - tuning gemma4's temperature, token limits or reasoning;
  - embedding, chunking and the index.
