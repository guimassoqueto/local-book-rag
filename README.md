# Local Book RAG

A locally hosted RAG system for indexing, searching and summarizing books with
open-weight models. It is a research environment: LLMs, embedding models and retrieval
strategies can be compared under controlled conditions without touching the application
code.

Everything runs on local infrastructure through Docker Compose, with no external LLM API.

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
make install    # create .venv with the locked dependencies and install the git hooks
```

Set `APP_UID` and `APP_GID` in `.env` if your user isn't 1000, so that the files the app writes
to `./data` stay yours.

On commit, the pre-commit hook fixes the staged files (trailing whitespace, final
newline, `ruff check --fix`, `ruff format`) and re-stages the fixes, so the commit only
fails on issues that cannot be fixed automatically. The commit message must be a
conventional commit (`feat: ...`, `chore: ...`) with a header of at most 72 characters.

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
| `make down`             | Stop the stack. Every volume stays                          |
| `make logs`             | Follow the app's logs                                       |
| `make pull-models`      | Download the configured models into Ollama                  |
| `make doctor`           | Check the services, models and GPU                          |
| `make test`             | Run the unit tests                                          |
| `make test-integration` | Run the tests that need the running stack                   |
| `make lint`             | Lint and format, applying fixes                             |
| `make lint-check`       | Lint and format checks only, no writes                      |
| `make commit`           | Commit through commitizen (conventional commit messages)    |
| `make hooks`            | (Re)install the pre-commit and commit-msg hooks             |
| `make update-hooks`     | Bump the pinned hook revisions in `.pre-commit-config.yaml` |
| `make check-updates`    | List what `make update` would upgrade, changing nothing     |
| `make update`           | Upgrade all dependencies to their latest versions           |
| `make reinstall`        | Delete `.venv` and run `make install` again                 |

`docker compose down -v` is not a reset: it deletes the named volumes, with the downloaded
models and the vector database in them.

## Interface

The Gradio interface at <http://localhost:7860> has four tabs:

| Tab           | What it does                                                                        |
| ------------- | ----------------------------------------------------------------------------------- |
| Library       | Upload, replace, remove and reindex books, and reset. Shows each book's status      |
| Chat          | Ask about one book, one chapter or several books, and inspect the retrieved passages |
| Summarization | Summarize a chapter in any of the types, and save the result                        |
| Research      | The latest question from the inside: models, each stage's scores, final context, reasoning, tokens, timings, and GPU memory |

Everything in it goes through the same services as the commands. Destructive actions need
the same confirmation in both, and errors appear as notifications that stay until dismissed,
because most of them say what to do next. A book that fails while indexing stays in the list
with its reason, and uploading it again retries it.

## Library

```bash
docker compose exec app book-rag add-book /path/inside/the/container/book.pdf
docker compose exec app book-rag list-books
```

Books go through extraction, normalization, structure detection and chunking. Each stage's
output stays in `data/processed/<book_id>/r<revision>/` for debugging, and the original file
in `data/original_books/<book_id>/`, from which everything else can be rebuilt. The catalog
in `data/metadata/catalog.db` is the source of truth for what the library holds. A file is
identified by its checksum, so uploading it twice under different names is detected.

How each format is read:

- **PDF**: PyMuPDF. The book's table of contents decides what a chapter is, and font sizes
  find the headings below it, or all of them when there is no table of contents. Running
  headers are recognized by repeating, or by carrying a number that follows the page. Page
  numbers are physical: 1 is the first page of the file, which is what a viewer jumps to.
  `pdf.extractor: docling` in `config/ingestion.yaml` runs layout models instead, for
  complex layouts.
- **Scanned PDFs** have no text to extract. They are rejected unless `pdf.ocr.enabled` is
  on, which sends them through Docling's OCR.
- **EPUB**: EbookLib, in spine order, with chapters taken from the table of contents.
  EPUBs have no pages, so `page_start` and `page_end` are null.
- **Markdown**: headings mark chapters and sections. Front matter can set `title`, `author`
  and `language`.

A chapter's `number` is its position in the book, which is unique where printed numbers are
not (a preface has none). The printed number stays in its title. Text before the first
chapter goes to chapter 0, "Front matter".

Chunk sizes are measured with the embedding model's own tokenizer, set in
`embedding_profiles` in `config/models.yaml`. Tokenizers are downloaded on first use and
never reach the network again.

### Changing the library

```bash
docker compose exec app book-rag replace-book book_001 /path/to/new.pdf
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
this touches the Docker volumes or the models in Ollama. The destructive operations ask for
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

## Index

Chunks go into one ChromaDB collection per index version, `book_chunks_v1` to begin with,
where every record carries its book, chapter, section, pages, language, embedding model and
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
book, chapter, section, language and page range. `config/retrieval.yaml` picks the strategy:

| `strategy` | Finds passages through                                                 |
| ---------- | ---------------------------------------------------------------------- |
| `dense`    | Nearest neighbors in ChromaDB                                          |
| `bm25`     | Term matching, stemmed in the book's language and ignoring accents     |
| `hybrid`   | Both, merged by `fusion.method`: `rrf` on ranks, `weighted` on scores  |

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

## Questions

```bash
docker compose exec app book-rag ask "What is opportunity cost?" --book book_001
docker compose exec app book-rag ask "Quais são os argumentos?" --book book_001 --chapter 4
docker compose exec app book-rag ask "Compare how they treat trade." --book book_001 --book book_002
docker compose exec app book-rag ask "What is the harm principle?" --language Portuguese
```

Answers come from the retrieved passages, with numbered citations that resolve to chapter,
section and pages. When the passages don't hold the answer, the model is told to say so
instead of answering from general knowledge.

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
```

The types (`brief`, `standard`, `comprehensive`, `analytical`) and their lengths are in
`config/generation.yaml`. A saved summary goes to `data/summaries/<book_id>/`, with a JSON
file saying how it was made.

Summaries don't use retrieval to pick their material: the top passages for "summarize this"
would leave out most of a chapter. Every chunk goes through map-reduce instead:

1. A chapter that fits in the context is summarized directly.
2. Otherwise, consecutive chunks are grouped in batches that a reply can do justice to, far
   smaller than what the context would hold, and each batch gets a partial summary.
3. A reply cut off by its token limit has lost the end of its batch, so the batch is redone
   in two halves. This is what makes the coverage figure mean something: `chunks_covered`
   counts chunks in steps that finished.
4. Partial summaries are sized to fit the final prompt together. Very long chapters merge
   them first, a few at a time.

Citations in a summary are computed, not claimed. Models don't carry source tags through
several rounds of summarizing: `gpt-oss` was seen numbering them upward, `[S1] [S2] [S3]`,
whatever they pointed at. So the model writes no citations, and each finished statement is
looked up among the chapter's chunks through the vector index, citing the passage it
resembles. It costs milliseconds per statement, and works the same for every model.
Statements close to no passage stay uncited and are counted, as the first place to look
for something the model added. The references quote each passage's opening words, because
that is how to find it in a book without pages.

## Benchmarks

Comparing configurations under controlled conditions is the point of this project, so the
benchmarks are a first-class part of it.

```bash
docker compose exec app book-rag pull-models --all          # every candidate model, about 40 GB
docker compose exec app book-rag fetch-benchmark-books      # verified against their checksums
docker compose exec app book-rag validate-benchmark         # every question, against the real text

make benchmark EXPERIMENT=retrieval                         # the whole dataset
make benchmark EXPERIMENT=generation LIMIT=2                # a sample, per book and category
```

| Experiment      | Compares                                                               | Measures                                                                                  |
| --------------- | ---------------------------------------------------------------------- | ----------------------------------------------------------------------------------------- |
| `extraction`    | PDF extractors                                                         | How much of each book's own structure survives                                            |
| `retrieval`     | Embedding models, strategies, fusion, rerankers, chunk sizes           | Recall@5, Recall@10, MRR, nDCG@10, context precision and recall                           |
| `generation`    | The four LLMs, on identical retrieved contexts                         | Faithfulness, correctness, relevance, citation accuracy, language, abstention             |
| `summarization` | The four LLMs, on chapters with known key points                       | Argument coverage, concepts, consistency, coherence, completeness, citation traceability  |
| `performance`   | The four LLMs, at 8K and 16K of context                                | Load time, time to first token, speeds, peak memory: the median of 3 runs after a warm-up |

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
more than noise. The full runs, and what they suggest, are in `docs/benchmark-results.md`.

An experiment is a YAML file: variants that are the normal configuration plus overrides, checked
by the same validation as `config/`. It runs in `benchmarks/workspace`, on separate files and
`bench_*` collections, so it can't touch the real library. Variants that index the same way
share a workspace. A workspace whose index no longer matches the configuration is rebuilt, but a
change to the ingestion code can't be seen: delete `benchmarks/workspace` after one.

The dataset is three books: *Quincas Borba* in Portuguese, *Think Python* in English from a PDF,
and *On Liberty* for its complex arguments. Each has 30 questions: 10 factual, 5 conceptual, 5
across sections, 5 about one chapter, and 5 that the book can't answer, some of them traps that
name a detail the text leaves out. All three books can be redistributed, so anyone can reproduce
the results, and their checksums guarantee the same files.

Relevance is stored as verbatim evidence quotes, not chunk IDs. IDs change with every chunk size,
and comparing chunk sizes is one of the experiments, while a quote finds its chunks under any
configuration. Each result row lists the chapters, pages and chunks the evidence resolved to.

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

Scoring is slow: about 30 s per answer for the three RAGAS metrics, and about a minute per
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
- The app container gets the GPU too, for the reranker and Docling when they are configured
  to use it. torch comes from the CUDA 13.4 index: the RTX 5060 Ti is a Blackwell GPU, which
  builds for older CUDA versions cannot drive.
- `config/` is mounted read-only, so a configuration change only needs
  `docker compose restart app`. The app validates all of it at startup.

## Configuration

| File                      | Holds                                                   |
| ------------------------- | ------------------------------------------------------- |
| `config/application.yaml` | Server, upload limits, timeouts and logging             |
| `config/models.yaml`      | The LLM, embedding model and reranker                   |
| `config/ingestion.yaml`   | PDF extraction, normalization, languages and chunking   |
| `config/retrieval.yaml`   | Retrieval strategy and its parameters                   |
| `config/generation.yaml`  | Temperature and token limits per task                   |

Unknown keys are errors, so a typo stops the app at startup instead of being ignored.
Addresses and directories come from the environment; their defaults are the Compose
service names.

## Layout

```
app/
  main.py          # the commands, and the entry point
  container.py     # builds the object graph: the only place that knows what is concrete
  config/          # typed settings, validated at startup
  ingestion/       # from a file to chunks: loaders, normalization, structure, chunking
  embeddings/      # the embedding provider interface and Ollama behind it
  retrieval/       # dense, BM25, fusion, reranking and the pipeline around them
  generation/      # the LLM provider, questions, summaries, prompts and citations
  storage/         # the catalog in SQLite, ChromaDB, and the library's files
  services/        # the operations: what both Gradio and the commands call
  interface/       # the Gradio tabs, as thin as they can be
  evaluation/      # the dataset, the metrics and the experiment runner
config/            # everything that can change without touching code
benchmarks/        # datasets and experiments. Books, workspaces and results stay untracked
data/              # the library: originals, processed files, summaries and the catalog
docs/              # what was decided and why, and what the benchmarks found
tests/unit/        # no services needed: real files, real SQLite, embedded ChromaDB, fake models
tests/integration/ # against the running stack and the real models
```
