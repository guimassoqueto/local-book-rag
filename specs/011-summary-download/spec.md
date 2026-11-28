# Feature Specification: Download a summary as Markdown

**Feature Branch**: `feat/summary-download`

**Created**: 2026-11-27

**Status**: Draft

**Input**: User description: "The Summarization tab's \"Save the summary\" button
(app/interface/summarization.py:38, on_save at :71-75, Gradio API name save_summary at :84) writes
the summary into the library, data/summaries/<book_id>/, through ChapterSummarizer.save
(app/generation/summarization.py:325). Replace it with a \"Download the summary\" button that gives
the browser a Markdown file of the summary just generated. The file is already formatted as the tab
shows it: a heading naming the book, the chapter and the summary type, then the summary with its
numbered citations and its references section. It ends with a footnote naming the model that wrote
it. The button stays disabled until a summary is generated, like the one it replaces. A service
method builds the Markdown, not app/interface (Principle IV). The tab no longer writes into
data/summaries/: `book-rag summarize --save` stays the way to keep a summary in the library, and
those are the summaries `reindex-all --regenerate-summaries` rewrites. The Chat tab is out of
scope: it has no save, and its answers share no code with ChapterSummary. Bead: iss-e25."

## Context

The Summarization tab summarizes one chapter of one book. Once a summary is generated, the tab
shows a report of how it was made (the chunks read, the steps, the model, and warnings such as the
statements that resemble no passage), then the summary itself. The summary is Markdown: the
sections the prompt asks for, as `##` headings ("Chapter overview", ...), in the reply's language,
with numbered citations such as `[3]`, and a `## References` section that the app adds, listing each
cited passage's section and excerpt. Its citations are computed by lookup, not claimed by the model
(Principle VII).

Under the summary, "Save the summary" writes it into the library: a Markdown file holding the
summary's text alone, and a JSON file saying how it was made, in `data/summaries/<book_id>/`
(`ChapterSummarizer.save`). `book-rag summarize --save` does the same from the command line, and
`reindex-all --regenerate-summaries` writes the saved summaries again with the local model, except
those a cloud model wrote. The Gradio API offers the button as `save_summary`.

A saved summary stays inside the app container. Nothing is kept in a volume or a host folder
(Principle II), so the file can't be opened from the owner's machine without copying it out of the
container, and it is deleted with the container, which `make up` recreates after any change to the
code or to `config/`. A download puts the summary on the owner's machine instead, where it lasts.
And a saved summary's Markdown file doesn't say which model wrote it: only its JSON file does.

What changes: the tab's button downloads a Markdown file of the summary it shows, formatted to be
read on its own, and stops writing into the library. What stays as it is: how a summary is
generated, its citations, its report, `book-rag summarize --save`, the saved summaries and their
files, and `reindex-all --regenerate-summaries`. The Chat tab is out of scope: it has nothing to
save, and its answers are made and shown by code that summaries don't share.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Download the summary the tab shows (Priority: P1)

The owner picks a book, a chapter and a summary type in the Summarization tab, and generates the
summary. Under it, "Download the summary", disabled until then, becomes available. One click, and
the browser saves a Markdown file named after the book, the chapter and the summary type. Opened
in any Markdown viewer, the file reads as a document of its own: a title naming the book and the
chapter, a line naming the summary type, the summary with its sections, its numbered citations and
its references, and, at the end, a note naming the model that wrote it.

**Why this priority**: It is the feature. Without it the summary can only be read in the tab, or
kept inside the container, where it is lost with it.

**Independent Test**: Generate a summary of a chapter of a real book on the running stack, with
the local model, and download it. Compare the file with the tab: its body is the summary the tab
shows, character for character, its title names the book and the chapter, and its closing note
names the model that the report names.

**Acceptance Scenarios**:

1. **Given** the tab before any summary is generated, **When** the owner looks at the download
   button, **Then** it is disabled.
2. **Given** a summary just generated, **When** the owner clicks "Download the summary", **Then**
   the browser saves one Markdown file, and nothing else is asked.
3. **Given** the downloaded file, **When** it is opened, **Then** it begins with a level-one heading
   naming the book's title and the chapter's number and title, followed by a line naming the
   summary type, and the language when one was asked for.
4. **Given** the downloaded file, **When** its body is compared with the summary the tab shows,
   **Then** they are the same text: its sections, its numbered citations and its references
   section, unchanged.
5. **Given** the downloaded file, **When** its end is read, **Then** a note, set apart from the
   summary, names the model that wrote it, and says whether it ran locally or which cloud provider
   ran it.
6. **Given** a summary that a fallback model wrote after the first model failed, **When** it is
   downloaded, **Then** the note names the model that wrote it, and none of those that failed.
7. **Given** a summary generated, **When** the owner then picks another book or chapter without
   generating again, **Then** the download still gives the summary the tab shows, named and titled
   after its own book and chapter.

---

### User Story 2 - Keeping a summary in the library stays with the command (Priority: P2)

The owner who wants a summary kept in the library, to be written again by
`reindex-all --regenerate-summaries`, runs `book-rag summarize <book> <chapter> --save`, which
works as it does today. The tab no longer writes into the library: downloading a summary leaves
`data/summaries/` as it was.

**Why this priority**: The tab's button is replaced, not added to, and what it did must still be
possible. It needs no new code, only that nothing else change.

**Independent Test**: List `data/summaries/` in the app container, download a summary from the tab,
and list it again: nothing was added. Run `book-rag summarize` with `--save` on the same chapter:
it writes the same two files, with the same names and the same keys in its JSON file, as on `main`.

**Acceptance Scenarios**:

1. **Given** a summary downloaded from the tab, **When** `data/summaries/` is listed, **Then** it
   holds the same files as before the download.
2. **Given** `book-rag summarize <book> <chapter> --save`, **When** it runs, **Then** it saves the
   summary's text alone and its JSON file, as on `main`, without the download's title or note.
3. **Given** the Gradio API, **When** its endpoints are listed, **Then** `save_summary` is gone, and
   `summarize` keeps its name and its inputs.

### Edge Cases

- **A generation that fails** after an earlier one succeeded leaves the earlier summary in the tab,
  and the download gives that one. The download never gives a summary other than the one the tab
  shows.
- **A summary without citations** has no references section, and the file holds the title, the
  summary and the note.
- **A summary written in another language than the book's** keeps its headings in that language.
  The file's own title line, type line and note are in English, like the `## References` heading
  the app already adds, and the type line names the language asked for.
- **A book title or a chapter title with characters that file names can't hold** (`/`, `:`, `?`,
  quotes), accented letters, or great length: the file name stays valid and within 100 characters
  (FR-008), and the title inside the file keeps the titles as they are.
- **The same chapter summarized in two types, or in two languages**: the two files get different
  names, since the name holds the type, and the language when one was asked for.
- **A chapter without a title** is named by its number alone, in the heading and in the file name.
- **A download long after the summary was generated**, beyond the hour Gradio keeps a cached file,
  still gives the file, for as long as the tab shows the summary.
- **Two browser tabs** each download the summary that their own tab shows.
- **A book removed after its summary was generated**: the download still gives the summary the tab
  shows. It reads nothing from the library.
- **A summary from a cloud model**: the note names the model and its provider. Downloading sends
  nothing to the provider: no model is called.

## Requirements *(mandatory)*

### Functional Requirements

#### The button

- **FR-001**: The Summarization tab MUST offer a "Download the summary" button where "Save the
  summary" is, and MUST NOT offer saving into the library any more.
- **FR-002**: The button MUST be disabled until a summary is generated, and available once one is,
  as the button it replaces is.
- **FR-003**: Clicking it MUST have the browser save one Markdown file, encoded in UTF-8, holding
  the summary that the tab shows at that moment, and no other.
- **FR-004**: The download MUST work however long after the summary was generated it is asked for,
  for as long as the tab shows that summary.

#### The file

- **FR-005**: The file MUST begin with a level-one heading naming the book's title and the chapter's
  number and title, or its number alone when it has no title, followed by a line naming the summary
  type, and the language when one was asked for.
- **FR-006**: The summary's text MUST follow, exactly as the tab shows it: its sections, its numbered
  citations and its references section, with nothing added, removed or reworded.
- **FR-007**: The file MUST end with a note, set apart from the summary, that names the model that
  wrote the summary, as its provider reported it, and says whether it is a local model or names its
  cloud provider. Models that failed before it MUST NOT be named: they wrote none of it.
- **FR-008**: The file's name MUST say which summary it holds: the book's title, the chapter's number
  and the summary type, and the language when one was asked for, with the `.md` extension. It MUST
  be a valid file name on Linux, macOS and Windows, of at most 100 characters with its extension,
  whatever the titles hold: a long book title is shortened, never the chapter, type or language.

#### What doesn't change

- **FR-009**: Downloading MUST call no model, contact no provider, read nothing from the library and
  write nothing into it: nothing new in `data/summaries/` or anywhere else under `data/`.
- **FR-010**: Any temporary copy that serving the file needs MUST be removed as Gradio's other
  cached copies are, within the hour and when the server shuts down, so that downloads don't pile
  up in the container.
- **FR-011**: `book-rag summarize --save`, the files it writes, `reindex-all --regenerate-summaries`
  and the summaries already saved MUST work and stay as they are.
- **FR-012**: How a summary is generated MUST NOT change: its prompts, its citations, its report and
  what the tab shows.
- **FR-013**: The Gradio API MUST no longer offer `save_summary`. `summarize` MUST keep its name and
  its inputs.
- **FR-014**: The Chat tab MUST NOT change.

#### Constraints from the constitution

- **FR-015**: The file and its name MUST be built by a service method, which the tab only calls and
  whose result it only hands to the browser (Principle IV).
- **FR-016**: The change MUST touch no prompt, no parser of model output, no judge or metric, and no
  input of the index fingerprint (Principles III, V and VI).

#### Records

- **FR-017**: `README.md` MUST say that the Summarization tab downloads the summary as a Markdown
  file, with its title and the note naming its model, and that keeping one in the library is
  `book-rag summarize --save`'s.
- **FR-018**: `docs/decisions.md` MUST record why the tab downloads instead of saving: a saved
  summary stays in the app container, lost when it is recreated and out of reach of the owner's
  machine (Principle II); why the file names its model, since a downloaded summary leaves its report
  and its JSON file behind; and the form chosen for the note.
- **FR-019**: The history MUST NOT be edited: the delivered specs, `specs/001` to `specs/010`, and
  the bug and assessment records (Principle VIII).

### Key Entities

- **Chapter summary**: a summary as the tab holds it once generated: its book and chapter, their
  titles, its type, the language asked for, its text with its references, and the model that wrote
  it with its provider. The download is made from it alone.
- **Downloaded summary**: a Markdown file on the owner's machine: a title, a type line, the
  summary's text, and a closing note naming the model. It is never written into the library.
- **Saved summary**: a summary kept in the library by `book-rag summarize --save`: its text alone in
  a Markdown file, and a JSON file saying how it was made. Unchanged by this feature.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: On the running stack, with a real book and the local model, a summary generated in the
  tab is downloaded in one click, and the file's body, between its type line and its note, equals
  the summary the tab shows, character for character. Its title names the book and the chapter, and
  its note names the model that the tab's report names.
- **SC-002**: The file from SC-001, opened in a common Markdown viewer, shows the title, every
  section of the summary, its citation numbers, its references and the note, with no Markdown left
  unrendered.
- **SC-003**: `data/summaries/` in the app container holds the same files before and after SC-001's
  download.
- **SC-004**: `book-rag summarize --save` on the same chapter writes the same two files as on `main`,
  with the same names and the same keys in the JSON file.
- **SC-005**: `make lint-check` is clean and `make test` passes, with unit tests for: the button
  disabled before a summary and available after; the title, the type line with and without a
  language, the body equal to the summary's text, and the note, for a local and a cloud model and
  after a failed attempt; a summary without citations; a chapter without a title; file names from
  titles holding unsafe characters, accents and great length; nothing written into the library;
  and `save_summary` gone from the API.

## Assumptions

- **The note is a closing line after a horizontal rule**, not Markdown's footnote syntax (`[^1]`),
  which some viewers show as written and which would need a marker in the text. It reads as a
  footnote wherever the file is opened, for example:

  ```markdown
  # <Book title>, chapter 4: <chapter title>

  Standard summary, in Portuguese.

  ## <the summary's sections, as the tab shows them>

  ## References

  - [1] <section>: “<excerpt>”

  ---

  Written by `<model>`, a local model.
  ```

- **The report stays in the tab.** The file holds the summary and the model, as asked: not the
  chunks read, the steps, the timings, the tokens or the warnings. A statement that resembles no
  passage is still visible in the file as one without a citation number.
- **No date in the file**: a summary doesn't record when it was generated, and the browser records
  when the file was saved.
- **The file's own labels are in English**, as the app's interface and the `## References` heading
  are, whatever language the summary is in.
- **The command line gets no download**: it prints the summary, and `--save` keeps it in the
  library, as today.
- **Nothing to measure** (Principle VI): the change claims no gain in quality or speed and changes no
  default, so it needs no benchmark. It touches no prompt, parser of model output or judge, so it
  needs no run of the models beyond SC-001's check (Principle V), and the extra steps that
  `AGENTS.md` asks of such changes, clarify, checklist and analyze, don't apply.
- **SC-001 needs the stack rebuilt from this branch**: `make up` recreates the app container after
  the code change, which deletes the library it holds, so the book has to be added again before the
  check (Principle II).
- **The release**: a feature, so the pull request is titled `feat:`, and its merge makes a minor
  release, v0.11.0 unless another release comes first.

## Results of the implementation, 2026-11-27

The change is in the working tree of `feat/summary-download`, on `main` at `b85b4cc`. The stack was
rebuilt from it with `make up`, reset with `reset-everything`, and the owner's book,
`02_a_era_das_revolucoes`, added back from its original (the same checksum, `98ca96bc…`): 31
chapters, 831 chunks. Every check used chapter 6, "Prefácio", a `brief` summary, and the local
model, `gpt-oss:20b`.

- **SC-001: pass.** A throwaway Playwright script drove the host's Google Chrome. Before the
  summary, "Download the summary" was disabled, and no "Save the summary" existed. After it, one
  click saved `02-a-era-das-revolucoes_chapter_06_brief.md`. Its first line is
  `# 02_a_era_das_revolucoes, chapter 6: Prefácio`, its third `Brief summary.`, and its last
  ``Written by `gpt-oss:20b`, a local model.``, after a rule: the model the tab's report names. Its
  seven Portuguese sections and its two references appear in the tab's text, in the same order.
  Read by hand, its body is the summary the tab showed. A second click, with another chapter picked
  and nothing generated, gave the same name and the same bytes.
- **SC-002: pass.** Rendered as CommonMark (`markdown_it`), the file has one `h1`, the seven sections
  and `References` as `h2`, one `hr` before the last paragraph, the model in a `code` element, and
  no `# `, `---`, `[^`, `**` or backtick left in its text. The book's title, with its underscores,
  renders as written.
- **SC-003: pass.** `ls -R data/summaries` gave the same listing before and after the download: no
  summary saved. The click sent no request to the server, which is why the download can't expire
  (FR-004, FR-009): the long form of the check, an hour's wait, wasn't run.
- **SC-004: pass.** `book-rag summarize book_001 6 --type brief --save` wrote
  `chapter_06_brief.md` and `chapter_06_brief.json` on `main`'s container and on the branch's, with
  the same 15 keys in the JSON file. The saved Markdown is still the summary's text alone.
- **SC-005: pass.** `make lint-check` is clean. `make test` ran 1344 unit tests before the change,
  and 1363 after.

### Corrections during implementation

- **Chapter 6, not 4.** quickstart.md and tasks.md T002 proposed chapter 4, which in this book is
  the list of illustrations, with nothing to summarize. Chapter 6, the preface, was used for every
  check.
- **Combining marks stay in a name.** contracts/summary-file.md first made a name of
  alphanumeric characters (`str.isalnum`) alone, which would cut words of scripts that write vowels
  as marks, such as Devanagari's, into pieces. The marks are kept now, and a test covers
  `हिन्दी साहित्य`. The contract, research.md R5 and data-model.md say so.
- **A third test file.** `tests/unit/test_provider_kinds.py` unpacked `summarize`'s four outputs
  too, which research.md R8 and plan.md's Project Structure didn't list. It reads the five now, and
  the model from the file's note. plan.md and tasks.md T020 list it.
- **Events without a Python function.** The download's event runs JavaScript alone, so its `fn` is
  `None`, and five lookups in `tests/unit/test_interface.py` that read `fn.fn.__name__` broke on it,
  or would have had the events come in another order. They go through a helper, `handler_name`,
  which gives `None` for such an event.
- **The Playwright command** needs `--no-project`, and has to run from the repository, where asdf
  finds uv's version. research.md R9 and tasks.md T014 say so.
