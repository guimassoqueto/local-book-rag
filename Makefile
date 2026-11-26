# asdf picks the Python version (.tool-versions) and uv installs the dependencies.
# Handing uv that exact version makes it fail instead of falling back to another
# Python, and rebuild .venv when .tool-versions changes.
export UV_PYTHON := $(shell awk '$$1 == "python" {print $$2}' .tool-versions)

.PHONY: env install reinstall update check-updates speckit-upgrade hooks update-hooks beads lint lint-check \
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

# Connect this clone to the private issue tracker (README, Setup): clone it beside this
# repository if it isn't there, and point .beads/redirect at it, so that this repository keeps no
# issue data of its own. Nothing else here needs beads. It never runs `bd init` here, which would
# commit beads' files and make this repository's origin the tracker's remote.
BEADS_TRACKER_URL ?= git@github.com:guimassoqueto/issues.git
BEADS_TRACKER_DIR ?= ../issues
BEADS_MIN_VERSION := 1.3.4

beads:
	@v=$$(bd version 2>/dev/null | sed -n 's/^bd version \([0-9][0-9.]*\).*/\1/p'); \
	if [ -z "$$v" ]; then \
		echo "beads (bd) isn't installed: see https://beads.gascity.com/getting-started/installation"; exit 1; \
	fi; \
	if [ "$$(printf '%s\n%s\n' $(BEADS_MIN_VERSION) "$$v" | sort -V | head -n 1)" != "$(BEADS_MIN_VERSION)" ]; then \
		echo "bd $$v is older than $(BEADS_MIN_VERSION): see https://beads.gascity.com/getting-started/upgrading"; exit 1; \
	fi
	@for f in embeddeddolt dolt metadata.json config.yaml; do \
		if [ -e ".beads/$$f" ]; then \
			echo ".beads/$$f exists: bd init ran here, and its remote may be this repository's origin."; \
			echo "Nothing was deleted. Move .beads aside by hand, then run make beads again."; exit 1; \
		fi; \
	done
	@if [ ! -d "$(BEADS_TRACKER_DIR)" ]; then \
		git clone "$(BEADS_TRACKER_URL)" "$(BEADS_TRACKER_DIR)" \
			&& chmod 700 "$(BEADS_TRACKER_DIR)/.beads" \
			&& git -C "$(BEADS_TRACKER_DIR)" config beads.role maintainer \
			&& (cd "$(BEADS_TRACKER_DIR)" && bd bootstrap) || exit 1; \
	fi
	@mkdir -p .beads && printf '%s/.beads\n' "$(BEADS_TRACKER_DIR)" > .beads/redirect
	@git config beads.role maintainer
	@bd where && echo "Beads of this repository: $$(bd count --label repo:local-book-rag)"

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
