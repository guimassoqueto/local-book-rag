# Quickstart: checking the progress of library operations

How to show the feature works, on fakes and then on the real stack and the four benchmark books.
What each step must show comes from the spec's success criteria; the contracts hold the details.

## Before anything

The Bash tool and a fresh shell need asdf's paths for `uv` and `make`:

```bash
export ASDF_DATA_DIR="$HOME/.asdf" PATH="$HOME/.asdf/shims:$HOME/.asdf:$PATH"
```

The stack runs (`make up`, `make pull-models`), and `benchmarks/books` on the host holds the four
books: `think-python.pdf`, `historia-economica-global.pdf`, `on-liberty.epub`, `quincas-borba.epub`.

## 1. The baseline, before any change to the code

The app container must still run `main`'s code: check that the branch has no change under `app/`
yet (`git diff main --stat -- app` is empty) and that the image was built from it.

```bash
docker compose exec app mkdir -p /app/benchmarks/books /app/benchmarks/results /tmp/devtools
docker compose cp benchmarks/books/. app:/app/benchmarks/books/
docker compose cp devtools/measure_library_progress.py app:/tmp/devtools/
docker compose exec -w /app app python -I /tmp/devtools/measure_library_progress.py --baseline --runs 3
docker compose cp app:/app/benchmarks/results benchmarks/
```

It works in `benchmarks/workspace/progress` and the `bench_progress_v` collections only, never on
the library (principle II). Expected: `benchmarks/results/library_progress_<time>/` with
`environment.json`, `durations.csv` (each operation, three runs) and `digests.json` (each book's
processed document and passages).

## 2. Unit tests

```bash
make lint-check
make test
```

Expected, among the rest:
- `tests/unit/test_progress.py`: counts that only grow and reach their totals, no time left before
  3 s and 10% or for books and summaries, the median's resistance to one stalled advance, a sink
  that raises without reaching the operation, nothing logged or tracked outside an operation.
- The lifecycle tests: each operation with a `Progress` and without leaves the same catalog, files,
  vectors and journal entries; a failure forced at each stage raises today's exception, leaves
  today's state, and the outcome names the stage (SC-004, SC-006).
- `tests/unit/test_interface.py`: each handler yields the area while the operation runs and the
  outcome line at the end; a refused call raises and leaves the area empty; the disable and enable
  events exist for the seven buttons.

## 3. The feature on the real books

Rebuild the app with the feature's code. **`make up` recreates the app container, which deletes the
library it holds** (principle II): list it first (`docker compose exec app book-rag list-books`) and
go ahead only if it is empty or the owner agrees.

```bash
make up
docker compose exec app mkdir -p /app/benchmarks/books /app/benchmarks/results /tmp/devtools
docker compose cp benchmarks/books/. app:/app/benchmarks/books/
docker compose cp devtools/measure_library_progress.py app:/tmp/devtools/
docker compose exec -w /app app python -I /tmp/devtools/measure_library_progress.py --runs 3 \
    --baseline-results benchmarks/results/library_progress_<baseline time>
docker compose cp app:/app/benchmarks/results benchmarks/
```

Expected in its report:
- **SC-002**: every count reached its total (244 and 212 pages, 425, 258, 176 and 454 passages, 4
  books, the saved summary) and never went backwards.
- **SC-003**: at least 90% of the times left shown within half and double the time actually left,
  none before 3 s and 10%.
- **SC-004**: the digests equal the baseline's.
- **SC-005**: no operation's median more than 5% or 1 s above the baseline's.
- **SC-009**: one stage line per stage reached, their durations within 1 s of the operation's.

A miss on SC-003 tunes R6's thresholds or pace, and the run is repeated.

## 4. The tab, in the browser

At `http://localhost:7860`, Library tab, on the real library. The removal and the resets delete
what is there: run them on a library the owner agrees to lose.

1. Add `think-python.pdf`. Within a second the area shows "Adding a book" and its first stage
   (SC-001); the bar fills with pages to 244, then with passages to 425; a time left appears after
   a few seconds in each; the seven buttons stay disabled until the end (SC-007); the outcome line
   stays.
2. Add `on-liberty.epub`: extraction shows the moving bar, without a count.
3. Add `think-python.pdf` again: refused as a duplicate, as today, with no stage and the buttons
   enabled again.
4. Process *Think Python* again, then replace it with `historia-economica-global.pdf`: the same
   stages, then the swap.
5. Save a summary of a chapter in the Summaries tab, then reindex the library with "Also write the
   saved summaries again": books counting to their number with each one's steps, the switch, then
   summaries counting; the line saying questions keep working; no time left for books or summaries.
6. During another addition, stop Ollama while the passages are embedded
   (`docker compose stop ollama`, which keeps its models), then start it again
   (`docker compose start ollama`): the outcome names the embedding stage, the error is today's,
   the book is listed as failed, and the buttons are enabled again.
7. Remove a book, then reset the index, then reset everything: their steps by name, with the moving
   bar, and their outcome lines.
8. Reload the page during a reindex: the reindex goes on (the log shows it finishing), the new page
   shows nothing of it, and an operation started from it is refused as busy.

## 5. The commands

```bash
docker compose exec app book-rag add-book /app/benchmarks/books/think-python.pdf 2>stages.txt
docker compose exec app book-rag reindex-all >report.txt 2>stages.txt
```

Expected: standard output as today (for `reindex-all`, the report only); on the error stream, a
line per stage and no more than one count line every 2 seconds per stage, plus its last (SC-008),
ending with `done`.

## 6. The log

```bash
docker compose exec app sh -c 'grep "stage " /app/logs/app.jsonl | tail -20'
```

Expected: one "stage finished" line per stage, with its key, count and duration, and the
operation's execution ID; a failed stage as "stage failed"; no title, file name or text from a book
(FR-015).
