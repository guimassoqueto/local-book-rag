# Data model: The progress of library operations

Nothing here is stored: a `Progress` lives as long as its operation, in memory. The only lasting
trace is the stage lines in the log (FR-015). The catalog, the journal and the index are unchanged.

## StageSpec

A stage an operation declares before it starts, so that the area can say "stage 2 of 5".

| Field      | Type                      | Meaning                                                                          |
| ---------- | ------------------------- | -------------------------------------------------------------------------------- |
| `key`      | `str`                     | The name in the log, such as `extract`.                                          |
| `label`    | `str`                     | The name on screen, such as "Extracting the text".                               |
| `unit`     | `str \| None`             | What a count counts: `pages`, `passages`, `books`, `summaries`, `originals`.     |
| `estimate` | `bool`                    | Whether a count shows a time left. False for books and summaries (Clarifications). |
| `steps`    | `tuple[StageSpec, ...]`   | The stages inside each item, for the books and summaries of a reindex.          |

A stage with a `unit` may still run without a count: extraction counts pages only for a PDF read
for its text (R11).

## The stages of each operation

The keys and labels are the plan's (FR-007 allows other names, not merging a counted stage into
another).

| Operation                         | Stages, in order                                                                                                                                                          |
| --------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Adding a book                     | `remove_failed` "Removing the earlier failed attempt" (only when retrying one), `store` "Storing the file", `extract`, `prepare`, `embed`, `save`                          |
| Replacing a book                  | `store` "Storing the replacement", `extract`, `prepare`, `embed`, `save`, `swap` "Swapping in the new version"                                                            |
| Processing a book again           | `extract`, `prepare`, `embed`, `save`, `swap`                                                                                                                             |
| Removing a book                   | `vectors` "Deleting its passages from the index", `processed` "Deleting its processed documents", `summaries` "Deleting its summaries", `original` "Deleting its original" or "Moving its original to the archive", `catalog` "Removing it from the catalog" |
| Resetting the index               | `collections` "Deleting the index", `processed` "Deleting the processed documents", `summaries` "Deleting the summaries", `sources` "Keeping a record of the originals", `catalog` "Clearing the catalog" |
| Resetting everything              | `collections`, `processed`, `summaries`, `originals` "Deleting the originals", `catalog`                                                                                  |
| Reindexing the library            | `adopt` "Bringing back kept originals" (only when there were any), `books` "Indexing the books", `switch` "Switching to the new index", `summaries` "Writing the summaries again" (only when chosen) |

Where `extract` is "Extracting the text" (unit `pages`, estimated), `prepare` "Preparing the
passages", `embed` "Embedding the passages" (unit `passages`, estimated) and `save` "Saving to the
index". The `books` stage counts books without a time left, with `extract`, `prepare`, `embed` and
`save` as its steps; the `summaries` stage counts summaries without a time left, with no declared
steps: the summarizer's own messages show as its note.

## ProgressView

What `Progress.snapshot()` returns, and what a sink receives: the spec's "progress update".

| Field        | Type                 | Meaning                                                                    |
| ------------ | -------------------- | -------------------------------------------------------------------------- |
| `operation`  | `str`                | "Adding a book", "Reindexing the library", ...                             |
| `subject`    | `str \| None`        | The book's ID, for an operation on one book.                               |
| `stage`      | `StageView \| None`  | The current stage. None before the first starts.                           |
| `step`       | `StageView \| None`  | The current step inside it, for a reindex's book.                          |
| `elapsed`    | `float`              | Seconds since the operation's progress began.                             |
| `meanwhile`  | `str \| None`        | What keeps working during the operation, for the reindex: "Questions keep working on the current index meanwhile." (FR-008) |
| `outcome`    | `Outcome \| None`    | Set once the operation has ended.                                          |

## StageView

| Field       | Type              | Meaning                                                                            |
| ----------- | ----------------- | ---------------------------------------------------------------------------------- |
| `key`       | `str`             | From its `StageSpec`.                                                              |
| `label`     | `str`             | From its `StageSpec`.                                                              |
| `position`  | `int`             | 1-based, among the stages of its list.                                             |
| `stages`    | `int`             | How many stages its list has.                                                      |
| `done`      | `int \| None`     | Items done, when it is counted.                                                    |
| `total`     | `int \| None`     | Items in all, when it is counted.                                                  |
| `unit`      | `str \| None`     | When it is counted.                                                                |
| `time_left` | `float \| None`   | Seconds, only where R6 allows one.                                                 |
| `note`      | `str \| None`     | "with OCR", the title of the book being indexed, a summary's own message.          |

## Outcome

| Field       | Type          | Meaning                                                      |
| ----------- | ------------- | ------------------------------------------------------------ |
| `succeeded` | `bool`        |                                                              |
| `stage`     | `str \| None` | The label of the stage it failed in, when it failed in one.  |
| `error`     | `str \| None` | The error's message, when it failed.                         |

What a successful operation did is told by its result, as today: the tab composes the outcome
line from the returned book or report, the same way it composes today's notification.

## Rules

- **Counts.** `done` starts at 0 when a count starts, only grows, and never exceeds `total`. A
  stage that ends normally with a count reports `done == total` (FR-010). Extraction may drop its
  count once, when OCR takes over (R11); its log line then keeps the pages it read.
- **Time left.** Only for a stage whose spec says `estimate`, once it has run 3 seconds and done
  10% of its items, as R6 computes it. None otherwise.
- **Positions.** A stage's position is its index in the operation's list; a step's, its index in
  its stage's `steps`. A conditional stage (`remove_failed`, `adopt`, `summaries`) is left out of the
  list when it won't run, so the positions stay consecutive.
- **Lifecycle.** `snapshot()` returns None until the operation begins, then views with a stage, and
  finally a view with an `outcome`. A refused operation never begins, so its snapshot stays None
  (R9).
- **Thread safety.** The operation's thread writes, the tab's handler reads: every read and write
  holds one lock, and `snapshot()` returns a frozen copy.

## The stage line in the log

One per stage reached, when it ends (FR-015, R13):

| Field              | When                                                     |
| ------------------ | -------------------------------------------------------- |
| message            | `stage finished`, or `stage failed`                      |
| `stage`            | always: the key                                          |
| `done`, `total`, `unit` | when it had a count                                 |
| `ocr`              | `true`, when extraction went to OCR                      |
| `duration_seconds` | always                                                   |
| `within`, `item`   | for a step inside a reindex's book: the outer stage's key and the book's ID |
| `execution_id`, `operation` | always, from `operation()`                      |

No title, file name or text from the book.
