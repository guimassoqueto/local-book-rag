# asdf picks the Python version (.tool-versions) and uv installs the dependencies.
# Handing uv that exact version makes it fail instead of falling back to another
# Python, and rebuild .venv when .tool-versions changes.
export UV_PYTHON := $(shell awk '$$1 == "python" {print $$2}' .tool-versions)

.PHONY: env install reinstall update check-updates speckit-upgrade hooks update-hooks lint lint-check \
	commit test test-integration up down restart logs pull-models doctor benchmark

env:
	@test -f .env && echo ".env already exists, leaving it untouched." || cp devtools/.env.sample .env

# Create .venv if needed and make it match uv.lock exactly.
install:
	@uv sync --all-extras
	@$(MAKE) --no-print-directory hooks

reinstall:
	@rm -rf .venv
	@$(MAKE) --no-print-directory install

# Upgrade every dependency to its latest version, rewriting uv.lock.
update:
	@uv sync --all-extras --upgrade

# Show what `make update` would change, without changing anything.
check-updates:
	@uv lock --upgrade --dry-run

# Regenerate Spec Kit's files from the specify-cli in uv.lock: run it after `make update`
# brings a new version, and review the diff. Each integration keeps its stored options
# (claude's --no-model-invocation). `extension add` and `update` render extension skills
# for the default integration only, so codex is made the default for a moment to get them.
# `integration use` rewrites the shared scripts without their executable bit, which the
# skills need: the chmod puts it back.
speckit-upgrade:
	@uv run specify integration upgrade claude
	@uv run specify integration upgrade codex
	@uv run specify extension update
	@uv run specify integration use codex
	@uv run specify integration use claude
	@chmod +x .specify/scripts/bash/*.sh
	@uv run specify integration status

hooks:
	@uv run pre-commit install && uv run pre-commit install --hook-type commit-msg

update-hooks:
	@uv run pre-commit autoupdate

lint:
	@uv run ruff check --fix .
	@uv run ruff format .

lint-check:
	@uv run ruff check .
	@uv run ruff format --check .

commit:
	@uv run cz commit

test:
	@uv run pytest -m "not integration"

# Needs `make up` and the models from `make pull-models`.
test-integration:
	@uv run pytest -m integration

up:
	@docker compose up -d --build

# Removes the containers, and with them the library, the vectors and the models: none is in a volume.
down:
	@docker compose down

restart:
	@docker compose restart

logs:
	@docker compose logs -f app

pull-models:
	@./scripts/pull_models.sh

doctor:
	@docker compose exec app book-rag doctor

# Run one experiment from benchmarks/experiments, as in `make benchmark EXPERIMENT=retrieval`, once
# benchmarks/ is copied into the app container (README, Benchmarks).
# LIMIT=2 takes a sample, of that many questions per book and category.
benchmark:
	@test -n "$(EXPERIMENT)" || { echo "usage: make benchmark EXPERIMENT=<name> [LIMIT=<n>]"; exit 1; }
	@docker compose exec app book-rag benchmark benchmarks/experiments/$(EXPERIMENT).yaml $(if $(LIMIT),--limit $(LIMIT))
