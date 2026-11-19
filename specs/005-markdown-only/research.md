# Research: Markdown-only books

The decisions behind `plan.md`, each with what was chosen, why, and what else was considered. The
code they rest on was read on `main` at `6b187f0` on 2026-11-19, and the running stack was
inspected the same day.

## R1. Where a book's title comes from

**Decision.** The pipeline takes the book's title as an argument, and nothing it reads can change
it. `IngestionPipeline.process(path, document_format, book_id, title, progress)` keeps its order
and renames `fallback_title` to `title`. Its callers already pass the stem of the name the file
arrived as:
- `BookService._ingest` and `_index_revision` pass `Path(book.original_filename).stem`.
- `LibraryService` passes the same when it reindexes a book or brings an original back.

So the title is the stem on every path, adding, replacing, processing again and reindexing, as
FR-005 asks. The Markdown loader stops reading `title` and `author` from the front matter, and
drops `_single_top_heading`. Since nothing reads either any more, the fields go too:
- `ExtractedDocument` keeps `format`, `blocks` and `language`.
- `BookStructure` loses `author`, and keeps `title`, which names the single chapter of a book
  without headings. `build_structure(document, title)` takes it as an argument. Since a title is
  always given, `_WHOLE_BOOK_TITLE` ("Full text") goes. On `main` the pipeline already always
  passed one, so no book ever got that chapter title (Corrections during planning).
- `ProcessedDocument` loses `author`.

`BookService` writes no author to the catalog, which keeps the column, and the Library tab keeps
its Author column, empty. `QuizSource.author` and the quiz prompts' ", by …" stay: they already
handle a missing author, and a later feature may fill it (Clarifications).

**Rationale.** The owner's conversions have no front matter, and their sample's 15 top-level
headings name no title, so today they are already titled after their file names (spec, Context).
Making the file name the only source means the owner controls the title by naming the file, which
is how they already name their books (`01_historia_economica_global.md`). Fields that nothing
fills would read as if something did.

**Alternatives considered.**
- *Keep reading a front-matter title when there is one.* The owner ruled it out (Clarifications).
- *Keep the fields and leave them empty.* That leaves code that seems to read a title and never
  does.
- *Reformat the stem* (`01 Historia economica global`). FR-005 says "as given and not reformatted".

## R2. Refusing a PDF or an EPUB

**Decision.** `validate_upload` (`app/ingestion/validation.py`) knows two extensions, `.md` and
`.markdown`, compared without case. Two more get a message of their own:
- `.pdf`: "This is a PDF. Books are Markdown files: convert it to Markdown first, with MarkItDown
  for example, and add the .md file."
- `.epub`: the same, saying it is an EPUB.

Any other extension keeps today's message, naming the accepted types: "Unsupported file type
'.docx'. Books are Markdown files: .markdown, .md." The Markdown checks don't change: empty, over
the limit, binary data, not UTF-8. `_require_pdf`, `_require_epub` and their constants go.

The check stays where it is today, in `BookService._read_upload`. That is the first thing
`add_book` and `replace_book` do inside the library lock, before the duplicate check, the index
check, the journal entry and storing. So a refused file leaves the catalog, the journal, the
index and the files as they were (SC-003), and the book being replaced keeps its revision.

**Rationale.** One place refuses, for the tab and the commands alike (principle IV). The
extension is enough: a PDF or EPUB renamed `.md` is refused by the binary and UTF-8 checks, as
today (edge cases).

**Alternatives considered.**
- *Sniffing the content* for `%PDF-` or a ZIP header in a `.md`. The binary check already refuses
  both, and a second message for them adds nothing.
- *Refusing in the tab and the commands.* Two copies of the rule (principle IV).

## R3. The tab's pickers, and Gradio's own type check

**Decision.** Both pickers keep `file_types`, now `[".md", ".markdown"]`, so the browser's dialog
offers only Markdown files (FR-004). Their label reads "Markdown book (.md, .markdown)", and a line
under "Add a book" says that books are Markdown files and that a PDF or EPUB is converted first.
The line names MarkItDown as an example, and says the file's name becomes the book's title.

A PDF can still reach the tab, dropped on the picker or chosen with the dialog's "all files".
Gradio then refuses it itself, before the handler runs. `gr.File` with `type="filepath"` checks
`file_types` in its preprocessing (`gradio/components/file.py`, `_process_single_file`) and raises
"Invalid file type. Please upload a file that is one of these formats: ['.md', '.markdown']". So
in the tab the message is Gradio's, not the service's, and the line under the heading carries the
advice to convert. The commands, and anything else that reaches the service, get the service's
message. Nothing is stored either way.

This departs from FR-002's wording for the tab, so the spec gets a correction (Corrections during
planning). A unit test checks that each picker's preprocessing refuses `book.pdf`, so a Gradio
upgrade that dropped the check would show. The quickstart drops a PDF on the picker in the browser
to see which message the owner gets.

**Alternatives considered.**
- *No `file_types`, so the service's message always shows.* FR-004 asks the dialog to offer only
  Markdown, and the label alone wouldn't do that.
- *`type="binary"`, which Gradio doesn't type-check.* The handler would lose the file's name,
  which is now the book's title.

## R4. What stays format-neutral

**Decision.** `DocumentFormat` keeps one member, `MARKDOWN`. Some code keeps using it, unchanged:
- the catalog's `format` column;
- `OriginalDocuments`' map from format to extension;
- the `DocumentLoader` protocol and the pipeline's map of loaders, with one entry.

Only the PDF and EPUB members, loaders and extensions go. `DocumentLoader.load(path)` loses its
`stage` parameter, which only the PDF loader used to count pages (R8).

**Rationale.**
- **No catalog migration.** The catalog's schema and the originals' layout don't change, so
  recovery, `reindex-all` and the stored `source.json` records stay as they are.
- **One call works on both versions of the code.** `pipeline.process(path, format, "book", stem)`
  means the same on `main` and on this branch. The chunk dump of R12 needs that, because it runs on
  both.
- **A later format slots in where the others were.**

**Alternatives considered.** *Removing the format everywhere*: a catalog column, its migration
and every caller, for no change anyone sees.

## R5. Pages, removed

**Decision.** Pages go from every place FR-014 lists:

| Where | What changes |
| ----- | ------------ |
| `Block` (`app/ingestion/base.py`) | loses `page_start`, `page_end` and `margin` |
| `Chunk` (`app/ingestion/chunker.py`) | loses `page_start` and `page_end`. The ChromaDB metadata follows, since `app/storage/chroma.py` stores every field but the text |
| `Chunker` | stops collecting pages. `ChunkPreservation` loses `page_numbers` |
| `Normalizer` | loses `_merge_across_pages`, which acts only when a block has a page (R6) |
| `Citation` (`app/generation/citations.py`) | loses `page_start`, `page_end` and `pages`. `reference` is book, chapter, section |
| `_describe` (`app/generation/prompts.py`) | the passage header loses `Pages:` |
| `_with_references` (`app/generation/summarization.py`) | a summary's references show the section and the excerpt |
| `RetrievalFilters` (`app/retrieval/base.py`), `app/retrieval/dense.py` | lose the page range and its metadata filters |
| `search` (`app/main.py`) | loses `--page-start` and `--page-end`, and prints chapter and section |
| `app/interface/formatting.py` | `pages_of` and `quiz_pages` go, and the scores table loses its "Pages" column |
| `QuizService._reference` | chapter and section |
| the quiz benchmark's reading rows (`READING_FIELDS`), the retrieval rows (`_relevant_places`) | lose `pages` and `relevant_pages` |

The quiz's `_PAGE_NUMBER` check (`app/generation/quiz.py`) stays, and so does the writer prompt's
"Don't ask about page numbers" (FR-016). The citation's excerpt stays: in a book without pages,
it is how a reader finds the passage.

**Rationale.** On `main`, a Markdown chunk already has `page_start = None`. So the prompts,
citations and passages a Markdown book gets are already page-free, and removing the fields
changes nothing a Markdown book shows, apart from the scores table's empty column. The prompts
sent for a Markdown book stay byte for byte the same, given the same title (R14).

**Alternatives considered.** *Reading page markers from the converted Markdown*: the owner ruled
it out (Clarifications), and the sample conversion has none.

## R6. Normalization without the PDF's cleaning

**Decision.** The `normalization` section of `config/ingestion.yaml` goes with its only key,
`remove_repeated_margins`, and so do `NormalizationConfig` and the `normalization` field of
`Settings`. A configuration that still has the section stops the app as an unknown key, which
covers FR-008's "naming the key". `Normalizer()` takes no configuration, and keeps the cleaning
that applies to any text: NFC, ligatures, invisible characters and whitespace. These go:
- `_drop_running_margins`, `_printed_page_offsets`, `_offsets`, `_roman_value`, `_margin_key`, and
  the constants they use;
- `_merge_across_pages` and `_continues`.

**Rationale.** Without `remove_repeated_margins` the section would be empty, and an empty section
that has to be present is a trap. Both removed steps are no-ops on Markdown on `main`:
- No Markdown block has `margin` set, so `_drop_running_margins` keeps every block.
- `_continues` returns `False` when the previous block has no `page_end`, so no paragraph is ever
  joined.

So the normalized blocks of a Markdown file stay identical (SC-002).

**Alternatives considered.** *Keep an empty `normalization:` section for later settings.* An empty
model that has to be present is noise, and a later setting can bring the section back.

## R7. The index fingerprint

**Decision.**
- `METADATA_SCHEMA_VERSION` (`app/services/index_service.py`) goes from 1 to 2, because the chunk
  metadata loses two keys.
- `chunking.model_dump()` loses `preserve.page_numbers`, so the fingerprint would change even
  without the bump.
- The benchmark's `index_key` drops its `extraction` entry, which held the `pdf` and
  `normalization` settings.

What follows is principle III's, unchanged:
- **An index built before.** `needs_reindex()` is true, `doctor` reports it, new books are
  refused, questions keep working, and `reindex-all` builds the next version without writing into
  the live collection.
- **The stack rebuilt.** On a fresh `make up` the library is empty. The first step is
  `reset-everything` (README, `docs/decisions.md` Infrastructure): ChromaDB keeps the old
  `book_chunks_v1`, and the new catalog would number its first index 1 again.

**Rationale.** The schema version is what says the stored metadata changed shape. Relying on the
chunking dump alone would hide that in a side effect.

**Alternatives considered.** *No bump, since the chunking change already moves the fingerprint*:
implicit, and wrong the day the two changes come apart.

## R8. Progress without pages or OCR

**Decision.**
- **The extraction stage.** In `INGEST_STEPS` it becomes
  `StageSpec(EXTRACT, "Extracting the text")`: no unit, no estimate, so it shows a moving bar, as
  a Markdown extraction shows today (FR-011).
- **OCR.** `Stage.uncount`, `Progress._uncount` and the `ocr` state and log field go: only the PDF
  loader called them, when it handed a book to Docling's OCR.
- **The loader.** It no longer receives a `Stage`. The pipeline still opens the extraction stage
  around the call, so the stage line is logged as today.
- **The rest of the tracker** stays: counts, the time left and the sink, which the embedding
  stage and the reindex use.

**Rationale.** These were the PDF's only uses of the tracker. Markdown extraction takes a tenth of
a second or less (`docs/decisions.md`, "What an operation counts"), so there is nothing to count.

**Alternatives considered.** *Counting a Markdown book's headings or blocks*: nothing waits on
them, and the stage is over before a count could be read.

## R9. Dependencies and the image

**Decision.** In `pyproject.toml`:
- `ebooklib` and `pymupdf` leave `dependencies`.
- The `docling` extra goes, with its `torchvision`. `torch` stays, through the `reranking` extra.

`uv lock` then drops whatever only those pulled in. On `main`'s lock that is `docling`,
`docling-core`, `docling-ibm-models`, `docling-parse`, `docling-slim`, `pymupdf`,
`pymupdf-layout`, `pymupdf4llm`, `pypdfium2`, `rapidocr` and `torchvision`, plus their own
dependencies that nothing else needs.

What happens on the branch:
- **The lock's diff** is read, and every package it removes is named in the results.
- **What stays.** `beautifulsoup4`, `lxml`, `markdown` and `pyyaml` read Markdown. `httpx` stays,
  because `app/utils/ollama_runtime.py` uses it.
- **The Dockerfile** doesn't change: `--all-extras` now installs `reranking` and `evaluation`.
  Docling's models were downloaded at first use, never into the image, so there is nothing to
  delete there.
- **SC-004.** The image's size is read with `docker image ls`, on `main`'s image and on the
  branch's, and the installed packages with `importlib.metadata` in the container.
- **The comments.** Those that name Docling go: `docker-compose.yml`, and `doctor`'s GPU line
  (FR-012), which becomes "no GPU visible to the application: the reranker stays on the CPU".

**Rationale.** These packages are what FR-009 names. Removing them by hand, then letting
`uv lock` work out the rest, keeps every other version where `main` has it.

## R10. The uncommitted dependency bump

**Finding.** The working tree holds an uncommitted bump that isn't this feature's: commitizen
4.19.4 in `.pre-commit-config.yaml`, and `uv.lock`, whose sha256 is `3160461f…` against main's
`32de6819…`. Among other packages, it moves gradio from 6.31.0 to 6.32.0 and docling from 2.150.0
to 2.151.0. The running app image was built at 11:43 on 2026-11-19 from `main`'s code, since its
`app/`, `config/` and `pyproject.toml` match `main` byte for byte, but from that bumped lock, and
it reports gradio 6.32.0 and docling 2.151.0.

**Decision.** The bump never enters this feature's commits. Before any `uv` command of this
feature, image build, or baseline run, one of these two holds, and the owner chooses which:
1. **It lands first** as its own `chore: update dependencies` pull request, as PR #14 and PR #15
   did, and this branch is rebased on it (recommended). The running image is then exactly `main`'s,
   code and lock, so the baselines of R12 and R13 run on it as it is, without a rebuild that would
   empty the owner's library before its time. SC-004 compares two images that differ only by this
   feature, and the feature's `uv lock` starts from `main`'s lock.
2. **It is stashed for the feature's whole length**, which takes
   `git stash push -m "chore: commitizen 4.19.4 + uv.lock (owner undecided)" -- .pre-commit-config.yaml uv.lock`.
   It is put back only after the pull request is open. The running image then isn't `main`'s, so
   `make up` rebuilds it from `main` before the baselines, which empties the library: today one
   book, `book_001`, `01_historia_economica_global`.

**Rationale.** A lock computed from the bumped one would carry a dozen unrelated upgrades into a
`feat!` commit. A baseline image that differs from the branch's by more than the feature makes
SC-004's size comparison and R13's runs compare two changes at once.

## R11. The benchmark's books

**Decision.** The dataset lives on the host, in `benchmarks/datasets`, outside the repository
(constitution, Development Workflow). It is edited there, and its schema is changed in code
(`app/evaluation/dataset.py`). `BenchmarkBook` keeps `key`, `role`, `title`, `author`, `language`
and `license`, and changes the rest:
- `filename` and `sha256` now name the Markdown file in `benchmarks/books`;
- `url` moves into `original: {url, sha256}`, kept for provenance and never fetched;
- `conversion` is new: MarkItDown's version and the plugins, as the owner names them.

The model forbids unknown keys, so an old `books.yaml` with a top-level `url` is refused by name.
`dataset_checksum` doesn't change: it hashes `books.yaml`, so it now covers the Markdown files'
checksums (FR-021).

Today only `fetch-benchmark-books` checks a book's checksum. That check moves:
`BenchmarkRunner.run()` and `validate()` check every dataset book first, as `_check_local_books`
does for local books, and stop on a missing or different file before any work. Their message says
the books are converted by the owner and names the README's section. Then:
- `fetch-benchmark-books` goes: the subcommand, `fetch_books`, and their tests.
- The extraction experiment goes too (R15).
- On the host, `benchmarks/experiments/extraction.yaml` is deleted.
- The quiz experiments' local book (`quiz.yaml`, `quiz_models.yaml`, `quiz_check.yaml`) points
  to the owner's Markdown, `01_historia_economica_global.md`, with its checksum.

`quiz_check.yaml`'s known cases quote the PDF's text, and nothing in this feature runs them, so
`docs/benchmark-results.md` notes they are checked when the quiz benchmarks next run.

The evidence quotes are corrected by hand, as FR-019 sets out:
1. Run `validate-benchmark` on the Markdown books.
2. For each quote it doesn't find, find the passage in the Markdown and copy it as it is written
   there, holding the same evidence.
3. Correct the chapter names in `questions.jsonl` and `chapter_key_points.jsonl` to the chapters
   the Markdown gives, under the same rule.
4. Run it again until it reports nothing.

No question is dropped. `docs/benchmark-results.md` records how many quotes and chapter names
changed, and any quote that couldn't be corrected, with the reason.

**Rationale.** Checking the books where the work starts keeps the guarantee that
`fetch-benchmark-books` gave: no question is measured against a text it wasn't validated on.
Provenance stays, without the application downloading files it can no longer read.

**Alternatives considered.** *Converting in the application, or downloading the Markdown.* The
owner converts with their own plugins, which the application doesn't have (spec, Context).

## R12. Proving the chunks unchanged (SC-002)

**Decision.** A development tool, `devtools/dump_chunks.py`, writes one JSON file per Markdown
file given. For each chapter it holds the number, the title, and the titles of its sections, in
order. For each chunk it holds the chapter number, the chapter title, the section title and the
text, in order. The title, the author and pages are left out, and the keys are sorted. It runs in
the app container with `python -I`, and builds the pipeline with `app.container.build_pipeline`
and the container's configuration, as `validate()` does. It calls
`pipeline.process(path, validate_upload(...), "book", stem)` positionally, which works on both
versions of the code (R4).

It runs twice on the same files: the three converted benchmark books and the owner's
`01_historia_economica_global.md`.
1. **On `main`'s image**, before this branch's first `make up`.
2. **On the branch's image**, after it.

The two outputs must be identical, compared with `cmp` on the host. The unit tests whose
Markdown files check chunk texts and chapters keep their expected values. A change to one, other
than a title, an author or a page, is a regression.

**The gate.** The branch's first `make up` waits for the owner's three converted books and their
conversion record, because the dump on `main`'s code needs them. Everything before it, the code
and `make test`, doesn't. This corrects the spec's assumption that nothing before the benchmark's
tasks needs them (Corrections during planning).

**Rationale.** Identical chunks are what make this a removal, not a change to reading Markdown,
and only the real books show it. Comparing digests of whole files would miss nothing, but would
say nothing about where a difference is: the JSON can be diffed.

**Alternatives considered.**
- *Building `main`'s image again later, beside the branch's.* That means a second 11 GB image, and
  a second stack or `docker run` with the tokenizer downloaded again.
- *Running `main`'s code on the host.* The host can't run the tokenizer offline, and a second
  virtual environment would bring Docling and CUDA wheels.

## R13. The paired retrieval comparison (FR-020)

**Decision.**
- **The experiment.** `benchmarks/experiments/markdown_books.yaml`, on the host, of kind
  `retrieval`, with one variant, `default`, without overrides: the default configuration, with
  the reranker on the CPU as `config/models.yaml` sets it.
- **The run on the originals.** It uses `main`'s image, `main`'s dataset and the original PDF and
  EPUBs, with `benchmarks/workspace` deleted first, and runs before the branch's first `make up`.
- **The run on the Markdown.** After that `make up`, it uses the branch's image and the Markdown
  dataset, again with the workspace deleted first.
- **Copies.** Both results are copied to the host, under `benchmarks/results`.

A development tool, `devtools/compare_runs.py`, runs on the host with `uv run`. It reads the two
`results.json` files, renames each run's `default` variant (`originals`, `markdown`), merges
their rows and summaries, and renders them with `app.evaluation.report.render(...,
baseline="originals")`. That reuses `paired_difference`: pairs by question ID, 4,000 resamples,
95%. It adds a table of each question whose metrics moved, with its book and category, to read
what those questions retrieved before naming a difference (FR-020). Each run keeps its own
environment block: dataset checksum, book checksums, packages and commit.

**Rationale.**
- **Why pairing.** `benchmark-report --baseline` pairs variants within one run, and one run can't
  hold two versions of the code. The totals recorded so far have no rows per question
  (Clarifications).
- **Why retrieval.** It needs no judge, so there is no judge to prove first (principle VI). At 75
  questions and about 4 s of reranking each on the CPU, a run takes minutes.
- **Why one variant.** It answers what the conversion changed under the configuration in use.

**Alternatives considered.**
- *A `--against` option of `benchmark-report`*: a product feature for a one-off comparison.
- *Reusing the retrieval runs already recorded*: no rows per question.

## R14. Checking it on real books and real models (principle V)

**Decision.** The real-book and real-model checks:
- **Ingestion** is checked on the three converted benchmark books and on the owner's
  `01_historia_economica_global.md`:
  - each is added from the tab and with `add-book` (SC-001);
  - the chunks are dumped (R12);
  - the retrieval comparison runs (R13).
- **The prompts.** The passage header loses only a `Pages:` part that a Markdown chunk never had,
  so its prompts are the same as on `main`, given the same title. `make test-integration` runs
  against the stack's models (gpt-oss:20b, qwen3-embedding:0.6b, Qwen3-Reranker-0.6B) and has to
  pass as on `main` (SC-006).
- **SC-008.** After it, the Chat tab, `ask`, `search`, a saved summary and a quiz on a Markdown
  book are read, to see no page and every citation resolving to book, chapter and section.

The generation, summarization and quiz benchmarks aren't run again (spec, Assumptions).

**Rationale.** Nothing a model reads changes for a Markdown book, apart from its title. The
integration tests are what show that parsing and citing still work against real output.

## R15. The extraction experiment and the development tools

**Decision.** These go:
- **The `extraction` kind**: its value in `Experiment.kind`, `_run_extraction`,
  `_EXTRACTION_METRICS`, `app/evaluation/extraction_metrics.py` and its tests. An experiment of
  that kind is then refused by the model's literal, naming the allowed kinds (FR-017).
- **`devtools/measure_library_progress.py`** and its 27 tests
  (`tests/unit/test_progress_devtool.py`). It measured specs/004's progress on two PDFs and two EPUBs, needs PyMuPDF for page counts, and
  its results are recorded in specs/004. The question it answered, whether reporting progress
  slows an operation, has its answer.
- **`comparable_text`** in `app/ingestion/base.py`: only the PDF and EPUB loaders and the
  extraction metrics used it. `ORDINAL` stays, for the structure extractor.
- **`html_to_blocks`' `anchors` and the positions it returns**: only the EPUB loader asked for
  anchors. With them goes the filter of `XMLParsedAsHTMLWarning`, which was there for EPUB's XHTML.
  `html_to_blocks` returns the blocks alone, which doesn't change them.
- **`ScannedDocumentError`.**

`docs/benchmark-results.md` keeps its Extraction section, marked as measured on PDF and EPUB
before v1.0.0.

**Alternatives considered.** *Porting the progress tool to Markdown*: nothing in it would
measure anything new, since Markdown extraction isn't counted (R8).

## R16. The tests

**Decision.**
- **Deleted.** `tests/unit/test_pdf_loader.py`, `test_epub_loader.py`, `test_extraction_metrics.py`,
  `test_progress_devtool.py` and `tests/integration/test_docling.py`. In `tests/documents.py` the
  PDF and EPUB writers go, and the module with them if nothing is left.
- **Rewritten with Markdown.** The tests that check something format-independent through a PDF or
  an EPUB keep checking it (FR-010):
  - `test_book_lifecycle.py` and `test_book_service.py`: adding, a book's chapters, duplicates;
  - `test_catalog.py`, and the test library in `tests/library.py`, which loses its PDF and EPUB
    loaders;
  - `test_quiz_service.py` and `test_summarization.py`, whose sample books are named `.pdf`;
  - `test_interface.py` and `test_structure_extractor.py`.
- **Changed to the new rules.**
  - `test_validation.py`: `.pdf` and `.epub` refused with the convert-first message, other types
    with the accepted list, Markdown checks unchanged.
  - `test_markdown_loader.py` and `test_pipeline.py`: the title is the file's stem and never the
    front matter or a single H1. The author is empty. Front matter is still removed, and its
    `language` and `lang` still read.
  - `test_normalizer.py`: only the cleaning tests stay.
  - `test_chunker.py`, `test_chunk_store.py`, `test_filters.py`, `test_citations.py`,
    `test_question_answering.py`, `test_bm25.py` and `tests/fakes.py`: no pages.
  - `test_progress.py`: no OCR. Its counted test stage counts chunks.
  - `test_config.py`: the three removed keys refused by name.
  - `test_benchmark.py` and `test_dataset.py`: the new book schema, the check before a run, the
    kind refused, no fetch.
  - `test_index_service.py`: the fingerprint moves with the schema version.
  - `test_commands.py`: `search` without a page range.
  - `test_interface.py`: the pickers' types and label, and their preprocessing refusing a PDF
    (R3).

**Rationale.** FR-010 asks that the lifecycle, the journal, duplicates, the catalog and progress
stay tested, now with Markdown.

## R17. The records

**Decision.**
- **`README.md`.**
  - *Library*: the commands with a `.md`, and how to prepare a book, from FR-022. It is converted
    outside the application, MarkItDown for example. It is named as it should be titled. Headings
    mark chapters and sections, with the chapter rules. Front matter is optional, for `language`.
    What is refused, and why.
  - *Following an operation*: extraction without a count, no OCR.
  - *Index* and *Retrieval*: metadata and filters without pages.
  - *Questions*, *Summaries* and *Quizzes*: citations and pointers without pages.
  - *Benchmarks*: the books are made by conversion with their record, no `fetch-benchmark-books`
    and no `extraction` kind.
  - *Deployment notes* and *Configuration*: no Docling, no `pdf` section.
- **`docs/decisions.md`.**
  - *Ingestion* gets new entries:
    - Markdown only, converted outside, departing from the first version's spec;
    - the title is the file name, and no author;
    - pages dropped rather than read from markers;
    - the benchmark's books record their conversion;
    - normalization keeps only the cleaning that applies to any text.
  - *Library lifecycle*: "What an operation counts" is updated, since extraction is no longer
    counted.
  - *Removed with PDF and EPUB (v1.0.0)*, a new closing section. One line each, with the failure
    that taught it:
    - running heads recognized by their page numbers;
    - each table-of-contents entry claiming one heading;
    - a heading the outline names never taken for a running head;
    - Docling and OCR as the PDF alternative.
  - *Evaluation* keeps the Docling comparison, a metric hiding a loss, and gains *Think Python*'s
    coverage, which is that kind of lesson too.
- **`docs/benchmark-results.md`.**
  - The Extraction section is marked as history.
  - A new section holds the two runs and their paired comparison.
  - Known limitations notes the quiz cases still to check (R11).
  - Reproducing uses the converted books, and points to where the dataset is recorded (R19). So
    do the README's Benchmarks section and `docs/decisions.md`'s line naming `c7bb785`.
- **Not edited.** The constitution's history in V and VI, the delivered specs, and the bug and
  assessment records under `.specify/` (Corrections during planning).

## R18. The release

**Decision.** The pull request's title is `feat!: accept only Markdown books`, which is under 72
characters. Its description ends with the `BREAKING CHANGE:` footer of FR-025, and the squash
merge keeps the description as the commit body. Commitizen has no `major_version_zero`, so the
release workflow takes 0.4.0 to 1.0.0.

**Rationale.** The owner chose a breaking release (Clarifications). A configuration with the
removed keys stops the app, and a script calling `fetch-benchmark-books` or `search --page-start`
fails.

## R19. Where the Markdown dataset is recorded [owner to confirm]

**Finding.** The dataset and the experiments live only on the host, in `benchmarks/` (ignored by
git). The constitution's Development Workflow, the README's Benchmarks section,
`docs/benchmark-results.md` and `docs/decisions.md` all say their last versions are at commit
`c7bb785`. This feature rewrites the dataset: Markdown books, their provenance, and quotes and
chapter names corrected to the Markdown text (R11). The results of R13 record its checksum. Left
on the host alone, that checksum would point at files nobody else has, and the corrections would
be lost with the folder.

**Decision (recommended).** The validated dataset is recorded in
`specs/005-markdown-only/benchmarks/`:
- `datasets/`: `books.yaml`, `questions.jsonl` and `chapter_key_points.jsonl`.
- `experiments/`:
  - `markdown_books.yaml`;
  - the three quiz experiments of `specs/003-chapter-quiz/benchmarks/`, with their local book
    pointed to the owner's Markdown.

This follows `specs/003-chapter-quiz/benchmarks/`, where that feature recorded its experiments.
The other experiments stay at `c7bb785`, less `extraction.yaml`. The Markdown books stay out of
the repository, as the originals did: their checksums and provenance identify them, and the check
of R11 refuses a different file. The README, `docs/benchmark-results.md` and `docs/decisions.md`
then point to the new place.

The constitution's sentence "their last versions are at `c7bb785`" stops being true, so it needs
a PATCH amendment through `/speckit-constitution`, which only the owner starts. It names where
the dataset now lives, before the pull request.

**Alternative.** The dataset stays on the host only, and `docs/benchmark-results.md` records its
checksum and how many quotes changed. This is closer to "dataset and experiments stay out of the
repository", but it leaves the corrected quotes in one place, and the next person to rebuild the
benchmark rewrites them.
