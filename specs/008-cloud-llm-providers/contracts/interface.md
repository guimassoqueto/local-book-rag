# Contract: the tabs and the commands

What the owner sees and types (FR-006 to FR-010, FR-013, FR-018, FR-022 to FR-025; `research.md`,
R9, R13 and R14). The handlers read input, call a service, and show what it returns.

## Without cloud settings

Every tab and command looks and prints as on `main` (FR-002, SC-001): no model choice, no notice,
no new row, no new line. `--model` and `--fallback` exist, and accept the local model's name only.

## The model choice, in the Chat and Summarization tabs

Each tab has its own, built by `app/interface/model_choice.py` (FR-009):

| Component | Shown | Content |
| --------- | ----- | ------- |
| Model (dropdown) | when a cloud model is offered | `gpt-oss:20b · local`, then `claude-sonnet-5-5 · Anthropic`, and so on; the local model on every page load |
| If it fails, then (multiselect) | while a cloud model is picked | the other cloud models offered, kept in the order chosen; note: "The local model answers last." |
| Notice | while a cloud model is picked | see below |

The notice (FR-010), from `models.describe(model, fallbacks)`:
- Chat: "The question and the passages found go to Anthropic: claude-sonnet-5-5, then
  claude-opus-5-5. If they fail, gpt-oss:20b answers, locally."
- Summarization: "The chapter's text goes to Anthropic: claude-sonnet-5-5. If it fails,
  gpt-oss:20b summarizes it, locally."

A fallback list that `describe()` refuses, a stale page's for example, shows the refusal in place
of the notice, and asking or generating shows it as an error.

## The Chat tab

| Moment | Status line | Answer area |
| ------ | ----------- | ----------- |
| searching | "Searching the books…", as today | empty |
| passages found | "Found 5 passages. Writing the answer…", as today; with a cloud model, "…Asking claude-sonnet-5-5 (Anthropic)…" | the text as it streams |
| a model fails | "⚠️ claude-sonnet-5-5 (Anthropic) failed: it limited the rate. Asking gpt-oss:20b…" | emptied, then the next model's text |
| answered by the local model, no failure | as today: "Answered in **3.1 s** · 211 tokens at 48 tokens/s" | the answer |
| answered otherwise | "Answered by claude-sonnet-5-5 (Anthropic) in **4.2 s** · 312 tokens at 85 tokens/s", then each failure on a line of its own | the answer |
| every model failed | the error, listing each failure | empty |

Sources and retrieved passages show as today, for the model that answered.

## The Summarization tab

- Progress messages, as today, plus each failure: "claude-sonnet-5-5 (Anthropic) failed: it
  limited the rate. Starting again with gpt-oss:20b."
- The report's first line names the provider beside the model: "(direct, `claude-sonnet-5-5`,
  Anthropic)". For a cloud model, it adds "Read 18,204 tokens and generated 1,377." A line per
  failed attempt follows. A local summary without failures reports as today (FR-022).
- "Save the summary" saves what the report shows, failures and tokens included.

## The Research tab

| Row or section | For a local answer with no failure | For any other answer |
| -------------- | ---------------------------------- | -------------------- |
| LLM | the model, as today | the model that answered, with its provider: `claude-sonnet-5-5` (Anthropic) |
| Failed first | absent | a row per failed attempt, in order: `claude-x` (Anthropic): it doesn't know this model |
| Prompt tokens, Generated tokens, Time to first token, Generation speed, Generation | as today | the cloud model's |
| Model loading, Prompt processing | as today | "unavailable", for a cloud model |
| The model's reasoning | as today | the reasoning, under "A summary of the reasoning, as Anthropic returns it", or "None came back." |
| Final context | as sent | as sent to the model that answered |
| Health checks, after an answer | today's checks, no provider | today's checks, no provider (FR-021) |
| Health checks, "Check again" | today's checks, plus each provider's rows | the same |

## The Library tab

After "Rebuild the index" with "Also write the saved summaries again", a notice lists the
summaries kept: "Kept as they were, written by a cloud model: book_001, chapter_04_standard
(claude-sonnet-5-5, Anthropic)."

## The commands

### `ask`

```text
book-rag ask QUESTION [--book ID]... [--chapter N]... [--language LANGUAGE]
             [--model NAME] [--fallback NAME]...
```

- Standard output: the answer as it streams, then "Sources:" and its lines, as today.
- Standard error, on a failure: "claude-sonnet-5-5 (Anthropic) failed: it limited the rate. The
  text above is discarded: gpt-oss:20b answers from the start."
- When a cloud model answered, or a model failed: a last line, "Answered by claude-sonnet-5-5
  (Anthropic)", before the timing.
- A refused sequence: the `ModelChoiceError`, before any search; the exit status is 1, as for
  any error.

### `summarize`

```text
book-rag summarize BOOK CHAPTER [--type TYPE] [--language LANGUAGE] [--save]
                   [--model NAME] [--fallback NAME]...
```

- Standard output: the summary, as today.
- Standard error: the progress, with each failure; then the last line, which adds the provider,
  and for a cloud model the tokens: "direct: 41/41 chunks in 2 steps, 23 cited, 2 statements
  without a source, 38.4s, claude-sonnet-5-5 (Anthropic), 18204 tokens read and 1377 generated".

### `doctor`

Runs `health.run(inference=..., providers=True)`. Each row as today:

```text
[ ok ] anthropic claude-sonnet-5-5 Claude Sonnet 5.5, 1000000-token window
[FAIL] anthropic claude-x Anthropic doesn't know this model
```

A failing provider row fails `doctor`, as any failing row does.

### `reindex-all`

After the lines of today, when summaries were kept:

```text
  kept as they were, written by a cloud model: book_001, chapter_04_standard (claude-sonnet-5-5, Anthropic)
```

### `pull-models`

As today, and it also downloads each cloud profile's tokenizer ("tokenizer o200k_base: ready").
It downloads no cloud model, and contacts no provider.
