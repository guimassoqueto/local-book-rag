# Feature Specification: Cloud models for chat and summaries, opt-in

**Feature Branch**: `feat/cloud-llm-providers`

**Created**: 2026-11-20

**Status**: Draft

**Input**: User description: "Cloud LLM providers for chat and summaries, opt-in, with the local
model as the default. The Chat and Summarization tabs, and the ask and summarize commands
(--model), get a model choice: the local model, preselected, plus the cloud models allowed in the
environment. Book, chapter and answer language work exactly as now. The Research tab reports the
model that answered, with its tokens, timings and reasoning where the provider returns them.
Providers sit behind one interface so that OpenAI, Gemini and others can be added later; only
Anthropic (Claude) is built now. Configuration is ANTHROPIC_API_KEY and ANTHROPIC_MODELS
(comma-separated) in .env, passed to the app container; with either missing, only the local model
is offered. The interface says when a request will send passages or a chapter to a provider. An
invalid key, unknown model, rate limit or outage is reported as an error, and the app never
answers with another model without saying so. Saved summaries record the provider and model, and
regenerating summaries in reindex-all never calls a cloud model. Embeddings, reranking, benchmarks
and judges stay local."

**Input, added before the first commit**: "If the selected cloud provider does not work, it will
generate the answer via the local model (as a fallback). But make the user define the fallback
sequence (for example, he can choose the primary model claude sonnet, then define claude opus as
the second fallback, and gemmini flash as third, then chatgpt astra as fourth, and local model as
the last option, in none works, and by default, if he/she does not define the second fallback, it
always be the local model)"

## Context

One model writes every answer and every summary today: the LLM that `config/models.yaml` names
(`llm.model`, `gpt-oss:20b`), served by Ollama in its own container, with its tokenizer and
reasoning setting in its profile in `llm_profiles`.

- **The Chat tab** asks it about the books selected, or the whole library when none is, about one
  chapter when a single book is selected, and in the language chosen ("Same as the question" by
  default). The answer streams as it is written, with numbered citations that resolve to book,
  chapter and section, and a reply that opens with the no-evidence marker is shown as an
  abstention. The `ask` command does the same, with `--book`, `--chapter` and `--language`.
- **The Summarization tab** has it summarize one chapter, in one of the summary types and a
  language ("Same as the book" by default), and saves the result on request. The `summarize`
  command does the same. A chapter that fits in the context is summarized in one step, and a
  longer one in several (map-reduce). Statements are cited by lookup against the chapter's chunks.
- **The Research tab** shows what happened inside the latest question. The LLM it names is read
  from the configuration, not from the answer. It lists the tokens read and generated, and the
  time to first token, model loading, prompt processing and generation as Ollama reports them;
  the model's reasoning; and the final context, as sent to the model.
- **A saved summary** keeps, next to its text, how it was made, its model included. With "Also
  write the saved summaries again" in the Library tab, or `--regenerate-summaries`, `reindex-all`
  writes every saved summary again with the configured model, in the language it was saved in.

Constitution 3.0.0 (`31811d9`, on this branch) changed Principle I for this feature. Inference is
local by default. Answers and chapter summaries may use a cloud model when the user picks one for
a request, and a cloud model is offered only when its provider's API key and allowed models are
set in the environment. Nothing goes to a provider without that choice, and then only what the
request needs. Embeddings, reranking, benchmarks and their judges always stay local: a cloud
model has no digest or seed, so its results can't be reproduced. A cloud model's name lives in
its provider's allow-list, and what all of a provider's models share goes in one profile in
`config/models.yaml`. The key is never written to the logs, the library or a result.

Before the first commit, the owner added fallbacks. When the model picked doesn't work, the
request goes to the next model of a sequence that the user defines, and to the local model last,
which is the only fallback when the user defines none. A model that the user puts in the sequence
is a model chosen for the request, which is what Principle I asks before anything goes to a
provider. Only Anthropic is built now, so until other providers come, a sequence holds Claude
models and then the local one.

Settings in `.env` reach the app's container when it is created. Nothing is kept in a volume
(Principle II), so setting or changing them takes `make up`, which recreates the container and
empties the library. The library is empty now, by the owner's choice.

What stays as it is: the search, from embeddings to reranking, and the passages it returns, in
their order; the prompts; ingestion, the index, its fingerprint and the catalog; the local model
and its settings; and the benchmarks and their judges.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - A question answered by Claude (Priority: P1)

The owner puts an Anthropic API key and the Claude models to offer in `.env`, and recreates the
app. The Chat tab now offers a model choice: the local model, preselected, then each allowed
Claude model. The owner selects a book, a chapter and "Portuguese", and picks a Claude model, and
the tab says that the question and the passages found will be sent to Anthropic, and that the
local model answers if Claude fails. The answer streams in Portuguese, cites the passages it was
given, and lists its sources as a local answer does. When Claude fails, the local model answers
the same question instead, and the tab says which model failed, and why. The next page load
starts on the local model again. `ask --model` does the same from the command line. Without the
two settings, the Chat tab and `ask` look and work as today.

**Why this priority**: It is the feature: a second model, chosen per question, whose answers keep
the traceability of local ones, and whose failures don't cost the answer. The other stories extend
it to summaries, to a sequence of fallbacks and to the Research tab.

**Independent Test**: With neither setting, compare the Chat tab and `ask` with `main`. Then set
both, with a valid key, one Claude model and one name that Anthropic doesn't know, recreate the
app, and ask the same question about one book and chapter, in a chosen language, with the local
model and with Claude, in the tab and with `ask`: compare the passages each was given, check that
every citation resolves, and ask one question that the passages can't answer. Then ask with the
unknown name, and check that the local model answers and that the failure is said.

**Acceptance Scenarios**:

1. **Given** neither setting, **When** the owner opens the Chat tab or runs `ask`, **Then** there
   is no model choice, the local model answers, and the tab and the command are as on `main`.
2. **Given** both settings, **When** the owner opens the Chat tab, **Then** it offers the local
   model, named as configured, marked local and preselected, then each allowed model, named with
   its provider.
3. **Given** a Claude model picked, **When** the owner looks before asking, **Then** the tab says
   that the question and the passages found will be sent to Anthropic, and that the local model
   answers if it fails.
4. **Given** a Claude model picked, and books, a chapter and a language chosen, **When** the owner
   asks, **Then** the search returns the same passages, in the same order, as for the local
   model, the answer streams in the chosen language, and each citation resolves to the book,
   chapter and section of a passage it was given.
5. **Given** a question that the passages don't answer, **When** Claude replies with the
   no-evidence marker, **Then** the reply is shown as an abstention, as a local one is.
6. **Given** a Claude model picked and no fallback defined, **When** Claude fails, **Then** the
   local model answers the same question from the start, and the tab says which model failed,
   its provider and why, and which model answered.
7. **Given** `ask --model` with an allowed Claude model, **When** it runs, **Then** it says on
   standard error, before sending anything, that the question and the passages found go to
   Anthropic, and answers as the tab does. With a name that isn't offered, it stops before
   searching, and lists the names offered.
8. **Given** an answer from Claude, **When** the page is loaded again, **Then** the local model is
   preselected again.

---

### User Story 2 - A chapter summarized by Claude (Priority: P2)

The owner picks a Claude model in the Summarization tab, which says that the chapter's text will
be sent to Anthropic, and that the local model summarizes it if Claude fails. The summary is made
as a local one is, in the type and language chosen, and its report names the provider and the
model. Saved, it records them. If Claude fails at any step, the summary starts again with the
next model, and its report names both. Later, `reindex-all` with the summaries regenerated writes
the local ones again and leaves Claude's alone, listing it as not written again: regenerating
never calls a cloud model. `summarize --model` does the same from the command line.

**Why this priority**: Summaries are the app's other use of an LLM, and the one that sends the
most: a chapter's whole text goes to the model. It builds on User Story 1's configuration and
choice.

**Independent Test**: With both settings, summarize one chapter with Claude in the tab, and
another with `summarize --model`, saving both, and a third with the local model, saved too. Check
each report and saved record. Then run `reindex-all --regenerate-summaries` with the provider
unreachable, and check that it made no request to it, wrote the local summary again, and left
both of Claude's as they were, listed as not written again.

**Acceptance Scenarios**:

1. **Given** a Claude model picked in the Summarization tab, **When** the owner looks before
   generating, **Then** the tab says that the chapter's text will be sent to Anthropic, and that
   the local model summarizes it if Claude fails.
2. **Given** a chapter, a type and a language, **When** Claude summarizes it, **Then** the summary
   follows the same steps as a local one: one step when the chapter fits the model's context and
   several otherwise, its statements cited by lookup, and those close to no passage counted.
3. **Given** a summary written by Claude, **When** it is shown, saved, or printed by `summarize`,
   **Then** its report and its saved record name the provider and the model that wrote it, and
   give the tokens it read and generated, summed over its steps.
4. **Given** a summary in several steps, **When** Claude fails at one of them, **Then** the summary
   starts again from its first step with the next model, and its report and saved record name the
   model that wrote it and the one that failed, with why and the tokens its finished steps spent.
5. **Given** saved summaries written by Claude and by the local model, **When** `reindex-all`
   runs with the summaries regenerated, **Then** no request reaches a provider, the local ones are
   written again as today, and each of Claude's is left as it was and listed, with its model, as
   not written again.
6. **Given** a summary saved before this feature, which names no provider, **When** `reindex-all`
   regenerates the summaries, **Then** it is read as written by the local model, and written
   again as today.

---

### User Story 3 - A sequence of fallbacks that the owner defines (Priority: P3)

With two Claude models allowed, the owner picks Claude Sonnet in the Chat tab, then Claude Opus as
its fallback. The tab shows the sequence: Sonnet, then Opus, then the local model, which always
ends it. When Sonnet fails, Opus gets the same question; when Opus fails too, the local model
answers. Each failure is said as it happens, and the answer names the model that wrote it. The
Summarization tab, and `--fallback` in the commands, work the same way. Once other providers are
built, their models can join a sequence: Sonnet, then Opus, then a Gemini model, then a ChatGPT
one, then the local model.

**Why this priority**: User Story 1's local fallback already keeps a failure from costing the
answer. A sequence lets the owner prefer another cloud model to the local one, and pays off most
once other providers exist.

**Independent Test**: Allow two real Claude models and two names that Anthropic doesn't know. Put
an unknown name first and a real model second: the real one answers, and the local model isn't
called. Put the two unknown names in a row: the local model answers, and both failures are listed,
in order.

**Acceptance Scenarios**:

1. **Given** a cloud model picked, **When** the owner defines its fallbacks, **Then** the tab
   offers the other cloud models offered, each at most once, in the order chosen, and shows the
   local model at the end of the sequence.
2. **Given** a sequence of Sonnet then Opus, **When** Sonnet fails, **Then** Opus gets the same
   request from the start, and when it answers, the local model isn't called.
3. **Given** a sequence of Sonnet then Opus, **When** both fail, **Then** the local model answers,
   and the tab lists both failures in order.
4. **Given** the local model picked, **When** the owner looks for fallbacks, **Then** there are
   none to define: the local model is the last model of every sequence.
5. **Given** `ask` or `summarize` with `--model` and `--fallback`, repeated, **When** it runs,
   **Then** it follows the same sequence and prints each failure as it happens. A name that isn't
   offered, or one given twice, is refused before anything is searched or sent.
6. **Given** a sequence whose models all fail, the local one included, **When** the request ends,
   **Then** it ends with an error that lists every failure, in order.

---

### User Story 4 - The Research tab shows a cloud answer from the inside (Priority: P4)

After a question answered by Claude, the Research tab names Anthropic and the Claude model that
wrote the answer, instead of the configured local model. It shows the tokens read and generated,
the time to first token and the total time, and the model's reasoning as Anthropic returned it,
saying that it is a summary of the reasoning, or that none came back. What a provider doesn't
report and the app can't measure, model loading and prompt processing, is shown as unavailable,
not as zero. When models failed before the one that answered, it lists them, in order, each with
its provider and why. The final context is exactly what was sent to the model that answered. Its
health checks reach the providers only when the owner clicks "Check again".

**Why this priority**: It lets the owner see what a cloud answer was given and what it cost. It
reads the other stories' answers, and changes nothing about them.

**Independent Test**: Ask one question with Claude, one with the local model, and one with an
unknown name first in the sequence, and read the Research tab after each.

**Acceptance Scenarios**:

1. **Given** an answer from Claude, **When** the Research tab updates, **Then** it names the
   provider and the model that wrote the answer.
2. **Given** an answer from Claude, **When** the tab shows its measures, **Then** it shows the
   tokens read and generated, the time to first token and the total time, and model loading and
   prompt processing as unavailable.
3. **Given** an answer from Claude, **When** the owner opens "The model's reasoning", **Then** it
   shows the reasoning that Anthropic returned and says that it is a summary, or says that none
   came back.
4. **Given** an answer that came after failures, **When** the tab updates, **Then** it lists each
   model that failed, in order, with its provider and the reason, before the one that answered.
5. **Given** an answer from the local model after one from Claude, **When** the tab updates,
   **Then** it shows what it shows today.
6. **Given** both settings, **When** the tab runs its checks on its own after an answer, **Then**
   no provider is contacted, and the checks leave providers out.
7. **Given** both settings, **When** the owner clicks "Check again", **Then** the checks report
   whether the key is accepted and whether each allowed model exists.

---

### Edge Cases

- **One setting without the other**, a key and no models or models and no key: no cloud model is
  offered, and the startup log and `doctor` say which setting is missing.
- **A model in the list that the provider doesn't know** is offered, since the app doesn't ask the
  provider until a request or a check. `doctor` and "Check again" report it, and a request with it
  fails like any other failure, moving on to the next model.
- **A key the provider refuses, a rate limit, a timeout or an outage**: the request moves on to
  the next model of its sequence, and the tab says which model failed and why. A rate limit, an
  overload or a lost connection is tried again twice, a few seconds apart, before it counts; a
  model silent for its profile's time is given up on at once. The request ends with an error only
  when the local model, the last, fails too.
- **A request the provider declines** is a failure too: the next model gets it, and the tab says
  that the provider declined it, with the provider's category for it when it gives one.
- **A reply with no usable answer**, with no text, such as one that spent its whole token limit on
  reasoning, is a failure, and the next model gets the request.
- **A reply cut off by its token limit, with text in it**, is an answer, as a local one is today:
  it is shown, and the request doesn't move on.
- **An abstention** is an answer, not a failure: the request doesn't move on.
- **A failure after part of the answer arrived**: the text that arrived is withdrawn. The tab
  removes it; a command, which can't take back what it printed, says on standard error that it is
  discarded. The next model starts over.
- **An allowed model that its profile can't serve**, one that refuses the profile's effort or its
  kind of reasoning, fails every request it gets, as rejected, and each failure says so. `doctor`
  and "Check again" name what it refuses. Nothing warns at startup, which contacts no provider.
- **A name that differs from an allowed one only in case** is another name: it is refused, with the
  names offered.
- **A failure at one step of a long summary**: the summary starts again, from its first step, with
  the next model. No summary is written by two models.
- **A question whose search finds nothing** calls no model, as today, so nothing is sent and no
  fallback runs.
- **A page left open across a restart that changed the allow-list**: a request whose sequence
  names a model no longer offered is refused, with the names offered, and loading the page again
  shows the new list.
- **The whole library selected**: the passages sent may come from several books, as they would be
  given to the local model.
- **A cloud model picked in one tab** leaves the other tab as it was: with Claude picked in the Chat
  tab, a summary still goes to the local model unless the Summarization tab picks otherwise.
- **A reply check**, when a provider's profile asks for one: the model that wrote the reply reads
  it again, with the question, as part of the same attempt.
- **The same chapter and type summarized again and saved** replace the saved summary, whichever
  model wrote either, as saving does today.
- **A cloud summary kept by `reindex-all`** was made from the chunks before the rebuild, so its
  references may name sections that changed. The report says so, and summarizing the chapter again
  refreshes it. It is kept even when its provider is no longer configured.
- **The interface published on the network** (`GRADIO_BIND_ADDRESS`): anyone who can open it, or
  call its API, can use the configured key. The README says so.
- **An experiment or a judge that names a cloud model** is refused before the run starts, with no
  request to any provider.
- **The provider unreachable when the app starts**: the app starts as usual, since it contacts no
  provider then, and a request with one of its models moves on to the next model.

## Clarifications

### Session 2026-11-20 (specify)

- Q: When the model picked fails, where does the request go? → A: To the next model of a sequence
  that the user defines, and to the local model last, which is the only fallback when the user
  defines none. The owner added this before the first commit.
- Q: Can a sequence leave the local model out, or put it before a cloud model? → A: No: the local
  model ends every sequence, as the owner confirmed.
- Q: Does a sequence outlive the page? → A: No: it resets with the model choice on every page
  load, as the owner confirmed.
- Q: Should summaries stream, as answers do? → A: Not in this feature, a call the owner left open:
  answers already stream, and streaming summaries, which would change local ones too, is a
  feature of its own, after this one.

### Session 2026-11-20

- Q: When may the app contact a cloud provider for something other than a request made with one of
  its models? → A: Only when the user asks for a check: `doctor`, or "Check again" in the Research
  tab. Never at startup, and never in the checks that run on their own after each answer.
- Q: Should the Chat and Summarization tabs each keep their own model choice and fallbacks, or
  should one choice apply to both tabs? → A: Each tab keeps its own, and both start on the local
  model.
- Q: Should a summary written by a cloud model report how many tokens it used, as answers already
  do? → A: Yes, for summaries that a cloud model wrote: the tokens read and generated, summed over
  its steps, in the tab's and `summarize`'s reports and in the saved record. Local summaries stay
  as today.

### Corrections from the requirements checklist, 2026-11-20

The owner answered the checklist's four questions
(`checklists/data-sharing-and-model-output.md`):
- A reply cut off by its token limit, with text in it, is an answer, as today (CHK011, FR-017).
- A model may stay silent for 120 seconds, its profile's setting, before the next one starts
  (CHK013, FR-017).
- A summary's record and reports count the tokens of the cloud attempts that failed before it,
  which were billed too (CHK017, FR-022).
- `ask` and `summarize` say what goes to which provider before sending, as the tabs do (CHK006,
  FR-008).

The rest the agent settled, from what the owner had decided before.
- **What a request carries** (FR-015): the prompt's instructions, the passages with their book,
  chapter and section, the titles a summary's prompt names, and the partial summaries. A check
  sends the key and the allowed models' names (FR-015, FR-021), not the key alone.
- **Where the key lives** (FR-004): `.env`, the app container's environment, and the shell that
  runs the integration tests; nowhere else. Anyone who can call the interface's API can use it,
  as anyone who can open the page can (FR-029, Edge Cases).
- **Failures** (FR-017, FR-018): the list matches the plan's reasons, "is down or overloaded" and
  "rejects the request" included; a declined request goes on like any failure, with its category
  shown; "withdrawn" is said for the tab and for a command; the error after every model failed
  ends with the local model's failure, for a summary as for an answer.
- **A misconfigured model** fails every request it gets, each failure said, and the checks name
  it; nothing warns at startup, which contacts no provider (Edge Cases).
- **`reindex-all`** keeps a cloud summary even when its provider is no longer configured, and says
  that its references may be out of date (FR-023, Edge Cases).
- **Measures and the reasoning** (FR-020, FR-025): generated tokens count the reasoning for every
  provider; a measure the app takes itself says so; the reasoning stays out of logs and records.
- **Precision.**
  - FR-001 compares names as written, case included.
  - FR-002 makes a provider with one setting a failing check in `doctor`.
  - FR-003 refuses a profile under a provider name the app doesn't implement.
  - FR-014 says what the profile's window is for: it caps what one request sends.
  - FR-029 adds the provider's terms for what it is sent, and which generation settings don't
    apply to a cloud model.
  - FR-030 adds the plan's own choices to the decisions to record.
  - FR-033 checks each allowed model, and the README says to check one allowed later.
  - SC-001 compares the commands' output line for line, notes the records' new keys, and counts
    requests in the unit tests.
  - SC-003 names its cases and what passes; SC-007, SC-008 and SC-009 say where they are measured.
  - The Assumptions add the fallbacks' control, the tabs' wording, and why the release is minor.

## Requirements *(mandatory)*

### Functional Requirements

#### Configuration

- **FR-001**: A cloud provider MUST be configured by two settings in `.env`, passed to the app's
  container: its API key, and its allowed models as a comma-separated list of model names. For
  Anthropic, they MUST be `ANTHROPIC_API_KEY` and `ANTHROPIC_MODELS`. Spaces around a name and
  empty entries MUST be ignored, and a name listed twice MUST be offered once. Names MUST be
  compared as written, case included.
- **FR-002**: A provider's models MUST be offered only when both its settings are set and not
  empty. With neither set, the app MUST look and work as it does without this feature. With one
  set and not the other, its models MUST NOT be offered, the startup log MUST say which setting is
  missing, and `doctor` MUST report it as a failing check.
- **FR-003**: What all of a provider's models share MUST be in one profile per provider in
  `config/models.yaml`, validated at startup like the rest of `config/`. A cloud model MUST need
  no profile of its own, and an allowed model whose provider has no profile MUST stop the app at
  startup (Principle I). A profile under a provider name that the app doesn't implement MUST stop
  it too, as any unknown key in `config/` does.
- **FR-004**: The key MUST be read from the environment only, and the interface MUST neither ask
  for it nor show it. It belongs in `.env`, in the app container's environment, which
  `docker inspect` and `docker compose config` show to anyone who can run Docker, and in the shell
  that exports it to run `make test-integration`, and nowhere else. Nothing MUST write it to the
  logs, the library, a saved summary or a benchmark result, and no error or message MUST show it
  (Principle I).
- **FR-005**: The sample environment file, `devtools/.env.sample`, MUST list both settings, empty,
  each with a comment that says what it holds.

#### Choosing a model and its fallbacks

- **FR-006**: When at least one cloud model is offered, the Chat and Summarization tabs MUST offer
  a model choice: the local model, named as configured, marked local and preselected on every page
  load, then each allowed model, named with its provider. When none is offered, they MUST show no
  choice.
- **FR-007**: With a cloud model picked, the tabs MUST let the user define its fallbacks: other
  offered cloud models, each at most once, in the order chosen. This sequence MUST end with the
  local model, which MUST be the only fallback when the user defines none. With the local model
  picked, there MUST be no fallback to define.
- **FR-008**: The `ask` and `summarize` commands MUST take `--model`, which names the local model
  or an offered cloud model, and `--fallback`, repeated, which names its fallbacks in order, under
  FR-007's rules. Without `--model`, the local model MUST answer. A name that isn't offered, or
  that appears twice, MUST be refused before anything is searched or sent, with the names offered.
  With a cloud model named, both commands MUST say on standard error, before anything is sent,
  what will go to which providers, as the tabs' notice does (FR-010).
- **FR-009**: Each tab MUST keep its own choice and fallbacks, which hold for the requests made
  from that tab until they change. A choice made in one tab MUST NOT change the other's, and
  nothing MUST keep a choice across page loads, restarts or commands.
- **FR-010**: While a cloud model is picked, the tab MUST say, before the request, what will go to
  which providers, in the sequence's order, and that the local model answers last: the question
  and the passages found, in the Chat tab, and the chapter's text, in the Summarization tab.

#### Answers and summaries from a cloud model

- **FR-011**: A question answered by a cloud model MUST go through the same search as with the
  local model, for the same books, chapter and language: the same passages, in the same order. The
  model MUST be given as many of them as fit its context, through the same prompt. Its reply MUST
  be read as a local one is: citations normalized and resolved to book, chapter and section,
  invented ones reported, and the no-evidence marker shown as an abstention (Principle VII).
- **FR-012**: A summary written by a cloud model MUST be made as a local one is: the same types and
  languages, one step when the chapter fits its context and several otherwise, statements cited by
  lookup, those close to no passage counted, and the claims verified when the configuration asks.
- **FR-013**: An answer from a cloud model MUST stream as it is written, in the Chat tab and in
  `ask`, as a local one does.
- **FR-014**: What is sent to a cloud model MUST be fitted to its context before it is sent, as it
  is for the local model, so that nothing is cut. A cloud model's context is a window that its
  provider's profile sets, far below the model's own, so that it also caps what one request
  sends, and so what it costs.
- **FR-015**: Nothing MUST be sent to a provider except for a request in whose sequence the user
  put one of its models, and then only what the request needs. For a question: the prompt's
  instructions, the question, and the passages, each with its book, chapter and section; and,
  when the provider's profile asks for a reply check, the model's own reply. For a summary: the
  prompt's instructions, the book's and the chapter's titles, the chapter's text, and the
  summaries made from it. The one other contact is a check that the user asks for (FR-021), which
  sends the key and the allowed models' names. Retrieval, embeddings, reranking, benchmarks and
  their judges MUST stay on local models (Principle I).
- **FR-016**: Each answer and summary MUST come from a model of its sequence, and MUST record the
  model that wrote it, as its provider reported it, with that provider, and the models that failed
  before it, in order, each with its provider and why. No model outside the sequence MUST answer.

#### Failures and fallbacks

- **FR-017**: A model of the sequence fails when its provider refuses the key, doesn't know the
  model, limits the rate, is down or overloaded, can't be reached, rejects the request, such as
  for a setting the model doesn't take, or declines it; when it sends nothing for the time that
  its provider's profile allows, 120 seconds; or when the model finishes without a usable answer,
  that is, with no text. A reply cut off by its token limit with text in it is an answer, as a
  local one is today, and so is an abstention: neither MUST count as a failure. A silent model
  MUST be given up on at once, never waited for twice; a rate limit, an overload or a lost
  connection MAY be tried again twice, a few seconds apart, before it counts. On a failure, the
  request MUST go to the next model of the sequence, from the start: the same question and
  passages, fitted to that model's context, or the same chapter. A declined request goes on like
  any other failure. Text that arrived from the failed model MUST be withdrawn: the tab removes
  it, and a command, which can't take back what it printed, says on standard error that it is
  discarded.
- **FR-018**: The tab and the command MUST say each failure as it happens: the model, its
  provider, the reason, with the provider's category when it declined the request and gives one,
  and the model asked next. The request MUST end with an error only when the last model of the
  sequence, the local one, fails too, and that error MUST list every failure, in order, the local
  model's last, for a summary as for an answer.
- **FR-019**: A summary MUST be written by one model. When one of its steps fails, the summary
  MUST start again from its first step with the next model of the sequence.
- **FR-020**: Each attempt MUST be logged with its provider, its model and its outcome, and never
  with the key, a book's text, a question, or the reasoning that a model returned, which can quote
  the passages. The reasoning appears in the Research tab only.
- **FR-021**: A provider MUST be contacted outside a request only when the user asks for a check:
  `doctor`, or "Check again" in the Research tab. The check MUST report, for each configured
  provider, whether its key is accepted and whether each allowed model exists, running no
  inference and sending the key and the allowed models' names, nothing else. Nothing MUST contact
  a provider at startup, and the checks that the Research tab runs on its own after each answer
  MUST leave providers out. When no provider has either setting, the checks MUST be the same as
  today.

#### Saved and regenerated summaries

- **FR-022**: A saved summary MUST record the model that wrote it, with its provider, and the
  models that failed before it, with why. The reports of the Summarization tab and of `summarize`
  MUST name them. For each cloud attempt of a summary, both reports and the saved record MUST give
  the tokens read and generated by the steps it finished: all of them for the model that wrote
  the summary, and, for one that failed, those it finished before failing, which were billed too.
  A summary that the local model wrote, with no failure before it, MUST report as today.
- **FR-023**: Regenerating the saved summaries in `reindex-all` MUST NOT call a cloud model. A
  saved summary that names a cloud provider MUST be left as it was, whether or not that provider
  is still configured, and the report MUST list it, with its model, as not written again. Since
  it was made from the chunks before the rebuild, the report MUST also say that its references
  may name sections that changed, and that summarizing the chapter again refreshes it. The others
  MUST be written again with the local model, as today. A summary saved before this feature,
  which names no provider, MUST be read as written by the local model.

#### The Research tab

- **FR-024**: The Research tab MUST name the model that wrote the latest answer, with its provider
  when that is a cloud provider, instead of the model that the configuration names, and MUST list
  the models that failed before it, in order, each with its provider and why. For an answer that
  the local model wrote with no failure before it, it MUST show what it shows today.
- **FR-025**: For an answer from a cloud model, it MUST show the tokens read and generated, the
  generated ones counting the reasoning as they do for the local model, the time to first token
  and the total time, and the reasoning as the provider returned it, saying when that is a summary
  of the reasoning and when none came back. A measure that the app takes itself for a cloud
  model, such as the generation's speed from the first token to the last, network included, MUST
  say so. A measure that the provider doesn't report and the app can't measure MUST be shown as
  unavailable, never as zero. Its final context MUST be exactly what was sent to the model that
  answered.

#### Providers to come

- **FR-026**: Answers, summaries, fallbacks, both tabs, the commands, `doctor` and the Research tab
  MUST reach every provider through one interface, so that adding another, such as OpenAI or
  Google Gemini, takes a provider of its own, its profile and its two settings, and no change to
  them. Its models MUST join a sequence as Claude's do. Only Anthropic MUST be built now.

#### What stays local

- **FR-027**: An experiment or a judge that names a cloud model MUST be refused before the run
  starts, as an unknown model is today, with no request to any provider.
- **FR-028**: Retrieval, the prompts, ingestion, the index, its fingerprint and the catalog MUST
  NOT change, and no reindex MUST be needed (Principles II and III). The local model MUST answer
  and summarize with its settings as today.

#### Records

- **FR-029**: `README.md` MUST say which provider is supported and how to configure it; that
  setting or changing either setting recreates the app container at `make up`, which empties the
  library (Principle II); what each request sends to the provider, and that the app contacts it
  at no other time than a check the user asks for; that the provider handles what it is sent under
  its own terms for API data, and where to read them; how to choose a model and its fallbacks in
  the tabs and with `--model` and `--fallback`, and that the local model ends every sequence;
  which settings of `config/generation.yaml` don't apply to a cloud model, such as its
  temperature, and where its own settings are; that anyone who can open the interface, or call
  its API, can use the key; that a model allowed later is trusted once it has passed the
  integration tests (FR-033); and that embeddings, reranking, benchmarks and judges stay local.
  Its opening MUST no longer say that there is no external LLM API.
- **FR-030**: `docs/decisions.md` MUST record the departure from local-only inference
  (constitution 3.0.0) and why a cloud model is chosen per request; why models are allowed in the
  environment, with one profile per provider; why the local model ends every sequence, why a
  summary starts again with the next model instead of mixing two, and why only the sequence's
  models answer; why `reindex-all` leaves a cloud summary as it was; which real Claude models the
  feature was checked on, with what they write differently from the local models, as the entries
  on `gpt-oss` do (Principle V); and the plan's own choices, which the spec doesn't make: no
  server-side fallbacks, no temperature, the approximate tokenizer, the profile's values and what
  kept each, the bound on a silent model, and how a command withdraws text.
- **FR-031**: The history MUST NOT be edited: the delivered specs, `specs/001` to `specs/007`
  (Principle VIII).

#### Constraints from the constitution

- **FR-032**: The tabs and the commands MUST only read the choice and its fallbacks, and show what
  the services return. Which models are offered, the rules of a sequence, the refusal of a name,
  the move to the next model, and every rule above MUST live in the services (Principle IV).
- **FR-033**: How the cloud provider's output is read MUST be checked against the real Claude
  models through `make test-integration`, on each model in `ANTHROPIC_MODELS`, which MUST skip
  those checks when the settings aren't set (Principle V). A model allowed later is trusted once
  it has passed them.

### Key Entities

- **Cloud provider**: a company that serves models over the internet, for an API key: Anthropic
  now, others later. It is configured by its two settings, and has one profile.
- **Allowed model**: a model name in a provider's allow-list, `ANTHROPIC_MODELS` for Anthropic. It
  is offered only with its provider's key.
- **Provider profile**: what all of a provider's models share, in `config/models.yaml`, validated
  at startup.
- **Sequence**: the models a request may go to, in order: the model picked, then the fallbacks the
  user defined, then the local model, which ends every sequence. With the local model picked, it
  is the whole sequence.
- **Attempt**: one model's try at a request, with its provider, its outcome, and the reason when
  it failed.
- **Answer**: as today, with the model that wrote it, its provider, and the attempts that failed
  before it.
- **Saved summary**: as today, with the provider next to the model that wrote it, and the attempts
  that failed before it; for each cloud attempt, the tokens read and generated by the steps it
  finished.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: With neither setting, the Chat, Summarization and Research tabs look and work as on
  `main`, and `ask`, `summarize`, `reindex-all` and `doctor` print, line for line, what they print
  on `main`. A saved summary's record gains FR-022's keys, which nothing shows differently. In the
  unit tests, with clients that count their requests, a session of questions and summaries makes
  none to any provider.
- **SC-002**: With both settings and a valid key, `doctor` and "Check again" report the key
  accepted and each allowed model found, and starting the app or answering with the local model
  makes no request to Anthropic. With a refused key, `doctor` reports it refused, and a question
  asked with a Claude model and no fallback defined is answered by the local model, the tab naming
  Anthropic, the refused key as the reason and the local model as the one that answered, with the
  key nowhere in the page or the logs.
- **SC-003**: With the settings exported, `make test-integration` runs each allowed Claude model on
  an excerpt written for the test. Five questions that its passages answer each get an answer that
  cites them in a form the app recognizes, every citation resolving to a passage it was given;
  three that they don't each get the no-evidence marker, read as an abstention; and a short
  chapter is summarized, its statements cited by lookup. All of them pass. Without the settings,
  those tests are skipped, and the others pass.
- **SC-004**: For a question asked with a Claude model, what reaches the provider is the Research
  tab's final context, and nothing else from the library, and the search returned the same
  passages, in the same order, as for the local model.
- **SC-005**: After a chapter summarized by Claude and saved, `reindex-all --regenerate-summaries`
  makes no request to any provider, leaves Claude's summary as it was, byte for byte, writes the
  local ones again, and lists Claude's, with its model, as not written again.
- **SC-006**: With an allowed name that Anthropic doesn't know picked first: with no fallback
  defined, the local model answers; with a real Claude model as its fallback, that model answers
  and the local model isn't called; with a second unknown name as its fallback, the local model
  answers. In each case, the tab, the command and the Research tab name every failure, in order,
  and the model that answered.
- **SC-007**: In the unit tests, a summary whose model fails at its second step is written whole by
  the next model, and its report and saved record name that model, and the one that failed with
  the tokens of its first step.
- **SC-008**: In the unit tests, when a model fails after part of its answer arrived, that text is
  gone from the tab before the next model's answer begins, `ask` says on standard error that it is
  discarded, and the final answer holds only the next model's text.
- **SC-009**: In the unit tests, a second provider kind, a fake one registered only where provider
  kinds are built, shows up in both tabs, in `--model` and `--fallback`, and in `doctor`, joins a
  sequence, answers, summarizes, and is reported by the Research tab, with no change to the
  services, the tabs or the commands.
- **SC-010**: An experiment variant and a judge that name a cloud model are each refused before
  the run starts, and no request reaches a provider.
- **SC-011**: After a session with a Claude model, failures included, a search of the logs, the
  saved summaries and the page finds no trace of the key.
- **SC-012**: `make lint-check` is clean, and `make test` passes, with unit tests for: the settings
  read, with both, one or neither set, spaces, a name listed twice and a name in another case; the
  choice offered, kept by each tab on its own, and a name refused; sequences, the default one, a
  defined one, and names refused for being unknown or repeated; the notices of FR-008 and FR-010;
  what is sent, and that only a check the user asks for contacts a provider outside a request
  (FR-021); each failure of FR-017 moving on to the next model, a silent model given up on once, a
  reply cut off with text kept as an answer; text withdrawn after a failure; a summary started
  again; the final error that lists every failure; the records of FR-016 and FR-022, the tokens of
  every cloud attempt included; the regeneration of FR-023; and the Research tab's report of
  FR-024 and FR-025.

## Assumptions

- **One person, on this machine.** The owner uses the app alone, and the interface is published on
  loopback by default. Anyone who can open the interface, or call its API, can spend the key,
  which the README says where it explains `GRADIO_BIND_ADDRESS`.
- **The settings take a new container.** A change to `config/` can be copied into the container
  and applied by a restart, which keeps the library. A change to `.env` reaches the app only when
  `make up` recreates the container, which empties the library.
- **The app needs no network to start.** It contacts a provider only for a request or for a check
  that the user asks for (FR-021), so with the provider unreachable, it starts as usual and
  answers with the local model.
- **Claude follows the prompts written for the local models**, the citation format and the
  no-evidence marker included. SC-003 checks it on the real models. If a prompt has to change,
  that is a decision of its own, measured on the local models too (Principles V and VI).
- **Settings that a provider doesn't take**, such as a sampling temperature on the current Claude
  models, are left out for its models, and the README says which (FR-029). Its profile holds what
  they do take, such as how much they reason and their token limits. The plan sets them, and
  checks them on the real models.
- **Token counts for a cloud model may be approximate**, the safety margin absorbing the error, as
  for `gemma4:12b`. A provider refuses a prompt too long for its model with an error, where Ollama
  cuts it silently, so a miscount can't drop passages unseen.
- **The reasoning that Anthropic returns is a summary** of the model's reasoning, not the reasoning
  itself, and only when the request asks for it.
- **Fallbacks are chosen, and said.** The local model ends every sequence, so a cloud failure costs
  no answer while the local model works, and every failure is said where the answer is shown.
  Only the sequence's models answer: no provider is asked to hand a request on to a model of its
  own choosing.
- **A fallback starts over.** The next model gets the request whole, so a failure late in a long
  summary costs the time and the tokens already spent.
- **A sequence resets with the page**, as the choice does: defining the same fallbacks again after
  a reload is the price of starting every page on the local model.
- **The fallbacks' control keeps the order of selection.** Gradio's multiselect is expected to, and
  `quickstart.md` § 9 checks it. If it doesn't, up to three ordered choices ("then", "then",
  "then") replace it, under the same rules (`research.md`, R13).
- **The tabs' wording is in the contracts.** The spec says what the labels and the notices must
  convey; `contracts/interface.md` gives their words.
- **Other providers wait for their own feature.** Until one is built, a sequence holds Claude
  models and then the local one.
- **Summaries still appear whole.** Answers stream as they are written, from either model
  (FR-013), as local ones do today. A summary shows its progress and then its text, as today:
  only its last step could stream, and its text changes once its statements are cited by lookup.
  Streaming summaries would change local ones too, so it is a feature of its own, after this one.
- **No prices.** The app shows tokens where it shows them today, and for each cloud attempt of a
  summary (FR-022), and estimates no cost. The provider's console reports what the key spent.
  With the settings exported, `make test-integration` spends a few cents per allowed model.
- **Benchmarks don't compare cloud models**: a cloud model has no digest or seed, so a run
  couldn't be reproduced (Principle I). The feature claims no gain in quality or speed and changes
  no default, so no benchmark run is needed (Principle VI).
- **`pull-models` and `doctor --inference`** concern the local models only.
- **The steps that `AGENTS.md` adds** apply: the feature reads a new model family's output, and
  changes what a saved summary records, so it runs clarify, checklist and analyze.
- **The release**: a feature, so the pull request is titled `feat:`, and its merge makes a minor
  release, v0.8.0 unless another release comes first. Nothing that a user relies on breaks: a
  saved summary's record gains keys, and those written before still read (FR-023). The
  constitution's major version governs the project, not the app's.
