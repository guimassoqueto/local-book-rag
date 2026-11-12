# Contract: the commands' progress

`add-book`, `replace-book`, `reindex-book`, `remove-book`, `reindex-all`, `reset-index` and
`reset-everything` pass the service a `Progress` whose sink prints `progress_text(view)` from
`app/interface/formatting.py` to the error stream, with an `interval` of 2 seconds (FR-014, R12).

## The error stream

One line per call of the sink, prefixed with the elapsed time:

```text
[0:00] Adding a book, book_003: stage 1 of 5, Storing the file
[0:00] Adding a book, book_003: stage 2 of 5, Extracting the text
[0:02] Adding a book, book_003: stage 2 of 5, Extracting the text, 31 of 244 pages
[0:04] Adding a book, book_003: stage 2 of 5, Extracting the text, 58 of 244 pages, about 18 s left
...
[0:22] Adding a book, book_003: stage 2 of 5, Extracting the text, 244 of 244 pages
[0:22] Adding a book, book_003: stage 3 of 5, Preparing the passages
[0:22] Adding a book, book_003: stage 4 of 5, Embedding the passages, 0 of 425 passages
...
[0:28] Adding a book, book_003: done
```

- A line when a stage starts; while it advances, a line with its count at most every 2 seconds;
  a line when it ends with its final count (SC-008).
- For a reindex, the book's step follows its stage: `stage 2 of 3, Indexing the books, 2 of 5
  books, Quincas Borba: step 3 of 4, Embedding the passages, 120 of 454 passages`.
- The last line says `done`, or `failed while <stage>`, and for a reindex's book `failed while
  indexing the books, at book_002, Quincas Borba, while embedding the passages`. The error itself is
  printed after it, as today (`error: <message>`, exit status 1).
- Times and counts read as in the tab (FR-002): `[0:38]`, `about 10 s left`, `0 of 0`.

## Standard output

Unchanged for six commands. `reindex-all` no longer prints its "Indexing …" and "Summarizing …"
lines there: they are on the error stream, as above. Its report, from "Index v… is active" on, is
unchanged.
