# Contract: the Library tab

What the owner sees and what a `gradio_client` caller gets. The tab reads input, starts a service
call, and renders what `Progress.snapshot()` returns; it computes no stage, count or time
(FR-016).

## The progress area

A `gr.HTML` under the index status, above the list of books, outside every accordion (FR-001).
Empty until the first operation, and again after the page is reloaded.

From the click until the operation's progress begins, while it runs its checks, the area shows
the operation as starting, with the moving bar: "Adding a book: starting" (FR-003). The labels are
the services' own constants, so the starting line and the stages name the operation alike.

While an operation runs, `progress_html(view)` from `app/interface/formatting.py` renders:

```text
Adding a book · book_003                                              0:12
Extracting the text — stage 2 of 5
[██████████████░░░░░░░░░░░░░░░░]  130 of 244 pages · about 10 s left
```

- The first line: the operation, its subject, and the time elapsed, as m:ss.
- The second: the stage's label and its position. For a reindex, the book's step follows on a
  line of its own, with its own position, count and time left: "Indexing the books — stage 2 of 3
  · 2 of 5 books · *Quincas Borba*", then "Embedding the passages — step 3 of 4".
- The bar: a `<progress>` with `value` and `max` when the stage, or the step, is counted; without
  `value`, the browser's moving bar, when it isn't (FR-002, Clarifications).
- The count and the time left, when there are; the stage's note, such as "with OCR".
- For a reindex, the `meanwhile` line: "Questions keep working on the current index meanwhile."
  (FR-008).

When the operation ends, the area keeps one line until the next operation starts (FR-004):

| Outcome                 | Line                                                                                     |
| ----------------------- | ---------------------------------------------------------------------------------------- |
| Added                   | "Added in 0:38. book_003: *Think Python*, with 23 chapters and 425 chunks." (today's notification, timed) |
| Replaced                | "Replaced in 0:40. book_003 is now *…*, with 425 chunks."                                |
| Processed again         | "Processed again in 0:29. book_003: 425 chunks."                                         |
| Removed                 | "Removed in 0:01. book_003 is gone; its original is in the archive." or "…its original was deleted." |
| Reindexed               | "Reindexed in 1:12. Index v4 is active: 4 books, 1313 chunks." plus the books brought back, still failing, and summaries not written, as today's notifications |
| Index reset             | "Reset in 0:01. The index is gone and the originals are kept. Reindex the library to rebuild it." |
| Everything reset        | "Reset in 0:01. The library is empty."                                                   |
| Failed                  | "Failed after 0:15, while embedding the passages: Ollama is down."                       |
| Reindex failed          | "Failed after 0:40, while indexing the books, at book_002, *Quincas Borba*, while embedding the passages: Ollama is down." (FR-004) |

The notifications of today stay, with the same text (FR-004).

A refused operation (no file, no book, a wrong confirmation, a duplicate, a busy library) leaves the
area empty, the starting line and any earlier outcome line included, and shows its error as today:
it never began (R9).

Times read as FR-002 sets them: the elapsed time as 0:38, or 1:02:05 past an hour; the time left as
"about 10 s left", rounded up to a multiple of 5 under a minute, or "about 3 min left"; "almost
done" once it has counted down to zero. An empty count reads "0 of 0" with a full bar.

## The events of each button

For each of the seven buttons, in order:

1. **disable**, `queue=False`, `api_visibility="private"`: the seven buttons, `interactive=False`,
   and the area, set to the operation's starting line. The tab's inputs stay editable (FR-005).
2. **the operation**, chained with `then`: the handler, a generator, with today's `api_name`
   (`add_book`, `replace_book`, `reindex_book`, `remove_book`, `reindex_all`, `reset_index`,
   `reset_everything`), today's inputs, `show_progress="hidden"`, and as outputs the area plus
   today's outputs (the confirmation box of the removal and the resets, which it empties on
   success).
3. **enable**, on the operation's `success` and on its `failure`, `api_visibility="private"`: the
   seven buttons, `interactive=True` (FR-005). If the walkthrough shows Gradio covering the area
   with an error state after a failure (research.md R5), the enabling event on `failure` also takes
   the area as input and sets it again, which keeps the outcome line visible.

The operation's event stays in `LibraryTab.changes`, so the list of books, the index status and
the dropdowns refresh after it, on success and on failure, as today, and not during it
(Clarifications).

## The handler

Each handler validates its input as today (a missing file or book raises `gr.Error` before
anything starts), then:

1. makes a `Progress()` without a sink and starts the service call in a daemon thread (R2, R3);
2. yields `progress_html(snapshot)` when the snapshot changed or a second has passed, polling every
   half second, until the thread ends (FR-003);
3. yields the outcome line, and the confirmation box's value where it has one;
4. if the call raised, raises it again, so `reports_errors` turns a `BookRagError` into today's
   `gr.Error`; otherwise shows today's notifications.

A `gradio_client` caller gets the same endpoints, with the same inputs. Their outputs gain the
area's final HTML, first: `add_book`, `replace_book`, `reindex_book` and `reindex_all` now return it
where they returned nothing, and `remove_book`, `reset_index` and `reset_everything` a pair, the area
and the emptied confirmation box. No caller in the repository reads them. A refused call raises, as
`tests/integration/test_interface.py` expects.

## What the tab doesn't do

- Show an operation started from another page or by a command: its buttons stay enabled, and its
  operations are refused as busy (spec, Assumptions).
- Stop an operation midway.
