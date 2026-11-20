# Quickstart: checking OpenAI's models for chat and summaries

How to check, on the owner's machine, that the feature does what the spec asks. The contracts say
what each check expects in detail: `contracts/configuration.md` and `contracts/providers.md`. The
interfaces' wording is 008's (`specs/008-cloud-llm-providers/contracts/interface.md`).

## 0. Before anything

- **An OpenAI API key**, from platform.openai.com, in `.env` as `OPENAI_API_KEY`, never in a chat
  or a file of the repository. `OPENAI_MODELS=gpt-6-luna,gpt-6.1-terra,gpt-6.2-sol` beside it
  (Clarifications). The checks below spend well under a dollar, most of it in § 2 and § 7.
- **A name that OpenAI doesn't know**, `gpt-no-such-model`, to make a model fail on purpose, and
  Claude's settings as they are in `.env`, for the mixed sequences.
- **What gets deleted**: § 3 recreates the app container, which deletes what it holds
  (Principle II): **the library, with the owner's *História* and every summary saved from it,
  whichever model wrote it, Claude's included**, the logs, the tokenizers and the reranker's
  weights it downloaded, and its copy of `benchmarks/`. ChromaDB and Ollama keep their data. § 1
  and § 2 touch none of it, so they run first.

## 1. Unit tests and lint (SC-012, SC-007, SC-008, SC-011)

```bash
make lint-check
make test
```

Expected: clean, and every test passes, `tests/unit/test_openai_provider.py` included. Then:

```bash
git diff main --stat -- app/services app/interface app/main.py tests/unit/test_anthropic_provider.py
```

Expected: no output. The services, the tabs and the commands are as on `main` (SC-011), and
Claude's provider tests passed without a change to them (FR-021, research.md R9).

## 2. The real models, before the stack (SC-003, SC-009, FR-026, Principle V)

On the host, with the settings exported from `.env` into this shell only:

```bash
set -a; . ./.env; set +a
uv run pytest -m integration tests/integration/test_cloud_generation.py -s
```

The cloud tests alone need no running stack: they call the providers directly. `make
test-integration` runs them with the others, which need `make up` and the models loaded.

Expected:
- **Each of the three models** passes the key check, the five answerable cases with citations that
  resolve, the three unanswerable ones read as abstentions, and the short summary cited by lookup.
  Claude's models run too, on Claude's settings, and pass as before.
- **The output prints**, per model, the app's estimate and OpenAI's input tokens for the eight
  questions' prompts and the summary's, the largest ratio, and the reasoning tokens of each reply
  (SC-009, research.md R6, R11).
- **A refusal to stream**, if OpenAI makes one, fails the cases of that model with the
  verification reason (Clarifications); a refused reasoning summary passes, without reasoning
  (FR-015). Either goes to `docs/decisions.md` as the owner's organization got it.

Then, by research.md R6's rules, in this order, running the cases again after each change:
- **A model the organization can't use**, because OpenAI doesn't know it for the key, won't let
  the project use it, or won't stream it to the organization: drop it from `OPENAI_MODELS` in
  `.env`, and record it with OpenAI's reason for `docs/decisions.md` (SC-003). The feature holds
  while one model remains.
- **An abstention in words, without the marker**, on any case of any model: set
  `check_abstentions: true` in `cloud_profiles.openai`, for every model.
- **A reply that ran out during its reasoning** (incomplete, no text): double `reasoning_tokens`.
- **The largest ratio**: into the profile's comments; above 1.11, the README says what the window
  caps in OpenAI's tokens.

Close the shell afterwards: it holds the key, as FR-004 allows.

## 3. The settings, and a book

`.env` holds both OpenAI settings. Recreating the app container **deletes the library, *História*
included** (§ 0):

```bash
make up
docker compose exec app book-rag reset-everything --confirm "DELETE EVERYTHING"
docker compose cp benchmarks/books/on-liberty.md app:/tmp/on-liberty.md
docker compose exec app book-rag add-book /tmp/on-liberty.md
docker compose exec app book-rag list-books
```

`reset-everything` clears the old collections that ChromaDB kept, as in 008. Expected: *On
Liberty* as `book_001`, indexed.

## 4. The checks (SC-002, FR-002, FR-017)

```bash
docker compose exec app book-rag doctor
```

Expected: Claude's rows as before, then `openai gpt-6-luna`, `openai gpt-6.1-terra` and `openai
gpt-6.2-sol`, each found. Then, each in its own process, so nothing is recreated:

```bash
docker compose exec -e OPENAI_API_KEY=sk-wrong app book-rag doctor
docker compose exec -e OPENAI_MODELS= app book-rag doctor
docker compose exec -e OPENAI_MODELS=gpt-6-luna,gpt-no-such-model app book-rag doctor
```

Expected: one failing row, "OpenAI refused the API key", and Claude's rows unchanged; a failing
row naming the missing `OPENAI_MODELS`; `gpt-no-such-model` failing, `gpt-6-luna` found. That
startup and local answers make no request to OpenAI is shown by the unit tests (SC-002), not here.

## 5. Questions (SC-004, User Story 1)

```bash
Q="What does Mill say about the tyranny of the majority?"
docker compose exec app book-rag ask "$Q" --book book_001
docker compose exec app book-rag ask "$Q" --book book_001 --model gpt-6-luna
docker compose exec app book-rag ask "$Q" --book book_001 --model gpt-6.2-sol --language Portuguese
docker compose exec app book-rag ask "Who won the 1998 World Cup?" --book book_001 --model gpt-6-luna
```

Expected: the notice on standard error before anything is sent, naming OpenAI; the same sources,
in the same order, for the three answers; every citation resolving; the Portuguese answer in
Portuguese; the last one an abstention. The inference log's `generation finished` names the model
OpenAI reported.

## 6. Fallbacks across providers (SC-006, User Story 3)

```bash
docker compose exec app book-rag ask "$Q" --book book_001 --model gpt-no-such-model
docker compose exec -e OPENAI_MODELS=gpt-6-luna,gpt-no-such-model app book-rag ask "$Q" --book book_001 --model gpt-no-such-model --fallback claude-haiku-5-5
docker compose exec -e ANTHROPIC_MODELS=claude-haiku-5-5,claude-no-such-model app book-rag ask "$Q" --book book_001 --model claude-no-such-model --fallback gpt-6-luna
docker compose exec -e ANTHROPIC_MODELS=claude-no-such-model -e OPENAI_MODELS=gpt-no-such-model app book-rag ask "$Q" --book book_001 --model claude-no-such-model --fallback gpt-no-such-model
```

The first is refused before searching: `gpt-no-such-model` isn't in `.env`'s list. Expected for
the others: Claude Haiku answers after the OpenAI failure; `gpt-6-luna` answers after the Claude
failure, and the local model makes no generation; `gpt-oss:20b` answers after both failures,
listed in order, each with its provider. The notice names both providers in the sequence's order.

## 7. Summaries (SC-005, User Story 2)

```bash
docker compose exec app book-rag summarize book_001 2 --model gpt-6.1-terra --save
docker compose exec app sh -c 'cat data/summaries/book_001/chapter_02_standard.json'
docker compose exec app sh -c 'sha256sum data/summaries/book_001/*.md'
docker compose exec app book-rag reindex-all --regenerate-summaries
docker compose exec app sh -c 'sha256sum data/summaries/book_001/*.md'
```

Expected: the report names `gpt-6.1-terra (OpenAI)` and its tokens; the JSON records `provider:
openai` and the tokens; `reindex-all` lists it as kept, with its model, the file unchanged byte
for byte, and makes no request to any provider.

## 8. The tabs (FR-007, User Stories 1, 3 and 4)

In the browser, at the interface's address:
- **Chat**: the choice lists `gpt-oss:20b (local)`, Claude's models, then `gpt-6-luna (OpenAI)`,
  `gpt-6.1-terra (OpenAI)`, `gpt-6.2-sol (OpenAI)`. Picking `claude-sonnet-5-5` with `gpt-6.2-sol`
  as its fallback shows "…go to Anthropic: claude-sonnet-5-5, then OpenAI: gpt-6.2-sol. If they
  fail, gpt-oss:20b answers, locally." Ask with `gpt-6.2-sol`: the answer streams.
- **Research**: after that answer, "gpt-6.2-sol (OpenAI)", the tokens read and generated, the time
  to first token and the total, loading and prompt processing unavailable, and the reasoning under
  "A summary of the reasoning, as OpenAI returns it", or "None came back." "Check again" shows
  OpenAI's rows; the checks that run on their own after an answer don't.
- **Summarization**: the notice for `gpt-6-luna` names OpenAI and the chapter's text.

## 9. The key, nowhere (SC-010)

```bash
docker compose exec app sh -c 'grep -rlF "$OPENAI_API_KEY" logs data || echo "no trace of the key"'
```

Expected: "no trace of the key". The page's source, saved from the browser after § 8, holds none
either.

## 10. Benchmarks stay local (SC-008, FR-019)

As 008's § 12, with `gpt-6-luna` in the variant's `llm.model`, then as the judge's `model`.
Expected: both refused before the run starts, and no request reaches OpenAI.

## 10a. The whole integration suite (SC-003, Principle V)

On the host, with the stack up from § 3 and the settings exported:

```bash
set -a; . ./.env; set +a
make test-integration
```

Expected: the cloud cases pass on Claude's models and on every OpenAI model that stays in
`OPENAI_MODELS`, and the local and stack tests pass as on `main`. If the reranker's GPU test runs
out of memory while `gpt-oss` is loaded, as it did in 008, unload the model and run that test
again. Close the shell afterwards.

## 11. The records, and the library

- `README.md` and `docs/decisions.md` say what FR-024 and FR-025 ask, with § 2's measurements.
- The library holds *On Liberty* and § 7's summary. The owner removes them, or resets the
  library, and adds *História* back.
