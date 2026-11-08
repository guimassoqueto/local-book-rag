# local-book-rag

Local RAG research platform for books. `.TASK/task.md` is the specification (it stays
local: `.git/info/exclude` keeps it out of the repository). Build it one milestone at a
time, in the order of its section 22.

`README.md` explains how the system works, and `docs/decisions.md` why. Read the second before
changing a behavior that looks odd: most of those decisions came from a failure on real books
or real model output, which unit tests didn't show.

## Conventions

- Python 3.13 from asdf (`.tool-versions`). uv manages `.venv`: add dependencies unpinned
  with `uv add --raw <pkg>` (plus `--dev` for tooling), run tools with `uv run`. Never
  `pip install`: `.venv` has no pip, so it would hit asdf's global Python.
- `asdf latest python 3.13` can answer with a free-threaded build (`3.13.18t`). Pin the
  plain version, and keep the Dockerfile's base image on the same one.
- `make lint` / `make lint-check`: ruff fix / check only (line length 120, config in
  `pyproject.toml`). `make test` runs the unit tests; `make test-integration` needs the
  running stack.
- A commit-msg hook enforces conventional commits (`feat:`, `fix:`, `chore:`, ...) with a
  72-character header; `make commit` runs commitizen.
- Use `git mv` when moving tracked files.
- `README.md` is the human-facing doc; update it when the architecture changes.

## Rules that are easy to break

- `docker compose down -v` deletes the Ollama models and the ChromaDB data. Nothing in
  this project may run it; resetting the library happens inside the application.
- Gradio and the CLI share the service layer in `app/services`: no business logic in
  either of them.
- Model names live in `config/`, never in Python.
- Vectors from different embedding models never share a collection, and a change to the
  embedding or chunking configuration needs an explicit reindex.
- Nothing may close an operation's journal entry until the work, or its undoing, has really
  finished. A failed cleanup is treated like a crash: recovery takes over.
- Never trust a model's output format. Test against the real models too: `gpt-oss` cites as
  `【3】`, ignores `think=False`, and numbers source tags upward whatever they point at.
- Benchmarks run in `benchmarks/workspace`, and must never touch the real library. When
  editing `benchmarks/datasets/questions.jsonl`, run `book-rag validate-benchmark`.
- Don't trust a benchmark number because it looks plausible: a broken judge scores, it doesn't
  crash. Before relying on a metric or changing a judge, check that it separates cases whose
  answer is known, such as a real summary, a distorted one and another chapter's.
- Nothing long goes through Ollama's OpenAI-compatible endpoint. It can't set `num_ctx`, so it
  runs at 4096 tokens and silently cuts the prompt. Use the provider in `app/generation`.
