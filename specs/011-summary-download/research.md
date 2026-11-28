# Research: Download a summary as Markdown

The decisions behind `plan.md`. Each says what was chosen, why, and what else was weighed.

## R1. How a Gradio download button behaves

**Finding.** Gradio 6.32's `gr.DownloadButton` downloads the file it already holds, at the moment
it is clicked. Its frontend (`gradio/templates/frontend/assets/Index-COeDj9g0.js`) calls the click
handler, if any, and at once makes a link to `value.url` with `download` set to `value.orig_name`,
and clicks it, without waiting for the handler. A handler that returns a new file only takes effect
on the next click. So the file has to exist on the server, as the button's value, before the click:
the tab would write it when the summary is generated.

Such a file is moved into Gradio's cache (`Block.move_resource_to_block_cache`), and the app sweeps
that cache: `delete_cache=(600, 3000)` removes the copies older than 50 minutes every 10 minutes
(`app/interface/gradio_app.py`, `docs/decisions.md`, Infrastructure). A summary generated, read in
the tab for an hour, then downloaded, would point at a deleted file: the browser reports a failed
download, and nothing in the tab says why. FR-004 forbids that.

## R2. The file is built in the browser

**Decision.** The service builds the file's name and text (R3) when the summary is generated. The tab
holds both in two hidden text boxes, and the button is a plain `gr.Button` whose click runs a few
lines of JavaScript, with no Python function: they make a `Blob` of the text, typed
`text/markdown;charset=utf-8`, and click a link to it named after the file, as Gradio's own
download button does with its file's URL.

**Rationale.**
- **It works however late** (FR-004): the text stays in the page for as long as the tab shows its
  summary. Nothing on the server can expire.
- **Nothing is written on the server** (FR-009, FR-010): no file in `data/`, none in Gradio's cache,
  none in `/tmp`. The click doesn't even reach the server, so it can't call a model or contact a
  provider.
- **Each browser tab downloads its own summary**: the hidden values are that page's.
- **What the tab already shows** is what is downloaded: the hidden values change only when a
  generation succeeds, with the summary text the tab shows, and a generation that fails leaves
  both as they were (the edge cases).
- **The rules stay in the service** (Principle IV): the JavaScript only turns a text it is given
  into a file under the name it is given. It decides nothing.

**Alternatives considered.**
- **`gr.DownloadButton`, its file written at generation** (R1): fails after 50 minutes.
- **The same, refreshed by its own click handler**: the click that finds the file swept still
  fails, and only the next one works.
- **A longer cache sweep, or `keep_in_cache`**: the sweep also removes uploaded books, which can be
  large (`docs/decisions.md`, Infrastructure), and a file kept in the cache stays until the
  container is recreated, so downloads would pile up (FR-010).
- **A timer that touches the cached file**: a request every few minutes from every open page, and a
  background tab's timers are slowed by the browser, so the file can still expire.
- **A route of the app's own that builds the file on request**: the summary lives in the page's
  session, which a route outside Gradio's events can't read without a server-side store of every
  summary generated.

## R3. Where the file is built: `ChapterSummarizer.summary_file`

**Decision.** A new method, `ChapterSummarizer.summary_file(summary) -> SummaryFile`, in
`app/generation/summarization.py`, returns the file's name and its text. `SummaryFile` is a frozen
dataclass with two fields, `name` and `text`, next to `ChapterSummary`.

**Rationale.** `ChapterSummarizer` is the summaries' service: the container exposes it as
`container.summaries`, and the tab and `book-rag summarize` already call its `summarize`, `save`
and `summary_types`. It holds `ModelChoices`, which the note needs to tell a local model from a
cloud one and to name the cloud provider (`is_cloud_provider`, `label_of`), as `save` and
`summary_report` already do. The method reads only the summary it is given: no catalog, no chunk,
no model, no file (FR-009).

**Alternatives considered.** A function in `app/interface/formatting.py`, next to
`summary_report`: that would put the file's rules in the interface, against Principle IV and the
input. A new service in `app/services`: it would wrap one method of `ChapterSummarizer`, which the
rest of the summary code already treats as the service.

## R4. The file's text

**Decision.** In this order, separated by one blank line:

1. **The title**: `# <book title>, chapter <number>: <chapter title>`, or
   `# <book title>, chapter <number>` when the chapter has no title (FR-005).
2. **The type line**: the summary type, capitalized, then `summary`, then `, in <language>` when a
   language was asked for, and a full stop: `Standard summary.`,
   `Comprehensive summary, in Portuguese.`
3. **The summary**: `summary.text`, its leading and trailing whitespace removed, and nothing else
   changed: its sections, its citation numbers and its `## References` section (FR-006).
4. **The rule**: `---`.
5. **The note**: ``Written by `<model>`, a local model.`` for the local provider, and
   ``Written by `<model>`, a cloud model from <label>.`` for a cloud one, where `<label>` is the
   provider's label (`Anthropic`, `OpenAI`). `<model>` is `summary.model`, as its provider reported
   it (FR-007).

The file ends with a newline.

**Rationale.**
- **A level-one title** sits above the summary's own sections, which the prompt asks for as `##`
  headings (`app/generation/prompts.py`), and above the `## References` heading the app adds.
- **The titles go in as they are**, without escaping Markdown's characters. They are the catalog's,
  as the tab's dropdowns show them, and a title taken from a file name, such as
  `02_a_era_das_revolucoes`, renders as written: CommonMark doesn't read an underscore between
  letters as emphasis. Escaping would make the file harder to read as text, for titles that hold
  `*` or `` ` ``, which no book in the library has.
- **The rule and the closing line** read as a footnote in every Markdown viewer, and as text where
  none is used. Markdown's footnote syntax (`[^1]`) needs a marker in the text, and some viewers show
  it as written (spec, Assumptions). The blank line before the rule keeps a `---` under the
  references from turning the last line into a heading.
- **Only the model that wrote it** is named: a summary is written by one model, which starts again
  from the first step when another fails (`docs/decisions.md`, Cloud models), so the models that
  failed wrote none of it.
- **Labels in English**, as the interface and `## References` are (spec, Assumptions).

## R5. The file's name

**Decision.** `<book>_chapter_<NN>_<type>[_<language>].md`, where:

- **`<book>`** is the book's title made safe: lowercased, Unicode-normalized (NFC), and each run of
  characters that aren't letters, digits or the marks that combine with them, in any script,
  replaced by one hyphen, with no hyphen at either end. A title that leaves nothing, such as one of
  punctuation alone, gives the book's ID instead. The marks are kept because some scripts write
  vowels with them: without them, `हिन्दी` would be split into pieces.
- **`<NN>`** is the chapter's number, on two digits or more, as saved summaries are named
  (`chapter_04`).
- **`<type>`** and **`<language>`** are made safe the same way. The language is there only when one
  was asked for.
- **The length** is at most 100 characters, extension included. When the name is longer, the
  book's part is cut, at its last hyphen within what fits if it has one, and the chapter, type and
  language are kept whole (FR-008).

Example: `02-a-era-das-revolucoes_chapter_04_standard.md`,
`memórias-póstumas-de-brás-cubas_chapter_12_brief_english.md`.

**Rationale.**
- **Valid on Linux, macOS and Windows**: letters, digits, hyphens, underscores and one dot hold
  none of Windows' reserved characters (`<>:"/\|?*`), no control character, and don't end in a dot
  or a space. Windows' reserved names (`CON`, `NUL`, ...) are refused only as a whole name, and
  every name here has the `_chapter_` part after the title.
- **Letters of any script are kept**: the three systems take them, and transliterating to ASCII
  would leave a title in another script empty. NFC keeps an accented letter one character, so a
  name is the same however its title was typed.
- **Underscores separate the parts, hyphens the words**, so the parts can be read back, and the
  order groups one book's files together when sorted.
- **100 characters** leave room for the folder on every system: Windows' paths stop at 260
  characters by default, and most file systems take 255 bytes for a name. A cut title still names
  its book, and the parts after it are what tell its summaries apart.

**Alternatives considered.** The saved summaries' name, `chapter_<NN>_<type>.md`: in a downloads
folder, it doesn't say which book. The book's ID (`book_001_...`): it means nothing outside the
library, and IDs are given again after `reset-everything`.

## R6. The tab

**Decision.** In `app/interface/summarization.py`:

- **`save`**, the "Save the summary" button, becomes `download`, `gr.Button("Download the summary",
  interactive=False)`, in the same place. Two hidden boxes join it, `file_name` and `file_text`,
  `gr.Textbox(visible=False)`.
- **`current`**, the `gr.State` that held the summary for the button, is removed: nothing reads it
  any more.
- **`on_generate`** returns the report, the summary's text, the file's name and text from
  `container.summaries.summary_file(summary)`, and `gr.Button(interactive=True)`, in that order.
  The `summarize` event keeps its name and its inputs (FR-013).
- **`on_save`** and its `save_summary` event are removed (FR-001, FR-013).
- **The button's click** runs the JavaScript of R2 with `fn=None`, `inputs=[file_name, file_text]`,
  no outputs, and `api_visibility="private"`, so it isn't offered by the API, as the tab's
  `book.change` isn't.

**Rationale.** The order of `on_generate`'s outputs keeps the report and the text first, where
`gradio_client` callers of `summarize` find them today. Through the API, `summarize` now also
returns the file's name and text, which a client can write itself, and which replace what
`save_summary` gave it. Hidden boxes are the way Gradio hands a JavaScript function a value that
isn't on the screen: `gr.State` stays on the server, and a JavaScript function receives the values
of its inputs from the page.

**What could differ on the real stack.** Whether a hidden box's value reaches the JavaScript is
Gradio's frontend behavior, which the unit tests can't run. The quickstart checks it in a browser
(§ 4). Should it not, `visible="hidden"` keeps the boxes in the page, out of sight, and the plan
holds otherwise.

## R7. What doesn't change

- **`ChapterSummarizer.save`**, `SummaryDocuments`, `book-rag summarize --save` and
  `reindex-all --regenerate-summaries`: untouched, and their tests too (FR-011). A saved summary's
  Markdown file stays the summary's text alone, without the download's title and note, and its JSON
  file still says which model wrote it.
- **`summarize`**, the prompts, the citation lookup and `summary_report`: untouched (FR-012).
- **The Chat tab, the Research tab, `app/main.py`, `config/`**: untouched (FR-014).
- **Gradio's cache sweep**: untouched. Downloads don't go through the cache.

## R8. Tests

`make test`, on real files, real SQLite and fake models, as today.

- **`tests/unit/test_summarization.py`**, `summary_file`:
  - the title, the type line, the body equal to the summary's text, the rule and the note, in that
    order, for a local model;
  - the type line and the name with a language, and without;
  - a cloud model's note names its provider's label; after a failed attempt, the note names the
    model that wrote the summary and not the one that failed;
  - a summary without citations: no references section, and the rest as usual;
  - a chapter without a title;
  - names from titles holding `/ : ? "`, accents, another script, punctuation alone (the book's ID)
    and great length (at most 100 characters, the chapter, type and language kept);
  - nothing is written: the summary documents' folder stays empty, and no model is called.
- **`tests/unit/test_interface.py`**:
  - `save_summary` is gone from the API, and `summarize` is there;
  - the download button is disabled before a summary, and `summarize` enables it;
  - `summarize` returns the file's name and text as `summary_file` builds them;
  - the button's click event runs JavaScript only, with the two hidden boxes as inputs, no outputs
    and no API name;
  - summarizing through the tab saves nothing into the library;
  - the tests that unpack `summarize`'s outputs (`report, text, generated, _`) read the new five,
    and those that read the model from the summary state read it from the file's note.
- **`make test-integration`** doesn't change: no prompt, parser or judge is touched (Principle V).

## R9. Checking on the stack

The JavaScript runs only in a browser, so SC-001 and SC-002 are checked in one, on the running
stack rebuilt from the branch (`quickstart.md`), with the owner's book and the local model,
`gpt-oss:20b`. The book's original is copied out of the app container first, since `make up`
deletes the library (Principle II), and added back after the rebuild.

The browser can be driven by a throwaway script, kept in the session's scratchpad and never
committed: Playwright, run from the repository with
`uv run --no-project --with playwright python -I <script>`, which fetches it into a temporary
environment and adds nothing to `pyproject.toml` or `uv.lock`, driving the host's
Google Chrome (`chromium.launch(channel="chrome")`), so no browser is downloaded. It clicks as a
person would, reads the file the browser saves (`page.expect_download()`), and records whether the
click sends a request (`page.on("request")`). If it can't run, the owner clicks by hand.

## R10. Records

- **`README.md`**: the Summarization row of the interface table says it downloads the summary as
  Markdown. The Summaries section says what the file holds and how it is named, and that keeping a
  summary in the library is `summarize --save`'s (FR-017).
- **`docs/decisions.md`**, Generation, with the summary decisions: why the tab downloads instead of
  saving; why the file is built in the browser, and not served by a download button (R1, R2); why
  the note names the model that wrote it, and only that one; the note's form (R4) (FR-018).
- **Not edited**: `specs/001` to `specs/010`, and the bug and assessment records (FR-019).
