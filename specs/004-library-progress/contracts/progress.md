# Contract: progress, from the operations down

What `app/utils/progress.py` offers, and what changes in the signatures it is threaded through.
The types are in `data-model.md`.

## `Progress`

```python
class Progress:
    def __init__(
        self,
        sink: Callable[[ProgressView], None] | None = None,
        interval: float = 0.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None: ...

    @contextmanager
    def operation(
        self,
        label: str,
        stages: Sequence[StageSpec],
        subject: str | None = None,
        meanwhile: str | None = None,
    ) -> Iterator[None]: ...

    @contextmanager
    def stage(self, key: str) -> Iterator[Stage]: ...

    def snapshot(self) -> ProgressView | None: ...


class Stage:
    def count(self, total: int) -> None: ...
    def advance(self, items: int = 1) -> None: ...
    def note(self, text: str | None) -> None: ...
    def item(self, item_id: str, note: str | None = None) -> None: ...
    def uncount(self, note: str) -> None: ...
```

- **`operation()`** begins the operation's progress, with its stages declared up front. On a normal
  exit it records a successful outcome. On an exception it records a failed one, with the label of
  the stage the exception came through, if any, the step and item for a reindex's book, and its
  message, and lets the exception through unchanged.
- **`stage(key)`** opens the declared stage of that key: a top-level one, or, while a stage with
  `steps` is open, one of its steps. It logs the stage line of `data-model.md` when it exits, as
  "stage finished" or, on an exception, "stage failed", which it lets through unchanged. A key not
  declared for where it is opened is logged as a warning, and the stage is shown without a
  position: nothing here raises into the operation (FR-012). A unit test runs every operation with
  a `Progress` that fails the test on such a warning.
- **Outside `operation()`**, `stage()` and every `Stage` method do nothing and log nothing, so code
  that runs without an operation, such as the benchmark's direct calls to `pipeline.process`, needs
  no special case.
- **`Stage.count(total)`** starts the stage's count at 0; a total of 0 is allowed, and reads "0 of
  0". **`advance(items)`** adds to it; an advance past the total is held at the total and logged as
  a warning. **`note(text)`** sets the line shown beside the stage. **`item(item_id, note)`**
  marks the item the stage's steps are about, for the steps' log lines, with its note.
  **`uncount(note)`** drops the count for the rest of the stage, keeping it for the log line, and
  sets the note.
- **The sink** is called with a fresh `ProgressView` at each stage's start, at a counted stage's
  end, at each `item()`, at the outcome, and, while a stage counts or notes, at most once per
  `interval` (research.md R7). An exception from the sink is
  logged once, at warning level, and the sink is dropped for the rest of the operation. Nothing a
  sink does reaches the operation.
- **`snapshot()`** returns None before the operation begins, then the current view, with `elapsed`
  and `time_left` computed at the moment of the call. It is safe to call from another thread.

## Where it is threaded

Every new parameter is optional and defaults to today's behavior, so the callers that don't pass
one, the benchmarks, recovery and the tests among them, run unchanged.

| Signature                                                                                   | Change                                                                 |
| ------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------- |
| `BookService.add_book(upload, filename, progress=None)`                                     | new `progress`                                                         |
| `BookService.replace_book(book_id, upload, filename, progress=None)`                        | new `progress`                                                         |
| `BookService.reindex_book(book_id, progress=None)`                                          | new `progress`                                                         |
| `BookService.remove_book(book_id, confirmation, archive_original=False, progress=None)`     | new `progress`                                                         |
| `LibraryService.reindex_all(regenerate_summaries=False, progress=None)`                     | `progress` replaces `on_progress`, whose only callers are the tab and `reindex-all` |
| `ResetService.reset_index(confirmation, progress=None)`, `reset_everything(...)`            | new `progress`                                                         |
| `IngestionService.ingest(..., progress=None)`                                               | new `progress`                                                         |
| `IngestionPipeline.process(path, document_format, book_id, fallback_title, progress=None)`  | new `progress`                                                         |
| `DocumentLoader.load(path, stage=None)`                                                     | new `stage`, used by `PdfLoader` only                                  |
| `LibraryData.delete_book(book_id, archive, progress=None)`, `clear(keep_originals, progress=None)` | new `progress`                                                  |

A service method given no `progress` makes a `Progress()` of its own, without a sink, so its stage
lines are logged all the same (FR-015).

## Guarantees

- The same calls, in the same order, reach the catalog, the journal, the stores and the files,
  with progress or without it (FR-011, SC-004). Unit tests compare the two.
- A stage's exception is the exception the operation raises today (FR-011, SC-006).
- The progress begins inside `operation()` and inside the library lock, after the checks that
  refuse an operation (R9). A refused operation has no progress.
- Extracted text, chunks, vectors and the index's fingerprint are the same as without progress
  (FR-013).
