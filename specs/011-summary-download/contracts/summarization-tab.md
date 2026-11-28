# Contract: the Summarization tab and its API

What the tab shows, what its events do, and what the Gradio API offers. `research.md` R2 and R6 give
the reasons.

## The tab

| Element                  | Before                                   | After                                                     |
| ------------------------ | ---------------------------------------- | --------------------------------------------------------- |
| Book, chapter, type, language, model choice, "Generate the summary" | as today | unchanged                              |
| The report and the summary | as today                               | unchanged                                                 |
| The button under the summary | "Save the summary", disabled until a summary | "Download the summary", disabled until a summary |
| What the button does     | writes `data/summaries/<book_id>/chapter_<NN>_<type>.md` and `.json`, and says where | the browser saves `SummaryFile.name`, holding `SummaryFile.text`; nothing is said, nothing is written on the server |
| Hidden values            | `current`, the `ChapterSummary` (server state) | `file_name`, `file_text` (in the page)              |

## Events

| Event                         | Inputs                                                       | Outputs                                                        | API name      |
| ----------------------------- | ------------------------------------------------------------ | -------------------------------------------------------------- | ------------- |
| book changes                  | book                                                         | chapter                                                        | private, unchanged |
| "Generate the summary" click  | book, chapter, type, language, model, fallbacks: unchanged   | report, summary text, `file_name`, `file_text`, the button enabled | `summarize`, unchanged |
| "Download the summary" click  | `file_name`, `file_text`                                     | none: JavaScript only (`fn=None`)                              | private       |
| "Save the summary" click      | removed                                                      | removed                                                        | `save_summary` removed |

- **A failed generation** raises, as today, and updates none of its outputs, so the button and the
  hidden values keep the previous summary's, matching the summary still shown.
- **The download click** makes a `Blob` of `file_text`, typed `text/markdown;charset=utf-8`, links
  to it with `download` set to `file_name`, clicks the link, removes it, and revokes the URL. It
  sends nothing to the server.

## Through `gradio_client`

- **`/summarize`**: the same inputs. Its outputs lose the summary's server state and gain the
  file's name and the file's text, after the report and the summary's text.
- **`/save_summary`**: gone. A client that kept summaries in the library through it runs
  `book-rag summarize --save` instead, or writes the file's text that `/summarize` returns.

## Unchanged

- **`book-rag summarize`**, with and without `--save`, and `reindex-all --regenerate-summaries`.
- **Every other tab and event**, and the API names `test_every_primary_operation_is_reachable`
  lists, but `save_summary`.
