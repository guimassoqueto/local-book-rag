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

Removing a format can't strand a book. Any change to the code or the configuration empties the
library at the next `make up`, because nothing lives outside the containers (constitution,
Principle II). So no stored PDF or EPUB can outlive this change.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Adding books as Markdown, and only as Markdown (Priority: P1)

The owner converts a book with MarkItDown and adds the `.md` file in the Library tab, or with
`add-book`. It goes in as a Markdown book does today: same chapters, sections, chunks, title,
author and language. Replacing a book works the same way. If the owner picks a PDF or an EPUB by
mistake, it is refused before anything is stored, with a message saying to convert the book to
Markdown first. The tab's file pickers offer only Markdown files.

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
   with a message that names the format and says to convert the book to Markdown first, and the
   book being replaced stays as it was.
3. **Given** a file of any other type, **When** the owner adds it, **Then** it is refused as
   today, with the accepted types listed, which are now `.md` and `.markdown`.
4. **Given** the Library tab, **When** the owner opens either file picker, **Then** it offers
   only `.md` and `.markdown` files, and its label names Markdown alone.
5. **Given** a book in the library, **When** the owner processes it again from its original or
   reindexes the library, **Then** it works as today, since every original is Markdown.

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
2. **Given** a `config/ingestion.yaml` that still has a `pdf` section,
   `normalization.remove_repeated_margins` or `chunking.preserve.page_numbers`, **When** the app
   starts, **Then** it stops with an error that names the key, as for any unknown key.
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
benchmark runs on them in a fresh workspace. Its results are recorded next to the last ones,
measured on the PDF and EPUBs, so that the owner can see what the conversion changed. The
extraction experiment goes, because what it measured was the PDF extractors and the originals'
tables of contents.

**Why this priority**: Without Markdown books, no benchmark can run, and every later comparison
of models or retrieval strategies depends on it. Removing the formats comes first, though: until
then, the benchmark still runs on the old code.

**Independent Test**: Run `validate-benchmark` on the Markdown dataset, then the retrieval
experiment on a fresh `benchmarks/workspace`, and read the report next to the PDF and EPUB
results in `docs/benchmark-results.md`.

**Acceptance Scenarios**:

1. **Given** the dataset's three books converted to Markdown, **When** `validate-benchmark`
   runs, **Then** every evidence quote is found in its book exactly as written. Quotes the
   conversion changed are corrected to the Markdown text and still prove the same answer.
2. **Given** the Markdown dataset and a fresh workspace, **When** the retrieval experiment runs,
   **Then** it completes, and its result records the dataset's checksum, which now covers the
   Markdown books.
3. **Given** the retrieval results on Markdown, **When** they are recorded, **Then**
   `docs/benchmark-results.md` shows them next to the last PDF and EPUB results, for information,
   and says that the books, not the system, changed between the two.
4. **Given** an experiment of the removed `extraction` kind, **When** it is run, **Then** it is
   refused as an unknown kind, and the extraction results recorded so far stay in
   `docs/benchmark-results.md` as history, marked as measured on PDF and EPUB.

---

### Edge Cases

- **An uppercase extension** (`BOOK.MD`) is accepted, because extensions are compared without
  case, as today.
- **A PDF or EPUB renamed to `.md`** is refused as binary data or as not UTF-8, as any Markdown
  file is today, and nothing is stored.
- **A Markdown file without headings** is accepted, as today. It becomes a single chapter, "Full
  text", which leaves summaries and quizzes by chapter with one chapter to choose.
- **A Markdown file without front matter** takes its title from its only top-level heading, or
  else from the file name. Its language is detected from the text and its author is unknown, as
  today.
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

## Requirements *(mandatory)*

### Functional Requirements

#### Accepting books

- **FR-001**: The library MUST accept a book only as a file with the `.md` or `.markdown`
  extension, compared without case, in the Library tab (adding and replacing) and in the
  `add-book` and `replace-book` commands.
- **FR-002**: A `.pdf` or `.epub` file MUST be refused before anything is stored or journaled.
  The message names the format and says to convert the book to Markdown first, and may name
  MarkItDown as an example. Replacing a book with one leaves the book as it was.
- **FR-003**: A file with any other extension MUST be refused as today, with the accepted
  extensions listed.
- **FR-004**: The Library tab's file pickers MUST offer only `.md` and `.markdown` files. Their
  labels, the commands' help and the error messages MUST name Markdown as the only format.
- **FR-005**: Reading a Markdown book MUST stay as it is today:
  - **the checks**: the size limit, an empty file, binary data, and UTF-8;
  - **the metadata**: title, author and language from front matter, or a single top-level
    heading as the title, or the file name;
  - **the structure**: headings as structure, the rules that find chapters and sections, the
    cleaning that applies to any text (Unicode normalization, ligatures, invisible characters,
    whitespace), language detection and chunking.

  The same file with the same configuration MUST give the same chapters, sections and chunk
  texts, in the same order, as on `main` (SC-002).
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
  parsing that reads Markdown.
- **FR-010**: Code, tests, test helpers, development tools, comments and settings that served
  only PDF or EPUB MUST be removed. A test that checks something independent of the format
  through a PDF or an EPUB MUST be rewritten with Markdown, so that what it checks is still
  checked.
- **FR-011**: The progress of adding, replacing or processing a book again MUST show its
  extraction stage without a count, as a Markdown book's extraction shows today. The page unit
  and the OCR state MUST go from the progress reporting.
- **FR-012**: `doctor` MUST NOT mention Docling. Its GPU check names only what still uses the
  GPU in the application, the reranker.
- **FR-013**: Everything else MUST be left as it was: questions, summaries, quizzes, retrieval,
  the library's operations and their confirmations. Pages are the one exception (FR-014 to
  FR-016).

#### Pages

- **FR-014**: Pages MUST be removed everywhere a book's pages appear or are used:
  - **what the reader sees**: citations in answers and summaries, the passages shown in the Chat
    tab and by `search` and `ask`, and the quiz's passage pointers;
  - **the prompts**: the passage header sent to the model;
  - **the filters**: the `search` command's page range and the page filter in retrieval;
  - **the index**: the chunk metadata (`page_start`, `page_end`), the setting
    `chunking.preserve.page_numbers`, and the cleaning that rejoins a paragraph cut by a page
    break;
  - **the benchmark**: its rows' page column.

  A citation then resolves to the book, chapter and section. A configuration that still holds
  `chunking.preserve.page_numbers` MUST stop the app at startup, naming the key.
- **FR-015**: Removing the page fields and the page setting changes the chunk metadata's schema
  and the chunking settings, both of which are in the index fingerprint. The fingerprint MUST
  change accordingly, and an index built before MUST be treated as any index whose configuration
  changed: `doctor` reports it, new books are refused, and `reindex-all` builds a new index
  version (Principle III). On a fresh `make up` the library is empty, so the first index is built
  under the new fingerprint.
- **FR-016**: The quiz's check that refuses a question pointing at a page, a passage number or
  "the excerpt" MUST stay as it is. It reads what the model writes, which can still name a page,
  and doesn't depend on the books having pages.

#### Benchmarks

- **FR-017**: The `extraction` experiment kind and its metrics MUST be removed (TOC coverage,
  chapters, chunks, pages covered), and with them the experiment that compares the PDF
  extractors. An experiment of that kind MUST be refused as unknown. The extraction results
  recorded so far MUST stay in `docs/benchmark-results.md`, marked as history measured on PDF and
  EPUB.
- **FR-018**: The benchmark dataset's three books MUST be Markdown files that the owner converts
  with the same MarkItDown setup as their own books. For each book, the dataset MUST record:
  - the Markdown file's name and checksum, which the benchmark checks before it runs, as it
    checks the originals today;
  - for provenance, the original's URL and checksum, and the conversion used (MarkItDown's
    version and the plugins, as the owner names them).

  `fetch-benchmark-books` MUST be removed, because the application can't read the files it
  downloads. The dataset's description MUST say that rebuilding the books takes the same
  conversion, so the questions hold only for files with the recorded checksums.
- **FR-019**: Every evidence quote in the dataset MUST be found in its Markdown book by
  `validate-benchmark`. A quote the conversion changed MUST be corrected to the Markdown text,
  holding the same evidence for the same answer. A question is never dropped to make the
  validation pass. If a quote can't be corrected, `docs/benchmark-results.md` says which, and why.
- **FR-020**: The retrieval experiment's default variant MUST be run on the Markdown dataset in
  a fresh `benchmarks/workspace`. Its result MUST be recorded in `docs/benchmark-results.md` next
  to the last results measured on PDF and EPUB, as information and not as a verdict, since the
  owner has already decided the format. A difference whose paired interval excludes zero MUST be
  named, along with the questions behind it.
- **FR-021**: A benchmark result MUST record the dataset's checksum as today. Since the dataset
  now names Markdown files, the checksum covers the books the questions were validated against.

#### Records

- **FR-022**: `README.md` MUST describe a library of Markdown books: how to add one, how to
  prepare one (converted outside the application, front matter recommended for the title, author
  and language, headings for chapters and sections), what is read from it, and what is refused.
  Its citations, passages and the `search` command MUST be described without pages. It MUST NOT
  describe PDF, EPUB, OCR or Docling as part of the system. The benchmark's section MUST say how
  its books are made (FR-018), in place of `fetch-benchmark-books`.
- **FR-023**: `docs/decisions.md` MUST record the decision and its reason, and that it departs
  from the first version's spec. It also records why pages were dropped rather than read from
  markers in the Markdown, and why the benchmark's books record how they were converted. Its
  decisions that explain only the removed readers, such as running heads, outline matching and
  the Docling comparison, MUST no longer read as part of the current system. A lesson that still
  applies, such as a metric hiding a loss, stays.
- **FR-024**: Principle VII of the constitution MUST be amended through `/speckit-constitution`
  before the plan, so that citations resolve to the book, chapter and section, without pages
  (FR-014).

### Key Entities

- **Book original**: the Markdown file the owner adds, identified by its checksum and stored as
  it arrived. It is the only kind of original the library holds.
- **Benchmark book**: one of the dataset's three books. It is now a Markdown file with its
  checksum, plus where it came from: the original's URL and checksum, and the conversion
  (FR-018).
- **Evidence quote**: a verbatim passage of a benchmark book that holds a question's answer. It
  is now verbatim in the Markdown text.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: The three converted benchmark books are added through the Library tab and with
  `add-book` without an error. Each one's chapters, as the Summaries tab lists them, are the
  chapters its Markdown headings mark, checked by reading the list against the file.
- **SC-002**: For the three converted benchmark books and every Markdown file used in the tests,
  the chapters, sections and chunk texts are identical, in the same order, between `main` and
  this branch, under the default configuration. Page fields are left out of the comparison: on
  `main` they are empty for Markdown, and here they no longer exist (FR-014).
- **SC-003**: A PDF and an EPUB are refused in each of the four ways in (tab add, tab replace,
  `add-book`, `replace-book`), each within a second. Afterwards, the catalog, the journal, the
  index and the library's files are as they were before the attempt.
- **SC-004**: The image no longer contains Docling, PyMuPDF or EbookLib, and is smaller than
  `main`'s. The image sizes of both are recorded in the plan's results.
- **SC-005**: Outside `docs/decisions.md`, `docs/benchmark-results.md` and `specs/`, the
  repository mentions PDF, EPUB, OCR, Docling, PyMuPDF or EbookLib only where it says that books
  are converted to Markdown outside the application, or that those formats are refused.
- **SC-006**: `make test` and `make test-integration` pass, and `doctor` reports no failure on
  the running stack.
- **SC-007**: `validate-benchmark` passes on the Markdown dataset with all 75 answerable
  questions kept, and the retrieval run of FR-020 is recorded with its comparison.
- **SC-008**: On the running stack, after `make test-integration`'s questions, summaries and
  quizzes, no answer, summary, quiz pointer or passage shown carries a page, and every citation
  still resolves to its book, chapter and section.

## Assumptions

- **No book needs migrating.** `make up` empties the library after any change to the code
  (Context), so the catalog never holds a PDF or EPUB book under the new code. A library whose
  catalog still named one would come only from data kept across containers, which the
  constitution forbids.
- **The application doesn't check how a file was made.** Any UTF-8 Markdown file is accepted,
  from MarkItDown or not, and the conversion's quality is the owner's to judge. The benchmark of
  FR-020 shows what it changes on the dataset's books.
- **MarkItDown's output is read as it is.** No rule is added for its quirks. If the dataset's
  books show any (headings it doesn't mark, for example), they are reported as follow-ups and not
  fixed in this feature, which keeps Markdown reading as it is (FR-005).
- **The owner provides the three converted books** before the benchmark's tasks, and the
  conversion record that goes with them (FR-018). The plan's tasks wait for them there, and
  nothing before those tasks needs them.
- **Only the retrieval experiment is measured**, because it needs no judge and covers what a
  different text changes first: which passages are found. The generation, summarization and quiz
  benchmarks can be run again later on the Markdown dataset. Their earlier results stay as they
  are, measured on PDF and EPUB.
- **The removal is a breaking change.** Anyone who adds PDFs or EPUBs loses that ability, so the
  pull request's title is expected to be `feat!:`, which the release workflow treats as a major
  release.
- **The specs of delivered features are history.** `specs/001` to `specs/004` mention PDF and
  EPUB and are not edited (Principle VIII).
