# Quickstart: checking Markdown-only books

How to show the feature works: on fakes first, then on the real stack with the converted books.
The order matters. The runs on `main`'s code (§ 3) must happen before this branch's first
`make up` (§ 4): that rebuild replaces `main`'s image and empties the library. What each step must
show comes from the spec's success criteria, and the contracts hold the details.

## 0. Before anything

The Bash tool and a fresh shell need asdf's paths for `uv` and `make`:

```bash
export ASDF_DATA_DIR="$HOME/.asdf" PATH="$HOME/.asdf/shims:$HOME/.asdf:$PATH"
```

The uncommitted dependency bump (`.pre-commit-config.yaml`, `uv.lock`) stays stashed for the
whole feature (`research.md`, R10). `git status --short` shows neither file as modified, and
`git stash list` shows it under "chore: commitizen 4.19.4 + uv.lock".

## 1. Unit tests and lint

```bash
make lint-check
make test
```

Expected:
- **Lint** is clean, and every unit test passes.
- **Refusals** (`tests/unit/test_validation.py`, `test_book_service.py`): `.pdf` and `.epub`
  refused with the convert-first message, other types with the accepted list, uppercase `.MD`
  accepted. Nothing is stored or journaled for a refused file, in an addition or a replacement.
- **The title** (`test_markdown_loader.py`, `test_pipeline.py`): the file's stem in every case.
  Front matter `title` and `author` and a single H1 are ignored, and `language` and `lang` are
  still read.
- **The configuration** (`test_config.py`): `pdf`, `normalization` and
  `chunking.preserve.page_numbers` each stop loading, and the error names the key.
- **The fingerprint** (`test_index_service.py`): it moves with `METADATA_SCHEMA_VERSION` 2.
- **The tab** (`test_interface.py`): each picker's preprocessing refuses `book.pdf`.
- **Markdown chunking**: the tests that check chunk texts and chapters keep `main`'s expected
  values.

None of the remaining tests writes a PDF or an EPUB (SC-006, User Story 2 scenario 3):

```bash
git grep -n -i -E 'write_pdf|write_epub|pymupdf|ebooklib|docling' -- tests devtools app   # nothing
```

## 2. The gate: the converted books

Before § 3, the owner puts these in `benchmarks/books` on the host:
- the three dataset books, converted with their MarkItDown setup, named as they name their books;
- `01_historia_economica_global.md`.

They also give the conversion record: MarkItDown's version and the plugins. Nothing in § 1 needs
them. Everything from § 3 on does.

## 3. On `main`'s code, before the rebuild

The image running on 2026-11-19 has `main`'s code but the stashed bump's lock (`research.md`,
R10). So it is rebuilt from this branch before any change under `app/`, while its `app/`,
`config/`, `pyproject.toml` and `uv.lock` are still `main`'s
(`git diff main --stat -- app config pyproject.toml uv.lock` is empty). That **deletes the
library the app container holds**, today `book_001`, which the owner allows. Old collections are
cleared by `reset-everything`, as after any rebuild:

```bash
make up
docker compose exec app book-rag reset-everything --confirm "DELETE EVERYTHING"
docker image ls local-book-rag-app --format '{{.Size}}'          # main's image size, for SC-004
```

Nothing is mounted, so the running container keeps `main`'s code whatever the host's files
become. Only the next `make up` changes it. So this rebuild comes first, the code changes go on
meanwhile, and the runs below wait for the converted books (§ 2), as long as no `make up` comes
between:

```bash
# The run on the original books, in a fresh workspace (FR-020).
stage=$(mktemp -d) && mkdir -p "$stage/benchmarks/results" "$stage/benchmarks/experiments"
cp -r benchmarks/datasets "$stage/benchmarks/"                   # main's dataset, unchanged
cp -r benchmarks/books "$stage/benchmarks/"                      # the originals and the Markdown
cp benchmarks/experiments/markdown_books.yaml "$stage/benchmarks/experiments/"
docker compose exec app rm -rf /app/benchmarks/workspace
docker compose cp -a "$stage/benchmarks" app:/app/              # /app is root's: -a keeps ownership
docker compose exec app book-rag benchmark benchmarks/experiments/markdown_books.yaml --commit "$(git rev-parse --short main)"

# The chunks on main's code (SC-002).
docker compose exec app mkdir -p /tmp/devtools
docker compose cp devtools/dump_chunks.py app:/tmp/devtools/
docker compose exec -w /app app sh -c 'python -I /tmp/devtools/dump_chunks.py --out /tmp/chunks-main /app/benchmarks/books/*.md'
docker compose cp app:/tmp/chunks-main benchmarks/results/
docker compose cp app:/app/benchmarks/results benchmarks/
```

This touches only `benchmarks/workspace` and the `bench_*` collections. `dump_chunks.py` calls
the pipeline alone (principle II). Expected:
- **The run on the originals.** `benchmarks/results/markdown_books_<time>/` holds 75 rows, one per
  answerable question. Its environment records `main`'s commit and the original books' checksums.
- **The chunk dumps.** `benchmarks/results/chunks-main/` holds one JSON file per Markdown book.

## 4. Rebuild with this branch

`make up` recreates the app container from this branch, which **deletes the library it holds**:
the owner's books, today `book_001`. The originals are on the host, to add again. ChromaDB and
Ollama keep their data. ChromaDB still holds the old `book_chunks_v*` collections, so the first
command clears them (`docs/decisions.md`, Infrastructure):

```bash
make up
docker compose exec app book-rag reset-everything --confirm "DELETE EVERYTHING"
docker compose exec app book-rag doctor
```

Expected: `doctor` reports no failure (SC-006). Its GPU line names only the reranker (FR-012).

SC-004:

```bash
docker image ls local-book-rag-app --format '{{.Size}}'          # smaller than § 3's
docker compose exec app python -c "import importlib.metadata as m
for name in ('docling', 'pymupdf', 'ebooklib', 'torchvision', 'pypdfium2', 'rapidocr'):
    try: print(name, m.version(name))
    except m.PackageNotFoundError: print(name, 'absent')"
```

Expected: every package absent, and the image smaller. Both sizes go into the results (SC-004).

The removed settings (User Story 2, scenario 2), one at a time, on a copy of the configuration:

```bash
docker compose exec app sh -c 'rm -rf /tmp/cfg && cp -r /app/config /tmp/cfg && printf "\npdf:\n  extractor: pymupdf\n" >> /tmp/cfg/ingestion.yaml && CONFIG_DIR=/tmp/cfg book-rag list-books'
```

Expected: it stops, and the error names `pdf`. The same goes for a `normalization:` section and
for `page_numbers: true` under `chunking.preserve`.

## 5. The chunks on this branch's code (SC-002)

```bash
stage=$(mktemp -d) && mkdir -p "$stage/books" && cp benchmarks/books/*.md "$stage/books/"
docker compose cp -a "$stage/books" app:/tmp/                                # the same Markdown files
docker compose exec app mkdir -p /tmp/devtools
docker compose cp devtools/dump_chunks.py app:/tmp/devtools/
docker compose exec -w /app app sh -c 'python -I /tmp/devtools/dump_chunks.py --out /tmp/chunks-branch /tmp/books/*.md'
docker compose cp app:/tmp/chunks-branch benchmarks/results/
for f in benchmarks/results/chunks-main/*.json; do cmp "$f" "benchmarks/results/chunks-branch/$(basename "$f")" || echo "DIFFERS: $f"; done
```

Expected: no "DIFFERS" line. One would fail SC-002: `diff` the two files to see where.

## 6. Adding books, and refusing PDFs and EPUBs

In the browser, on the Library tab:
1. **The pickers.** Open each one: the dialog offers only `.md` and `.markdown`. The note under
   "Add a book" says that books are Markdown and how to convert one.
2. **Adding.** Add each of the three converted books and the História Markdown. Each is indexed,
   titled with its file name, with an empty author. The Summaries tab lists each one's chapters,
   which match its Markdown headings when read against the file (SC-001).
3. **Refusals in the tab.** Drop `think-python.pdf` on "Add a book", and `on-liberty.epub` on
   "Change a book" with a book chosen. Each is refused at once, by Gradio's message naming the
   accepted types (`research.md`, R3), and the book list doesn't change.

From the commands, where the file keeps its name on the way in (`contracts/books.md`):

```bash
docker compose cp benchmarks/books/think-python.pdf app:/tmp/
docker compose cp benchmarks/books/on-liberty.epub app:/tmp/
docker compose exec app book-rag add-book /tmp/think-python.pdf               # refused: PDF, convert first
docker compose exec app book-rag replace-book book_001 /tmp/on-liberty.epub   # refused: EPUB, convert first
docker compose exec app book-rag list-books                                   # as before both
```

Expected (SC-003):
- each refusal comes within a second;
- `list-books` shows the same books, revisions and statuses;
- the log shows no operation started for either.

## 7. The benchmark on the Markdown books

On the host, the dataset becomes the Markdown one (`contracts/benchmark.md`, `data-model.md`):
`books.yaml` gets the new schema, the Markdown files' names and checksums, and the originals'
URLs, checksums and the conversion. Then:

```bash
stage=$(mktemp -d) && mkdir -p "$stage/benchmarks/results" "$stage/benchmarks/books"
cp -r benchmarks/datasets benchmarks/experiments "$stage/benchmarks/"
cp benchmarks/books/*.md "$stage/benchmarks/books/"
docker compose cp -a "$stage/benchmarks" app:/app/       # the container from § 4 has no benchmarks/ yet
docker compose exec app book-rag validate-benchmark
```

Expected at first: the quotes and chapter names the conversion changed. Each is corrected in
`benchmarks/datasets` on the host, and the folder is copied in again with
`docker compose cp -a benchmarks/datasets app:/app/benchmarks/`, then validated until nothing is
listed. No question is removed (FR-019). Then:

```bash
docker compose exec app book-rag fetch-benchmark-books        # refused: unknown command
docker compose exec app rm -rf /app/benchmarks/workspace
docker compose exec app book-rag benchmark benchmarks/experiments/markdown_books.yaml --commit "$(git describe --always --dirty)"
docker compose cp app:/app/benchmarks/results benchmarks/
uv run python devtools/compare_runs.py benchmarks/results/markdown_books_<main> benchmarks/results/markdown_books_<branch> --labels originals markdown
```

Expected (SC-007): `validate-benchmark` passes with 75 answerable questions. The comparison shows
each metric's paired difference with its interval, and the questions that moved. The questions
behind any difference whose interval leaves zero out are read in both runs' `rows.csv` before
`docs/benchmark-results.md` names it.

An `extraction` experiment is refused when it loads, naming the allowed kinds (FR-017).

Once it validates, the dataset and the experiments are recorded in
`specs/005-markdown-only/benchmarks/`, if the owner confirms `research.md` R19.

## 8. Real models (SC-006, SC-008)

```bash
make test-integration
```

Expected: it passes as on `main`. Then read, on a Markdown book:
- an answer in the Chat tab, with its sources and passages, and its scores table without "Pages";
- `book-rag ask` and `book-rag search`, which has no `--page-start`;
- a saved summary's references;
- a quiz's passage pointers.

No page appears anywhere, and every citation reads as book, chapter and section (SC-008).

## 9. What the repository still says (SC-005)

```bash
git grep -n -i -E '\b(pdfs?|epubs?|ocr|docling|pymupdf|ebooklib)\b' -- . \
  ':!docs/decisions.md' ':!docs/benchmark-results.md' ':!specs/' \
  ':!.specify/memory/constitution.md' ':!.specify/bugs/' ':!.specify/assessments/' ':!uv.lock'
```

Expected: only lines that say books are converted to Markdown outside the application, or that
PDF and EPUB are refused: the refusal messages and their tests, the README, the tab's note and
the commands' help. Excluded, as history: the decisions, the results, specs, the constitution's
Why sections, and the bug and assessment records (Corrections during planning). `uv.lock` is
checked apart: `git grep -n -i -E 'docling|pymupdf|ebooklib|pypdfium|rapidocr' uv.lock` finds
nothing.
