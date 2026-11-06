# local-book-rag

Local RAG research platform for books. `.TASK/task.md` is the specification (it stays
local: `.git/info/exclude` keeps it out of the repository). Build it one milestone at a
time, in the order of its section 22.

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
