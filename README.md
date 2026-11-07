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
