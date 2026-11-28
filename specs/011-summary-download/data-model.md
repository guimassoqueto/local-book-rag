# Data model: Download a summary as Markdown

No stored data changes. The feature adds one value, built from a summary and never kept on the
server.

## `SummaryFile` (new)

A frozen dataclass in `app/generation/summarization.py`, next to `ChapterSummary`, returned by
`ChapterSummarizer.summary_file(summary)`.

| Field  | Type  | What it holds                                                               |
| ------ | ----- | --------------------------------------------------------------------------- |
| `name` | `str` | The file's name, with `.md`: `contracts/summary-file.md`, The name (R5)     |
| `text` | `str` | The file's Markdown, ending with a newline: `contracts/summary-file.md` (R4) |

**Built from** these fields of the `ChapterSummary`, and nothing else:

| `ChapterSummary` field | Used for                                                 |
| ---------------------- | -------------------------------------------------------- |
| `book_title`           | the title, and the name's first part                     |
| `book_id`              | the name's first part, when the title leaves nothing     |
| `chapter_number`       | the title, and the name's `chapter_<NN>`                 |
| `chapter_title`        | the title, left out when empty                           |
| `summary_type`         | the type line, and the name                              |
| `language`             | the type line, and the name, when one was asked for      |
| `text`                 | the body, its surrounding whitespace removed             |
| `model`                | the note                                                 |
| `provider`             | the note: local, or a cloud model from its label         |

The other fields (the chunks, the steps, the statements, the verification, the timings, the
attempts and the tokens) stay in the tab's report and in a saved summary's JSON file.

**Rules.**
- `text` begins with `# ` and holds `summary.text.strip()` once, unchanged (FR-005, FR-006).
- `text` ends with `\n\n---\n\nWritten by ` and the note, then a newline (FR-007).
- `name` ends with `.md`, is at most 100 characters, holds only letters, digits, combining marks,
  `-`, `_` and the one `.`, and holds the chapter, type and language parts whole (FR-008).
- Building it reads nothing and writes nothing: no catalog, no chunk, no model, no file (FR-009).

## The Summarization tab's values

| Value                  | Before                          | After                                                  |
| ---------------------- | ------------------------------- | ------------------------------------------------------ |
| `current` (`gr.State`) | the `ChapterSummary`, for Save  | removed                                                |
| `file_name` (hidden)   | none                            | `SummaryFile.name` of the summary the tab shows        |
| `file_text` (hidden)   | none                            | `SummaryFile.text` of the summary the tab shows        |
| the button             | "Save the summary", disabled    | "Download the summary", disabled until a summary       |

The hidden values change only when a generation succeeds, together with the summary text the tab
shows. A failed generation leaves all of them as they were.

## Unchanged

- **`ChapterSummary`**: its fields and how `summarize` fills them.
- **Saved summaries**: `data/summaries/<book_id>/chapter_<NN>_<type>.md`, the summary's text alone,
  and its `.json` file, written by `ChapterSummarizer.save` for `book-rag summarize --save` only.
- **The catalog, the index, ChromaDB, `config/`**: untouched.
