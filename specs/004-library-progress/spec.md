# Feature Specification: The progress of library operations

**Feature Branch**: `feat/library-progress`

**Created**: 2026-11-12

**Status**: Draft

**Input**: User description: "Show the progress of every library operation in the Library tab:
adding a book, replacing it, processing it again from its original, removing it, reindexing the
library, resetting the index and resetting everything. The services report structured progress
(stage, items done, items total), and the Library tab and the commands only display it. Countable
stages show a count and an estimate of the time left within the stage: pages or files while
extracting, chunks while embedding, books and saved summaries while reindexing the library. Stages
that can't be counted (OCR, removal, resets) show what is happening without a percentage. The
tab's buttons are disabled while an operation runs. Reporting progress never changes what an
operation does, how it fails, or what its journal records. Out of scope: stopping an operation
midway, and showing operations started by another process."

## Context

The owner asked for a loader in the Library tab that shows how much is left of each operation
that changes the library. Today the tab gives no measure of progress: adding, replacing,
processing a book again and reindexing the library report what they are doing with the progress
held at zero, and removing a book and the two resets report nothing until they end. On the
command line, `reindex-all` prints a line per book, and the other commands print nothing until
they end.

How long the stages take decides what is worth counting. Each stage was timed on 2026-11-12, in
the app container, on the four benchmark books, with the default configuration (PyMuPDF with
tables, no OCR, `qwen3-embedding:0.6b` on the GPU in batches of 16), writing nothing to the
library, the catalog or ChromaDB:

| Book                        | Format | Pages | Passages | Extraction  | Cleaning, structure, passages | Embedding     |
| --------------------------- | ------ | ----- | -------- | ----------- | ----------------------------- | ------------- |
| *Think Python*              | PDF    | 244   | 425      | 22.2–22.5 s | under 0.1 s                   | 5.5 s, 16.6 s |
| *História econômica global* | PDF    | 212   | 258      | 14.5–14.9 s | under 0.1 s                   | 4.4 s         |
| *On Liberty*                | EPUB   | –     | 176      | under 0.1 s | 0.1 s                         | 3.0 s         |
| *Quincas Borba*             | EPUB   | –     | 454      | 0.1 s       | 0.2 s                         | 6.7 s         |

- **A PDF's extraction is the longest stage of adding one**, at 0.07 to 0.09 s a page, and its
  pace is steady from page to page.
- **Embedding goes at 0.2 to 0.3 s a batch, but a batch can stall.** In the first run, one of
  *Think Python*'s 27 batches took 8.4 s, and the stage 16.6 s; in the second, no batch took over
  0.26 s, and the stage 5.5 s. An estimate made from the first batches alone can be several
  times off.
- **An EPUB's extraction takes a tenth of a second**: a count of its files would be gone before
  it could be read.
- **Books differ ten-fold**: from 3.1 s for *On Liberty* to 28 or 39 s for *Think Python*, so the pace
  of the books done so far says little about the ones left. Saved summaries differ the same way:
  gpt-oss takes 104 s for a chapter on average (`docs/benchmark-results.md`, Summarization), and
  chapters differ several times in length.
- **Removing a book and the resets delete** vectors, files and catalog rows, which takes moments,
  not minutes.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Adding, replacing or processing a book again, with how much is left (Priority: P1)

The owner adds a book in the Library tab. A progress area, visible without opening any section,
shows the operation and the stage it is in, such as "Extracting the text, stage 2 of 5", with
"130 of 244 pages" on a bar that fills, the time left once the stage has a pace, and the time since
the operation began. The next stage, embedding the passages, counts passages the same way. While
it runs, the tab's buttons can't start another operation. When it ends, the area says how it
ended: the book added, with its chapters and passages, or the stage it failed at and why.
Replacing a book and processing it again from its original show the same stages, plus the swap to
the new version.

**Why this priority**: Adding a book is what the owner does most, and the longest operation on a
single book. It also builds what every other story uses: the progress area, the stages and the
disabled buttons.

**Independent Test**: Add *Think Python* through the Library tab and watch the area: the stages
in order, pages counting to 244, passages counting to 425, a time left that appears once a stage
has a pace, buttons disabled until the end, and the outcome line. Then process it again, and
replace it with another document, and see the same.

**Acceptance Scenarios**:

1. **Given** a PDF, **When** the owner adds it, **Then** the area shows, in order, storing the
   file, extracting the text (counting pages), preparing the passages, embedding them (counting
   passages) and saving them to the index, each with its position among the stages.
2. **Given** a countable stage that has run long enough to have a pace, **When** the area
   updates, **Then** it shows the time left in that stage, and it never shows one from the
   stage's first items alone.
3. **Given** an EPUB or a Markdown file, **When** the owner adds it, **Then** extracting the text
   shows no count, and embedding counts passages.
4. **Given** a scanned PDF and OCR switched on, **When** the owner adds it, **Then** reading its
   pages counts them, and the OCR that follows shows that it is running, without a count.
5. **Given** an operation running from the tab, **When** the owner looks at the tab's buttons,
   **Then** none of the seven can start another operation, and all of them can once it ends,
   whether it succeeded, failed or was refused.
6. **Given** a stage that fails, **When** the operation ends, **Then** the area says at which
   stage it failed and why, and the library is exactly as the same failure leaves it today.
7. **Given** an operation that is refused before it starts (no file chosen, the same file already
   in the library, another operation running), **When** the owner starts it, **Then** the refusal
   is shown as today, and no stage is.
8. **Given** a book being replaced or processed again, **When** its new version is indexed,
   **Then** the area shows the same stages as adding it, and then the swap to the new version.

---

### User Story 2 - Reindexing the library, book by book (Priority: P2)

The owner reindexes the library. The area shows which book is being indexed, such as "Book 2 of
5: *Quincas Borba*", with that book's own stage and its count, then the switch to the new index,
then, if chosen, the saved summaries being written again, such as "Summary 3 of 7", with what the
summary is doing. Questions keep working on the current index meanwhile, and the area says so.
When it ends, it says what the reindex did: the index version, the books and passages, the books
that still fail, and the summaries that couldn't be written.

**Why this priority**: It is the longest operation by far, a sum of every book and, with
summaries, minutes for each one. It is also the one that changes the embedding model or the
chunking, so the owner runs it after every such change.

**Independent Test**: With the four benchmark books in the library and two saved summaries,
reindex the library with summaries and watch the area: books counting to 4 with each one's stages,
the switch, summaries counting to 2, and the outcome line matching the report.

**Acceptance Scenarios**:

1. **Given** a library of N books, **When** the owner reindexes it, **Then** the area shows each
   book in turn as k of N, with its title and its own stages and counts.
2. **Given** a book with no working version that fails during the reindex, **When** the reindex
   goes on, **Then** the area shows the next book, and the outcome line names the books that
   still fail.
3. **Given** saved summaries and the option to write them again, **When** the books are done,
   **Then** the area shows the switch to the new index, then summaries counting to their total,
   each with what it is doing.
4. **Given** a reindex counting books or summaries, **When** the area updates, **Then** it shows
   the count and the time elapsed, and no time left for the whole stage (Assumptions).
5. **Given** originals kept by a reset of the index, **When** the owner reindexes, **Then** the
   area shows them being brought back, and they count among the books.

---

### User Story 3 - Removing a book and resetting, without a guess (Priority: P3)

The owner removes a book, resets the index or resets everything. The area shows each step as it
happens, such as deleting the book's passages from the index, its processed documents, its
summaries, its original or moving it to the archive, and removing it from the catalog, without a
count or a percentage. When it
ends, it says what was removed.

**Why this priority**: These take moments, so a measure of progress adds little. What matters is
the same feedback and the same disabled buttons as the other operations, so the tab behaves one
way.

**Independent Test**: Remove a book, then reset the index, then reset everything, and check that
each shows its steps without a count, disables the buttons while it runs, and ends with its
outcome line.

**Acceptance Scenarios**:

1. **Given** a book and its ID typed as confirmation, **When** the owner removes it, **Then** the
   area shows its steps and ends saying the book was removed, and whether its original was
   archived.
2. **Given** the confirmation of either reset, **When** the owner runs it, **Then** the area
   shows its steps and ends saying what is gone and what was kept.
3. **Given** a missing or wrong confirmation, **When** the owner starts the operation, **Then**
   it is refused as today, and no step is shown.

---

### User Story 4 - The same progress on the command line (Priority: P4)

The owner runs `add-book`, `replace-book`, `reindex-book`, `remove-book`, `reindex-all`,
`reset-index` or `reset-everything`. The terminal shows the same stages and counts as the tab,
without a line per page or passage, and the command's result as today.

**Why this priority**: The commands call the same operations, so they get the progress at little
cost, and a long `reindex-all` from the terminal stops being silent between books.

**Independent Test**: Run `add-book` with *Think Python* and `reindex-all` in the container, and
check the lines against the tab's stages, their number against the bound in FR-014, and the
result line against today's.

**Acceptance Scenarios**:

1. **Given** any of the seven commands, **When** it runs, **Then** each stage it reaches prints a
   line as it starts, and a countable stage prints its count from time to time and when it ends.
2. **Given** a command whose standard output is read by a script, **When** it runs, **Then** the
   progress goes to the error stream, and standard output holds only what it holds today.

---

### Edge Cases

- **An operation from another process or another browser page.** The lock refuses the new one
  as today ("another operation is running"), and its progress isn't shown (out of scope).
- **The page is reloaded, or the browser closed, during an operation.** The operation runs to its
  end, unaffected. The reloaded page shows no progress for it, and refuses a new operation as
  busy until it ends.
- **A stage too fast to read**, such as removing a book or preparing the passages. It may flash
  by; the outcome line stays after the operation ends.
- **A PDF found to be scanned after its pages are read.** Without OCR, it fails at extraction as
  today, and the area says so. With OCR, the stage changes to OCR, without a count.
- **A document with no text after cleaning.** It fails at preparing the passages, as today.
- **A reindex of an empty library.** Refused before any stage, as today.
- **A summary that fails during a reindex.** The count goes on, and the outcome line lists it, as
  the warning does today.
- **The application stopped or restarted during an operation.** The operation stops with it, as
  today: the thread it runs in doesn't keep the process alive. Recovery finishes or undoes it at the
  next start, as today. The new page shows nothing of it.
- **A second click during an operation.** It can't start anything while the buttons are
  disabled; one from another page is refused as busy.

## Clarifications

### Session 2026-11-12

- Q: Should the time left cover only the current stage, or also the books and summaries left, or
  the whole operation? → A: Only the current stage (pages, passages). Books and summaries show
  their count and the time elapsed, without a time left.
- Q: Should the progress area have a bar that fills, or is text with the counts and times enough?
  → A: A bar that fills with the count in a countable stage, and a moving indicator that doesn't
  fill in a stage without one, with the text in both.
- Q: Should the application's log record the end of each stage, with its name, count and
  duration? → A: Yes, one line per stage, among the lines the operation already logs.
- Q: Should extracting an EPUB or a Markdown file show only the stage's name, without counting
  files? → A: Yes. Only a PDF's extraction counts pages.
- Q: Should the tab's list of books refresh during an operation, as each book's status changes, or
  only when it ends, as today? → A: Only when it ends, as today.

### Corrections during planning, 2026-11-12

- **Adding a book starts with storing the file, not checking it.** The checks that can refuse an
  addition (a busy library, a duplicate, an index that needs a reindex) run before the progress
  begins (`research.md`, R9), so a refused file shows no stage, as User Story 1's scenario 7 asks.
  When the file retries a book that failed before, removing that failed attempt comes before the
  progress begins too: it runs in its own journal entry, before the addition's operation, and
  takes moments (corrected by the requirements checklist, CHK003).
- **A reindex brings kept originals back before its checks**, as it does today, and that order
  stays (FR-011). So that stage is reported already done when the progress begins, with the number
  of originals brought back.

### Corrections from the requirements checklist, 2026-11-12

`checklists/lifecycle-and-measurement.md` found gaps and conflicts, resolved here and in the plan.
- **Nothing in the progress raises into an operation** (FR-012): a stage that wasn't declared is
  logged, not raised, since `add_book` would turn any exception into a failed book.
- **Removing an earlier failed attempt is no longer a stage** (FR-007): it runs before the
  addition's operation and journal entry, where its log line couldn't belong to the operation.
- **A failed reindex names the book and its step** (FR-004).
- **The area shows "starting"** while an operation runs its checks (FR-003, SC-001), and a refusal
  empties it.
- **Times and counts have set forms** (FR-002, FR-006, FR-010): elapsed as 0:38, time left rounded,
  counting down between advances, "0 of 0" for an empty stage, an advance past the total held.
- **The criteria are measurable as written**: SC-003's sampling, SC-004's "identical", SC-005's
  baseline and statistic, SC-006's "today", SC-009's sum of top-level stages.
- **The equivalence of FR-011 is verified** by comparing each operation with and without progress,
  and `research.md` R15 says what a crash in each stage leaves.

## Requirements *(mandatory)*

### Functional Requirements

#### What the tab shows

- **FR-001**: The Library tab MUST have a progress area, visible without opening any of its
  sections, for the seven operations: adding a book, replacing it, processing it again from its
  original, removing it, reindexing the library, resetting the index and resetting everything.
- **FR-002**: While an operation runs, the area MUST show: the operation, and its book when it
  has one; the current stage by name, and its position among the operation's stages; for a
  countable stage, the items done of the total, with their unit (pages, passages, books,
  summaries); the time left in the stage where FR-006 allows one; and the time since the
  operation began. A countable stage MUST also show a bar that fills with its count, and a stage
  without a count an indicator that moves without filling, so that no bar suggests a share it
  doesn't have. The elapsed time MUST read as minutes and seconds (0:38), with hours past an hour
  (1:02:05). The time left MUST read "about N s left" under a minute, N rounded up to a multiple
  of 5, and "about N min left" from a minute on, N rounded to the nearest minute.
- **FR-003**: The area MUST change within 1 second of an operation starting, and at least once a
  second while it runs, the elapsed time included, so that a stage without a count still shows
  the operation is alive. Until the operation's progress begins, while it runs the checks that can
  refuse it, the area MUST show that the operation is starting, with the moving indicator.
- **FR-004**: When an operation ends, the area MUST say how: what it did, as today's notification
  says it, or the stage it failed at and why. A reindex that fails while indexing a book MUST also
  name the book and the step it failed in. That line stays until the next operation starts or the
  page is reloaded. An operation refused before its progress began leaves the area empty, the
  earlier line included, and shows its refusal as today. The notifications the tab shows today
  stay, and the list of books refreshes when the operation ends, as today, not during it.
- **FR-005**: While an operation started from the tab runs, the tab's seven buttons MUST NOT start
  another one, and all of them MUST be usable again once it ends, whether it succeeded, failed or
  was refused. The tab's inputs (the file, the book, the checkboxes and the confirmation boxes)
  stay editable: the running operation read its own when it started.

#### Counts and estimates

- **FR-006**: A countable stage MUST show a time left only once it has a pace, and never from its
  first items alone. The time left MUST come from the pace of the stage so far. A stage has a pace
  once it has run 3 seconds and done 10% of its items, a default the plan may tune against SC-003
  on the four benchmark books. Between two advances, the time left MUST count down with the time
  since the last one, and MUST NOT go below zero; at zero the area reads "almost done". A stalled
  batch, as in the Context, MUST NOT throw it off for the rest of the stage: in a stage whose
  advances keep one pace but for a single advance ten times slower, every time left shown after
  that advance MUST be within half and double the time actually left.
- **FR-007**: The stages of adding a book MUST be: storing the file; extracting the text, counting
  pages for a PDF read for its text, and without a count for OCR, an EPUB or a Markdown file;
  preparing the passages; embedding the passages, counting them; and saving them to the index.
  Replacing a book MUST show the same stages, and processing it again the same from extraction
  on, since it has no file to store; both then show the swap to the new version. The plan may name
  the stages differently, but not merge a countable one into another.
- **FR-008**: Reindexing the library MUST show: bringing back kept originals, when there are
  any; each book as k of N, with its title and its own stages of FR-007 from extraction to saving;
  the switch to the new index; and, when chosen, the saved summaries as s of S, each with the
  steps the summary reports. Books and summaries MUST be counted without a time left (Assumptions).
  The area MUST say that questions keep working meanwhile.
- **FR-009**: Removing a book, resetting the index and resetting everything MUST show their steps
  by name, without a count or a percentage.
- **FR-010**: A count MUST never go backwards within a stage, and MUST reach its total when the
  stage finishes. A count whose total is zero reads "0 of 0", with a full bar. An advance that
  would pass the total is held at the total and logged as a warning, never raised. A scanned PDF
  sent to OCR counts its pages to their total before OCR begins; the stage then drops its count
  and says it is running OCR.

#### What doesn't change

- **FR-011**: Reporting progress MUST NOT change what an operation does: its result, its errors,
  the library it leaves, its journal entries and what recovery does after a crash at any point.
  Each operation MUST make the same changes to the catalog, the journal, the stores and the files,
  in the same order, with progress and without it, which the unit tests compare, and the existing
  recovery tests MUST pass unchanged. `research.md`, R15, says what a crash in each stage leaves
  and how recovery finishes or undoes it.
- **FR-012**: A failure to show progress, such as a page closed or a terminal gone, MUST NOT fail
  or change the operation. It is logged, and the operation goes on. Nothing the progress does MUST
  raise into the operation, not even a mistake in reporting it, such as a stage that wasn't
  declared: that is logged as a warning, and a unit test holds every operation's stages to its
  declaration.
- **FR-013**: Reporting progress MUST NOT change what is extracted, prepared, embedded or stored,
  so the index's fingerprint is unchanged and no reindex is needed after this feature.

#### The commands

- **FR-014**: The seven commands MUST show the same stages and counts as the tab, on the error
  stream: a line when a stage starts, and for a countable stage a line with its count no more
  often than every 2 seconds, plus one when it ends. Standard output MUST hold only what it holds
  today, apart from `reindex-all`'s progress lines, which move to the error stream.

#### The log

- **FR-015**: Every stage an operation reaches MUST leave one line in the application's log when it
  ends, with its name, its count and total when it has them, and its duration, among the lines the
  operation already logs. A stage that fails leaves its line too, saying so. The line holds no
  text from the book. Recovery, which repairs interrupted operations when the lock is taken and
  before any progress begins, logs no stage lines: it keeps its own "interrupted operation
  repaired" lines.

#### Constraints from the constitution

- **FR-016**: The stages, counts, times left and outcomes MUST come from the operations
  themselves, in the service layer, and so MUST how often a display hears of them: a command sets
  the interval, the operation's progress keeps to it. The Library tab and the commands MUST only
  display them, and compute none (principle IV). Composing the line of a successful outcome from
  what the operation returned, as today's notifications are composed, and writing times and counts
  in the forms of FR-002, are display.
- **FR-017**: Every operation MUST keep running under the library lock and its journal entry as
  today, with the progress reported from inside them (principle II): it begins inside the lock,
  after the checks that can refuse the operation, and every stage that changes the library runs
  while the operation's journal entry is open, as the change itself does today.
- **FR-018**: The feature MUST be checked on the four benchmark books, real ones, for counts that
  reach their totals, for estimates against SC-003, and for processed documents and passages
  identical to today's (principle V).
- **FR-019**: `README.md` MUST describe the progress area, the commands' progress lines and the
  stage lines in the log, and `docs/decisions.md` MUST record what is counted, what isn't, and
  why, with this spec's measurements (principle VIII).

### Key Entities

- **Progress update**: what an operation reports as it runs. The operation and its book, the
  current stage and its position among the stages, the items done and their total and unit for a
  countable stage, the time left when there is one, and the time elapsed.
- **Stage**: a named part of an operation, such as extracting the text or embedding the passages.
  Either countable, with a unit and a total known when it starts, or not.
- **Outcome**: how an operation ended. What it did, or the stage it failed at and why, with the
  book and the step for a reindex.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: For each of the seven operations, the tab shows the operation within 1 second of the
  click, as starting while its checks run (FR-003), and its first stage within 1 second of its
  progress beginning.
- **SC-002**: On the four benchmark books, every count reaches its total (pages, the PDF's page
  count, also for a scanned PDF before OCR takes over; passages, the book's passage count; books,
  the library's; summaries, the saved ones whose chapter remains), and none goes backwards.
- **SC-003**: Over adding the four benchmark books, three times each, at least 90% of the times
  left are within half and double the time actually left in the stage, and none is shown before
  the stage has a pace. They are sampled every quarter of a second while a stage shows one, each
  sample counting once, so a long stage weighs more than a short one, as it does on screen.
- **SC-004**: Adding, replacing, processing again and reindexing the four benchmark books leaves
  processed documents and passages identical to today's: the same bytes in each book's extracted,
  normalized and passage files, when both runs make the same operations in the same order on an
  empty workspace, so that the books' IDs and revisions match. The journal entries are the same,
  apart from their IDs and times.
- **SC-005**: No operation on the four benchmark books takes longer than today by more than 5% or
  1 second, whichever is larger, comparing the median of three runs with the median of three runs
  of `main`'s code on the same books and machine. A reindex that writes summaries again is left
  out: its time is the model's writing.
- **SC-006**: A failure forced in each stage of each operation of `data-model.md`'s table, through
  what the stage depends on (the loader, the embedding model, the store, the files), leaves the
  library, the journal and recovery exactly as the same failure leaves them without progress, which
  stands for today, and the outcome names the stage.
- **SC-007**: While an operation runs from the tab, none of the seven buttons starts another; once
  it ends, by success, failure or refusal, all seven work again within 1 second.
- **SC-008**: Each command prints a line per stage it reaches, and no more than one count line
  every 2 seconds for a stage, plus its last.
- **SC-009**: For each operation on the four benchmark books, the log holds one line per stage
  reached, steps included, and the durations of its top-level stages add up to the operation's
  logged duration within 1 second.

## Assumptions

- **Books and summaries are counted without a time left**, a departure from the description that
  the owner confirmed (Clarifications): the books took from 3.1 to 39 s each, and summaries differ
  with their chapters' length, so the pace of those done says little about those left. The
  current book's or summary's own stages give the time left where they can. A time left for the
  whole operation, from paces kept from earlier operations on this machine, was left out: it would
  keep data across operations, which this feature doesn't. The stage lines in the log (FR-015) are
  what such an estimate would start from.
- **An EPUB's or a Markdown file's extraction shows no count**, a departure from the description's
  "files" that the owner confirmed (Clarifications): it took 0.1 s or less on both EPUBs.
- **The measurements are this machine's**, with the default configuration. A slower GPU, OCR, or
  a larger book makes every stage longer, and the counts and times left matter more there.
- **The progress belongs to the page that started the operation.** Another page, or the same page
  reloaded, doesn't see it, and the lock refuses its operations as busy, as today.
- **Stopping an operation midway is out of scope**, and so is the progress of the Summaries, Quiz
  and Chat tabs, of recovery at startup, and of `doctor`.
- **An operation called without a display shows nothing, and logs its stages.** The benchmarks
  call the services without one, so their runs log stage lines too. Recovery doesn't run as an
  operation of its own, and logs none (FR-015).
- **The area's text is in English**, as the whole interface is.
- **The area's text carries everything the bar shows**: the stage, its count and its total. The
  area isn't announced to screen readers as it changes: the one reader of this application reads
  the screen. Accessibility beyond that is out of scope.
- **The seven operations keep their API endpoints**, by name and inputs. Their outputs gain the
  progress area's last value, which no caller in the repository reads.
- **The thresholds of FR-006 and the bound of FR-014 are defaults** that the plan may tune, as
  long as SC-003 and SC-008 hold.
