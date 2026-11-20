# Local Book RAG

A locally hosted RAG system for indexing, searching and summarizing books with
open-weight models. It is a research environment: LLMs, embedding models and retrieval
strategies can be compared under controlled conditions without touching the application
code.

Everything runs on local infrastructure through Docker Compose, and the local model answers by
default. Answers and chapter summaries can also come from a cloud model, Claude for now, once its
API key is set and when you pick it for a request (see Cloud models). Nothing else leaves the
machine.

## Requirements

- [asdf](https://asdf-vm.com) with the `python` and `uv` plugins. `.tool-versions` pins
  Python 3.13 and uv; `asdf install` installs both.
- Docker Engine with the Compose plugin
- NVIDIA drivers and the NVIDIA Container Toolkit

Check that containers can reach the GPU before starting anything:

```bash
docker run --rm --gpus all nvidia/cuda:12.8.0-base-ubuntu24.04 nvidia-smi
```

## Setup

```bash
make env        # copy devtools/.env.sample to .env (won't overwrite an existing one)
make install    # create .venv with the locked dependencies, Spec Kit's CLI among them, and install the git hooks
```

Set `APP_UID` and `APP_GID` in `.env` if your user isn't 1000. Files copied into the app container
with `docker compose cp` keep your IDs, and the app can write only to what its own user owns.

On commit, the pre-commit hook fixes the staged files (trailing whitespace, final
newline, `ruff check --fix`, `ruff format`) and re-stages the fixes, so the commit only
fails on issues that cannot be fixed automatically. The commit message must be a
conventional commit (`feat: ...`, `chore: ...`) with a header of at most 72 characters.

`main` takes no direct or force pushes, admins included: changes land through pull requests,
whose title must be a conventional commit too (`pr-title` workflow), since a squash merge
commits it. Each merge into `main` runs the `release` workflow: commitizen reads the commits
since the last `v*` tag and picks the bump (`fix`/`perf` patch, `feat` minor, `feat!` or a
`BREAKING CHANGE` footer major), then the workflow pushes the tag and publishes a GitHub
release with the changes grouped by type. A merge of only `docs`, `chore`, `ci`, `test` or
`refactor` commits releases nothing. The version lives in the tags: `pyproject.toml`'s
`version` is not bumped, since nothing can push the commit that would bump it.

## How changes are made

Since v0.1.0, every change that isn't trivial goes through [Spec Kit](https://github.com/github/spec-kit),
which keeps what was asked for, and why, next to the code that does it:

| Change                 | Flow                                                                  | Its record                     |
| ---------------------- | --------------------------------------------------------------------- | ------------------------------ |
| A feature              | `/speckit-specify`, `-plan`, `-tasks`, `-implement`, `-converge`      | `specs/NNN-<name>/`            |
| A bug                  | `/speckit-bug-assess`, `-fix`, `-test`                                | `.specify/bugs/<name>/`        |
| An idea to weigh first | `/speckit-assess-intake`, `-research`, `-define`, `-shape`, `-decide` | `.specify/assessments/<name>/` |

These are skills that run inside a coding agent, not terminal commands. They are generated for
Claude Code in `.claude/skills/`, and in `.agents/skills/` for Codex, Cursor, Gemini CLI, Copilot,
OpenCode and the other agents that read it, where Codex calls them as `$speckit-specify`. The rules
every change has to respect are in `.specify/memory/constitution.md`, and `AGENTS.md` says which
flow fits which change. The generated files are never edited by hand: after `make update` brings a
new `specify-cli`, `make speckit-upgrade` regenerates them.

## Running

```bash
make up            # build the app image and start Ollama, ChromaDB and the app
make pull-models   # first run only: download the models named in config/models.yaml
make doctor        # check the services, the models and the GPU
```

The interface is at <http://localhost:7860>. `docker compose exec app book-rag doctor
--inference` also runs both models, and reports how much of the LLM is on the GPU.

| Command                 | Does                                                        |
| ----------------------- | ----------------------------------------------------------- |
| `make up`               | Build the app image and start the stack                     |
| `make down`             | Remove the containers, with the library and the models      |
| `make logs`             | Follow the app's logs                                       |
| `make pull-models`      | Download the configured models into Ollama                  |
| `make doctor`           | Check the services, models and GPU, and any cloud provider  |
| `make test`             | Run the unit tests                                          |
| `make test-integration` | Run the tests that need the running stack                   |
| `make lint`             | Lint and format, applying fixes                             |
| `make lint-check`       | Lint and format checks only, no writes                      |
| `make commit`           | Commit through commitizen (conventional commit messages)    |
| `make hooks`            | (Re)install the pre-commit and commit-msg hooks             |
| `make update-hooks`     | Bump the pinned hook revisions in `.pre-commit-config.yaml` |
| `make check-updates`    | List what `make update` would upgrade, changing nothing     |
| `make update`           | Upgrade all dependencies to their latest versions           |
| `make speckit-upgrade`  | Regenerate Spec Kit's skills and scripts for a new version  |
| `make reinstall`        | Delete `.venv` and run `make install` again                 |

Nothing is kept in a volume or a host folder. Each container holds its own data: the app has the
library and its logs, ChromaDB the vectors, and Ollama the models. `docker compose stop`, `start`
and `restart` keep all of it. Removing a container deletes what it held, whether `make down` removes
it or `make up` recreates it after a rebuild:

- **The app** is recreated by `make up` after any change to the code or to `config/`, and comes back
  with an empty library. ChromaDB still has the old library's vectors, and the new catalog numbers
  its indexes from 1 again, so the next book would go into the old `book_chunks_v1`, among the
  previous books' passages. Run `docker compose exec app book-rag reset-everything` before adding
  one: it deletes every `book_chunks_v*` collection.
- **Ollama** needs `make pull-models` again: about 14 GB for the configured models.

## Interface

The Gradio interface at <http://localhost:7860> has four tabs:

| Tab           | What it does                                                                        |
| ------------- | ----------------------------------------------------------------------------------- |
| Library       | Upload, replace, remove and reindex books, and reset. Shows each book's status, and the progress of each operation |
| Chat          | Ask about one book, one chapter or several books, and inspect the retrieved passages. With a cloud model set up, pick the model and its fallbacks for the tab |
| Summarization | Summarize a chapter in any of the types, and save the result. Its own model choice, as in Chat |
| Research      | The latest question from the inside: the model that answered and any that failed first, each stage's scores, final context, reasoning, tokens, timings, and GPU memory |

Everything in it goes through the same services as the commands. Destructive actions need
the same confirmation in both, and errors appear as notifications that stay until dismissed,
because most of them say what to do next. A book that fails while indexing stays in the list
with its reason, and uploading it again retries it.

## Library

The library reads Markdown books, `.md` or `.markdown`. Books are converted to Markdown outside
the application, with Microsoft MarkItDown and whatever plugins suit them, and added as files:

```bash
docker compose cp "01_historia_economica_global.md" app:/tmp/   # the container sees no folder of the host
docker compose exec app book-rag add-book "/tmp/01_historia_economica_global.md"
docker compose exec app book-rag list-books
```

A book's title is its file's name without the extension, as it is, so a book copied into the
container keeps its name on the way: copied to `/tmp/book.md`, it would be titled `book`. A
book has no author. An upload in the interface needs no copy. Books go through extraction,
normalization, structure detection and chunking. The library lives in the app container, under `/app/data`. Each stage's
output stays in `data/processed/<book_id>/r<revision>/` for debugging, and the original file
in `data/original_books/<book_id>/`, from which everything else can be rebuilt. The catalog
in `data/metadata/catalog.db` is the source of truth for what the library holds. A file is
identified by its checksum, so uploading it twice under different names is detected.

Preparing a book:

- **Headings mark chapters and sections.** The outermost level used more than once holds the
  chapters, and the levels below it their sections. A single outermost heading is taken for the
  book's own title line, so its children are the chapters, and its text shows nowhere. A
  heading that says "Chapter N" or "Capítulo N" outranks its depth when depth clearly got it
  wrong, and "Part" headings are seen through. A book without headings is one chapter, titled
  with the book's title.
- **Front matter is optional**, a YAML block between `---` lines at the top. It is removed from
  the text, and only its `language` (or `lang`) is read: the language is detected from the text
  otherwise. Front matter that doesn't parse, or isn't closed, stays in the text.
- **What isn't the book's text is left out** before the language is detected and the chapters are
  found:
  - **Project Gutenberg's header and license.** A book that holds both of Gutenberg's own markers,
    "\*\*\* START OF THE PROJECT GUTENBERG EBOOK … \*\*\*" and the matching END line, keeps only
    what lies between them.
  - **A table of contents or a printed index.** A heading that reads, in full and in any case,
    "Table of Contents", "Contents", "Sumário", "Index" or "Índice remissivo" goes with everything
    under it, down to the next heading at its level or above. A heading that only contains one of
    these words stays.

  A publisher's pages without a heading, such as a catalog record or a copyright notice, stay in
  the chapter they end up in: remove them when converting the book.
- **The file is checked** before anything is stored: it must be UTF-8, hold no binary data, and
  be at most 512 MB.
- **A PDF or an EPUB is refused**, with a message to convert it to Markdown first. In the
  Library tab, the file pickers offer only Markdown, and a PDF or EPUB dropped on them anyway is
  refused by Gradio before the application sees it.

A chapter's `number` is its position in the book, which is unique where printed numbers are
not (a preface has none). The printed number stays in its title. Text before the first
chapter goes to chapter 0, "Front matter". The cleaning that follows extraction applies to any
text: Unicode composition, ligatures, invisible characters and whitespace.

Chunk sizes are measured with the embedding model's own tokenizer, set in
`embedding_profiles` in `config/models.yaml`. Tokenizers are downloaded on first use and
never reach the network again.

### Changing the library

```bash
docker compose exec app book-rag replace-book book_001 /tmp/new_name.md
docker compose exec app book-rag remove-book book_001 [--archive]
docker compose exec app book-rag reindex-book book_001
docker compose exec app book-rag reindex-all [--regenerate-summaries]
docker compose exec app book-rag reset-index
docker compose exec app book-rag reset-everything
```

| Operation          | Effect                                                                  |
| ------------------ | ----------------------------------------------------------------------- |
| `add-book`         | Adds one book. Others aren't touched. The same file twice is refused    |
| `replace-book`     | Swaps a book for a new document, keeping its ID                         |
| `remove-book`      | Deletes one book and what is derived from it. `--archive` keeps the original in `data/archive` |
| `reindex-book`     | Processes a book again from its original. This retries a failed book    |
| `reindex-all`      | Rebuilds the index from the originals with the current configuration    |
| `reset-index`      | Empties the library, keeping the originals, which `reindex-all` brings back |
| `reset-everything` | Deletes the whole library, originals included                           |

`scripts/reset_library.sh` and `scripts/reindex_library.sh` do the same from the host. None of
this touches the models in Ollama. The destructive operations ask for
confirmation in the service layer, so Gradio and the commands can't differ: a book's ID to
remove it, `RESET INDEX`, or `DELETE EVERYTHING`.

How changes stay safe:

- A book's chunks carry a revision. A replacement is indexed next to the live one, and stays
  out of searches until it is verified, when one SQLite transaction moves the book over. So
  a failure leaves the book as it was, and at no moment does a search find a mix of both.
- `reindex-all` does the same at the scale of the library. A staging collection fills up while
  the old index keeps answering, and every book moves in one transaction.
- Each change is journaled in the catalog while it runs. After a crash, the next start or the
  next change reads the journal, and either finishes the change or undoes it, depending on
  whether the swap had happened.
- A lock file lets one change happen at a time across the interface and the commands.
  Searches don't wait for it. The operating system releases it when a process dies.
- Each original has a `source.json` next to it, because `reset-index` clears the catalog: it
  is what lets `reindex-all` bring the books back with their IDs.

Index versions are never reused, even after `reset-everything`, because a running server
identifies an index by its version and must not mistake a new one for the one it has cached.
The catalog keeps the count, so a new app container starts it over (see Running).

### Following an operation

The Library tab shows the progress of its seven operations in an area under the index status:

- **The operation**, its book, and the time since it began, as 0:38.
- **The stage it is in**, with its position: "Embedding the chunks — stage 4 of 5". A bar fills where
  the stage is counted: the chunks as they are embedded, and, in a reindex, the books and the saved
  summaries. Where it isn't counted, the bar moves without filling: extracting the text, which
  takes a tenth of a second or less, preparing the chunks, saving them, the steps of a removal and
  of the resets.
- **The time left** in a stage of chunks, once it has run 3 seconds and done a tenth of its
  items: "about 15 s left", or "about 2 min left". Books and summaries are counted without one,
  since they differ too much in size for those done to say much about those left.
- **For a reindex**, the book being indexed, with its own step, and a line saying that questions
  keep working on the current index meanwhile.

From the click until its first stage, the area says the operation is starting, and the seven
buttons stay disabled until it ends. Then the area keeps one line: what the operation did, or the
stage it failed in and why, with the book and its step for a reindex. An operation refused before
it began, such as a duplicate, a wrong confirmation or a busy library, shows no stage. The
progress belongs to the page that started the operation: another page, or the same one reloaded,
doesn't see it, and has a new operation refused as busy until it ends. An operation can't be
stopped midway.

The commands print the same stages to the error stream: a line as each stage starts, a count line
at most every 2 seconds, and `done` or `failed while …` at the end. Standard output keeps their
result, so `reindex-all` prints only its report there.

Each stage also leaves a line in the app's log, `logs/app.jsonl`, when it ends: `stage finished`
or `stage failed`, with `stage`, `done`, `total` and `unit` when it was counted,
`duration_seconds`, and `within` and `item` (the book's ID)
for a step of a reindex. Every line carries the operation's execution ID, and none carries a
title, a file name or text from a book.

## Index

Chunks go into one ChromaDB collection per index version, `book_chunks_v1` to begin with,
where every record carries its book, chapter, section, language, embedding model and
index version. Which index is active is recorded in the catalog, along with everything that
shaped it: the embedding model and the digest of its weights, its dimensions, as read from
the model, and the chunking settings.

Vectors from different models never meet. When any of that changes, even when a tag is
pulled again and brings new weights, `doctor` reports it, new books are refused, and the
index stays as it is until an explicit `reindex-all`. Questions keep working meanwhile,
because they are embedded with the model that built the index, not the configured one. The
query template is the exception: it changes how questions are embedded, not what is stored,
so it can be tuned freely.

Embedding runs on different devices depending on the work, set in `config/models.yaml`:

| Work                  | On the GPU                 | On the CPU                 |
| --------------------- | -------------------------- | -------------------------- |
| Indexing              | 59 chunks/s, batches of 64 | 5 chunks/s                 |
| A query, model loaded | 6 ms                       | 16 ms                      |
| A query, cold start   | 9.2 s                      | 0.5 s                      |

So indexing uses the GPU, unloading the LLM first, and queries use the CPU, which leaves the
LLM alone in VRAM. `embedding.batch_size` is 16, which gives 32 chunks/s; 64 is nearly twice
as fast.

Each request names its device. Left unset, Ollama keeps whatever runner is already loaded,
so a model that a query placed on the CPU would stay there for a whole book.

Both models return unit vectors, and input longer than the model's context is refused rather
than truncated, which is what Ollama would do silently by default.

## Retrieval

```bash
docker compose exec app book-rag search "What is opportunity cost?" --book book_001 --chapter 4
```

`search` shows what the system retrieves, with each stage's score. It accepts filters by
book, chapter, section and language. `config/retrieval.yaml` picks the strategy:

| `strategy` | Finds passages through                                                            |
| ---------- | --------------------------------------------------------------------------------- |
| `dense`    | Nearest neighbors in ChromaDB                                                     |
| `bm25`     | Term matching, stemmed in the book's language, ignoring accents and old spellings |
| `hybrid`   | Both, merged by `fusion.method`: `rrf` on ranks, `weighted` on scores             |

Reranking is a separate stage on top of any of them, in `retrieval.reranker.enabled`. It runs
inside the app through sentence-transformers, since Ollama has no reranking API. Both
candidates load the same way, so switching is a matter of `reranker.model` in
`config/models.yaml`. On the CPU, the default, it takes 4 s for the 24 passages of a typical
search, and 0.6 s with `device: cuda`.

Every book is searched on its own and the results are taken in turns. With one global
top-k, a question comparing two books could come back with passages from only one of them.

The BM25 index is built in memory over exactly the chunks a search may return, about 60 ms
for a 1,300-chunk book. So there is no second index on disk to keep in step with ChromaDB, and
term rarity reflects the part of the book being searched.

Portuguese books printed before the spelling reforms spell many words differently from today:
*Quincas Borba* has Sophia, elle and facto where a reader types Sofia, ele and fato. With
`bm25.historical_spelling` on, lexical search treats both spellings as one word, in either
direction. It is off by default: on the benchmark, it didn't improve lexical search by more than
noise, and the default configuration came out the same (`docs/benchmark-results.md`).
- **Only the words it compares are folded.** Passages are shown as the book prints them, nothing
  stored changes, and switching the setting needs a restart (see Deployment notes), not a reindex.
- **It needs `stemming`**, and applies only to books in Portuguese.
- **A few modern words are left as they are**, where a pattern would merge them with another, as
  pacto with pato. `docs/decisions.md` has the measurement behind this.

## Questions

```bash
docker compose exec app book-rag ask "What is opportunity cost?" --book book_001
docker compose exec app book-rag ask "Quais são os argumentos?" --book book_001 --chapter 4
docker compose exec app book-rag ask "Compare how they treat trade." --book book_001 --book book_002
docker compose exec app book-rag ask "What is the harm principle?" --language Portuguese
docker compose exec app book-rag ask "What is the harm principle?" --model claude-sonnet-5-5
```

Answers come from the retrieved passages, with numbered citations that resolve to the book,
chapter and section. When the passages don't hold the answer, the model is told to say so
instead of answering from general knowledge. It opens such a reply with a marker, and the
application shows the reply as an abstention: "The model found no answer in the selected books".

Some models sometimes abstain in words, without the marker: asked who did something, they reply
that the passages say only "someone". With `check_abstentions: true` in a model's profile in
`config/models.yaml`, the model reads each reply without the marker again, in one short call,
and an abstention it finds is shown as one. It is on for `gemma4:12b` and `qwen3.5:9b`, where it
took about a quarter of a second, and for the Claude models (see Cloud models). A check that
fails, or can't be read, leaves the reply an answer. It can still take a partial answer for an
abstention: `docs/decisions.md` has its measurements.

Passages are fitted to the context window before anything is sent, reserving room for the
reply and `generation.context.safety_margin`. This matters: Ollama doesn't refuse a prompt
that is too long, it silently cuts it and answers from what is left. Token counts come from
each model's own tokenizer, set in `llm_profiles` in `config/models.yaml`, and for `gpt-oss`
they match Ollama's count exactly.

Models differ in more than quality, and none of the code above the provider depends on it:

- Reasoning is set per model in `llm_profiles`, and checked against what the model supports.
  `gpt-oss` reasons whatever it is told, so its setting is `low`.
- Reasoning counts against `max_tokens`. If it uses all of it, the result is an error, not
  an empty answer.
- `gpt-oss` cites as `【3】`, however the prompt shows it. Citations are normalized, and text
  in code is skipped: `t = [1, 2, 3]` is a list, not three sources.
- Told to answer "in the language of the question", `gpt-oss` answered some English questions
  in Spanish. The question's language is identified and named in the prompt instead, unless
  the question is too short to tell, and `--language` overrides it.

## Summaries

```bash
docker compose exec app book-rag summarize book_001 4 --type comprehensive --save
docker compose exec app book-rag summarize book_001 4 --model claude-sonnet-5-5 --fallback claude-opus-5-5
```

The types (`brief`, `standard`, `comprehensive`, `analytical`) and their lengths are in
`config/generation.yaml`. A saved summary goes to `data/summaries/<book_id>/`, with a JSON
file saying how it was made. A summary is in the book's language unless `--language` names another,
and its section headings are given to the model already in that language: asked to translate
them, `qwen3.5` kept the English ones.

Summaries don't use retrieval to pick their material: the top passages for "summarize this"
would leave out most of a chapter. Every chunk goes through map-reduce instead:

1. A chapter that fits in the context is summarized directly.
2. Otherwise, consecutive chunks are grouped in batches that a reply can do justice to, far
   smaller than what the context would hold, and each batch gets a partial summary.
3. A reply cut off by its token limit has lost the end of its batch, so the batch is redone
   in two halves. This is what makes the coverage figure mean something: `chunks_covered`
   counts chunks in steps that finished.
4. Partial summaries are sized to fit the final prompt together. Very long chapters merge
   them first, a few at a time. Models overrun the length they are given, `gpt-oss` by twice,
   so a round of merges that barely condenses asks the next one for half as much.

Citations in a summary are computed, not claimed. Models don't carry source tags through
several rounds of summarizing: `gpt-oss` was seen numbering them upward, `[S1] [S2] [S3]`,
whatever they pointed at. So the model writes no citations, and each finished statement is
looked up among the chapter's chunks through the vector index, citing the passage it
resembles. It costs milliseconds per statement, and works the same for every model.
Statements close to no passage stay uncited and are counted, as the first place to look
for something the model added. The references give each passage's section and quote its
opening words, because that is how to find it: books have no pages.

A saved summary's JSON file also records its model's provider, the models that failed before it,
and, for a cloud model, the tokens it read and generated. `reindex-all --regenerate-summaries`
writes the saved summaries again with the local model, except those a cloud model wrote: it leaves
them as they were, lists them, and calls no cloud model (see Cloud models).

## Cloud models

Answers and chapter summaries can come from Claude, through Anthropic's API, beside the local
model. Two settings in `.env` turn it on, and both are needed:

```dotenv
ANTHROPIC_API_KEY=sk-ant-...
ANTHROPIC_MODELS=claude-sonnet-5-5,claude-opus-5-5
```

`ANTHROPIC_MODELS` is the list of models the tabs and the commands offer, in that order. With one
setting alone, nothing is offered, the log says which one is missing, and so does `doctor`.
**Setting or changing either takes `make up`, which recreates the app container and empties the
library** (see Running): add the books again afterwards, after `reset-everything`.

**What goes where.** The local model stays the default, on every page load and in every command.
A cloud model answers only a request that picks it: the Model dropdown in the Chat or the
Summarization tab, each tab keeping its own choice, or `--model` in `ask` and `summarize`. Before
anything is sent, a notice says what goes where: for a question, the question and the passages
found, which are the Research tab's final context; for a summary, the chapter's text, in one step
or several. Nothing else from the library is sent, and the app contacts Anthropic at no other
time, except when you ask for a check: `doctor`, or "Check again" in the Research tab, which send
the key and the allowed models' names and run no inference. Anthropic handles what it is sent
under its own terms for API data: read its commercial terms,
<https://www.anthropic.com/legal/commercial-terms>, and its privacy policy,
<https://www.anthropic.com/legal/privacy>, before setting a key.

**Fallbacks.** "If it fails, then" in a tab, or `--fallback`, repeated, in a command, lists other
cloud models to ask in order; the local model ends every sequence, so a request always gets an
answer unless the local model fails too. A model fails when Anthropic refuses the key, doesn't
know the model, limits the rate, is down or overloaded, can't be reached, rejects or declines the
request, sends nothing for 120 seconds, or when the model replies with no text. A rate limit, an
overload or a lost connection is tried again twice first, a few seconds apart; a silent model never
is. The next model starts from the beginning: the Chat tab removes the text the failed one wrote,
and `ask` says on standard error that the text above is discarded. Each failure is said as it
happens, and again with the answer or the summary. A reply cut off by its token limit, and an
abstention, are answers, not failures.

**The Research tab** names the model that answered, with its provider, and each that failed first.
For a cloud model, model loading and prompt processing are unavailable, the generation's speed and
time are measured by the app, network included, and the reasoning is the summary Anthropic
returns, or "None came back".

**Settings.** What every Claude model shares is its profile, `cloud_profiles.anthropic` in
`config/models.yaml`: the window the app works with (64K tokens, far below the models' own, to cap
what one request sends), the reasoning effort, the room set aside for reasoning, and the timeout.
The task limits in `config/generation.yaml` apply, with that room added; their temperature
doesn't, since the current Claude models take no sampling setting. Tokens are counted with
`o200k_base`, since Claude's tokenizer isn't public, and Claude counts about one and a half times
as many for the same prompt, more than the safety margin absorbs: the 64K cap is about 100K of
Claude's own tokens. Nothing is lost to the miscount, since the API refuses a prompt that doesn't
fit instead of cutting it, and the models' own window is far larger.

**Costs and the key.** Anthropic bills each request, a failed one included. An answer without the
no-evidence marker costs one more short call, since Claude Haiku 5.5 sometimes abstains in words
and the profile's `check_abstentions` is on. A cloud summary's report shows the tokens it read and
generated, and those of each attempt that failed. The key is in the
app container's environment: anyone who can open the interface, or call its API, can spend it (see
Deployment notes).

**Before trusting a model,** run the integration tests on it: with both settings exported in the
shell, `make test-integration` runs each model of `ANTHROPIC_MODELS` on an excerpt written for the
test, five questions it answers, three it doesn't, and a summary, and checks how the app reads
what the model writes. They cost a few cents per model, and are skipped without the settings. A
model allowed later is trusted once it has passed them.

**What stays local:** embeddings, reranking, benchmarks and their judges. A cloud model has no
digest and no seed, so its results can't be reproduced, and the index, every search and every
comparison rest on those. An experiment or a judge that names a cloud model is refused before the
run starts.

## Benchmarks

Comparing configurations under controlled conditions is the point of this project, so the
benchmarks are a first-class part of it. The runner, the metrics and the report are in
`app/evaluation`. `benchmarks/` itself is ignored by git: the dataset's last version is in
`specs/005-markdown-only/benchmarks/`, with the experiment that feature added, `no_reranking` is
in `specs/007-retrieval-rows/benchmarks/`, the other experiments' last versions are in commit
`c7bb785`, and `docs/benchmark-results.md` records what the runs found. The books are never in the
repository (see the dataset, below). Neither the image nor a mount brings `benchmarks/` into the
app container, so a run starts by copying it in, and ends by copying the results out before the
container goes:

```bash
git archive c7bb785 benchmarks/experiments | tar -x           # the experiments
rm benchmarks/experiments/extraction.yaml                     # a kind that no longer exists
cp -r specs/005-markdown-only/benchmarks/. benchmarks/        # the dataset, and markdown_books.yaml
cp -r specs/007-retrieval-rows/benchmarks/. benchmarks/       # no_reranking.yaml
# the three Markdown books go into benchmarks/books (see the dataset, below)
docker compose cp -a benchmarks app:/app/                     # into the app container
docker compose exec app book-rag pull-models --all            # every candidate model, about 40 GB
docker compose exec app book-rag validate-benchmark           # the books' checksums, then every question

make benchmark EXPERIMENT=retrieval                         # the whole dataset
make benchmark EXPERIMENT=generation LIMIT=2                # a sample, per book and category

docker compose cp app:/app/benchmarks/results benchmarks/   # the results, out of the container
```

The container holds no `.git`, so a result records the code's commit only when it is passed with
`--commit`, which `make benchmark` doesn't do:

```bash
docker compose exec app book-rag benchmark benchmarks/experiments/retrieval.yaml --commit "$(git describe --always --dirty)"
```

The experiments in that commit:

| Experiment      | Compares                                                               | Measures                                                                                  |
| --------------- | ---------------------------------------------------------------------- | ----------------------------------------------------------------------------------------- |
| `retrieval`     | Embedding models, strategies, fusion, rerankers, chunk sizes           | Recall@5, Recall@10, MRR, nDCG@10, context precision and recall                           |
| `generation`    | The four LLMs, on identical retrieved contexts                         | Faithfulness, correctness, relevance, citation accuracy, language, abstention             |
| `summarization` | The four LLMs, on chapters with known key points                       | Argument coverage, concepts, consistency, coherence, completeness, citation traceability  |
| `performance`   | The four LLMs, at 8K and 16K of context                                | Load time, time to first token, speeds, peak memory: the median of 3 runs after a warm-up |

`markdown_books`, in `specs/005-markdown-only/benchmarks/experiments/`, is a `retrieval`
experiment with one variant, the default configuration. It ran on two versions of the code and of
the books, and `devtools/compare_runs.py` pairs two such runs question by question, which
`benchmark-report --baseline` can't do across runs. For each question whose Recall@5, MRR or
nDCG@10 moved, it shows what each run retrieved: the ranks its evidence took, and the chunks that
ranked above it, down to the lowest-ranked evidence among the first ten. A run written before the
rows recorded their rankings says that it didn't record one. `no_reranking`, in
`specs/007-retrieval-rows/benchmarks/experiments/`, is the default configuration with reranking
off, the second run that checked this comparison.

Results go to `benchmarks/results/<experiment>_<time>/`: `summary.csv`, `rows.csv` with every
question, answer and summary, and `results.json`, which also records what a result means nothing
without: the digest and quantization of each model, the Ollama and package versions, the hardware,
the full configuration and the checksum of the dataset. A sampled run says so in `complete: false`.
`rows.jsonl` grows as rows complete, so a run that dies after hours keeps what it did.

```bash
docker compose exec app book-rag benchmark-report benchmarks/results/<run> --baseline <variant>
```

shows a run as Markdown tables, with each variant compared to the baseline, question by question
or chapter by chapter. The dataset is small, and this paired bootstrap tells which differences are
more than noise. A result of a kind the benchmark doesn't run, such as an old `extraction` run, is
refused rather than rendered in part. The full runs, and what they suggest, are in
`docs/benchmark-results.md`.

An experiment is a YAML file: variants that are the normal configuration plus overrides, checked
by the same validation as `config/`. It runs in `benchmarks/workspace`, on separate files and
`bench_*` collections, so it can't touch the real library. Variants that index the same way
share a workspace. A workspace whose index no longer matches the configuration is rebuilt, but a
change to the ingestion code can't be seen: delete `benchmarks/workspace` after one.

Its dataset is three books: *Quincas Borba* in Portuguese, *Think Python* in English, and *On
Liberty* for its complex arguments. Each has 30 questions: 10 factual, 5 conceptual, 5 across
sections, 5 about one chapter, and 5 that the book can't answer, some of them traps that name a
detail the text leaves out.

The books are Markdown files, converted the way the owner converts their own books. For each,
`books.yaml` records the Markdown file's name and sha256, the original it came from (*Think
Python*'s PDF, and the two EPUBs from Project Gutenberg, with their URLs and checksums), and the
conversion: MarkItDown's version and commit, each plugin's version and commit, Python's version,
and the command. A run and `validate-benchmark` check each file's sha256 first, and stop on a
missing or different file. All three books can be redistributed, so anyone can rebuild them: the
same conversion of the same originals gives the same files.

A newer MarkItDown, or another plugin, gives other files, and makes a new version of the dataset:
convert the three books again, record their new checksums and the conversion in `books.yaml`, run
`validate-benchmark`, and correct each quote it lists to the new text, holding the same evidence,
without dropping a question. A result records the dataset's checksum, so results on two versions
are never mixed up. Compare them as two runs, with `devtools/compare_runs.py`.

Relevance is stored as verbatim evidence quotes, not chunk IDs. IDs change with every chunk size,
and comparing chunk sizes is one of the experiments, while a quote finds its chunks under any
configuration. Each result row lists the chapters and chunks the evidence resolved to. A retrieval
row also lists, by chunk ID, its ranking, every passage the search considered in the order that
its scores read, and its context, the passages kept after reranking. So what ranked above the
evidence can be read from the results. An ID holds within its run only: another chunk size, or
another ingestion, numbers the chunks differently.

Automated scores are a first signal, not a verdict. RAGAS and the summary rubric rely on a model
as judge, the same one for every candidate, so they compare candidates with each other rather
than measure anything absolute. Read the answers in `rows.csv` before concluding anything: in one
reviewed chapter the rubric gave full marks to a summary that misattributed who said what, and
that only coverage and a human reader caught.

The judge runs at the widest context window (`generation.context.max_size`), with each experiment
setting its reasoning. A metric the judge can't produce is left out and counted, in the
`<metric>_samples` columns, instead of being scored as zero. If you change a judge, its prompts or
its reasoning, check first that it can still separate cases whose answer is known: see "A judge has
to prove itself" in `docs/decisions.md`.

Scoring is slow: about 35 s per answer for the three RAGAS metrics, and about a minute per
chapter for the rubric and key points. A full `generation` run takes hours, so `LIMIT` exists for a
first look.

## Deployment notes

- Ollama and ChromaDB are published on `127.0.0.1` only: neither has authentication, and
  Docker's published ports bypass host firewalls. The app reaches them over the internal
  network. Gradio is on loopback too, unless `GRADIO_BIND_ADDRESS` in `.env` says otherwise.
- The images are pinned by digest. `ollama/ollama:latest` would make benchmark results
  depend on the day the image was pulled.
- The `chromadb/chroma` image runs the Rust server, which has no Python and ignores the
  `IS_PERSISTENT` family of settings. Its `/config.yaml` already persists to `/data`, and
  the healthcheck talks to the heartbeat endpoint through bash.
- The app container gets the GPU too, for the reranker when it is configured
  to use it. torch comes from the CUDA 13.4 index: the RTX 5060 Ti is a Blackwell GPU, which
  builds for older CUDA versions cannot drive.
- `ANTHROPIC_API_KEY`, when set, is in the app container's environment: `docker inspect` and
  `docker compose config` show it to anyone who can run Docker, and anyone who can open the
  interface, or call its API, can spend it. Keep `GRADIO_BIND_ADDRESS` on loopback unless everyone
  who can reach it may. The app writes the key nowhere: not in a log, a saved summary or a result.
- `config/` is copied into the image, and nothing mounts it. `make up` applies a change by
  rebuilding, which empties the library (see Running). To keep the library, copy the change in
  and restart: `docker compose cp config/. app:/app/config`, then `docker compose restart app`.
  The app validates all of it at startup.

## Configuration

| File                      | Holds                                                   |
| ------------------------- | ------------------------------------------------------- |
| `config/application.yaml` | Server, upload limits, timeouts and logging             |
| `config/models.yaml`      | The LLM, embedding model and reranker, and each cloud provider's profile |
| `config/ingestion.yaml`   | Languages and chunking                                  |
| `config/retrieval.yaml`   | Retrieval strategy and its parameters                   |
| `config/generation.yaml`  | Temperature and token limits per task                   |

Unknown keys are errors, so a typo stops the app at startup instead of being ignored.
Addresses and directories come from the environment; their defaults are the Compose
service names. So do a cloud provider's key and allowed models, read apart from the rest, so that
nothing that records the configuration, such as a benchmark's result, holds the key. A cloud model
takes `config/generation.yaml`'s token limits but not its temperature; the rest of its settings are
its provider's profile.

## Layout

```
app/
  main.py          # the commands, and the entry point
  container.py     # builds the object graph: the only place that knows what is concrete
  config/          # typed settings, validated at startup
  ingestion/       # from a file to chunks: loaders, normalization, structure, chunking
  embeddings/      # the embedding provider interface and Ollama behind it
  retrieval/       # dense, BM25, fusion, reranking and the pipeline around them
  generation/      # the LLM providers, local and cloud, the model choices, questions, summaries, prompts and citations
  storage/         # the catalog in SQLite, ChromaDB, and the library's files
  services/        # the operations: what both Gradio and the commands call
  interface/       # the Gradio tabs, as thin as they can be
  evaluation/      # the dataset, the metrics and the experiment runner
config/            # everything that can change without touching code
docs/              # what was decided and why, and what the benchmarks found
tests/unit/        # no services needed: real files, real SQLite, embedded ChromaDB, fake models
tests/integration/ # against the running stack and the real models
specs/             # one directory per feature since v0.1.0: its spec, plan and tasks
.specify/          # Spec Kit: the constitution, templates and scripts, and the bug and idea records
.claude/skills/    # Spec Kit's skills for Claude Code, generated
.agents/skills/    # the same skills for the agents that read .agents/skills, generated
```
