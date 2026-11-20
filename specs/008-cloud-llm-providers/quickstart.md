# Quickstart: checking cloud models for chat and summaries

How to check, on the owner's machine, that the feature does what the spec asks. The contracts say
what each check expects in detail: `contracts/configuration.md`, `contracts/services.md` and
`contracts/interface.md`.

## 0. Before anything

- **An Anthropic API key**, from the Claude Console. The checks below spend well under a dollar,
  most of it in § 8's summaries and § 13's integration tests.
- **Which models**: `claude-haiku-5-5`, the cheapest, and `claude-sonnet-5-5`, plus a name that
  Anthropic doesn't know, `claude-no-such-model`, to make a model fail on purpose.
- **What gets deleted**: § 2 and § 3 rebuild or recreate the app container, which deletes what it
  holds (Principle II): the library, its logs, the tokenizers and the reranker's weights it
  downloaded, and its copy of `benchmarks/`. The library is empty now, by the owner's choice.
  ChromaDB and Ollama keep their data.

## 1. Unit tests and lint (SC-012)

```bash
make lint-check
make test
```

Expected: both pass. The unit tests cover what a stack can't easily show: the settings read with
one, both or neither set; every failure reason moving on to the next model; text withdrawn after
a failure (SC-008); a summary that fails at its second step, written whole by the next model
(SC-007); a second, fake provider (SC-009); and no trace of a fake key in the logs (SC-011).

## 2. Without the settings (SC-001)

`.env` without `ANTHROPIC_API_KEY` and `ANTHROPIC_MODELS`. Commit the branch first, so that the
image holds it. `make up` rebuilds the image and recreates the app container, deleting what § 0
lists. ChromaDB still holds the old library's collections, and the new catalog numbers its indexes
from 1 again, so `reset-everything` comes next, as in `specs/007`. It deletes the library, now
empty, and every `book_chunks_v*` collection:

```bash
make up
docker compose exec app book-rag reset-everything --confirm "DELETE EVERYTHING"
docker compose exec app book-rag doctor
```

Expected:
- `doctor` prints the rows that it prints on `main`, and no row about a provider.
- The Chat and Summarization tabs show no model choice and no notice; the Research tab, no new
  row.
- `book-rag ask --help` lists `--model` and `--fallback`; everything else prints as on `main`.

## 3. The settings, and a book

Add to `.env`, replacing the key:

```dotenv
ANTHROPIC_API_KEY=sk-ant-...
ANTHROPIC_MODELS=claude-haiku-5-5,claude-sonnet-5-5,claude-no-such-model
```

Changing `.env` makes `make up` recreate the app container, which deletes what § 0 lists again,
the library still empty (Principle II). Then add *On Liberty*, one of the benchmark's books, for
the checks:

```bash
make up
docker compose exec app book-rag reset-everything --confirm "DELETE EVERYTHING"
docker compose cp benchmarks/books/on-liberty.md app:/tmp/on-liberty.md
docker compose exec app book-rag add-book /tmp/on-liberty.md
docker compose exec app book-rag list-books
```

Expected: the app starts, and nothing contacted Anthropic while it did (no "generation finished"
or check in its log). *On Liberty* is `book_001`.

## 4. The checks (SC-002, FR-002, FR-021)

```bash
docker compose exec app book-rag doctor
```

Expected: a row per allowed model. `claude-haiku-5-5` and `claude-sonnet-5-5` pass, each with its
display name and window; `claude-no-such-model` fails: "Anthropic doesn't know this model". So
`doctor` exits with 1.

In the Research tab, after any answer, the health checks show no provider row; "Check again"
shows the three rows above.

To see the check of a refused key without losing the library, call `doctor` with a wrong key in
its own process: `docker compose exec -e ANTHROPIC_API_KEY=sk-ant-wrong app book-rag doctor`.
Expected: one failing row, "Anthropic refused the API key", and no key in the output.

## 5. The same passages (SC-004, User Story 1)

```bash
Q="What does Mill say about the tyranny of the majority?"
docker compose exec app book-rag ask "$Q" --book book_001
docker compose exec app book-rag ask "$Q" --book book_001 --model claude-haiku-5-5
docker compose exec app book-rag ask "$Q" --book book_001 --model claude-sonnet-5-5 --language Portuguese
```

Expected:
- The three answers cite passages, and every citation resolves to a book, chapter and section.
- The second and third end with "Answered by … (Anthropic)"; the first prints as on `main`.
- The third answers in Portuguese.
- In the Chat tab, with Claude picked, the notice names Anthropic before asking. The Research
  tab's final context for Claude holds the same passages, in the same order, as for the local
  model: the search is the same.

## 6. An abstention (FR-011)

```bash
docker compose exec app book-rag ask "Who won the 1998 World Cup?" --book book_001 --model claude-haiku-5-5
```

Expected: "The model found no answer in the sources." Claude used the no-evidence marker, and the
app read it as an abstention. If it abstained in words instead, without the marker, that goes to
`docs/decisions.md`, and the profile's `check_abstentions` is reconsidered (Principle V).

## 7. Fallbacks (SC-006, User Stories 1 and 3)

```bash
docker compose exec app book-rag ask "$Q" --book book_001 --model claude-no-such-model
docker compose exec app book-rag ask "$Q" --book book_001 --model claude-no-such-model --fallback claude-haiku-5-5
docker compose exec app book-rag ask "$Q" --book book_001 --model claude-haiku-5-5 --fallback claude-haiku-5-5
```

Expected:
1. Standard error says that `claude-no-such-model` (Anthropic) failed, because Anthropic doesn't
   know it, and that `gpt-oss:20b` answers. The local model answers, and the last line names it.
2. `claude-haiku-5-5` answers, and the local model isn't called.
3. Refused before any search: a name given twice. The error lists the names offered.

In the Chat tab, the same three, picking the model and the fallbacks: the status line says each
failure as it happens, and the Research tab lists it under "Failed first".

## 8. Summaries (SC-005, User Story 2)

```bash
docker compose exec app book-rag summarize book_001 2 --model claude-haiku-5-5 --save
docker compose exec app book-rag summarize book_001 3 --save
docker compose exec app sh -c 'cat data/summaries/book_001/chapter_02_standard.json'
docker compose exec app sh -c 'sha256sum data/summaries/book_001/*.md'
docker compose exec app book-rag reindex-all --regenerate-summaries
docker compose exec app sh -c 'sha256sum data/summaries/book_001/*.md'
```

Expected:
- Chapter 2's last line names `claude-haiku-5-5 (Anthropic)` and its tokens; its JSON file holds
  `provider: anthropic`, `failed_attempts: []` and `tokens`. Chapter 3's is the local model's,
  with `provider: ollama` and no `tokens`.
- `reindex-all` lists chapter 2's summary as kept, written by `claude-haiku-5-5`. Its checksum
  doesn't change; chapter 3's does, written again by the local model.
- In the Summarization tab, with Claude picked, the notice says that the chapter's text goes to
  Anthropic. With `claude-no-such-model` picked, the progress says that it failed, and the summary
  is the local model's, whose report names the failure.

## 9. The tabs' choices (FR-006 to FR-010)

In the browser:
1. Pick `claude-sonnet-5-5` in the Chat tab. The Summarization tab still shows the local model.
2. In the Chat tab, pick `claude-no-such-model`, then `claude-haiku-5-5`, as fallbacks: the
   notice lists them in that order, and so does the request's sequence (§ 7). Pick them in the
   other order: the notice follows. This is the check that Gradio's multiselect keeps the order
   of selection (`research.md`, R13).
3. Reload the page: both tabs are back on the local model, with no fallbacks.

## 10. The Research tab (User Story 4, FR-024, FR-025)

Ask once with `claude-sonnet-5-5`, then once with the local model:
- After Claude: the LLM row names `claude-sonnet-5-5` and Anthropic; tokens, time to first token
  and generation speed are Claude's; model loading and prompt processing read "unavailable"; the
  reasoning is labeled as Anthropic's summary, or says that none came back.
- After the local model: what the tab shows on `main`.

## 11. The key, nowhere (SC-011)

```bash
docker compose exec app sh -c 'grep -rlF "$ANTHROPIC_API_KEY" logs data || echo "no trace of the key"'
```

Expected: "no trace of the key". The page source and the command outputs of § 4 to § 10 hold none
either.

## 12. Benchmarks stay local (SC-010)

```bash
cat > benchmarks/experiments/cloud_refused.yaml <<'EOF'
name: cloud_refused
kind: generation
description: Must be refused before it runs (specs/008, SC-010).
judge:
  model: gpt-oss:20b
  embedding_model: qwen3-embedding:0.6b
  max_tokens: 6000
  reasoning: low
variants:
  - name: claude
    overrides:
      llm: {model: "claude-haiku-5-5"}
EOF
docker compose cp -a benchmarks app:/app/
docker compose exec app book-rag benchmark benchmarks/experiments/cloud_refused.yaml --limit 1
rm benchmarks/experiments/cloud_refused.yaml
```

§ 2's rebuild deleted the container's copy of `benchmarks/`, so the copy brings the dataset back
with the experiment.

Expected: refused before it runs, because `llm_profiles` has no entry for `claude-haiku-5-5`, and
no request reaches Anthropic. The same with the judge's `model` set to `claude-haiku-5-5`.

## 13. Integration tests (SC-003, Principle V)

On the host, with the settings exported from `.env` to the tests:

```bash
set -a; . ./.env; set +a
make test-integration
```

Expected: the cloud tests run on `claude-haiku-5-5`, the first allowed model, and pass: an answer
whose citations resolve, an abstention with the marker, the stats and the reasoning, a short
summary cited by lookup, the key check. Without the settings exported, they are skipped and the
others pass. What Claude wrote differently from the local models goes to `docs/decisions.md`
(FR-030).

## 14. The records, and the library

- `README.md` and `docs/decisions.md` say what FR-029 and FR-030 ask.
- The library holds *On Liberty* and the summaries of § 8. The owner removes them, or resets the
  library, and adds their own book back.
- To stop offering Claude, empty both settings in `.env` and run `make up`, which recreates the
  container and empties the library again.
