# Quickstart: checking the quiz's removal

How to show the feature works: first without services, then on the real stack. Order matters
twice. The comparisons with `main` (§ 3) need a worktree of `main` and no stack. The checks that
use the host's quiz files (§ 6) come before those files are deleted (§ 7). What each step must
show comes from the spec's success criteria, and the contracts hold the details.

## 0. Before anything

A fresh shell needs asdf's paths for `uv` and `make`:

```bash
export ASDF_DATA_DIR="$HOME/.asdf" PATH="$HOME/.asdf/shims:$HOME/.asdf:$PATH"
```

`git status --short` is clean on `feat/remove-chapter-quiz`, and `uv.lock` is `main`'s: no
dependency changes (FR-008).

## 1. Unit tests and lint

```bash
make lint-check
make test
```

Expected:
- **Lint** is clean: no import left unused by the removal (`research.md`, R2).
- **Every unit test passes**, with the four quiz test files gone and the shared files changed as
  R10 lists.
- **The refusals**, each in its test:
  - `test_config.py`: a `quiz` section under `generation` stops loading, naming
    `generation.quiz` (FR-003);
  - `test_benchmark.py`: an `extraction`, a `quiz` and a `quiz_check` experiment are refused,
    naming the four kinds, and a retrieval experiment with any of the five removed fields is
    refused (FR-011);
  - `test_report.py` and `test_commands.py`: a `quiz`, a `quiz_check` and an `extraction` result
    are refused, naming the kind, with nothing on standard output (FR-012).
- **What stays**: one provider for `llm.model` in the container (`test_container.py`), the four
  tabs in order (`test_interface.py`), the cache sweep within the hour and the stop on SIGTERM.

## 2. Nothing left (SC-001)

```bash
git grep -i -l quiz -- . ':!docs/decisions.md' ':!docs/benchmark-results.md' ':!specs/' ':!.specify/assessments/'
git grep -i -n quiz -- docs/decisions.md docs/benchmark-results.md
```

Expected: the first prints nothing. The second finds, in `docs/decisions.md`, only the section
"Removed: the chapter quiz (v0.6.0)", and in `docs/benchmark-results.md` only the quiz's section,
with its removal line (FR-015, FR-016). The dataset's "não quiz fitar" is under `specs/`, and the
books aren't in the repository.

## 3. The same as `main` (SC-002, SC-006, US3)

**The diff.**

```bash
git diff main --stat
git diff main -U0 -- app/generation/prompts.py | grep '^+[^+]'
```

Expected:
- `--stat` lists none of `app/services/index_service.py`, `app/storage/catalog.py`,
  `app/ingestion/chunker.py`, `app/ingestion/pipeline.py`, `config/ingestion.yaml`,
  `config/models.yaml`, `config/retrieval.yaml`, `app/evaluation/summary_metrics.py`,
  `app/evaluation/ragas_llm.py`, `app/generation/question_answering.py`,
  `app/generation/summarization.py` and `app/generation/citations.py` (R8, R9).
- The `grep` prints nothing: `prompts.py` only lost lines.

**The prompts and a report, built on both trees.** A throwaway script, kept in the session's
scratchpad and never committed (R8), prints:
- `app.__file__`, to show which tree it loaded;
- one SHA-256 per prompt, for fixed inputs: every builder left in `prompts.py`, on an English and
  a Portuguese question and passage, and the summary judge's two prompts with fixed values;
- the SHA-256 of `render()` on a retrieval result from the host's `benchmarks/results/`
  (`markdown_books_*`), without and with `--baseline`'s comparison.

It runs on a worktree of `main` and on the branch, with the branch's `.venv`. `PYTHONPATH` puts
each tree's `app` before the editable install's:

```bash
git worktree add "$SCRATCH/main-tree" main
PYTHONPATH="$SCRATCH/main-tree" .venv/bin/python "$SCRATCH/same_as_main.py" > "$SCRATCH/main.txt"
PYTHONPATH="$PWD" .venv/bin/python "$SCRATCH/same_as_main.py" > "$SCRATCH/branch.txt"
diff "$SCRATCH/main.txt" "$SCRATCH/branch.txt"   # only the app.__file__ line differs
git worktree remove "$SCRATCH/main-tree"
```

Expected: every hash is the same on both. The results go to the spec's results section.

## 4. The rebuild, and what it deletes

`make up` rebuilds the app image and recreates the app container, which deletes its library
(empty on 2026-11-19: `list-books` showed no book), its logs, and `data/quiz_downloads`. ChromaDB
and Ollama keep their data, models included (R15). The new catalog numbers its indexes from 1
again, so `reset-everything` comes first. It deletes the library, empty as it is, and every
`book_chunks_v*` collection in ChromaDB:

```bash
make up
docker compose exec app book-rag reset-everything --confirm "DELETE EVERYTHING"
docker compose exec app book-rag doctor
```

Expected: `doctor` reports no failure (SC-003).

## 5. On the running stack (SC-003, SC-004)

```bash
make test-integration
time docker compose restart app
```

Expected: the integration tests pass without `test_quiz.py`, and the restart takes under 2 s.

In the browser, at <http://localhost:7860>:
1. The tabs are Library, Chat, Summarization and Research, and no other.
2. Add `benchmarks/books/on-liberty.md` in the Library tab. When it is indexed, it is in the Chat
   and Summarization tabs' lists.
3. Ask a question about it in the Chat tab. The answer cites its passages by book, chapter and
   section.
4. Summarize one of its chapters in the Summarization tab, and save the summary.

## 6. The refusals on the stack (SC-005)

Each with a file copied into the container, which is put back or removed afterwards:

```bash
# A configuration that still has a quiz section
docker compose cp app:/app/config/generation.yaml "$SCRATCH/generation.yaml"
git show main:config/generation.yaml > "$SCRATCH/generation-with-quiz.yaml"
docker compose cp "$SCRATCH/generation-with-quiz.yaml" app:/app/config/generation.yaml
docker compose exec app book-rag doctor          # stops: generation.quiz
docker compose cp "$SCRATCH/generation.yaml" app:/app/config/generation.yaml
docker compose exec app book-rag doctor          # passes again

# A quiz experiment, and a quiz result. The runner loads the dataset before the experiment.
docker compose exec app mkdir -p /app/benchmarks/results
docker compose cp specs/005-markdown-only/benchmarks/. app:/app/benchmarks/
docker compose cp specs/003-chapter-quiz/benchmarks/quiz.yaml app:/app/benchmarks/experiments/
docker compose cp specs/003-chapter-quiz/benchmarks/quiz_check.yaml app:/app/benchmarks/experiments/
docker compose exec app book-rag benchmark benchmarks/experiments/quiz.yaml         # refused
docker compose exec app book-rag benchmark benchmarks/experiments/quiz_check.yaml   # refused
docker compose cp benchmarks/results/quiz_20261111T130111197357Z app:/app/benchmarks/results/
docker compose exec app book-rag benchmark-report benchmarks/results/quiz_20261111T130111197357Z
docker compose exec app rm -r /app/benchmarks
```

Expected: `doctor` stops on the copied configuration, naming `generation.quiz`, and passes once
the file is back. `benchmark` refuses both experiments before opening a workspace, naming the four
kinds and the fields it doesn't know. `benchmark-report` prints the error of
`contracts/benchmark.md` and nothing else.

## 7. The host's quiz files (FR-013)

After § 6, and only then:

```bash
rm benchmarks/experiments/{quiz,quiz_models,quiz_check,key_cases}.yaml
rm -r benchmarks/results/quiz_2026* benchmarks/results/quiz_models_2026* benchmarks/results/quiz_check_2026*
ls benchmarks/experiments benchmarks/results
```

Expected: the experiments left are `default_llm_generation`, `default_llm_summarization`,
`generation`, `historical_spelling`, `markdown_books`, `performance`, `retrieval` and
`summarization`. The results left are the retrieval runs (`markdown_books_*`), `chunks-*`,
`library_progress_*` and `compare_originals_markdown.md`. Git sees no change, since `benchmarks/`
is ignored.

## 8. The records

- `README.md`: four tabs, no Quizzes section, no quiz kinds, and the `--commit` advice in the
  Benchmarks section's general part (R11).
- `docs/decisions.md`: the entries of R12 deleted, reworded and added.
- `docs/benchmark-results.md`: the quiz's section kept with its removal line, and the Known
  limitations of R13.
- § 2's search, run again: still the same.
