# Feature Specification: Markdown-only books

**Feature Branch**: `feat/markdown-only`

**Created**: 2026-11-19

**Status**: Draft

**Input**: User description: "Accept only Markdown books, and remove PDF and EPUB ingestion
completely. The owner converts books to Markdown outside the app, with Microsoft MarkItDown and
their own and open-source plugins, and adds the resulting .md file. Uploads in Gradio (add and
replace) and the commands accept only .md and .markdown. A PDF or EPUB is refused with a message
saying to convert it to Markdown first. Remove the PDF and EPUB loaders, the OCR path, Docling,
PyMuPDF and ebooklib with their dependencies, the pdf section of config/ingestion.yaml and its
settings, and every piece of code, test, benchmark and documentation that served only those
formats. Markdown ingestion keeps working as today: YAML front matter for title, author and
language, and headings as the book's structure. README.md and docs/decisions.md record the change,
which departs from the first version's spec."

## Context

This is a personal project, and the owner already converts every book to Markdown with Microsoft
MarkItDown, using their own plugins and open-source ones. Converting inside the application
duplicates that work, with readers the owner no longer uses.

Today the library reads three formats, and two of them carry most of the ingestion code:

- **PDF**: PyMuPDF by default, or Docling's layout models (`pdf.extractor: docling`), with
  Docling's OCR for scanned PDFs when `pdf.ocr.enabled` is on. The PDF reader takes chapters from
  the book's outline and headings from font sizes. It marks text at the top or bottom of a page
  so that the cleaning step can drop running heads. It is also the only reader that gives pages.
- **EPUB**: EbookLib, in spine order, with chapters from the table of contents. No pages.
- **Markdown**: headings mark chapters and sections, front matter can set `title`, `author` and
  `language`. No pages.

Beyond the readers, some parts of the application exist only for PDF and EPUB:

- **Configuration.** The `pdf` section of `config/ingestion.yaml`, and
  `normalization.remove_repeated_margins`, which acts only on the page edges that the PDF reader
  marks.
- **Cleaning.** It rejoins paragraphs that a page break cut, which needs pages.
- **Upload checks.** One check makes sure a `.pdf` is a PDF, and another that an `.epub` is a ZIP
  file that doesn't expand too far.
- **Dependencies.** The image installs a `docling` extra. `torch` stays, because the reranker
  needs it too.
- **Progress.** While a PDF is extracted, the library's progress counts pages and has a state for
  OCR (`specs/004-library-progress`). Markdown extraction shows no count.
- **The extraction benchmark.** It compares the two PDF extractors, measures how much of a book's
  own table of contents survives (it reads the PDF outline or the EPUB navigation), and how many
  pages the chunks cover.
- **The benchmark dataset.** Its three books are one PDF (*Think Python*) and two EPUBs
  (*Quincas Borba*, *On Liberty*), which `fetch-benchmark-books` downloads and checks against
  their checksums. Its 75 answerable questions hold evidence quotes, and `validate-benchmark`
  requires each one to appear in its book exactly as written.
- **Pages, from PDFs alone.** Citations show "p. N", a quiz's passage pointer shows pages, the
  `search` command filters by a page range, the prompt's passage header carries pages, and chunk
  metadata stores `page_start` and `page_end`. With Markdown only, every one of these would stay
  empty, so they go (FR-014).

The owner gave a sample of their conversion: *História econômica global* converted from its PDF
(1,686 lines, 49,779 words). Read by today's Markdown reader, cleaning and structure steps on
2026-11-19, with no model involved, it gives:

- **The structure**: 15 chapters, the numbered "Capítulo 1" to "Capítulo 9" with their 2 to 7
  sections each, and the acknowledgements, epilogue, references, further reading, list of
  illustrations and list of tables. The file has 15 level-1 headings, 30 level-2 headings and
  1 level-3 heading, and every one of them is a real heading.
- **The language**: Portuguese, detected from the text.
- **No title and no author.** The file has no front matter, and with 15 top-level headings none
  of them is the title, so the book would be titled after its file name,
  `01_historia_economica_global`, with no author.
- **No pages, page numbers or running heads**, and no words broken at line ends. The book's
  title appears once in the text.
- **No tables and no images.** The list of tables is a paragraph whose entries run into each
  other.
- **The publisher's advertisements are still there.** At the end, a level-3 heading "Table of
  Contents" holds the book's table of contents run into one line, followed by advertisements for
  other books ("Compre agora e leia"). They would go into the last chapter, "Lista de tabelas".
  The same back matter is behind an open bug in today's ingestion (`docs/benchmark-results.md`,
  Known limitations).

Removing a format can't strand a book. Any change to the code or the configuration empties the
library at the next `make up`, because nothing lives outside the containers (constitution,
Principle II). So no stored PDF or EPUB can outlive this change.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Adding books as Markdown, and only as Markdown (Priority: P1)

The owner converts a book with MarkItDown and adds the `.md` file in the Library tab, or with
`add-book`. It goes in as a Markdown book does today, with the same chapters, sections, chunks
and language. Its title is its file name, and it has no author. Replacing a book works the same
way. If the owner picks a PDF or an EPUB by mistake, it is refused before anything is stored,
with a message saying to convert the book to Markdown first. The tab's file pickers offer only
Markdown files.

**Why this priority**: This is the change the owner asked for, and the rest follows from it.

**Independent Test**: Add a Markdown book through the tab and with `add-book`, and compare its
chapters and chunks with the same file added on `main`. Then try a PDF and an EPUB in the tab, in
`add-book` and in `replace-book`, and check each refusal and that the library is unchanged.

**Acceptance Scenarios**:

1. **Given** a `.md` or `.markdown` file, **When** the owner adds it from the tab or the command
   line, **Then** it is indexed as it would be today, and its chunks are the same as on `main`
   (SC-002).
2. **Given** a `.pdf` or an `.epub`, **When** the owner adds it, or replaces a book with it, from
   the tab or the command line, **Then** it is refused before anything is stored or journaled,
   with a message that names the format and says to convert the book to Markdown first (in the
   tab, Gradio's message naming the accepted types, beside the tab's note on converting), and
   the book being replaced stays as it was.
3. **Given** a file of any other type, **When** the owner adds it, **Then** it is refused as
   today, with the accepted types listed, which are now `.md` and `.markdown`.
4. **Given** the Library tab, **When** the owner opens either file picker, **Then** it offers
   only `.md` and `.markdown` files, and its label names Markdown alone.
5. **Given** a book in the library, **When** the owner processes it again from its original or
   reindexes the library, **Then** it works as today, since every original is Markdown.
6. **Given** a Markdown file named `01_historia_economica_global.md`, with or without a title
   and author in its front matter or a single top-level heading, **When** the owner adds it,
   **Then** the book is titled `01_historia_economica_global` and its author is empty.

---

### User Story 2 - Nothing left of PDF and EPUB (Priority: P2)

The application no longer has PDF or EPUB code, settings, dependencies, tests or documentation,
nor pages, which only PDFs ever gave: citations point to the book, chapter and section. The image
no longer installs Docling, PyMuPDF or EbookLib, or downloads Docling's models.
`config/ingestion.yaml` has no `pdf` section, and a configuration that still has one stops the app
at startup, as any unknown key does. The README describes a library of Markdown books, and how to
prepare one.

**Why this priority**: Code that is never used still has to be maintained, tested, upgraded and
built into the image. The owner asked for the formats to be removed completely, not just
switched off.

**Independent Test**: Build the image and check that the removed packages aren't installed and
that it is smaller than `main`'s. Start the app with the new configuration, and again with a `pdf`
section added back to see it refused. Search the repository for the removed formats (SC-005).
Run `make test`, `make test-integration` and `doctor`.

**Acceptance Scenarios**:

1. **Given** the new image, **When** its installed packages are listed, **Then** Docling,
   PyMuPDF and EbookLib aren't among them, nor anything installed only for them. What other
   features use, such as the reranker's GPU stack, stays.
2. **Given** a `config/ingestion.yaml` that still has a `pdf` section, a `normalization`
   section or `chunking.preserve.page_numbers`, **When** the app starts, **Then** it stops with
   an error that names the key, as for any unknown key.
3. **Given** the unit and integration tests, **When** they run, **Then** they pass, and none of
   them reads or writes a PDF or an EPUB. Behavior that today's tests check through a PDF or an
   EPUB but that doesn't depend on the format, such as the library's lifecycle, the journal,
   duplicate detection, the catalog and progress, is still checked, with Markdown.
4. **Given** `doctor`, the commands' help, the interface's labels and the README, **When** the
   owner reads them, **Then** none of them mentions PDF, EPUB, OCR or Docling, except to say that
   books are converted to Markdown outside the application.
5. **Given** an answer, a summary, a quiz's pointers to passages, or the passages that the Chat
   tab, `search` and `ask` show, **When** the owner reads them, **Then** each passage is located
   by book, chapter and section, and none shows a page. `search` has no page range.

---

### User Story 3 - The benchmark on Markdown books (Priority: P3)

The benchmark dataset's three books become Markdown files converted the way the owner converts
their own books. `validate-benchmark` finds every evidence quote in them, and the retrieval
benchmark runs on them in a fresh workspace. Its results are compared, question by question,
with a run on the original PDF and EPUBs, so that the owner can see what the conversion changed. The
extraction experiment goes, because what it measured was the PDF extractors and the originals'
tables of contents.

**Why this priority**: Without Markdown books, no benchmark can run, and every later comparison
of models or retrieval strategies depends on it. Removing the formats comes first, though: until
then, the benchmark still runs on the old code.

**Independent Test**: Run `validate-benchmark` on the Markdown dataset, then the retrieval
experiment on a fresh `benchmarks/workspace`, and read its paired comparison with the run on the
original books.

**Acceptance Scenarios**:

1. **Given** the dataset's three books converted to Markdown, **When** `validate-benchmark`
   runs, **Then** every evidence quote is found in its book exactly as written. Quotes the
   conversion changed are corrected to the Markdown text and still prove the same answer.
2. **Given** the Markdown dataset and a fresh workspace, **When** the retrieval experiment runs,
   **Then** it completes, and its result records the dataset's checksum, which now covers the
   Markdown books.
3. **Given** a retrieval run on `main` with the original books and one on this branch with the
   Markdown books, **When** they are compared, **Then** `docs/benchmark-results.md` shows both,
   with the paired interval of each metric, for information, and says that the books changed
   between the two, along with the code that read them.
4. **Given** an experiment of the removed `extraction` kind, **When** it is run, **Then** it is
   refused as an unknown kind, and the extraction results recorded so far stay in
   `docs/benchmark-results.md` as history, marked as measured on PDF and EPUB.

---

### Edge Cases

- **An uppercase extension** (`BOOK.MD`) is accepted, because extensions are compared without
  case, as today.
- **A PDF or EPUB renamed to `.md`** is refused as binary data or as not UTF-8, as any Markdown
  file is today, and nothing is stored.
- **A Markdown file without headings** is accepted, as today. It becomes a single chapter, titled
  with the book's title, which leaves summaries and quizzes by chapter with one chapter to choose.
- **A title or author in the front matter, or a single top-level heading**, no longer names the
  book: the title is the file name and the author stays empty. The front matter is still removed
  from the text, and its `language` (or `lang`) still sets the language. Without it, the
  language is detected from the text, as today.
- **A single top-level heading** is still read by the structure rules as the book's own title
  line, not as a chapter. With the title taken from the file name, its text now shows nowhere.
- **Front matter that doesn't parse as YAML, or isn't closed,** stays in the text, as today.
- **The file's name** is what remains after the upload's name cleaning: the folders of a path are
  dropped, characters that can't be printed are removed, and a name left empty becomes `unnamed`.
  `BOOK.MD` is titled `BOOK`. A file named only `.md` has no extension, so it is refused as an
  unsupported type.
- **Two files with the same name and different content** are two books with the same title,
  told apart by their IDs.
- **Replacing a book with a file of another name** changes the book's title to the new name,
  since the title comes from the file.
- **Images in the Markdown**, including inline `data:` images, add no text to the book. A file
  over the upload limit (512 MB) is refused, as today.
- **The same book converted twice with different plugins** gives two files with different
  checksums, so the library accepts both as two books. Checksums identify files, not books, as
  today.
- **Replacing a Markdown book with a PDF** is refused, and the book keeps its current version.
- **Starting the new version of the app** with a library from an older one can't happen with
  PDF or EPUB books in it, because `make up` empties the library (Context).

## Clarifications

### Session 2026-11-19 (specify)

- Q: With no PDFs, no book has pages. Should pages be dropped everywhere, read from page markers
  that the owner's conversion writes, or kept in the code but unused? → A: Dropped everywhere.
  Citations, quiz pointers, the passages shown, the `search` page filter, the prompts and the
  chunk metadata lose them, along with the settings and the cleaning that served them. Principle
  VII is amended to drop "pages".
- Q: Who converts the benchmark's three books, and how does the dataset record where they came
  from? → A: The owner converts them with the same MarkItDown setup as their own books. The
  dataset names the Markdown files and their checksums. For provenance it keeps each original's
  URL and checksum and the conversion used, which is MarkItDown's version and the plugins.
  `fetch-benchmark-books` is removed, since the application can't read what it downloads.

### Session 2026-11-19

- Q: How should the retrieval results on the Markdown books be compared with those on the
  original PDF and EPUBs? → A: The owner left the choice to the agent and gave a sample
  conversion (Context). Paired, with two fresh runs: the default retrieval variant on `main`'s
  code with the original books, before the container is rebuilt, and on this branch with the
  Markdown books. The two are compared question by question with the paired bootstrap. The
  totals already recorded have no rows per question, so they can't be paired.
- Q: When a Markdown book has no front matter, as in the owner's sample, where should its title
  and author come from? → A: The book's title is always its file name, and its author is never
  read. Book information stays minimal until plugins that supply it are found. The catalog's
  author field stays, and stays empty.
- Q: Should this change be released as a breaking change (v0.4.0 to v1.0.0) or as a regular
  feature (v0.5.0)? → A: As a breaking change: the pull request's title is `feat!:`, with a
  `BREAKING CHANGE` footer listing what was removed, which releases v1.0.0.
- Q: In `docs/decisions.md`, what should happen to the decisions that only explained the PDF and
  EPUB readers? → A: Each is shortened to one line, with the decision and the failure that
  taught it, in a closing section "Removed with PDF and EPUB (v1.0.0)". Lessons that still
  apply anywhere stay where they are.

### Corrections during planning, 2026-11-19

- **In the tab, a PDF or EPUB is refused by Gradio, not by the service.** The pickers offer only
  Markdown (FR-004). Gradio's own check refuses a file forced past them, dropped or chosen with
  "all files", before the service runs, and its message names the accepted types. So the advice
  to convert first is in a note under "Add a book". FR-002's message is what the commands get,
  and anything else that reaches the service (`research.md`, R3).
- **A Markdown file without headings is one chapter titled with the book's title**, its file
  name. It isn't titled "Full text": the pipeline has always given the structure a title, so on
  `main` too that chapter took the book's title (R1).
- **`normalization` goes whole.** `remove_repeated_margins` was its only key, so a configuration
  that still has a `normalization` section stops the app, and the error names `normalization`
  (R6).
- **The benchmark books' checksums are checked by `benchmark` and `validate-benchmark`.** Today
  only `fetch-benchmark-books` checks them, so the check moves where the work starts (R11).
  Chapter names in the questions and key points that the conversion changed are corrected too,
  under FR-019's rule.
- **The converted books are needed before the image is rebuilt with this branch's code**, not
  only at the benchmark's tasks. Proving the chunks unchanged (SC-002) reads them on `main`'s
  code, which the rebuild replaces (R12).
- **SC-005 leaves out more history.** The constitution's Why sections, which tell the Docling and
  *Think Python* failures behind principles V and VI. The bug and assessment records under
  `.specify/`, which are history like the specs. And `uv.lock`, which is generated and is checked
  on its own for the removed packages.

### Corrections from the requirements checklist, 2026-11-19

The owner answered the checklist's main findings (`checklists/removal-and-measurement.md`):
- "You can reset-everything any time you want" (CHK006).
- The quiz is removed by the next feature (CHK011).
- The agent chooses how to handle the dataset's record, the baseline's packages, the outside
  dependencies (CHK023, CHK027, CHK034) and the breaking-change footer (CHK032).

The rest the agent settled.
- **After the rebuild, `reset-everything` comes first** (FR-015). The old version said the first
  index would be built fresh, but ChromaDB keeps the old collections.
- **The quiz goes next.** Its changed inputs aren't proved again, and its experiments aren't
  touched (Assumptions).
- **The comparison's edge cases.** A chapter the conversion merged, split or lost is replaced by a
  stated rule (FR-019). A question whose evidence resolves nowhere is left out of the pairing and
  counted (FR-020). These two are about the retrieval benchmark, not the quiz.
- **The dataset's record.** The validated dataset is recorded in
  `specs/005-markdown-only/benchmarks/`, with a constitution amendment before the pull request
  (FR-018, Assumptions, R19).
- **The pending bump stays stashed** for the whole feature, and both images are built from
  `main`'s lock apart from this feature's change (FR-020, SC-004, R10).
- **The footer** adds the whole `normalization` section, `search`'s page options, the results'
  page columns and the dataset's schema (FR-025).
- **Precision.**
  - SC-002 names the books and the unit tests.
  - SC-003, SC-004 and SC-008 say what is compared and read.
  - FR-002 gives the order of the checks.
  - FR-004 says what the tab's note may name.
  - FR-005 lists every path that sets a title, and every place an author is empty.
  - FR-014 lists every place pages are shown.
  - FR-018 says where the description goes, and what the conversion record holds.
  - FR-021 says what the checksum covers.
  - FR-022 tells the reader to keep the file's name.
  - FR-023 lists the decisions to move.
  - The edge cases cover a single top-level heading, front matter that doesn't parse, and the
    file's name.

## Requirements *(mandatory)*

### Functional Requirements

#### Accepting books

- **FR-001**: The library MUST accept a book only as a file with the `.md` or `.markdown`
  extension, compared without case, in the Library tab (adding and replacing) and in the
  `add-book` and `replace-book` commands.
- **FR-002**: A `.pdf` or `.epub` file MUST be refused before anything is stored or journaled.
  The message names the format and says to convert the book to Markdown first, and may name
  MarkItDown as an example. Replacing a book with one leaves the book as it was. In the Library
  tab, Gradio refuses such a file before the service, with its own message naming the accepted
  types, whatever its exact wording, and nothing is stored or journaled. A note under "Add a book"
  says three things: books are Markdown files; a PDF or EPUB is converted to Markdown first, with
  MarkItDown as an example; and the file's name becomes the book's title (Corrections during
  planning). The checks keep today's order: a busy library first, then the file's type, size and
  content, then a duplicate, then an index that needs a reindex.
- **FR-003**: A file with any other extension MUST be refused as today, with the accepted
  extensions listed.
- **FR-004**: The Library tab's file pickers MUST offer only `.md` and `.markdown` files. Their
  labels, the commands' help and the error messages MUST name Markdown as the only accepted
  format. They, and the tab's note, may name PDF, EPUB and MarkItDown only to say that a book is
  converted first, or why a file is refused.
- **FR-005**: Reading a Markdown book MUST stay as it is today, except for its title and author:
  - **the checks**: the size limit, an empty file, binary data, and UTF-8;
  - **the title**: always the name of the file the book arrived as, without its extension, as
    given and not reformatted. That holds on every path that indexes a book: adding, replacing,
    processing it again, `reindex-all`, and an original brought back by a rebuild, each of which
    reads the name recorded with the original. A title or author in the front matter, or a
    single top-level heading, MUST NOT set it.
  - **the author**: never read, and left empty in the catalog, whose field stays for a later
    feature. Wherever an author is shown or passed on today, it is empty: the Library tab's
    Author column, the quiz's prompts, and its check for questions answerable without reading.
    The tab keeps its Author and Format columns, one empty and the other always `markdown`.
  - **the front matter**: still removed from the text, and its `language` (or `lang`) still
    sets the book's language;
  - **the structure**: headings as structure, the rules that find chapters and sections, the
    cleaning that applies to any text (Unicode normalization, ligatures, invisible characters,
    whitespace), language detection and chunking.

  The same file with the same configuration MUST give the same chapters, sections and chunk
  texts, in the same order, as on `main` (SC-002). Only the title and the author may differ.
- **FR-006**: Identifying a book by its checksum, the library lock, the journal and recovery
  MUST work as today.

#### Removing PDF and EPUB

- **FR-007**: The application MUST NOT read PDFs or EPUBs by any path: none of the PDF
  extractors, OCR, the EPUB reader, their upload checks, or the errors that only they raise, such
  as the one for a scanned PDF.
- **FR-008**: The `pdf` section of `config/ingestion.yaml` and its settings MUST be removed. So
  MUST `normalization.remove_repeated_margins` and the dropping of running heads that it
  switches, since only the PDF reader marks the page edges it acts on. A configuration that still
  holds any of them MUST stop the app at startup, naming the key, as any unknown key does.
- **FR-009**: The packages installed only for PDF or EPUB, and the models they download, MUST
  be removed from the dependencies and the image: Docling and its extra, PyMuPDF and EbookLib.
  Packages that something else still uses MUST stay, such as the reranker's GPU stack and the HTML
  parsing that reads Markdown. "Installed only for them" means the packages the lock drops once the
  three are removed. Docling's models were downloaded when first used, into the container and
  never into the image, so removing Docling is what removes them.
- **FR-010**: Code, tests, test helpers, development tools, comments and settings that served
  only PDF or EPUB MUST be removed. A test that checks something independent of the format
  through a PDF or an EPUB MUST be rewritten with Markdown, so that what it checks is still
  checked. The removal includes `devtools/measure_library_progress.py`. It measured
  `specs/004`'s progress on the PDF and EPUB books with PyMuPDF, and the question it answered is
  settled.
- **FR-011**: The progress of adding, replacing or processing a book again MUST show its
  extraction stage without a count, as a Markdown book's extraction shows today. The page unit
  and the OCR state MUST go from the progress reporting.
- **FR-012**: `doctor` MUST NOT mention Docling. Its GPU check names only what still uses the
  GPU in the application, the reranker.
- **FR-013**: Everything else MUST be left as it was: questions, summaries, quizzes, retrieval,
  the library's operations and their confirmations. The exceptions are a book's title and author
  (FR-005) and pages (FR-014 to FR-016).

#### Pages

- **FR-014**: Pages MUST be removed everywhere a book's pages appear or are used:
  - **what the reader sees**:
    - citations in answers;
    - a saved summary's references;
    - the passages shown in the Chat tab and by `search` and `ask`, with `search` printing
      chapter and section;
    - the Chat tab's scores table, which loses its Pages column;
    - the quiz's passage pointers;
  - **the prompts**: the passage header sent to the model;
  - **the filters**: the `search` command's page range and the page filter in retrieval;
  - **the index**: the chunk metadata (`page_start`, `page_end`), the setting
    `chunking.preserve.page_numbers`, and the cleaning that rejoins a paragraph cut by a page
    break;
  - **the benchmark**: the retrieval rows' `relevant_pages` and the quiz reading's `pages`
    column.

  A citation then resolves to the book, chapter and section. A configuration that still holds
  `chunking.preserve.page_numbers` MUST stop the app at startup, naming the key. Pages go as
  data. Wording that tells a model not to name pages stays (FR-016).
- **FR-015**: Removing the page fields and the page setting changes the chunk metadata's schema
  and the chunking settings, both of which are in the index fingerprint. The fingerprint MUST
  change accordingly, and an index built before MUST be treated as any index whose configuration
  changed: `doctor` reports it, new books are refused, and `reindex-all` builds a new index
  version (Principle III). After the rebuild, `reset-everything` is the first command, before
  any book. The library is empty, but ChromaDB keeps the old `book_chunks_v*` collections, and a
  new catalog would number its first index 1 again and reuse one (`docs/decisions.md`,
  Infrastructure). The owner allows a reset at any time.
- **FR-016**: The quiz's check that refuses a question pointing at a page, a passage number or
  "the excerpt" MUST stay as it is. It reads what the model writes, which can still name a page,
  and doesn't depend on the books having pages. So does the prompts' wording that tells the model
  not to name pages.

#### Benchmarks

- **FR-017**: The `extraction` experiment kind and its metrics MUST be removed (TOC coverage,
  chapters, chunks, pages covered), and with them the experiment that compares the PDF
  extractors. An experiment of that kind MUST be refused as unknown. The extraction results
  recorded so far MUST stay in `docs/benchmark-results.md`, marked as history measured on PDF and
  EPUB.
- **FR-018**: The benchmark dataset's three books MUST be Markdown files that the owner converts
  with the same MarkItDown setup as their own books. For each book, the dataset MUST record:
  - the Markdown file's name and checksum, which `benchmark` and `validate-benchmark` check
    before they read a book, as `fetch-benchmark-books` checked the originals;
  - for provenance, the original's URL and checksum, and the conversion used: MarkItDown's
    version, each plugin's name and version, and any options, as the owner gives them.

  `fetch-benchmark-books` MUST be removed, because the application can't read the files it
  downloads. The header comment of `books.yaml` MUST say that rebuilding the books takes the same
  conversion, so the questions hold only for files with the recorded checksums. Once it
  validates, the dataset is recorded in `specs/005-markdown-only/benchmarks/datasets/`, with the
  experiment of FR-020 in `benchmarks/experiments/` beside it (`research.md`, R19). The Markdown
  books stay out of the repository, as the originals did.
- **FR-019**: Every evidence quote in the dataset MUST be found in its Markdown book by
  `validate-benchmark`. A quote the conversion changed MUST be corrected to the Markdown text,
  holding the same evidence for the same answer. A question is never dropped to make the
  validation pass. If a quote can't be corrected, `docs/benchmark-results.md` says which, and why.
  - **A corrected quote** keeps `validate-benchmark`'s rules: it is found exactly, and is at most
    30 words. Each change shows as a diff between the dataset at `c7bb785` and the recorded one,
    which the owner reviews in the pull request.
  - **A chapter name the conversion changed**, in a question or a key point, is corrected the same
    way.
  - **A chapter the conversion merged, split or lost** is replaced. A question takes the Markdown
    chapter that holds its first evidence quote. A key point takes the one that holds the original
    chapter's opening. `docs/benchmark-results.md` lists each case.
- **FR-020**: The retrieval experiment's default variant MUST be run twice, each in a fresh
  `benchmarks/workspace`:
  - on `main`'s code with the original PDF and EPUBs, before the container is rebuilt with this
    branch;
  - on this branch with the Markdown books.

  The two images MUST be built from the same lock, apart from this feature's change
  (`research.md`, R10). The two runs MUST be compared question by question, paired by question
  ID, with the project's paired bootstrap (4,000 resamples, 95%). Each run judges relevance
  against its own books' evidence quotes.
  - **Evidence found nowhere.** A question none of whose evidence resolves to a chunk, in either
    run, is left out of the pairing and counted.
  - **Evidence partly found.** A quote that resolves to no chunk while the question's others do
    counts as missed, as today, by the same rule in both runs.

  Both runs and their comparison MUST be recorded in `docs/benchmark-results.md`, as information
  and not as a verdict, since the owner has already decided the format. A difference whose
  interval excludes zero MUST be named, along with the questions behind it: those whose metric
  moved the same way. For each, the record says whether its evidence was found in each run, and
  what was retrieved instead.
- **FR-021**: A benchmark result MUST record the dataset's checksum as today. That checksum
  hashes `books.yaml`, the questions and the key points, and `books.yaml` holds each Markdown
  book's checksum, which the run checks first (FR-018). So a result's dataset checksum identifies
  the books it was measured on.

#### Records

- **FR-022**: `README.md` MUST describe a library of Markdown books: how to add one, how to
  prepare one (converted outside the application, named as the book should be titled, headings
  for chapters and sections, and optional front matter for the language), what is read from it,
  and what is refused.
  Its citations, passages and the `search` command MUST be described without pages. It MUST NOT
  describe PDF, EPUB, OCR or Docling as part of the system. The benchmark's section MUST say how
  its books are made (FR-018), in place of `fetch-benchmark-books`. It MUST say that a book's
  title comes from its file's name, so a book copied into the container keeps its name on the
  way.
- **FR-023**: `docs/decisions.md` MUST record the decision and its reason, and that it departs
  from the first version's spec. It also records why pages were dropped rather than read from
  markers in the Markdown, and why the benchmark's books record how they were converted.
  Decisions that explain only the removed readers MUST move to a closing section, "Removed with
  PDF and EPUB (v1.0.0)", shortened to one line each: the decision and the failure that taught
  it. They are:
  - running heads recognized by their page numbers;
  - each table-of-contents entry claiming one heading;
  - a heading the outline names never taken for a running head;
  - Docling, with OCR, as the alternative PDF reader.

  A lesson that still applies anywhere stays where it is. *Think Python*'s coverage lesson stays
  under Evaluation, beside the Docling comparison, since both are metrics hiding a loss. "What an
  operation counts" is updated where it is, since extraction is no longer counted. "Questions
  don't point to their passage" stays as it is.
- **FR-024**: Principle VII of the constitution MUST be amended through `/speckit-constitution`
  before the plan, so that citations resolve to the book, chapter and section, without pages
  (FR-014).
- **FR-025**: The pull request's title MUST be a breaking `feat!:`, and its description MUST end
  with a `BREAKING CHANGE` footer that the squash commit keeps. The footer lists what was
  removed:
  - PDF and EPUB input, OCR and Docling;
  - pages in citations, passages and quiz pointers, and `search`'s `--page-start` and
    `--page-end`;
  - the book's title from front matter or a heading, and its author;
  - `fetch-benchmark-books` and the `extraction` experiment kind;
  - the removed settings, which stop the app at startup if they are still there: `pdf`, the
    whole `normalization` section and `chunking.preserve.page_numbers`;
  - in benchmark results, the `relevant_pages` and `pages` columns. In the dataset's `books.yaml`,
    Markdown files, with the original's `url` moved under `original` and a `conversion` record.

  The release is v1.0.0.

### Key Entities

- **Book original**: the Markdown file the owner adds, identified by its checksum and stored as
  it arrived. It is the only kind of original the library holds.
- **Book**: its title is its original's file name without the extension, and its author is
  empty. Everything else is as today.
- **Benchmark book**: one of the dataset's three books. It is now a Markdown file with its
  checksum, plus where it came from: the original's URL and checksum, and the conversion
  (FR-018). Its `title` and `author` name it in the benchmark's messages and its provenance. The
  library never reads them: a benchmark workspace titles the book by its file name, as it does any
  book.
- **Evidence quote**: a verbatim passage of a benchmark book that holds a question's answer. It
  is now verbatim in the Markdown text.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: The three converted benchmark books are added through the Library tab and with
  `add-book` without an error. Each one's chapters, as the Summaries tab lists them, are the
  chapters its Markdown headings mark, checked by reading the list against the file.
- **SC-002**: The chapters, sections and chunk texts are identical, in the same order, on
  `main`'s image and this branch's, under the default configuration (`research.md`, R12). This
  holds for:
  - the three converted benchmark books, and the owner's `01_historia_economica_global.md`;
  - the unit tests that check a Markdown file's chapters, sections or chunk texts
    (`test_markdown_loader`, `test_pipeline`, `test_chunker`, `test_structure_extractor`,
    `test_html_blocks`), which keep `main`'s expected values.

  Left out of both comparisons: page fields, which on `main` are empty for Markdown and here no
  longer exist (FR-014); the title and the author (FR-005); and the title of a heading-less
  file's only chapter, which is the book's title.
- **SC-003**: A PDF and an EPUB are refused in each of the four ways in (tab add, tab replace,
  `add-book`, `replace-book`), each within a second of the click or of the command's start.
  Afterwards, these are as they were before the attempt, compared as the unit tests' library
  snapshot compares them: the catalog's rows, the journal's entries, the index's chunks, and the
  files under the library's data directory.
- **SC-004**: The image no longer contains Docling, PyMuPDF or EbookLib, and is smaller than
  `main`'s image, built from `main`'s commit and lock (`research.md`, R10). `docs/decisions.md`
  records both sizes and the packages the lock dropped.
- **SC-005**: Outside `docs/decisions.md`, `docs/benchmark-results.md`, `specs/`, the
  constitution's Why sections, the bug and assessment records under `.specify/`, and `uv.lock`,
  the repository mentions PDF, EPUB, OCR, Docling, PyMuPDF or EbookLib only where it says that
  books are converted to Markdown outside the application, or that those formats are refused.
  `uv.lock` names none of the removed packages. Nor do `README.md`, the commands' help or the
  Library tab describe a book's page, page range or page number, except the quiz's rule that a
  question doesn't name one (FR-016).
- **SC-006**: `make test` and `make test-integration` pass, and `doctor` reports no failure on
  the running stack.
- **SC-007**: `validate-benchmark` passes on the Markdown dataset with all 75 answerable
  questions kept, and both retrieval runs of FR-020 are recorded with their paired comparison.
- **SC-008**: On the running stack, these are read on the owner's
  `01_historia_economica_global.md` and on one converted benchmark book:
  - three answers in the Chat tab, with their sources, passages and scores table;
  - one `ask` and one `search`;
  - one saved chapter summary;
  - one chapter quiz.

  None shows a page, and every citation reads as book, chapter and, when the passage has one,
  section.

## Assumptions

- **No book needs migrating.** `make up` empties the library after any change to the code
  (Context), so the catalog never holds a PDF or EPUB book under the new code. A library whose
  catalog still named one would come only from data kept across containers, which the
  constitution forbids. The same goes for what was derived from the books, the processed files
  and the saved summaries, which live in the app container too. ChromaDB's old collections
  outlive it, which is why `reset-everything` comes first (FR-015).
- **The application doesn't check how a file was made.** Any UTF-8 Markdown file is accepted,
  from MarkItDown or not, and the conversion's quality is the owner's to judge. The benchmark of
  FR-020 shows what it changes on the dataset's books.
- **MarkItDown's output is read as it is.** No rule is added for its quirks. If the dataset's
  books show any (headings it doesn't mark, for example), they are reported as follow-ups and not
  fixed in this feature, which keeps Markdown reading as it is (FR-005).
- **What the owner provides, and when.**
  - **Before the image is rebuilt with this branch's code**: the three converted books in
    `benchmarks/books` on the host, under names the owner chooses, which `books.yaml` records.
    With them comes the conversion record: MarkItDown's version, each plugin's name and version,
    and any options (FR-018). Proving the chunks unchanged reads the books on `main`'s code,
    which that rebuild replaces. The code and the unit tests don't need them.
  - **Before the pull request**: a PATCH amendment of the constitution through
    `/speckit-constitution`, which the owner starts. Its Development Workflow names `c7bb785` as
    the dataset's last version, and the amendment names `specs/005-markdown-only/benchmarks/`
    instead (R19).
- **The pending dependency bump stays out.** The uncommitted bump of `.pre-commit-config.yaml` and
  `uv.lock` stays stashed for the whole feature. So `main`'s image for the baselines and this
  branch's image differ only by this feature. The bump is redone as its own `chore:` after this
  feature merges (R10).
- **Only the retrieval experiment is measured**, because it needs no judge and covers what a
  different text changes first: which passages are found. The generation and summarization
  benchmarks can be run again later on the Markdown dataset, whose key points then name the
  Markdown chapters (FR-019). Their earlier results stay as they are, measured on PDF and EPUB.
  `extraction.yaml` is deleted from the host's experiments. A regression in citations or
  abstentions would show in two places: `make test-integration`'s abstention cases, and SC-008's
  reading. A Markdown book's prompts are the same as on `main` apart from its title, and no parser
  changes.
- **The quiz is removed by the next feature.** The owner decided on 2026-11-19 that the quiz
  goes next, since they don't use it. Until then it keeps working.
  - **Its prompts**, and its check for questions that can be answered without reading, now get
    the file name and no author. That is already what the owner's books get, since their
    conversions have no front matter. The prompts' wording doesn't change.
  - **The check isn't proved again**, since the quiz goes next.
  - **Its benchmark experiments** stay on the host as they are, still naming the PDF of *História
    econômica global*, and aren't run.
- **The specs of delivered features are history.** `specs/001` to `specs/004` mention PDF and
  EPUB and are not edited (Principle VIII).
