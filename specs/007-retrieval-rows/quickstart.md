# Quickstart: checking what the retrieval rows record

How to show that the feature works: first without services, then on the real stack. Order matters
twice:
- `main`'s outputs come first (§ 2), while the running container is still `main`'s code.
- The rebuild deletes the owner's library (§ 3), and they add their book back at the end (§ 10).

What each step must show comes from the spec's success criteria. The contracts hold the details.

## 0. Before anything

A fresh shell needs asdf's paths for `uv` and `make`. The steps below share these names, so they
run in one shell:

```bash
export ASDF_DATA_DIR="$HOME/.asdf" PATH="$HOME/.asdf/shims:$HOME/.asdf:$PATH"
MAIN=benchmarks/results/markdown_books_20261120T021742092846Z   # main's run, before the fix
FIX=benchmarks/results/markdown_books_20261120T022603129972Z    # the fix's run, SC-001's baseline
OUT="$(mktemp -d)"                                              # outside the repository
```

`git status --short` is clean on `feat/retrieval-rows`. `uv.lock` is `main`'s: no dependency
changes.

## 1. Unit tests and lint (SC-006)

```bash
make lint-check
make test
```

Expected: lint is clean, and every unit test passes, with the new ones of `research.md`, R11:
- `test_benchmark.py`:
  - both lists in each of the three files;
  - the six scores computed again from them;
  - the lists as the search returned them;
  - the context as the ranking's first `top_k`, with reranking on and off;
  - both lists in the rows of a run that fails;
  - `summary.csv` without them, and generation rows without them.
- `test_compare_runs.py`:
  - each case of FR-009 and FR-010: evidence first, evidence below other chunks, several quotes,
    none within the first ten, none retrieved, a ranking shorter than ten;
  - each run's IDs under its own label;
  - two runs without the lists, and one without them paired with one that has them;
  - no question moved;
  - today's tests, unchanged.
- `test_report.py`: a result with the lists renders as the same result without them.

## 2. `main`'s outputs, before the change (SC-003, SC-004, FR-015)

**The fix's two result folders**, file by file, to check at the end that nothing rewrote them:

```bash
sha256sum "$MAIN"/* "$FIX"/* > "$OUT/old-runs.sha256"
```

**The comparison, on `main`'s code**: before the branch changes `devtools/compare_runs.py`, or
later from a worktree of `main` (`git worktree add "$OUT/main" main`, with the same command run
there on absolute paths):

```bash
uv run python devtools/compare_runs.py "$MAIN" "$FIX" --labels main fix > "$OUT/compare-main.md"
```

**`benchmark-report`, on `main`'s code.** The running container is v0.6.1's image, whose `app/` is
`main`'s. It has no `benchmarks/` until one is copied in:

```bash
docker compose cp -a benchmarks app:/app/
for run in "$MAIN" "$FIX"; do
  name=$(basename "$run")
  docker compose exec -T app book-rag benchmark-report "$run" > "$OUT/report-main-$name.md"
  docker compose exec -T app book-rag benchmark-report "$run" --baseline default > "$OUT/report-main-$name-baseline.md"
done
```

Expected: six files in `$OUT`, none of them empty. `compare-main.md` lists four questions that
moved, as `docs/benchmark-results.md` records.

## 3. The rebuild, and what it deletes

Commit the change first, so that the runs name a commit that holds it (`research.md`, R10).

`make up` rebuilds the app image from the branch and recreates the app container. That deletes:
- the owner's library, *História econômica global*;
- its logs;
- the reranker's weights, which the new container downloads again on its first search;
- the container's copy of `benchmarks/`.

ChromaDB and Ollama keep their data, models included. The new catalog numbers its indexes from 1
again, so `reset-everything` comes next. It deletes the library, now empty, and every
`book_chunks_v*` collection in ChromaDB:

```bash
make up
docker compose exec app book-rag reset-everything --confirm "DELETE EVERYTHING"
docker compose exec app book-rag doctor
```

Expected: `doctor` reports no failure.

## 4. The two runs (SC-001, SC-005)

`make benchmark` doesn't pass `--commit`, so the runs are started by hand (README, Benchmarks):

```bash
cp specs/007-retrieval-rows/benchmarks/experiments/no_reranking.yaml benchmarks/experiments/
docker compose cp -a benchmarks app:/app/
COMMIT="$(git describe --always --dirty)"
docker compose exec app book-rag benchmark benchmarks/experiments/markdown_books.yaml --commit "$COMMIT"  # about 6 minutes
docker compose exec app book-rag benchmark benchmarks/experiments/no_reranking.yaml --commit "$COMMIT"    # about a minute
```

Each run prints `Results: benchmarks/results/<experiment>_<time>`. Copy only those two out, so that
nothing writes into the older folders:

```bash
NEW=benchmarks/results/markdown_books_<time>   # as the first run printed it
OFF=benchmarks/results/no_reranking_<time>     # as the second run printed it
docker compose cp "app:/app/$NEW" benchmarks/results/
docker compose cp "app:/app/$OFF" benchmarks/results/
```

Expected:
- **The first run** indexes the three books in a fresh workspace.
- **The second run** indexes nothing: it reuses the first run's workspace (`research.md`, R9).
- **Both** say `complete: true`.

## 5. The same rows (SC-001)

A throwaway check on the host compares the inputs that the two runs recorded, then every row:

```bash
uv run python - "$FIX" "$NEW" <<'EOF'
import json, sys
from pathlib import Path

FIELDS = ("relevant_chapters", "relevant_chunks", "recall_at_5", "recall_at_10", "mrr", "ndcg_at_10",
          "context_precision", "context_recall")
fix, new = (json.loads(Path(run, "results.json").read_text(encoding="utf-8")) for run in sys.argv[1:])
for key in ("configuration_sha256", "dataset_sha256", "book_sha256"):
    print(key, fix["environment"][key] == new["environment"][key])
embedding = "qwen3-embedding:0.6b"
print(embedding, fix["environment"]["models"][embedding]["digest"] == new["environment"]["models"][embedding]["digest"])
rows = [{(row["variant"], row["question"]): row for row in run["rows"]} for run in (fix, new)]
print(len(rows[0]), "rows, the same questions:", rows[0].keys() == rows[1].keys())
print("rows that differ:", [key for key in rows[0] if any(rows[0][key][f] != rows[1][key][f] for f in FIELDS)])
EOF
cmp "$FIX/summary.csv" "$NEW/summary.csv" && echo "summary.csv: identical"
```

Expected:
- **Every input** prints `True`: the same configuration, dataset, books and embedding model.
- **The rows**: 75, the same questions, and `rows that differ: []`.
- **`summary.csv`**: identical, byte for byte.

A row that differs is a change to look into, not noise. A run of `main`'s code on the same models
tells whether this change moved it (`research.md`, R8).

## 6. The scores from the lists (SC-002)

A throwaway script, piped into the app container the way `devtools/default_llm.py` is, checks each
row of the new run:
- it loads the configuration, and opens the default variant's workspace as the runner does, which
  indexes nothing, since the workspace exists;
- for each row of `rows.jsonl`, it resolves the question's evidence quote by quote with
  `relevant_chunks`;
- it computes the six scores again from the row's `ranking` and `context`
  (`contracts/retrieval-rows.md`, What the lists satisfy);
- it checks that `context` is `ranking[:5]`.

```bash
docker compose exec -T app python - "$NEW" < "$OUT/check_rows.py"
```

Expected: 75 rows checked, every score equal, every context the ranking's first five, and no
ranking longer than 30.

## 7. `benchmark-report` (SC-003)

```bash
for run in "$MAIN" "$FIX"; do
  name=$(basename "$run")
  docker compose exec -T app book-rag benchmark-report "$run" | cmp - "$OUT/report-main-$name.md"
  docker compose exec -T app book-rag benchmark-report "$run" --baseline default | cmp - "$OUT/report-main-$name-baseline.md"
done
docker compose exec -T app book-rag benchmark-report "$NEW" > "$OUT/report-new.md"
diff "$OUT/report-main-$(basename "$FIX").md" "$OUT/report-new.md"
```

Expected:
- **The four `cmp`** print nothing: the fix's two runs render on this branch exactly as on
  `main`, with and without `--baseline default`.
- **The `diff`** shows one changed line, the one that says when, and with which Ollama, each run
  ran. The tables are the same, and the lists appear nowhere.

## 8. The comparison (SC-004, SC-005, FR-015)

```bash
uv run python devtools/compare_runs.py "$MAIN" "$FIX" --labels main fix > "$OUT/compare-branch.md"
diff "$OUT/compare-main.md" "$OUT/compare-branch.md"
uv run python devtools/compare_runs.py "$FIX" "$NEW" --labels fix branch
uv run python devtools/compare_runs.py "$NEW" "$OFF" --labels default no_reranking > "$OUT/compare-reranking.md"
sha256sum -c --quiet "$OUT/old-runs.sha256" && echo "the older runs: unchanged"
```

Expected:
- **`main` against the fix**: the `diff` only adds lines at the end. They are the section "What
  ranked above the evidence", with eight rows: the four questions that moved, `main`'s row then
  the fix's, each `not recorded` in both cells (SC-004).
- **The fix against the new run**: 75 pairs, none left out, every difference `+0.000 (+0.000 to
  +0.000)`, `None.` under "Questions that moved", and no new section (SC-004).
- **The default against reranking off**: questions that moved, each with both runs' rows in the
  new table. A throwaway check rebuilds each of those rows from the two runs' `rows.jsonl`, by
  FR-009 and FR-010. It is written from the spec, not from the devtool's code, and every row has
  to agree (SC-005). Read a few by hand too: one that the reranker lifted, and one that it sank.
- **The older runs**: unchanged, file for file (FR-015).

## 9. The diff (SC-007)

```bash
git diff main...HEAD --name-only
```

The three dots compare with where the branch left `main`, so a later merge into `main` doesn't
count. Expected: only the files of `plan.md`'s Project Structure, `README.md`, `docs/decisions.md`,
`docs/benchmark-results.md` and `specs/007-retrieval-rows/`. None is in `app/retrieval`,
`app/ingestion`, `app/generation`, `app/storage` or `config/`.

## 10. The records, and the library

- **`README.md`, Benchmarks**: a retrieval row lists its ranking and its context, by chunk ID, and
  `devtools/compare_runs.py` shows what ranked above the evidence of each question that moved
  (FR-016).
- **`docs/decisions.md`, Evaluation**: why the rows record the two lists, why IDs and not texts,
  and why the comparison reads to that depth (FR-017).
- **`docs/benchmark-results.md`**: the two runs, where their results are, and what the comparison
  showed. Its section on the publisher-back-matter fix keeps its inference (FR-018).
- **The history**: `git diff main...HEAD --name-only -- .specify specs/001-* specs/002-* specs/003-*
  specs/004-* specs/005-* specs/006-*` prints nothing (FR-019).

The library has been empty since § 3. The owner adds their book back (README, Library):

```bash
docker compose cp "<book>.md" app:/tmp/
docker compose exec app book-rag add-book "/tmp/<book>.md"
```
