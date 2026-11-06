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

## Setup

```bash
make env        # copy devtools/.env.sample to .env (won't overwrite an existing one)
make install    # create .venv with the locked dependencies and install the git hooks
```

On commit, the pre-commit hook fixes the staged files (trailing whitespace, final
newline, `ruff check --fix`, `ruff format`) and re-stages the fixes, so the commit only
fails on issues that cannot be fixed automatically. The commit message must be a
conventional commit (`feat: ...`, `chore: ...`) with a header of at most 72 characters.
