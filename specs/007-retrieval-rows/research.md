# Research: What the retrieval benchmark retrieved

The decisions behind `plan.md`, each with what was chosen, why, and what else was considered. The
code they rest on was read on `feat/retrieval-rows` at `6ac56ef` on 2026-11-20, whose `app/` and
`devtools/` are `main`'s (`aa54d1b`). The host's results were read the same day. Line numbers are
`main`'s, for orientation; names are what the tasks follow.

## R1. Where the lists come from

**Decision.** The row records the two lists that `_run_retrieval` already builds
(`app/evaluation/benchmark.py`, lines 344–345), and that its scores are computed from:

```python
ranking = [passage.chunk.chunk_id for passage in result.candidates]
context = [passage.chunk.chunk_id for passage in result.passages]
```

The same two lists go to the metrics and into the row, so nothing is computed twice.
`RetrievalPipeline.run` (`app/retrieval/pipeline.py`, lines 43–59) sets them:
- **`candidates`**: every passage the retriever found for each book, reordered by the reranker
  when it is on. With the default configuration, that is dense search's 15 best and BM25's 15
  best, merged by reciprocal rank fusion: up to 30, fewer when the two lists overlap.
- **`passages`**: the first `top_k` of them, taken in turns across books. A benchmark question
  searches one book, so the context is the ranking's first `retrieval.reranker.top_k` (5), which
  `config/retrieval.yaml` says is "also how many passages a search returns when reranking is off".

So with reranking on, the ranking is the reranker's order of every candidate. With reranking off,
it is the retriever's order: fusion's for a hybrid search, dense or BM25's alone otherwise. In both
cases the context is its first five.

`_run_generation` keeps its own search (lines 370–378), which records nothing new (FR-007).

**Rationale.** FR-001 to FR-003 ask for the lists the scores were computed from, and only those.
Recording the very variables that the metrics read makes FR-003 hold by construction: no second
computation can drift from the first. No search, model call or time is added (spec, Assumptions).

**Alternatives considered.**
- *The passages' texts*: the owner asked for IDs. A run's commit and books give the texts again,
  and texts would make each row some fifty times larger (spec, Assumptions).
- *Each stage's order and scores* (dense, BM25, fusion, reranker): not asked for, and a variant
  with reranking off already measures the retriever's own order. The pipeline would have to return
  them, in `app/retrieval`, which SC-007 keeps out of the diff.
- *The ranking's first ten only*: MRR reads it down to the first piece of evidence, however deep
  (FR-001).

## R2. Names, types and place in the row

**Decision.** Two keys, `ranking` and `context`, after `rerank_seconds`, last in the row. In
`rows.jsonl` and `results.json` each is a JSON array of chunk IDs, in order. A row written before
this change has neither key (`contracts/retrieval-rows.md`).

**Rationale.**
- **The names** are those of the metric functions' parameters (`recall_at_k(ranking, …)`,
  `context_precision(context, …)`) and of `_run_retrieval`'s variables, so a column leads to the
  function that read it.
- **Last in the row**, the columns of `rows.csv` keep their places, and the two long cells come
  after everything a reader scans.
- **Arrays** keep the order explicit, and a reader of the JSON needs no splitting.

**Alternatives considered.**
- *`ranked_chunks` and `context_chunks`, next to `relevant_chunks`*: the values already say they
  are chunk IDs. In the middle of `rows.csv`, two cells of up to a kilobyte would push the scores
  out of view.
- *Strings joined with "; " in the JSON too, as `relevant_chunks` is*: every reader would have to
  split them. `relevant_chunks` stays a string, since FR-005 keeps it as it is.

## R3. One cell each in `rows.csv`

**Decision.** `_write_csv` (lines 657–664) writes a list as one cell, its items joined with "; ",
the way `_relevant_places` joins `relevant_chunks`. Every other value is written as today.

**Rationale.** FR-004. The rule sits in the writer that every kind shares, but only retrieval rows
hold lists. A generation row holds numbers, booleans and its answer, a summarization row numbers
and its summary, and a performance row numbers and strings (`_judge_answer`, `JudgeScores`,
`SummaryScores` and `PerformanceResult`, read on 2026-11-20). So no other kind's `rows.csv`
changes (FR-007), and neither does `summary.csv`, which holds averages and counts (SC-001). No
chunk ID holds "; ", so a cell splits back into its list.

**Alternatives considered.**
- *Join the two keys by name in `_write`*: the shared writer would name a retrieval field, for the
  same output.
- *csv's default*: Python's representation, `['book_001_…', …]`, which isn't how `relevant_chunks`
  is written.

## R4. What can't change, and why

**Decision.** Nothing else in the runner, the metrics or the report changes. Each guarantee rests
on code this feature doesn't touch:

| Guarantee | Why it holds |
| --------- | ------------ |
| The six scores (FR-005) | The same functions compute them from the same lists and the same evidence. Only the row's dictionary gains two keys. |
| `relevant_chapters`, `relevant_chunks` | `_relevant_places` doesn't change. |
| The averages: `summary.csv`, and `summary`, `by_category` and `by_book` in `results.json` | `summarize` (lines 624–654) averages the metrics it is given, `_RETRIEVAL_METRICS`, and counts failures. It reads no other field. |
| `benchmark-report` (FR-006, FR-013) | `render` reads the summaries and, from the rows, only `variant`, the metric and `_item(row)`, which is the question (`app/evaluation/report.py`). Neither it nor `app/main.py` changes. |
| The rows of the other kinds (FR-007) | `_run_generation`, `_run_summarization` and `_run_performance` don't change, and their rows hold no list (R3). |
| Results written before (FR-015) | Only the run that made a results folder writes into it, and `devtools/compare_runs.py` writes nothing. |

The timings vary from run to run, as today.

The files grow. On the fix's run, `rows.jsonl` holds 75 rows in 35 KB. A chunk ID has up to 31
characters, so the two lists add about 1.2 KB to a row with the default configuration, and about
0.3 MB to the three files of a 75-question run. `results.json` grows most, as its `indent=1` puts
each ID on a line of its own.

**Rationale.** FR-005, FR-006 and FR-013. Each guarantee is also checked on the stack, not only
reasoned (SC-001 to SC-004).

**Alternatives considered.** *Compact lists in `results.json`*: it would change how
`results.json` is written for every kind, to save about 0.1 MB a run.

## R5. What ranked above the evidence

**Decision.** For each question that moved, and for each run, `devtools/compare_runs.py` reads the
run's row:
1. **The evidence** is the chunk IDs of the run's `relevant_chunks`, split on "; ".
2. **Its ranks** are the positions, from 1, of the ranking's chunks that are evidence.
3. **The depth** is the largest of those ranks that is 10 or less: the lowest-ranked evidence
   among the first ten. When none is 10 or less, it is the smallest of them: the highest-ranked
   evidence, however deep.
4. **Shown**: the evidence's ranks down to the depth, and every chunk above the depth that isn't
   evidence, with its rank, in rank order (FR-009).
5. **No evidence in the ranking**: the run says that its evidence wasn't retrieved, and shows the
   ranking's first ten, with their ranks, or all of it when it is shorter (FR-010).
6. **No ranking in the row**, which is a row written before this change: the run says that it
   didn't record it (FR-014).

On the fix's two questions, had their runs recorded rankings:
- **`think_python_multi_section_05`**, MRR 0.5 on `main`: its first evidence was second, so the
  chunk at rank 1 is shown, and any chunk between it and its other evidence within ten.
- **`on_liberty_conceptual_01`**, MRR 1.0 in both runs, Recall@5 0.571 on `main`: three of its
  seven quotes ranked between the sixth and the tenth places. The depth is the lowest of them, so
  the chunks shown are those that pushed the three quotes out of the first five.

**Rationale.**
- **The depth** follows the scores that decide whether a question moved, Recall@5, MRR and
  nDCG@10 (`_MOVING`). Two of them read no deeper than ten, and MRR reads down to the first piece
  of evidence. So the reading stops at the last evidence within ten, or at the first evidence when
  none is within ten.
- **Above the first piece of evidence only** would show nothing for `on_liberty_conceptual_01`
  (spec, Context).
- **A run's evidence is its own `relevant_chunks`**, since an ID holds within its run only
  (FR-011).

**Alternatives considered.**
- *Above the first piece of evidence only*: it misses every move below it, as above.
- *The whole ranking*: up to 30 IDs per run and question, most of them below anything that a
  moving score reads.
- *The chunks that entered or left the first ten between the runs*: that matches IDs across runs,
  which FR-011 forbids. The fix renumbered every chunk after a dropped chapter.
- *Ranks per quote*: a row holds only the union of its quotes' chunks, `relevant_chunks`. The
  depth already reaches every quote that moved within the first ten.

## R6. The comparison's new table

**Decision.** After "Questions that moved", when at least one question moved,
`render_comparison` adds a section:

```text
## What ranked above the evidence

| question | run | evidence at | ranked above it |
| --- | --- | --- | --- |
```

Each question that moved gets two rows, in the order of "Questions that moved": the first run's,
then the second's, each under its label. `contracts/compare-runs.md` fixes the cells. When no
question moved, the section isn't printed. Everything before it is today's output, unchanged.

**Rationale.** FR-009 to FR-012.
- **One row per run** keeps each run's IDs under its own label (FR-011).
- **A table like the one above it** reads in a terminal, and pastes into
  `docs/benchmark-results.md` as the other tables do.
- **Appended after today's output**, it leaves today's lines as they are. So the comparison of two
  old runs differs from `main`'s output only by the new section (SC-004).

**Alternatives considered.**
- *Two more columns in "Questions that moved"*: a row would carry up to 60 IDs, and today's table
  would change shape.
- *A section per question, with a list per run*: longer, and harder to scan across questions.
- *The two runs side by side, rank by rank*: it suggests that the chunks the two runs put at one
  rank are related, which FR-011 rules out.

## R7. Results written before this change

**Decision.**
- **`devtools/compare_runs.py`** reads a row's ranking with `row.get("ranking")`. Without one, both
  cells of that run say `not recorded`. `merge` already copies whole rows, so a new run's lists
  reach the new table, and nothing else in the pairing changes.
- **`benchmark-report`** reads nothing new.
- **No result is rewritten, completed or migrated.** The devtool reads `results.json` and prints.

**Rationale.** FR-013 to FR-015, and User Story 3.

**Alternatives considered.**
- *Refuse a result without the lists*: every result that `docs/benchmark-results.md` records is
  one, and the next comparison may pair one of them with a new run.
- *One warning for the whole run*: a cell for each run and question says exactly where a ranking
  is missing, and is the same in a mixed comparison.

## R8. Checking the scores against the fix's run

**Decision.** The baseline of SC-001 is the publisher-back-matter fix's run,
`benchmarks/results/markdown_books_20261120T022603129972Z`:
- **The experiment**: `markdown_books`, one variant, `default`, the default configuration.
- **The code**: recorded as `fix/publisher-back-matter 84f8bf1-dirty`, the fix uncommitted on
  `main`. It was committed 20 minutes later as PR #21's only commit, and merged as `9e0ff70`.
  `main` has changed only `docs/benchmark-results.md` since (`aa54d1b`).
- **Its inputs**, as `results.json` records them:
  - the dataset `cd57a42a6369…`;
  - the books' checksums (`quincas_borba` `ae3e75a1…`, `think_python` `380a8ec6…`, `on_liberty`
    `5588535e…`);
  - the configuration `40986b09d6d0b813…`, the same as on `main`'s run;
  - qwen3-embedding:0.6b at `ac6da0dfba84`;
  - Qwen/Qwen3-Reranker-0.6B on the CPU.

The run on this branch takes the same dataset and books, the host's copies, which the run checks by
checksum before anything. `config/` doesn't change, so `configuration_sha256` has to be the same.
The embedding model is the one in Ollama, whose digest the result records.

The comparison:
- **The rows**, by question, on eight fields: the six scores, `relevant_chapters` and
  `relevant_chunks`. Each has to be exactly equal, since the same computation gives the same
  floats.
- **`summary.csv`**, byte for byte, with `cmp`.
- **SC-002**, in the app container after the run. A throwaway script opens the run's workspace as
  the runner does, resolves each question's evidence, quote by quote, with `relevant_chunks`, and
  computes the six scores again from the row's two lists. It also checks that the context is the
  ranking's first five.

**The reranker** isn't an Ollama model. It comes from Hugging Face, unpinned, and the rebuilt
container downloads it again. A new revision would move rows. If a row differs, a run of `main`'s
code on the same models tells whether this change moved it (spec, Assumptions).

**Rationale.** The same inputs have given the same rows before: `main`'s run gave the same rows as
`specs/005`'s Markdown run. So an exact comparison is the right one, and any difference is a
change to look into.

**Alternatives considered.**
- *Compare the averages only*: two moves that cancel out would pass.
- *Compare with a tolerance*: the scores have been equal across runs, so a tolerance could only
  hide a change.
- *Run `main`'s code again as the baseline*: the fix's run is `main`'s code, as above, so that run
  would be repeated.

## R9. A second run, with reranking off

**Decision.** One experiment with one variant, the default configuration with reranking off. It
is kept with this spec, as `specs/005` kept `markdown_books.yaml`:
`specs/007-retrieval-rows/benchmarks/experiments/no_reranking.yaml`.

```yaml
name: no_reranking
kind: retrieval
description: >-
  The default configuration with reranking off: the retriever's own order, so that two runs that
  rank differently can be compared question by question (specs/007-retrieval-rows, SC-005).

variants:
  - name: hybrid_rrf
    overrides:
      retrieval: {reranker: {enabled: false}}
```

`hybrid_rrf` is the name that `retrieval.yaml` gives the same configuration. It indexes the way the
default does, so it reuses the workspace that the run of SC-001 built (`index_key`).

**Rationale.** SC-005 needs two runs on this branch that rank differently, with one variant each,
since the comparison takes one variant per run. No experiment gives that: `retrieval.yaml`'s
`hybrid_rrf` comes with eight other variants. FR-008 keeps the existing experiments as they are.
This one is added, and changes none of them.

**Alternatives considered.**
- *Run `retrieval.yaml`*: nine variants, two of them with another chunk size, which index again.
  And the comparison refuses a run of several variants.
- *Split a run of several variants into two results*: a new tool, for one check.
- *Turn reranking off in the container's `config/`*: a configuration change, which FR-008 rules
  out, and which `configuration_sha256` would record as another configuration.
- *Keep the file on the host only*: `benchmarks/` is ignored by git, and the constitution keeps an
  experiment that a feature adds in that feature's spec folder.

## R10. Running on the branch's code

**Decision.** `make up` rebuilds the app image from the branch and recreates the app container.
That deletes:
- the owner's library, *História econômica global*;
- the library's logs;
- the reranker's weights, which the container downloaded;
- the container's copy of `benchmarks/`.

ChromaDB and Ollama keep their data, models included. The new catalog numbers its indexes from 1
again, so `reset-everything --confirm "DELETE EVERYTHING"` follows, as the publisher-back-matter
fix did, and as `specs/006`'s quickstart § 4 did. It deletes every `book_chunks_v*` collection.
After the checks, the owner adds their book back.

`main`'s outputs come first. The running container is v0.6.1's image, whose `app/` is `main`'s, so
`benchmark-report` renders the fix's two runs on `main`'s code before the rebuild.
`devtools/compare_runs.py` runs on the host, on `main`'s code, before the branch changes it, or
from a worktree of `main`.

The runs pass `--commit "$(git describe --always --dirty)"`. Made after the change is committed,
they name a commit that holds it.

**Rationale.** Principle II: a document that recreates a container says what that deletes. A
result's `--commit` names the code that its image was built from.

**Alternatives considered.** *Copy the changed `benchmark.py` into the running container*: it would
keep the library. But the container would no longer be the image it was built from, and the
result would name a commit that its image doesn't hold.

## R11. Tests

**Decision.** SC-006's unit tests, in three files.

`tests/unit/test_benchmark.py`, on the `lab` fixture (one book, embedded ChromaDB, fake embedder
and reranker):
- **The three files**: a retrieval run's row holds `ranking` and `context` in `rows.jsonl`,
  `results.json` and `rows.csv`. They are the same in all three, and each `rows.csv` cell is the
  list joined with "; " (FR-001, FR-002, FR-004).
- **The scores again**: the six scores, computed again from the row's two lists and the question's
  evidence (`relevant_chunks` over the workspace's chunks), equal the row's (FR-003).
- **What the search returned**: with the search replaced by one that returns a known result, the
  ranking is its candidates and the context its passages, in their order (FR-001, FR-002).
- **Reranking off and on**: with the fake reranker and without it, the context is the ranking's
  first `top_k`.
- **A run that fails** keeps both lists in the rows that `rows.jsonl` already holds (edge case).
- **What stays**: `summary.csv` holds no list (FR-006), and a generation run's rows hold neither
  key (FR-007).

`tests/unit/test_compare_runs.py`, on made-up results, as today:
- **Each case of FR-009 and FR-010**:
  - evidence first, with no other chunk between its pieces: nothing above;
  - evidence below other chunks;
  - several pieces, the first at rank 1 and another lower within the first ten: the chunks
    between them;
  - none within the first ten: every chunk above the first piece;
  - none retrieved: the first ten;
  - a ranking shorter than ten.
- **Each run's IDs under its own label**, never matched with the other's (FR-011).
- **Two runs without the lists**: today's output, followed by `not recorded` for each run of each
  question that moved (FR-014).
- **One run without the lists, paired with one that has them** (FR-014).
- **No question moved**: no new section (SC-004).
- **The existing tests stay**, unchanged (FR-012).

`tests/unit/test_report.py`:
- **A result whose rows hold the lists renders exactly as the same result without them**, with and
  without a baseline (FR-006, FR-013).

**Rationale.** SC-006, and each requirement that a unit test can show without the stack. The rest
is the stack's (`quickstart.md`, § 4 to § 8).

## R12. Records

**Decision.**
- **`README.md`, Benchmarks.** The paragraph on evidence quotes ends "Each result row lists the
  chapters and chunks the evidence resolved to". It adds that a retrieval row also lists its
  ranking and its context, by chunk ID, and that an ID holds within its run. Where it names
  `devtools/compare_runs.py`, it adds what the devtool shows for a question that moved, and it
  names `no_reranking` beside `markdown_books` (FR-016).
- **`docs/decisions.md`, Evaluation.** A new entry, "Retrieval rows record what was retrieved",
  after "Generation rows record how much of the evidence reached the model", with FR-017's three
  reasons:
  - the reading that the publisher-back-matter fix couldn't do, and Principle VI;
  - IDs and not texts, and an ID holds within its run;
  - the depth, and `on_liberty_conceptual_01`.

  It adds to, and doesn't contradict, "Relevance is stored as evidence quotes, not chunk IDs": a
  ranking's IDs are read only within their run, against that run's evidence.
- **`docs/benchmark-results.md`.** A new section after "Matter that isn't the book's text" records
  the run of SC-001: the same rows as the fix's run, every score of every question, and where its
  results are. It also records the run of SC-005, and what its comparison showed. "Reproducing"
  names `no_reranking`. The fix's section keeps its inference (FR-018).
- **`devtools/compare_runs.py`'s docstring** says what the new table shows. It also says "in one
  of the runs" where it says "in either run": the script leaves a question out when one run
  resolved its evidence to no chunk.

**Rationale.** FR-016 to FR-019, and Principle VIII. `.specify/bugs/publisher-back-matter/` and
`specs/001` to `specs/006` aren't edited.

## R13. What this feature doesn't do

- **Read the fix's runs again.** They hold no rankings. Reading them would mean running `main`'s
  old code with this change (spec, Assumptions).
- **Change any other kind's rows**, or the generation kind's retrieval (FR-007).
- **Show the lists in `benchmark-report`** (FR-006).
- **Add a development tool to check rows.** The quickstart's checks are throwaway scripts, and the
  unit tests keep the rules.
