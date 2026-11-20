# Feature Specification: What the retrieval benchmark retrieved

**Feature Branch**: `feat/retrieval-rows`

**Created**: 2026-11-20

**Status**: Draft

**Input**: User description: "Record what the retrieval benchmark retrieved. A retrieval row in
rows.csv and rows.jsonl holds the question's scores and where its evidence is (relevant_chapters,
relevant_chunks), but not what the search returned. So when a question's score moves between two
runs, what outranked its evidence can't be read from the results, only guessed, as happened in
.specify/bugs/publisher-back-matter (fix.md, Follow-ups), while Principle VI reads rows before
concluding. Each retrieval row should also record the ranking its metrics were computed from, as
chunk IDs in rank order, and the passages kept as context after reranking. Comparing two runs
(devtools/compare_runs.py) should show, for each question that moved, what ranked above its
evidence in each run. The scores must not change: the same configuration and dataset give the
same metrics as before, row for row. Results written before this change, without these fields,
must still render in benchmark-report and compare_runs. Generation, summarization and performance
rows are out of scope."

## Context

The retrieval benchmark scores each question by where its evidence ranks. For each variant and
question it writes a row: to `rows.jsonl` as the run goes, and to `rows.csv` and `results.json`
at its end. The row holds the question's book and category, where its evidence is under the
variant's chunking (`relevant_chapters`, `relevant_chunks`), six scores, and the seconds that the
search and the reranking took.

To score a question, the benchmark holds two lists of chunks:

- **The ranking**: every passage the search considered, in rank order. With the default
  configuration, that is dense search's 15 best chunks and BM25's 15 best, merged by reciprocal
  rank fusion and reordered by the reranker: up to 30 chunks. Recall@5, Recall@10 and nDCG@10
  read its first five or ten, and MRR reads it down to the first piece of evidence, however deep.
- **The context**: the passages kept after reranking, the ones an answer would be given, five
  with the default configuration. Context precision and context recall read it. Each of the
  benchmark's questions searches one book, so its context is the ranking's first five, which is
  why context recall equals Recall@5 (`docs/decisions.md`, Evaluation).

It keeps the scores and drops both lists. A row says how well the evidence ranked, and not what
ranked above it.

That stopped a reading. The fix of `.specify/bugs/publisher-back-matter` stopped indexing Project
Gutenberg's header and license, tables of contents and printed indexes. Its retrieval check ran
the default configuration on `main`'s code and on the fix, and paired the two runs with
`devtools/compare_runs.py`: four questions improved, and none got worse. Two of them:

- **`think_python_multi_section_05`**: its MRR went from 0.5 to 1.0, so on `main` one chunk
  ranked above its evidence.
- **`on_liberty_conceptual_01`**: its Recall@5 went from 0.571 to 1.0, so on `main` three of its
  seven quotes ranked between the sixth and the tenth places. Its MRR was 1.0 in both runs: what
  pushed those quotes down ranked below its first piece of evidence, not above it.

Neither run recorded which chunks those were. `docs/benchmark-results.md` names the removed tables
of contents, index and license as the likely candidates, "but that is inferred, not read", and the
fix's report lists the gap among its follow-ups. Principle VI has rows read before anything is
concluded. A generation row holds its answer, and a summarization row its summary, so both can be
read. A retrieval row holds only its scores and where its evidence is, which leaves nothing to
read but the scores.

`devtools/compare_runs.py` pairs two retrieval runs of one variant each, question by question,
which `benchmark-report --baseline` can't do across runs: one run can't hold two versions of the
code. It leaves out a question whose evidence resolved to no chunk in one of the runs, and renders
each metric's difference with its paired bootstrap interval. Then it lists the questions whose
Recall@5, MRR or nDCG@10 moved, with both runs' values and the chunks that each run's evidence
resolved to. It can't show what ranked above the evidence, since no run records it.

A chunk's ID names its book, its chapter's position and its own position in the book
(`book_001_chapter_11_chunk_0021`). It holds within its run only: another chunk size changes every
ID, and the fix renumbered the evidence wherever a dropped chapter came before it. So one ID can
name different text in two runs, and the same text can have two IDs.

What stays as it is: the search, how the evidence resolves to chunks, the scores and their
averages, the dataset, the experiments, the workspaces and the index, and what `benchmark-report`
prints. The rows of the generation, summarization and performance kinds are out of scope.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Retrieval rows that say what the search returned (Priority: P1)

The owner runs a retrieval experiment and opens its rows. Next to its scores, each row holds the
ranking they were computed from, as chunk IDs in rank order, and the context kept after
reranking, as chunk IDs in order. Computing a row's scores again from those two lists and its
question's evidence gives the row's values. A run of the same configuration, on the same dataset,
books and models, gives every question the same scores as the last run before this change.

**Why this priority**: Everything else reads these two lists. Without them a comparison has
nothing to show, and a retrieval row can't be read beyond its scores.

**Independent Test**: Run `markdown_books`, the experiment of the last run before this change
(the publisher-back-matter fix's), on this branch and in a fresh workspace. Check that every row
holds both lists, compute its six scores again from them, and compare each row's scores with that
run's.

**Acceptance Scenarios**:

1. **Given** a retrieval run, **When** a question is scored, **Then** its row holds the ranking,
   every chunk the search considered in rank order, and the context, the chunks kept after
   reranking in their order: in `rows.jsonl` as soon as the row is written, and in `rows.csv` and
   `results.json` at the run's end.
2. **Given** a row, **When** its Recall@5, Recall@10, MRR and nDCG@10 are computed again from its
   ranking, and its context precision and context recall from its context, against its question's
   evidence, **Then** each equals the row's value.
3. **Given** the configuration, dataset, books and models of the last run before this change,
   **When** the same experiment runs on this branch, **Then** each question's six scores,
   `relevant_chapters` and `relevant_chunks` are the same as in that run, row for row, and so are
   the averages.
4. **Given** a variant with reranking off, **When** it runs, **Then** each row's ranking is the
   retriever's order, the one its scores were computed from, and its context is the passages that
   the search returns.
5. **Given** a run's `rows.csv`, **When** the owner opens it, **Then** each list is one cell, its
   chunk IDs in order, written the way `relevant_chunks` is.

---

### User Story 2 - A comparison that shows what ranked above the evidence (Priority: P2)

The owner pairs two retrieval runs with `devtools/compare_runs.py`. Under "Questions that moved",
each question shows, for each run, the chunks that ranked above its evidence, each with its rank,
and the ranks its evidence took. Had the publisher-back-matter fix's runs recorded their
rankings, the owner would have read which chunks pushed `on_liberty_conceptual_01`'s quotes out of
the first five on `main`, instead of inferring them.

**Why this priority**: It is the reading the fix's check couldn't do. It needs User Story 1's
lists, and adds only how a comparison shows them.

**Independent Test**: Run the comparison's unit tests, on rows whose rankings are known. On the
stack, run the default configuration and the same with reranking off, pair the two runs, and
check each moved question's chunks and ranks against what the rows record.

**Acceptance Scenarios**:

1. **Given** two runs that recorded their rankings, **When** they are compared, **Then** each
   question that moved shows, for each run, the chunks ranked above its evidence that hold none of
   it, in rank order, each with its rank, and the ranks of its evidence.
2. **Given** a question whose evidence took a run's first places, with no other chunk between its
   pieces, **When** it moved, **Then** that run shows nothing above its evidence, and the ranks
   its evidence took.
3. **Given** a question with several quotes, whose first piece of evidence ranked first and
   another piece lower, among the first ten, **When** it moved, **Then** the chunks between them
   that hold no evidence are shown, as what ranked above the lower piece. This is what
   `on_liberty_conceptual_01` would have shown on `main`.
4. **Given** a question none of whose evidence is among a run's first ten, **When** it moved,
   **Then** that run shows every chunk above its first piece of evidence, however deep it ranked.
5. **Given** a question none of whose evidence is in a run's ranking, **When** it moved, **Then**
   that run says that its evidence wasn't retrieved, and shows its first ten chunks, the ones that
   took the evidence's places.
6. **Given** two runs on different code or chunking, **When** they are compared, **Then** each
   run's chunks are shown under its own label, as that run numbered them, and none is matched with
   the other run's.

---

### User Story 3 - Older results, rendered as before (Priority: P3)

The owner keeps the results of earlier runs on the host, and none of them holds the two lists.
`benchmark-report` renders them as it does today. `devtools/compare_runs.py` compares them, with
each other or with a new run, and says where a run didn't record its ranking.

**Why this priority**: Every result recorded in `docs/benchmark-results.md` was written before
this change, and the next comparison may pair one of them with a new run. It comes last because it
asks for nothing new, only that nothing breaks.

**Independent Test**: Render the publisher-back-matter fix's two runs with `benchmark-report`, and
compare them with `devtools/compare_runs.py`, on `main` and on this branch, and compare the
outputs. Then pair the fix's run with a new one.

**Acceptance Scenarios**:

1. **Given** a result written before this change, **When** `benchmark-report` renders it, with or
   without `--baseline`, **Then** its output is the same as `main`'s for the same file, byte for
   byte.
2. **Given** two results written before this change, **When** they are compared, **Then** the
   pairing, the intervals and the questions that moved are the same as on `main`, and each
   question that moved says that neither run recorded its ranking.
3. **Given** a result written before this change and one written after, **When** they are
   compared, **Then** each question that moved shows what ranked above its evidence in the new
   run, and says that the old run didn't record it.
4. **Given** a new run, **When** `benchmark-report` renders it, **Then** it shows the same tables
   as for an old run with the same scores: the two lists aren't metrics, and appear nowhere in its
   output.

---

### Edge Cases

- **A question whose evidence resolved to no chunk** under a run's chunking still records its
  ranking and its context. Its scores are 0, as today, and the comparison leaves it out of the
  pairing, as today.
- **A chunk that holds two quotes, or a quote held by two overlapping chunks**: every chunk in the
  run's `relevant_chunks` is evidence, and none of them is shown as ranking above the evidence.
- **A ranking shorter than ten, or even than five**, as a chapter-specific question's can be, its
  search being limited to one chapter: it is recorded as it is, and the comparison reads it as far
  as it goes.
- **A variant with reranking off** records the retriever's order as its ranking, and the passages
  that the search returns, the ranking's first five, as its context.
- **A run of several variants**: each row records its own variant's lists. `benchmark-report
  --baseline` pairs the variants as today, and `devtools/compare_runs.py` still takes one variant
  per run.
- **A sampled run** (`--limit`) records the same lists, and says `complete: false`, as today.
- **A run that dies before its end** keeps both lists in the rows that `rows.jsonl` already holds.
- **One chunk ID in both runs of a comparison** can name different text, when the runs chunked or
  ingested differently. The comparison shows each run's IDs under that run's label, and draws no
  link between them.
- **A result of another kind**, generation, summarization or performance, is still refused by
  `devtools/compare_runs.py`, and its rows don't change.

## Requirements *(mandatory)*

### Functional Requirements

#### What a retrieval row records

- **FR-001**: Each retrieval row MUST record its ranking: the chunk IDs of every passage that the
  search considered, in the order that its scores were computed from, the reranker's when
  reranking is on and the retriever's when it is off. It MUST hold the whole ranking, not its
  first ten: MRR reads it down to the first piece of evidence, however deep.
- **FR-002**: Each retrieval row MUST record its context: the chunk IDs of the passages kept after
  reranking, in their order, the ones that its context precision and context recall were computed
  from. With reranking off, they are the passages that the search returns.
- **FR-003**: A row's six scores MUST be computed from the two lists that it records, and from
  nothing else, so that computing them again from the row and its question's evidence gives the
  row's values.
- **FR-004**: Both lists MUST be in each retrieval row of `rows.jsonl`, written with the row, and
  of `rows.csv` and `results.json`. In `rows.csv`, each list MUST be one cell, its chunk IDs in
  order, written as `relevant_chunks` is.

#### What doesn't change

- **FR-005**: For the same configuration, dataset, books and models, each row's six scores,
  `relevant_chapters` and `relevant_chunks` MUST be the same as before this change, and so MUST
  the averages in `summary.csv` and `results.json`. The search, the resolution of the evidence to
  chunks and the scores' definitions MUST NOT change. The seconds that the search and the
  reranking take aren't scores, and vary from run to run as today.
- **FR-006**: The two lists MUST NOT be treated as metrics: nothing averages or counts them, and
  `benchmark-report` doesn't show them. Its output for a run MUST depend only on what it shows
  today.
- **FR-007**: The rows of the generation, summarization and performance kinds MUST NOT change, and
  the generation kind's retrieval, run once before its models answer, MUST record nothing new.
- **FR-008**: The index, the catalog, the configuration, the dataset and the experiments MUST NOT
  change, and no reindex is needed. A workspace built before this change MUST stay valid: the
  ingestion code doesn't change, so `benchmarks/workspace` needn't be deleted.

#### Comparing two runs

- **FR-009**: For each question that moved, which is as today a question whose Recall@5, MRR or
  nDCG@10 differ between the runs, `devtools/compare_runs.py` MUST show, for each run, what ranked
  above its evidence: the chunks of that run's ranking that hold none of the evidence and rank
  above its lowest-ranked chunk of evidence among the first ten, or, when none of its evidence is
  among the first ten, above its highest-ranked one. Each chunk MUST be shown with its rank, in
  rank order, and so MUST the ranks that its evidence took down to that point. A question's
  evidence, in a run, is the chunks of that run's `relevant_chunks`.
- **FR-010**: When a run's ranking holds none of the question's evidence, the comparison MUST say
  so, and show that run's first ten chunks, with their ranks, as what took the evidence's places.
- **FR-011**: The comparison MUST show each run's chunk IDs as that run recorded them, under that
  run's label, and MUST NOT match one run's IDs with the other's.
- **FR-012**: What the comparison shows today MUST stay: what each run was, the questions left
  out, the pairing with each metric's interval, and, for each question that moved, its values in
  both runs and the chunks that its evidence resolved to in each.

#### Results written before this change

- **FR-013**: `benchmark-report` MUST render a result written before this change exactly as
  `main` does, with or without `--baseline`.
- **FR-014**: `devtools/compare_runs.py` MUST compare results written before this change, with
  each other and with new ones. For each question that moved, a run without its ranking MUST be
  shown as not having recorded it, and everything else as today.
- **FR-015**: Results written before this change MUST NOT be rewritten, completed or migrated.
  What they didn't record stays unknown.

#### Records

- **FR-016**: `README.md`, in Benchmarks, MUST say that each retrieval row also lists its ranking
  and its context, by chunk ID, and that `devtools/compare_runs.py` shows, for each question that
  moved, what ranked above its evidence in each run.
- **FR-017**: `docs/decisions.md`, in Evaluation, MUST record:
  - why retrieval rows record their ranking and their context: the reading that the
    publisher-back-matter fix couldn't do, which its report left as a follow-up, and Principle
    VI's reading of rows;
  - why they record IDs and not texts, and that an ID holds within its run only;
  - why the comparison reads down to the lowest-ranked evidence among the first ten, or to the
    highest-ranked when none is there: the scores that decide whether a question moved read no
    deeper, and `on_liberty_conceptual_01` moved below its first piece of evidence.
- **FR-018**: `docs/benchmark-results.md` MUST record the run that checks FR-005 (SC-001): that it
  gave the same rows as the fix's run, every score of every question, and where its results are.
  Its section on the publisher-back-matter fix keeps its inference: those runs were written before
  this change.
- **FR-019**: The history MUST NOT be edited: `.specify/bugs/publisher-back-matter/` and the
  delivered specs, `specs/001` to `specs/006` (Principle VIII).

#### Constraints from the constitution

- **FR-020**: The benchmark MUST write nothing new outside its run's results folder, and reach
  nothing outside `benchmarks/workspace` and the `bench_*` collections (Principle II).
- **FR-021**: The change MUST touch no metric, judge, prompt, parser of model output, or input of
  the index fingerprint (Principles III, V and VI).

### Key Entities

- **Retrieval row**: one per variant and question, in `rows.jsonl`, `rows.csv` and
  `results.json`. It holds the question, its book and category, where its evidence is
  (`relevant_chapters`, `relevant_chunks`), six scores and two timings, and with this change its
  ranking and its context.
- **Ranking**: the chunk IDs of every passage the search considered, in rank order, after
  reranking when it is on: up to 30 with the default configuration. Recall@5, Recall@10, MRR and
  nDCG@10 are computed from it.
- **Context**: the chunk IDs of the passages kept after reranking, in their order: five with the
  default configuration, and in the benchmark the ranking's first five. Context precision and
  context recall are computed from it.
- **Chunk ID**: names a chunk's book, its chapter's position and its own position in the book. It
  holds within the run that recorded it.
- **Comparison**: two retrieval runs of one variant each, paired by question. For each question
  that moved, it shows what ranked above the evidence in each run.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: On this branch, in a fresh workspace, `markdown_books`, the default configuration,
  run with the dataset, books, configuration and models of the publisher-back-matter fix's run
  (`benchmarks/results/markdown_books_20261120T022603129972Z`, whose `results.json` records their
  checksums and digests), gives all 75 questions the same six scores, `relevant_chapters` and
  `relevant_chunks` as that run, and a `summary.csv` identical to that run's, byte for byte.
- **SC-002**: In each of SC-001's 75 rows, the six scores computed again from the recorded ranking
  and context, against the question's evidence, equal the row's values, and the context is the
  ranking's first five, or all of it when it holds fewer.
- **SC-003**: `benchmark-report` prints the same tables for SC-001's run as for the fix's run, the
  two outputs differing only in the line that says when, and with which Ollama, each ran. For each
  of the fix's two runs, it prints the same output on this branch as on `main`, byte for byte,
  with and without `--baseline default`.
- **SC-004**: `devtools/compare_runs.py`, on the fix's two runs, gives the same pairing, intervals
  and questions that moved as on `main`, and each of the four questions that moved says that
  neither run recorded its ranking. On the fix's run and SC-001's, it pairs 75 questions, leaves
  none out, and finds none that moved. The fix's two result folders are unchanged afterwards, file
  for file (FR-015).
- **SC-005**: On two runs made on this branch that rank differently, the default configuration
  and the same with reranking off, `devtools/compare_runs.py` shows what ranked above the evidence
  of each question that moved, in each run, and every chunk, rank and depth it shows agrees with
  the rankings in the rows, by FR-009 and FR-010.
- **SC-006**: `make lint-check` is clean and `make test` passes, with unit tests for: both lists in
  each of the three files; the scores computed again from them; a variant with reranking off; each
  case of FR-009 and FR-010 (evidence first, evidence below other chunks, several quotes, none
  among the first ten, none retrieved); and a run without the lists, alone and paired with a new
  one.
- **SC-007**: Since the branch left `main` (`git diff main...HEAD`), the change touches only the
  files that `plan.md`'s Project Structure lists and the records (`README.md`, `docs/`, this
  spec's folder), and none of those files is in `app/retrieval`, `app/ingestion`,
  `app/generation`, `app/storage` or `config/`.

## Assumptions

- **The lists are already there.** To score a question, the benchmark builds its ranking and its
  context, then keeps only the scores. Recording them adds no search, no model call and no time to
  a run, and about a kilobyte to each row with the default configuration.
- **IDs, not texts**, as the owner asked. An ID tells the book, the chapter's position and the
  chunk's place in the book, which is often enough to tell a chapter from front or back matter. A
  chunk's text can be found again from the commit and the books that the result records, which
  give the same chunks again.
- **Not recorded**: the order before reranking, and each stage's scores (dense, BM25, fusion and
  reranker). A variant with reranking off measures the retriever's own order.
- **The same inputs have given the same rows before**: in the fix's check, `main`'s run gave the
  same rows as `specs/005`'s Markdown run, every score of every question. So a row that differs in
  SC-001 is a change to look into, not noise: a run on `main`'s code, with the same models, tells
  whether this change moved it.
- **Nothing to measure** (Principle VI): the change claims no gain in quality or speed and changes
  no default, so SC-001 checks that nothing moved instead of measuring against a baseline variant.
  It touches no metric, judge, prompt or parser of model output, so it needs no run of the LLMs
  (Principle V), and the extra steps that `AGENTS.md` asks of such changes, clarify, checklist and
  analyze, don't apply.
- **Older runs stay unread.** The fix's runs hold no rankings, so what outranked the evidence on
  `main` stays an inference. Reading it would mean running `main`'s old code with this change,
  which this feature doesn't do.
- **The release**: a feature, so the pull request is titled `feat:`, and its merge makes a minor
  release, v0.7.0 unless another release comes first.
