# Local Book RAG Constitution

The rules every change to this project keeps. Some come from the first version's spec
(`.TASK/task.md`, which stays local), and most of the others from failures on real books or real
model output, which `docs/decisions.md` records.

## Core Principles

Each principle opens with its rules, then says why they exist, and ends with the check a plan must
pass in its Constitution Check. A change without a plan, such as a bug fix, keeps the same rules.

### I. Local-first and model-independent

- No inference leaves this machine. Answers, summaries, embeddings, reranking and benchmark judging
  all run on local models, in Ollama or inside the app.
- Model names live in configuration: `config/models.yaml`, and the experiments in
  `benchmarks/experiments/` that override it. The code in `app/` names a model only in a comment
  or docstring that explains a workaround, and never branches on one.
- All of `config/` is validated at startup, and an unknown key is an error, so a typo stops the
  app instead of being ignored.
- What differs between models lives in their profiles in `config/models.yaml`, keyed by model
  name: `llm_profiles` for tokenizer and reasoning, `embedding_profiles` for tokenizer and
  templates. A model without a profile stops the app at startup.
- Models, like every external service, sit behind provider interfaces, and `app/container.py` is
  the only place that knows the concrete classes.

**Why.** This is a research environment for open-weight models: its point is to compare LLMs,
embedding models and retrieval strategies under controlled conditions, without touching the code.
The first version's spec put local-first at the top of its design principles, and asked that
changing an LLM never require changing business logic. With profiles, switching a model is one
line, and a model without one fails at startup instead of embedding without its instructions.

**Check.** The plan calls no inference API outside this machine, judges included. A model it adds
or switches to is named only in configuration, and an LLM or embedding model gets a profile.
Whatever has to differ between models is a profile setting, not a condition in code. A setting it
adds is validated at startup like the rest.

### II. The library is never at risk

- The originals in `data/original_books/` are the source of truth. Everything derived from them
  can be rebuilt by `reindex-all`, and only removing or replacing a book, or `reset-everything`,
  deletes one.
- A change to one book leaves every other book as it was.
- Adding a book is idempotent: a file is identified by its checksum, so the same file is refused
  the second time, under any name, instead of being indexed twice.
- Every change to the library runs under the library lock and is journaled in the catalog. Its
  entry closes only when the work, or its undoing, has really finished. A cleanup that fails is
  treated like a crash: the entry stays open, and recovery finishes or undoes the change at the
  next start.
- Destructive operations are confirmed in the service layer, so Gradio and the commands ask for
  the same thing: the book's ID to remove it, `RESET INDEX`, `DELETE EVERYTHING`.
- Nothing runs `docker compose down -v`: it deletes the named volumes, with the downloaded models
  and the vector database in them. The library is reset inside the application, which touches no
  volume and no model.
- Benchmarks run in `benchmarks/workspace`, on their own files and `bench_*` collections, and
  never touch the real library.

**Why.** The first version's spec asked for persistent storage, isolated books, idempotent
ingestion, explicit destructive operations, recoverable indexing, and the originals kept as the
source of truth. The
journal rule comes from a real failure: a catch-all `finally` once closed entries for work that had
failed, and left half-deleted books with nothing to finish the job. Experiments index, clear and
rebuild their workspaces at will, which is safe only because nothing they do can reach the
library.

**Check.** Every change the plan makes to the books, the catalog or the index runs inside a
journaled operation, and the plan says what a crash at each step leaves behind and how recovery
finishes or undoes it. Books stay identified by their checksum. Anything it deletes is confirmed
in the service. No step, script or
document runs `docker compose down -v`, and benchmark code reaches nothing outside
`benchmarks/workspace` and the `bench_*` collections.

### III. Index integrity

- Each index version has its own ChromaDB collection (`book_chunks_v1`, ...), and its record in
  the catalog keeps a fingerprint of what shaped it: the embedding model and the digest of its
  weights, its dimensions as read from the model, the document template, the tokenizer, the
  chunking settings and the metadata schema's version. Index versions are never reused, even after
  `reset-everything`.
- Vectors from different embedding models never share a collection.
- A change to the embedding or chunking configuration needs an explicit `reindex-all`. Until then,
  `doctor` reports it, new books are refused, and the index stays as it is, even when a tag pulled
  again brings new weights. Questions keep working, embedded with the model that built the index.
- The query template is the one exception: it changes how questions are embedded, not what is
  stored, so it can be tuned freely.

**Why.** A search compares a question's vector with the stored ones, which only means something
when the same model, with the same weights and the same input format, made both. Vectors of the
same size from different weights mix without any error and rank wrongly, and a tag pulled again
can bring new weights under the same name. The first version's spec asked that a configuration
change never silently change indexed data, and that embedding or chunking changes require an
explicit reindex. A running server identifies an index by its version, so a reused version could
pass for the one it has cached.

**Check.** If the plan changes the embedding model or its weights, the document template, the
tokenizer or the chunking settings, it relies on an explicit `reindex-all`, which builds a new
index version, and writes nothing into the live collection. A new embedding or chunking setting
joins the fingerprint (`IndexService.current_configuration`), unless, like the query template, it
changes only how questions are embedded.

### IV. One service layer

- Gradio (`app/interface`) and the commands (`app/main.py`) call the same services in
  `app/services`, and hold no business logic: they read input, call a service and show what it
  returns.
- Rules, validation and confirmations live in the service, so the two can't differ.

**Why.** The first version's spec forbade duplicating business logic between Gradio, the commands
and the services. Two copies would disagree sooner or later, and a confirmation checked in only one
of them would let the other delete without it.

**Check.** Every operation the plan adds or changes is a service method, and the Gradio tab or
command that calls it only reads input and shows output. Nothing in `app/interface` or
`app/main.py` checks a rule, confirms or writes on its own.

### V. Verified on real models and real books

- Never trust a model's output format: parse what the models really write, not what the prompt
  asked for. `gpt-oss` cites as `【3】`, ignores `think=False`, and, asked to carry source tags
  through a summary's map-reduce, numbered them upward whatever they pointed at. So citations are
  normalized, its reasoning is set to `low`, and summary citations are computed, not claimed.
- Ollama doesn't refuse what doesn't fit: it cuts it silently. So prompts are fitted to the
  context before they are sent, input longer than the embedding model's context is refused, and
  nothing long goes through Ollama's OpenAI-compatible endpoint, which can't set `num_ctx`, runs
  at 4096 tokens and cuts the prompt. Long calls use the provider in `app/generation`.
- A change to a prompt, to how model output is parsed, or to a judge is checked against the real
  models, not only by unit tests, whose models are fakes. A change to ingestion is checked on
  real books.

**Why.** Unit tests didn't show the failures behind most of `docs/decisions.md`. `t = [1, 2, 3]`
in an answer parsed as citations of three sources. RAGAS, sent through the OpenAI-compatible
endpoint, ran at 4096 tokens and scored answers against part of their sources. 20 of *Think
Python*'s "Glossary", "Exercises" and "Debugging" headings were dropped as running heads, while
the extraction benchmark reported full coverage.

**Check.** A plan that touches a prompt, a parser of model output or a judge says which real
models it runs on, through `make test-integration` or a benchmark, and what it expects there. A
plan that touches ingestion names the real books it is checked on. Every call that can be long
goes through the provider in `app/generation`.

### VI. Measured, not assumed

- Benchmarks decide. A change made for quality or speed, or one that changes a default, is
  compared with a baseline variant in a benchmark run, and `book-rag benchmark-report --baseline`
  shows the difference.
- A difference counts only when its paired bootstrap interval (4,000 resamples, 95%) excludes
  zero. On this small dataset, most don't.
- A judge proves itself before its scores mean anything, and again after a change to its prompts,
  its reasoning or its model: it has to separate cases whose answer is known, such as the correct
  answer from an invented one, and a real summary from a distorted one and from another chapter's.
- Scores are a first signal, not a verdict: the answers and summaries in `rows.csv` are read
  before anything is concluded. A metric the judge can't produce is left out and counted, never
  scored as zero.
- A workspace can't see a change to the ingestion code, so `benchmarks/workspace` is deleted after
  one, before measuring.
- A result records what it means nothing without: the digest and quantization of each model, the
  Ollama and package versions, the hardware, the full configuration and the dataset's checksum. A
  sampled run says so, in `complete: false`.

**Why.** A broken judge scores, it doesn't crash. At `low` reasoning, the summary judge copied the
sample values in its prompt without reading the summary, and rated every model 0.0. Exact
comparison made Docling look as if it had lost 82% of a book's structure. The judge also disagrees
with itself: given the same 75 answers, byte for byte, it moved a single answer's faithfulness by
0.13 on average from one day to the next. And the rubric once gave full marks to a summary that
misattributed who said what. The first version's spec asked for experiments that are reproducible,
on explicit and versioned configurations: a number whose model and configuration aren't recorded
can't be compared with the next one.

**Check.** A plan that claims an improvement names the experiment, the baseline variant and the
metric that decides, and reads an interval that includes zero as no difference. A plan that adds
or changes a judge or a metric first shows it separating cases whose answer is known. A plan that
changes ingestion code measures on a fresh `benchmarks/workspace`. A new experiment or metric
records everything a result needs to be reproduced.

### VII. Every answer traceable to its passages

- Answers come from the retrieved passages, with numbered citations that resolve to the book,
  chapter, section and pages of each one.
- When the passages don't hold the answer, the model says so, with the no-evidence marker,
  instead of answering from general knowledge, and the application shows that as an abstention,
  not as an answer.
- Summaries cite by lookup: each finished statement is matched against the chapter's chunks, and
  a statement close to no passage stays uncited and is counted.

**Why.** The first version's spec made traceability a design principle, and answers with source
references part of its definition of done. A research platform has to show where each claim
came from, because a citation can look right and be false: asked of the whole library, `gpt-oss`
once named a character's daughter with a citation of a chapter that doesn't say so.

**Check.** A plan that changes how answers or summaries are made keeps every claim traceable to a
passage the model was given, and keeps the no-evidence path working. It says how the generation
benchmark's citation accuracy and abstention quality, or the summary's uncited count, would show
a regression.

### VIII. Decisions are recorded

- `README.md` says how the system works, and `docs/decisions.md` why: what was decided, and the
  measurement or failure that decided it, including where it departs from the first version's
  spec. `docs/benchmark-results.md` is the record of the benchmark runs, whose result files stay
  out of the repository.
- A feature isn't done until both `README.md` and `docs/decisions.md` reflect it.
- A delivered spec is history: its `specs/NNN-*` directory isn't edited again, and a later change
  gets a new one.

**Why.** Many behaviors here look odd until their reason is known, and that reason was usually a
failure that unit tests didn't show: unrecorded, the next change brings it back. Since a delivered
spec isn't edited again, what stays true has to live in the README, and why in
`docs/decisions.md`.

**Check.** The plan's tasks update `README.md` wherever the system works differently, and
`docs/decisions.md` with each choice and its reason. A plan that changes a behavior that looks odd
first finds out from `docs/decisions.md` why it is that way.

## Development Workflow

- **Python 3.13 from asdf.** `.tool-versions` pins Python and uv. Pin the plain version:
  `asdf latest python 3.13` can answer with a free-threaded build (`3.13.18t`). The Dockerfile's
  base image stays on the same version.
- **uv, never pip.** uv manages `.venv`. Dependencies are added unpinned with
  `uv add --raw <pkg>` (`--dev` for tooling), and tools run with `uv run`. `.venv` has no pip, so
  `pip install` would hit asdf's global Python.
- **ruff, through `make lint`.** `make lint` fixes, `make lint-check` only checks. The line length
  is 120, configured in `pyproject.toml`. On commit, the pre-commit hook fixes the staged files.
- **Tests.** Every significant component has automated tests. `make test` runs the unit tests,
  which need no services: real files, real SQLite, embedded ChromaDB, fake models.
  `make test-integration` runs against the running stack and the real models, after `make up` and
  `make pull-models`.
- **Branches** are named `type/slug`, after the conventional commit type: `feat/…`, `fix/…`,
  `chore/…`. Spec Kit's `{number}-{slug}` names aren't used: its git extension isn't installed.
- **Commits** are conventional, with a header of at most 72 characters, which the commit-msg hook
  enforces. `make commit` runs commitizen. Tracked files move with `git mv`.
- **The PR title decides the release.** `main` takes no direct or force pushes, so every change
  lands through a pull request, squash merged: its title becomes the commit, and has to be a
  conventional commit too (`pr-title` workflow). The `release` workflow picks the bump from it:
  `fix` and `perf` patch, `feat` minor, `feat!` or a `BREAKING CHANGE` footer major, anything
  else no release.
- **The benchmark dataset.** After editing `benchmarks/datasets/questions.jsonl`, run
  `book-rag validate-benchmark`: every evidence quote has to be in its book exactly as written.
- **Spec Kit** takes every change that isn't trivial, and `AGENTS.md` says which flow fits which
  change.

## Governance

- **This constitution prevails over Spec Kit's templates**, and over the specs, plans and tasks
  made from them. A conflict changes the spec, plan or tasks, not the principle. A plan can't
  justify a violation in its Complexity Tracking table: the plan changes, or the constitution is
  amended first.
- **Templates aren't overridden.** An override replaces a whole template and stops following
  upstream changes, so this file carries the project's checks instead. An override waits for a
  change that shows a template missing something this file can't supply. Spec Kit's generated
  files are never edited by hand: `make speckit-upgrade` regenerates them.
- **Compliance.** Plan, tasks, analyze and converge check their work against this file:
  `/speckit-plan` fills its Constitution Check from the checks above, before research and again
  after design, and `/speckit-analyze` reports a conflict with a principle as critical. The bug
  commands don't read it, and the assessment ones hardly do, which is why `AGENTS.md` imports it.
- **`AGENTS.md` is the runtime guidance file.** It imports this file, which Claude follows, tells
  other agents to read it, and says which flow fits which change. The rules aren't copied into it:
  two copies would disagree sooner or later. `CLAUDE.md` only imports `AGENTS.md`.
- **Amendments** go through `/speckit-constitution`, and land through a pull request like any
  other change. The Sync Impact Report it writes at the top of this file is removed before the
  commit.
- **Versioning** is semantic. MAJOR removes a principle or a governance rule, or redefines one
  incompatibly. MINOR adds a principle or a section, or materially expands one. PATCH clarifies or
  rewords without changing what is required. The ratification date stays, and the amendment date
  is the date of the latest version.

**Version**: 1.0.0 | **Ratified**: 2026-11-08 | **Last Amended**: 2026-11-08
