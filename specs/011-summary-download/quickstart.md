# Quickstart: checking the download

How to check the feature, from the unit tests to a real summary downloaded in a browser. The file's
form is in `contracts/summary-file.md`, the tab's in `contracts/summarization-tab.md`.

## 0. Before anything

- On `feat/summary-download`, with the change in the working tree: `make up` builds the image from
  it, `app/` and `config/` included, committed or not.
- The stack up (`docker compose ps`: `app`, `chromadb` and `ollama` healthy), and `gpt-oss:20b` in
  Ollama (`make pull-models`).
- A browser on the machine that serves the interface, at `http://127.0.0.1:7860`
  (`GRADIO_BIND_ADDRESS`, loopback by default). § 4 can be run by hand, or by a throwaway
  Playwright script driving the host's Google Chrome (`research.md`, R9).

## 1. Unit tests and lint (SC-005)

```bash
make lint-check
make test
```

Expected: lint is clean, and every test passes, the new ones of `research.md` R8 included.
`make test-integration` isn't needed: no prompt, parser of model output or judge changes.

## 2. Before the rebuild: the book, and `main`'s saved summary (SC-004)

`make up` will recreate the app container, which deletes the library it holds (§ 3). Copy the
book's original out first, under its original name, which is also its title:

```bash
docker compose exec app cat data/original_books/book_001/source.json   # original_filename
docker compose cp app:/app/data/original_books/book_001/original.md /tmp/02_a_era_das_revolucoes.md
```

Then keep what `main`'s `summarize --save` writes, to compare with the branch's (FR-011). Pick a
short chapter, so the summary takes a minute or two:

```bash
docker compose exec app book-rag summarize book_001 4 --type brief --save
docker compose exec app sh -c 'ls data/summaries/book_001; cat data/summaries/book_001/chapter_04_brief.json' > /tmp/main-saved.txt
```

## 3. The rebuild, and what it deletes

`make up` rebuilds the app image from the branch and recreates the app container. That deletes:
- the owner's library: `book_001`, `02_a_era_das_revolucoes`, 831 chunks, and the summary § 2 saved;
- its logs;
- the reranker's weights, which the new container downloads again on its first search.

ChromaDB and Ollama keep their data, models included. The new catalog numbers its indexes from 1
again, so `reset-everything` comes next, confirmed in the service. It deletes the library, now
empty, and every `book_chunks_v*` collection in ChromaDB. Then the book goes back:

```bash
make up
docker compose exec app book-rag reset-everything --confirm "DELETE EVERYTHING"
docker compose cp /tmp/02_a_era_das_revolucoes.md app:/tmp/
docker compose exec app book-rag add-book /tmp/02_a_era_das_revolucoes.md
docker compose exec app book-rag doctor
```

Expected: the book is `INDEXED` again as `book_001`, with 831 chunks, and `doctor` reports no
failure.

## 4. A summary downloaded in the browser (SC-001, SC-002, SC-003)

```bash
docker compose exec app sh -c 'ls -R data/summaries 2>/dev/null' > /tmp/before.txt
```

Open the interface, and in the Summarization tab:

1. Before anything, "Download the summary" is disabled, and there is no "Save the summary".
2. Pick `02_a_era_das_revolucoes`, chapter 4, `brief`, "Same as the book", the local model, and
   generate.
3. Once the summary shows, the button is available. Click it once. The browser saves
   `02-a-era-das-revolucoes_chapter_04_brief.md`, asking nothing.
4. Open the file as text. Expected (`contracts/summary-file.md`):
   - its first line is `# 02_a_era_das_revolucoes, chapter 4: <the chapter's title>`, and its
     third line `Brief summary.`;
   - its body is the summary the tab shows: copy the tab's text, or read it through
     `gradio_client`'s `/summarize`, and compare;
   - its last lines are `---`, a blank line, and ``Written by `gpt-oss:20b`, a local model.``, the
     model the tab's report names.
5. Open it in a Markdown viewer (VS Code's preview, or GitHub's). Expected: the title, the
   summary's Portuguese `##` sections, its citation numbers, its `## References` and the note under a
   rule, with no Markdown left showing as written.
6. Pick another chapter without generating, and click again: the same file comes, named after
   chapter 4 (User Story 1, scenario 7).

Then:

```bash
docker compose exec app sh -c 'ls -R data/summaries 2>/dev/null' > /tmp/after.txt
diff /tmp/before.txt /tmp/after.txt
```

Expected: no difference. Downloading wrote nothing into the library (FR-009).

Should step 3 save nothing, or an empty file, the hidden boxes' values didn't reach the JavaScript:
`research.md` R6 says what to change.

## 5. A download long after the summary (FR-004, FR-009)

The quick form: watch the page's requests while clicking "Download the summary" (the browser's
network panel, or Playwright's `page.on("request")`). Expected: the click sends no request to the
server. The file is made in the page, so nothing on the server can expire, and Gradio's sweep
(every 10 minutes, the copies older than 50) has nothing of it to delete.

The long form, optional: leave the page as § 4 left it for more than an hour, then click again.
Expected: the same file, whole.

## 6. `summarize --save` on the branch (SC-004)

```bash
docker compose exec app book-rag summarize book_001 4 --type brief --save
docker compose exec app sh -c 'ls data/summaries/book_001; cat data/summaries/book_001/chapter_04_brief.json' > /tmp/branch-saved.txt
```

Expected: the same two files as in `/tmp/main-saved.txt`, `chapter_04_brief.md` and `.json`, and
the JSON file with the same keys. Its values, such as the timings and the statements, can differ:
the model wrote the summary again.

## 7. The records

- **`README.md`**: the Summarization row and the Summaries section (FR-017).
- **`docs/decisions.md`**, Generation: the download, the browser-built file, the note (FR-018).
- **The history**: `git diff main...HEAD --name-only -- .specify specs/001-* specs/002-* specs/003-*
  specs/004-* specs/005-* specs/006-* specs/007-* specs/008-* specs/009-* specs/010-*` prints
  nothing (FR-019).

The library holds the book again since § 3, and the summary that § 6 saved. Like any saved
summary, it stays with its book until the book is removed or replaced: nothing deletes one summary
alone.
