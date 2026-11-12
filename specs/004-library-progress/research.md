# Research: The progress of library operations

The decisions behind `plan.md`, each with what was chosen, why, and what else was considered. The
spec's Context holds the measurements they rest on.

## R1. Where progress is tracked

**Decision.** A new module, `app/utils/progress.py`, holds `Progress`: a tracker that an operation
reports its stages and counts to, and that anyone can ask for a snapshot. The services own it: each
of the seven service methods takes an optional `progress` and makes a silent one when it gets
none, so the stage lines of FR-015 are logged for every operation, from the tab, the commands, the
benchmarks or the tests alike.

**Rationale.** The counts come from below the services: pages from the PDF loader, passages from
the embedding provider's batches. `app/ingestion` and `app/embeddings` can't import from
`app/services`, so the tracker lives in `app/utils`, beside `logging`, which they all use already.
The stage lists, the time left and the outcome are computed in it, so the tab and the commands only
render what it returns (FR-016, principle IV).

**Alternatives considered.**
- *Plain callbacks, `on_progress: Callable[[str], None]`, as `reindex_all` and the summarizer have
  today.* A string can't carry a count, a total or a position, and the tab would have to parse it
  back.
- *An event stream from each service, as `QuizService.prepare` yields events.* See R2: a generator
  can't hold the library lock and the operation's log context across Gradio's worker threads.

## R2. How the tab follows an operation

**Decision.** The tab's handler is a generator. It starts the service call in a thread of its own,
then, until the thread ends, asks `progress.snapshot()` every half second and yields the area's HTML
when the snapshot changed or a second has passed. When the thread ends, it yields the outcome, and
re-raises the operation's error, if any, so that `reports_errors` shows it as today.

**Rationale.**
- **Gradio's own progress bar can't do it.** It draws over an event's output components, and none
  of the tab's seven events has one, so the `progress(0, desc=…)` calls in
  `app/interface/library.py` today most likely show nowhere. It also shows an estimate of its own,
  from the event's earlier runs, for the whole operation, which the owner ruled out
  (Clarifications), and it disappears when the event ends, so the outcome line of FR-004 needs a
  component anyway.
- **The service can't be the generator.** An operation holds the library lock, a `FileLock` that
  belongs to the thread that took it, and runs inside `operation()`, whose context variable a
  Gradio generator can't reset between its steps: each step may run in a different worker thread.
  `docs/decisions.md` records the second for the quiz, whose `prepare()` logs its operation lines
  itself for that reason. One thread from start to end keeps both as they are.
- **Polling, not pushing.** Nothing the operation does waits on the page: a page closed mid-way
  only stops the polling, and the operation runs on (FR-012). The elapsed time comes in the
  snapshot, computed by the tracker, so the tab computes nothing (FR-016).

**Alternatives considered.**
- *A queue the tracker pushes to and the handler drains.* It works too, but a queue nobody drains
  grows for the rest of a long reindex after the page is closed, and the elapsed time would still
  need a tick.
- *A `gr.Timer` polling a per-session state.* It keeps polling when nothing runs, and the
  operation would still need a thread to run in.

## R3. The operation's thread

**Decision.** A daemon thread, started by the handler, runs the service call from start to end.

**Rationale.** It is what the call runs in today: Gradio runs a handler in an AnyIO worker thread,
started from its server's daemon thread, so it is a daemon too. A server that shuts down mid-way
kills the operation as it does today, and recovery finishes or undoes it at the next start
(principle II). The lock is taken and released in that one thread, and `operation()` sets and
resets its context there.

**Alternatives considered.** *A non-daemon thread*: a shutdown would wait for a reindex that can
take minutes, with summaries, and `docker stop` kills the process after 10 s anyway.

## R4. Disabling the buttons

**Decision.** Each of the seven buttons runs three events in a chain: one that disables all seven,
without the queue; the operation's handler, which keeps today's `api_name`; and, on its success
and on its failure, one that enables them again. The refresh of the book list stays where it is,
on the handler's success and failure (`app/interface/gradio_app.py`).

**Rationale.** Gradio's `then` doesn't run after an error, as `gradio_app.py` already notes, so the
enabling event is attached with `success` and `failure`, like the refresh. The handler stays the
event the API names, so `gradio_client` and `tests/integration/test_interface.py` call it as
before, without the button events.

**Alternatives considered.** *Yielding the buttons' state from the handler.* The API would then
return seven button updates with every call, and an error before the last yield would leave them
disabled.

## R5. The progress area

**Decision.** A `gr.HTML` at the top of the tab, under the index status, holding a native
`<progress>` element and a line of text. A countable stage sets its `value` and `max`, so the bar
fills; a stage without a count leaves `value` out, which every browser draws as a moving bar that
doesn't fill. The handler's event uses `show_progress="hidden"`, so Gradio's overlay doesn't cover
the area.

**Rationale.** It is what the owner chose (Clarifications) with no JavaScript and no image: the
indeterminate state of `<progress>` is the browser's own. `gr.HTML` in Gradio 6.31 takes a
`css_template` for its styling.

**Alternatives considered.** *A `gr.Slider` or `gr.Markdown` with a text bar*: neither has an
indeterminate state, and a slider invites dragging.

## R6. The time left

**Decision.** For a countable stage that shows one (pages, passages), the pace is the weighted
median of the seconds per item over every advance of the stage so far, each advance weighing as
many items as it carried. The time left shows once the stage has run 3 seconds and done 10% of its
items (FR-006), and is `max(items left × pace − seconds since the last advance, 0)`, so it counts
down between advances.

**Rationale.** In the spec's first run, one batch of *Think Python*'s 27 took 8.4 s against 0.2 to
0.3 s for the others. A mean carries that stall to the end of the stage: if it comes early, the
estimate halfway through is about three times the time actually left (12.4 s spent on 13 batches,
so 0.9 s a batch for the 14 left, against 0.3 s), while a median doesn't move. The 3 s and 10%
keep the estimate off a stage's first items, which include its start-up. Counting down between
advances keeps it right during a long batch or a slow page.

**Alternatives considered.**
- *The mean pace*: thrown off by a single stall, as above.
- *An exponential moving average*: carries a stall for several advances, and needs a weight to
  tune.
- *The pace of the last N advances*: noisy on pages, whose time varies with their tables.

The thresholds and the pace are tuned against SC-003 if the measurement misses it.

## R7. How often a display hears of progress

**Decision.** The tracker calls its sink, when it has one, at a stage's start and end, at an
operation's end, and at most every `interval` seconds while a stage advances. The commands use a
sink that prints to the error stream, with an `interval` of 2 seconds (FR-014). The tab passes no
sink: it polls (R2).

**Rationale.** The throttle is part of the tracker, so the commands only print what reaches them
(FR-016). A sink that raises, such as a closed terminal, is logged once and dropped, and the
operation goes on (FR-012).

## R8. Who reports which stage

**Decision.**

| Stage                               | Opened by                                          | Counted by                                   |
| ----------------------------------- | -------------------------------------------------- | -------------------------------------------- |
| Removing the earlier failed attempt | `BookService.add_book`, when retrying a failed one | –                                            |
| Storing the file                    | `BookService.add_book` and `replace_book`          | –                                            |
| Extracting the text                 | `IngestionPipeline.process`                        | `PdfLoader.load`, a page at a time           |
| Preparing the passages              | `IngestionPipeline.process`                        | –                                            |
| Embedding the passages              | `IngestionService.ingest`                          | `embed_documents`'s `on_batch`, which exists |
| Saving to the index                 | `IngestionService.ingest`                          | –                                            |
| Swapping in the new version         | `BookService.replace_book` and `reindex_book`      | –                                            |
| The steps of a removal or a reset   | `LibraryData.delete_book` and `clear`              | –                                            |
| Bringing back kept originals        | `LibraryService.reindex_all`                       | the originals brought back                   |
| Indexing the books                  | `LibraryService.reindex_all`                       | its loop over the books                      |
| Switching to the new index          | `LibraryService.reindex_all`                       | –                                            |
| Writing the summaries again         | `LibraryService.reindex_all`                       | its loop over the saved summaries            |

**Rationale.** Each stage is opened where its work is done, so a failure inside it is attributed
to it without any bookkeeping (FR-004). The loaders get the extraction's stage as an optional
argument, so the benchmark's direct calls to `pipeline.process` keep working unchanged.

## R9. When an operation's progress begins

**Decision.** Inside `operation()`, once the checks that refuse an operation have passed: the busy
lock, a confirmation, a duplicate checksum, an index that needs a reindex, a missing original, an
empty library. `reindex_all` brings back kept originals before its checks, today; that order stays
(FR-011), and when it brought any back, its first stage is reported already done, with their count.

**Rationale.** A refused operation then shows no stage (US1 scenario 7, US3 scenario 3, the
edge cases), and the stages cover the operation's logged duration, so their durations add up to it
(SC-009). The checks take milliseconds, so the first stage still shows within a second of the click
(SC-001).

**Alternatives considered.** *Moving `reindex_all`'s adoption after its checks*, to report it as a
running stage. That changes what a refused reindex leaves in the catalog, which this feature
mustn't (FR-011).

## R10. Failures

**Decision.** A stage's context logs "stage failed" and lets the exception through unchanged; the
tracker keeps the stage it happened in, for the outcome. Nothing the tracker does raises into the
operation: a sink's exception is caught there (R7).

**Rationale.** `BookService.add_book` turns any exception from ingestion into a FAILED book, with a
catch-all `except Exception`. An exception from the display would therefore fail the book: the
tracker never lets one out, and a unit test holds it to that (FR-011, FR-012, SC-006).

## R11. The extraction's count

**Decision.** `PdfLoader.load` counts the pages it reads for their text. When it finds the PDF
scanned and hands it to OCR, the stage drops its count and notes "with OCR" (US1 scenario 4).
Docling as the PDF extractor, EPUB and Markdown report the stage without a count (Clarifications).

**Rationale.** PyMuPDF's page loop is the one place that knows both the total and each page.
Docling's converter offers no page callback, and an EPUB's extraction took 0.1 s or less.

## R12. The commands' lines

**Decision.** The seven commands pass a `Progress` whose sink prints `progress_text(view)` from
`app/interface/formatting.py` to the error stream, with an `interval` of 2 seconds. `reindex-all`
stops printing its book lines to standard output (FR-014).

**Rationale.** The tab and the commands describe a stage with the same function, so they can't
drift apart. The commands' standard output stays their result, as `summarize` already does with its
progress.

## R13. The stage lines in the log

**Decision.** At a stage's end, `log_event(logger, "stage finished" or "stage failed", ...)` with
`stage` (its key), `done`, `total` and `unit` when it has a count, `duration_seconds`, and, for a
stage inside a book or a summary of a reindex, `within` (the outer stage's key) and `item` (the book's ID).
They are logged inside `operation()`, so they carry its execution ID.

**Rationale.** FR-015, with no text from the book: titles and file names stay out, the book's ID
identifies it.

## R14. Measuring it on real books

**Decision.** A script, `devtools/measure_library_progress.py`, run in the app container, builds an
isolated library in `benchmarks/workspace/progress`, with `bench_progress_v` collections, as the
benchmarks do (principle II). On the four benchmark books, it adds each one, processes it again,
replaces one, reindexes the library with a saved summary, removes a book, and resets the index and
everything. It records each operation's duration, a digest of each book's processed document and
passages, and, with the feature's code, a snapshot every quarter second. It writes them, with the
environment (commit, GPU, configuration, the books' checksums), to
`benchmarks/results/library_progress_<time>/`, and computes SC-002, SC-003, SC-005 and SC-009.

It runs first on `main`'s code, as the baseline, before any change, then on the feature's, three
times each. The digests answer SC-004, and the durations SC-005. The reindex that writes a saved
summary again runs once, in the feature's run, for its counts: a summary's time varies with what
the model writes, so SC-005 compares the reindexes without summaries.

**Rationale.** Principle V asks for real books, and SC-003 and SC-005 can only be measured on them:
the fakes of the unit tests take no time. The workspace is reset at each run, so a change to the
ingestion code can't leave a stale index behind (principle VI).

**Alternatives considered.**
- *A benchmark experiment kind.* Experiments compare variants of a configuration; this compares two
  versions of the code, once.
- *The real library.* The measurement adds and removes books at will, which principle II keeps away
  from it.
