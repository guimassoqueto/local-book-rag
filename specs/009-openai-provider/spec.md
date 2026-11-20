# Feature Specification: OpenAI models for chat and summaries, opt-in

**Feature Branch**: `feat/openai-provider`

**Created**: 2026-11-20

**Status**: Draft

**Input**: User description: "OpenAI (ChatGPT) as a second cloud provider for chat and summaries,
built on the structure specs/008-cloud-llm-providers delivered: a provider class of its own behind
the same cloud provider interface, registered in app/container.py's CLOUD_PROVIDERS next to
Anthropic, a cloud_profiles.openai profile in config/models.yaml, and the same two settings Claude
has: OPENAI_API_KEY and OPENAI_MODELS (comma-separated allow-list) in .env, passed to the app
container. If either is missing, no OpenAI model is offered and the app works as if the provider
didn't exist. OpenAI's models join the model choice and the fallback sequence exactly as Claude's
do: the Chat and Summarization tabs, the ask and summarize commands (--model, --fallback), doctor
and the Research tab. Nothing else changes: the local model stays the default; embeddings,
reranking, benchmarks and judges stay local; prompts, retrieval, ingestion and the index stay as
they are. The provider uses OpenAI's own SDK against OpenAI's API, never Ollama's
OpenAI-compatible endpoint. Its reading of the replies (stream, stop reasons, citations, the
no-evidence marker, reasoning) is checked on real OpenAI models with the owner's key, as Claude's
was."

**The owner's request, before the input above**: "using the same structure (classes and
interfaces) we will implement OpenAI ChatGPT models. Remember: we must have the same two env
variables created for claude, now for openai chatgpt. I already have a valid openai token that we
can use, and the models should be set in env separated by commas, as it is now."

## Context

`specs/008-cloud-llm-providers` (v0.8.0, `664df70`) let answers and chapter summaries come from a
cloud model, picked per request, with the local model as the default and the last model of every
sequence. It built one provider, Anthropic, and the structure for the next ones:

- **A provider kind** is a class of its own, registered under its name in one place,
  `CLOUD_PROVIDERS` in `app/container.py`. Its name keys its profile, `cloud_profiles.<name>` in
  `config/models.yaml`, and prefixes its two settings, `<NAME>_API_KEY` and `<NAME>_MODELS`, read
  from the app container's environment. It builds one model's provider, which streams and
  generates as the local one does, and it runs the check that `doctor` and "Check again" ask for.
  Building it contacts nothing.
- **Everything else reaches providers through that interface**: the model choice and the
  fallbacks of the Chat and Summarization tabs, `--model` and `--fallback` in `ask` and
  `summarize`, the notices that say what goes to which provider, the move to the next model, the
  records of answers and saved summaries, `reindex-all`'s handling of cloud summaries, `doctor`,
  and the Research tab. Its spec required that adding a provider take "a provider of its own, its
  profile and its two settings, and no change to them" (FR-026 there), and its unit tests proved
  it with a fake second provider (SC-009 there).
- **What Claude showed on the real models** shaped the Anthropic profile: its replies were read as
  the local models' are, but Claude Haiku abstained in words, without the marker, so the profile
  turned `check_abstentions` on; Claude's tokenizer isn't public, so the app's estimate runs about
  a third low; the SDK's own retries are off, so a silent model is given up on once, after 120
  seconds (`docs/decisions.md`, "Cloud models").

Constitution 3.0.0 already covers any cloud provider: a cloud model only when the user picks it
for a request, and then only what the request needs; the provider's key and allowed models in the
environment, and a single profile per provider in `config/models.yaml`; the key never written to
the logs, the library or a result; embeddings, reranking, benchmarks and judges always local. No
amendment is needed.

The owner has an OpenAI API key and will allow OpenAI's models in the environment, as Claude's are.
Settings in `.env` reach the app's container when it is created, so setting them takes `make up`,
which recreates the container and empties the library. The library holds the owner's *História*
now (book_001).

What stays as it is: the search, from embeddings to reranking, and the passages it returns, in
their order; the prompts; ingestion, the index, its fingerprint and the catalog; the local model
and Claude, with their settings; the rules of a sequence; the benchmarks and their judges.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - A question answered by an OpenAI model (Priority: P1)

The owner puts an OpenAI API key and the OpenAI models to offer in `.env`, and recreates the app.
The Chat tab's model choice now lists the local model, preselected, then Claude's models, then
each allowed OpenAI model, named with its provider. The owner selects a book, a chapter and
"Portuguese", picks an OpenAI model, and the tab says that the question and the passages found
will be sent to OpenAI, and that the local model answers if it fails. The answer streams in
Portuguese, cites the passages it was given, and lists its sources as a local answer does. When
the OpenAI model fails, the local model answers instead, and the tab says which model failed, and
why. `ask --model` does the same from the command line. Without the two settings, the Chat tab and
`ask` look and work as they do on `main`.

**Why this priority**: It is the feature: a second cloud provider, chosen per question, whose
answers keep the traceability of local and Claude ones. The other stories extend it to summaries,
to sequences across providers, and to the Research tab and the checks.

**Independent Test**: With neither setting, compare the Chat tab and `ask` with `main`. Then set
both, with a valid key, one OpenAI model and one name that OpenAI doesn't know, recreate the app,
and ask the same question about one book and chapter, in a chosen language, with the local model
and with the OpenAI model, in the tab and with `ask`: compare the passages each was given, check
that every citation resolves, and ask one question that the passages can't answer. Then ask with
the unknown name, and check that the local model answers and that the failure is said.

**Acceptance Scenarios**:

1. **Given** neither OpenAI setting, **When** the owner opens the Chat tab or runs `ask`, **Then**
   no OpenAI model is offered, and the tab and the command are as on `main`, with or without
   Claude's settings.
2. **Given** both OpenAI settings, **When** the owner opens the Chat tab, **Then** it offers the
   local model, marked local and preselected, then Claude's models when they are configured, then
   each allowed OpenAI model, named with its provider, in the order of `OPENAI_MODELS`.
3. **Given** an OpenAI model picked, **When** the owner looks before asking, **Then** the tab says
   that the question and the passages found will be sent to OpenAI, and that the local model
   answers if it fails.
4. **Given** an OpenAI model picked, and books, a chapter and a language chosen, **When** the
   owner asks, **Then** the search returns the same passages, in the same order, as for the local
   model, the answer streams in the chosen language, and each citation resolves to the book,
   chapter and section of a passage it was given.
5. **Given** a question that the passages don't answer, **When** the OpenAI model replies with the
   no-evidence marker, or abstains in words and the profile asks for a reply check, **Then** the
   reply is shown as an abstention, as a local one is.
6. **Given** an OpenAI model picked and no fallback defined, **When** it fails, **Then** the local
   model answers the same question from the start, and the tab says which model failed, its
   provider and why, and which model answered.
7. **Given** `ask --model` with an allowed OpenAI model, **When** it runs, **Then** it says on
   standard error, before sending anything, that the question and the passages found go to
   OpenAI, and answers as the tab does.

---

### User Story 2 - A chapter summarized by an OpenAI model (Priority: P2)

The owner picks an OpenAI model in the Summarization tab, which says that the chapter's text will
be sent to OpenAI, and that the local model summarizes it if the OpenAI model fails. The summary is
made as a local one is, in the type and language chosen, and its report names the provider, the
model and the tokens it used. Saved, it records them. Later, `reindex-all` with the summaries
regenerated leaves it as it was, as it leaves Claude's, and lists it as not written again.
`summarize --model` does the same from the command line.

**Why this priority**: Summaries are the app's other use of an LLM, and the one that sends the
most: a chapter's whole text goes to the model. It builds on User Story 1's settings and choice.

**Independent Test**: With both settings, summarize one chapter with an OpenAI model in the tab,
and another with `summarize --model`, saving both. Check each report and saved record. Then run
`reindex-all --regenerate-summaries`, and check that it made no request to OpenAI, and left both
summaries as they were, listed as not written again.

**Acceptance Scenarios**:

1. **Given** an OpenAI model picked in the Summarization tab, **When** the owner looks before
   generating, **Then** the tab says that the chapter's text will be sent to OpenAI, and that the
   local model summarizes it if the OpenAI model fails.
2. **Given** a chapter, a type and a language, **When** an OpenAI model summarizes it, **Then** the
   summary follows the same steps as a local one: one step when the chapter fits the profile's
   window and several otherwise, its statements cited by lookup, and those close to no passage
   counted.
3. **Given** a summary written by an OpenAI model, **When** it is shown, saved, or printed by
   `summarize`, **Then** its report and its saved record name OpenAI and the model, and give the
   tokens it read and generated, summed over its steps.
4. **Given** a saved summary written by an OpenAI model, **When** `reindex-all` runs with the
   summaries regenerated, **Then** no request reaches a provider, and the summary is left as it
   was and listed, with its model, as not written again.

---

### User Story 3 - Sequences across providers (Priority: P3)

With Claude and OpenAI both configured, the owner picks a Claude model in the Chat tab, then an
OpenAI model as its fallback. The tab says that the question and the passages go to Anthropic,
then to OpenAI if Claude fails, and that the local model answers last. When Claude fails, the
OpenAI model gets the same question; when it fails too, the local model answers. The same works
the other way round, and in the Summarization tab, and with `--fallback` in the commands. This is
the sequence that `specs/008` described and couldn't build yet: Sonnet, then Opus, then a ChatGPT
model, then the local model.

**Why this priority**: A second provider pays off most when one provider's outage, rate limit or
refused key can fall back on the other before the local model. It needs User Story 1, and changes
none of the rules of a sequence.

**Independent Test**: With both providers configured, put an allowed name that Anthropic doesn't
know first and a real OpenAI model second: the OpenAI model answers, and the local model isn't
called. Then put an allowed name that OpenAI doesn't know first and a real Claude model second:
Claude answers. Then put the two unknown names in a row: the local model answers, and both
failures are listed, in order.

**Acceptance Scenarios**:

1. **Given** both providers configured and a cloud model picked, **When** the owner defines its
   fallbacks, **Then** the tab offers every other offered cloud model, from both providers, each
   at most once, in the order chosen, and shows the local model at the end of the sequence.
2. **Given** a sequence of a Claude model then an OpenAI model, **When** the owner looks before
   asking, **Then** the tab names both providers, in the sequence's order, and what each would be
   sent.
3. **Given** a sequence whose Claude model fails, **When** the OpenAI model answers, **Then** the
   local model isn't called, and the tab names the failure and the model that answered.
4. **Given** a sequence whose models all fail, the local one included, **When** the request ends,
   **Then** it ends with an error that lists every failure, in order, each with its provider.

---

### User Story 4 - The Research tab and the checks see OpenAI (Priority: P4)

After a question answered by an OpenAI model, the Research tab names OpenAI and the model as
OpenAI reported it. It shows the tokens read and generated, the time to first token and the total
time, and the model's reasoning as OpenAI returned it, saying that it is a summary, or that none
came back. What OpenAI doesn't report and the app can't measure is shown as unavailable, not as
zero. `doctor` and "Check again" report whether OpenAI accepts the key and whether each allowed
model exists, without running a model.

**Why this priority**: It lets the owner see what an OpenAI answer was given and what it cost, and
find a wrong key or model name before asking. It reads the other stories' answers, and changes
nothing about them.

**Independent Test**: Ask one question with an OpenAI model and one with the local model, and
read the Research tab after each. Run `doctor` with a valid key and every allowed model real, then
with a wrong key, and then with a name that OpenAI doesn't know in the list.

**Acceptance Scenarios**:

1. **Given** an answer from an OpenAI model, **When** the Research tab updates, **Then** it names
   OpenAI and the model that OpenAI reported, and shows the tokens read and generated, the time to
   first token and the total time, with model loading and prompt processing as unavailable.
2. **Given** an answer from an OpenAI model, **When** the owner opens "The model's reasoning",
   **Then** it shows the reasoning that OpenAI returned and says that it is a summary, or says that
   none came back.
3. **Given** both settings and a valid key, **When** the owner runs `doctor` or clicks "Check
   again", **Then** the checks report the key accepted and each allowed OpenAI model found, next to
   Claude's rows when Claude is configured.
4. **Given** a key that OpenAI refuses, **When** the owner runs `doctor`, **Then** it reports one
   failing row for OpenAI, saying that it refused the key, and Claude's rows are unchanged.
5. **Given** both settings, **When** the Research tab runs its checks on its own after an answer,
   **Then** OpenAI isn't contacted.

---

### Edge Cases

- **One OpenAI setting without the other**: no OpenAI model is offered, and the startup log and
  `doctor` say which setting is missing. Claude's models are offered as before, when Claude is
  configured.
- **OpenAI configured, Claude not**: the choice lists the local model and OpenAI's models only.
- **A name that two providers allow, or that is also the local model's name**: a request that
  names it couldn't say which provider it goes to, so the app refuses to start, naming the name and
  where it appears, as it refuses any other configuration it can't apply. A provider counts only
  when its models are offered, with both its settings set; a list without its key clashes with
  nothing.
- **The model that OpenAI reports may differ from the name allowed**, such as a dated version of
  it. The records and the Research tab's "answered by" name the model reported, as they do for
  every provider. Everything that compares a name with the allow-list uses the allowed name:
  choosing, refusing a name, a stale page's sequence, and the model picked that the Research tab
  names when nothing was retrieved.
- **A model in the list that OpenAI doesn't know** is offered, since the app doesn't ask OpenAI
  until a request or a check. `doctor` and "Check again" report it, and a request with it fails
  like any other failure, moving on to the next model.
- **An account that can't pay**: out of credit, or over a spending or usage limit set on the
  organization or the project. OpenAI answers it with the status it uses for a rate limit. It is a
  failure of its own, said as the account being out of credit or over a limit, and is not tried
  again, since waiting doesn't fix it.
- **A model that the profile can't serve**, one that refuses the profile's reasoning effort, or
  doesn't reason at all: it fails every request it gets, as rejected, and each failure says what
  OpenAI refused. OpenAI's description of a model doesn't say which settings it takes, so `doctor`
  and "Check again" can't warn: the first request finds out, and the README says so.
- **A model the key's project isn't allowed to use**, or a country OpenAI doesn't serve: OpenAI
  refuses the request as forbidden, which is not a refused key. The request fails as rejected,
  with OpenAI's code; `doctor` and "Check again" report it on that model's row, and go on to the
  next model.
- **A model that OpenAI won't serve as the request asks to the key's organization**, such as
  streaming a model or returning its reasoning only to a verified organization: a refusal to
  stream is a failure at once, said as "OpenAI streams this model only to a verified organization"
  when OpenAI's error can be recognized as that, and as a rejection with OpenAI's code otherwise;
  the next model gets the request, and the model is never asked again without streaming
  (Clarifications). The README says how to verify the organization. An answer is never lost
  because OpenAI won't return its reasoning: the request is sent again once, at once, without
  asking for it, and the Research tab says that no reasoning came back.
- **A request OpenAI declines**, the model refusing it or its moderation stopping the reply, is a
  failure, even when part of the answer had already arrived, which is withdrawn: the next model
  gets it, and the tab says that OpenAI declined it, with OpenAI's category when it gives one.
- **A reply with no usable answer**, with no text, such as one that spent its whole token limit on
  reasoning, is a failure, and the next model gets the request. **A reply cut off by its token
  limit, with text in it**, is an answer, and **an abstention** is an answer: neither moves on.
- **A failure after part of the answer arrived**: the text that arrived is withdrawn, as for
  Claude: the tab removes it, and a command says on standard error that it is discarded.
- **A rate limit, an overload, a lost connection or a timeout** behave as they do for Claude: the
  first three are tried again twice, a few seconds apart, before anything has streamed; a model
  silent for its profile's time is given up on at once. Silent means that nothing at all arrives
  from OpenAI, not even an event of the stream: OpenAI announces a response before its text, so a
  model that reasons longer than the profile's time without sending anything times out, while
  one whose stream keeps arriving doesn't.
- **The OpenAI key in the app's environment**: OpenAI's own library, which the benchmarks' judges
  already use to reach Ollama, reads `OPENAI_API_KEY` on its own when it isn't given a key. With
  the setting set, the judges still reach Ollama, with their own key, and no library sends anything
  to OpenAI on its own.
- **OpenAI keeps what it is sent**: the app asks it not to store a request and its reply for later
  retrieval, where its API lets a request choose. What OpenAI keeps under its own terms the README
  says, with where to read them: its abuse-monitoring logs, for up to 30 days; the start of a
  prompt, which it caches on its own for a short time, about 30 minutes by default, to bill a
  repeat less, and which no request argument turns off; and nothing for training, unless the
  organization has opted in to share its API data, a setting of OpenAI's dashboard that the app
  can't change. The encrypted copy of the reasoning that comes back with an unstored response is
  dropped: neither shown, logged nor recorded.
- **A ChatGPT subscription** isn't the key: the key is an OpenAI API key, whose organization pays
  per token. Some ChatGPT subscriptions (Pro, Business) can claim monthly API credits for an
  organization their owner also owns, which its key then spends. The README says so.
- **An experiment or a judge that names an OpenAI model** is refused before the run starts, with no
  request to any provider.
- **OpenAI unreachable when the app starts**: the app starts as usual, since it contacts no
  provider then, and a request with one of its models moves on to the next model.

## Clarifications

### Session 2026-11-20 (specify)

- Q: Which kind of OpenAI models will `OPENAI_MODELS` hold, given that one profile serves them all
  (Principle I)? → A: Only models that reason, the GPT-5 line and later. The profile sets their
  effort and asks for a summary of their reasoning, as Anthropic's does; a model that doesn't
  reason fails every request, said, and the next model gets it. The alternatives were any model
  with no effort sent, each reasoning at its own default and none of it shown, or settings per
  model, which would have taken an amendment of Principle I first (FR-003).

### Session 2026-11-20

- Q: If OpenAI refuses to stream a model's answer because the owner's organization isn't verified,
  does the model fail and the request move on, or is it asked again without streaming? → A: It
  fails at once, with OpenAI's reason, and the next model of the sequence gets the request; it is
  never asked again without streaming, which would leave the request without the bound on a
  silent model. The README says how to verify the organization (FR-014, FR-024).
- Q: Which OpenAI model names will `OPENAI_MODELS` hold? → A: `gpt-6-luna,gpt-6.1-terra,gpt-6.2-sol`,
  in that order. The profile's effort is one that all three take, the integration tests and the
  stack checks run on them, and the plan checks the names with `doctor` before relying on them
  (FR-003, FR-026, SC-003).

### Corrections from the requirements checklist, 2026-11-20

The owner asked for the checklist to be resolved (`checklists/data-sharing-and-model-output.md`).
Four of its items were the owner's to decide; the agent took the defaults below, which stand
unless the owner says otherwise:
- **Prompt caching** (CHK002): accepted. OpenAI caches the start of a prompt for a short time on
  its own; it isn't storage for retrieval, no request argument turns it off, and the README says
  so (Edge Cases, FR-012, FR-024).
- **A clarified name that the owner's organization can't use** (CHK036): dropped from
  `OPENAI_MODELS` and recorded in `docs/decisions.md` with OpenAI's reason; the feature holds as
  long as one model remains (SC-003, FR-025).
- ***História*'s saved summaries** (CHK037): recreating the container deletes them with the book,
  whichever model wrote them; `quickstart.md` § 0 says so before anything runs (Assumptions).
- **Anthropic's billing error** (CHK038): it keeps its "key refused" wording, since Claude stays as
  it is (FR-021); moving it to "out of credit" is a follow-up, recorded in `docs/decisions.md`
  (FR-025, Assumptions).

The rest the agent settled, each with a change here or in the plan's documents, which the
checklist's items name:
- **What a request carries** (FR-012): its exclusions listed by name; the prompt's messages sent
  with their own roles, the system message included, so that "the same prompt" holds literally
  (FR-008).
- **The key** (FR-004, FR-020, FR-023): any part of it counts as the key; every client of OpenAI's
  library that the app builds is given its key and its address, never the environment's.
- **Failures** (FR-014, FR-015): only a 401 is a refused key, and a 403 a rejection with its code;
  "out of credit" covers spending and usage limits; a refusal after text is a decline, its text
  withdrawn; silence means nothing at all arriving; the verification refusal has fallback words;
  the retry without a reasoning summary is allowed, once, and counts against nothing.
- **The profile** (FR-003): the example now names a case that can occur; OpenAI's profile must
  name an effort.
- **Criteria** (SC-002, SC-003, SC-008, SC-009, SC-011, SC-012): each says how it is measured.

## Requirements *(mandatory)*

The rules that `specs/008-cloud-llm-providers` set for every cloud provider hold for OpenAI as
they are: the model choice and its fallbacks (FR-006 to FR-010 there), answers and summaries
(FR-011 to FR-016), failures and fallbacks (FR-017 to FR-021), saved and regenerated summaries
(FR-022, FR-023), and the Research tab (FR-024, FR-025). The requirements below say what OpenAI
adds to them, and what a reader of this spec alone needs to check.

### Functional Requirements

#### Configuration

- **FR-001**: OpenAI MUST be configured by two settings in `.env`, passed to the app's container:
  `OPENAI_API_KEY`, its API key, and `OPENAI_MODELS`, its allowed models as a comma-separated list
  of model names, read as Anthropic's are: spaces around a name and empty entries ignored, a name
  listed twice offered once, names compared as written, case included.
- **FR-002**: OpenAI's models MUST be offered only when both its settings are set and not empty.
  With neither set, the app MUST look and work as it does on `main`, whatever Claude's settings
  are. With one set and not the other, its models MUST NOT be offered, the startup log MUST say
  which setting is missing, and `doctor` MUST report it as a failing check. Each provider's
  settings MUST decide its own models alone.
- **FR-003**: What all of OpenAI's models share MUST be in one profile, `cloud_profiles.openai` in
  `config/models.yaml`, validated at startup like the rest of `config/`: the tokenizer that fits
  prompts, the window the app works with, the reasoning effort sent with each request, the room
  set aside for reasoning, whether a reply without the marker is checked, and how long OpenAI may
  send nothing. A setting's value MUST be one that its provider takes, so that an effort that a
  provider doesn't name stops the app at startup, such as `minimal` in Anthropic's profile; OpenAI
  names every effort that Anthropic does, and `none` and `minimal` besides. OpenAI's profile MUST
  name an effort: with none, each model would reason at its own default. The profile MUST serve
  OpenAI's models that reason, GPT-5 and later, such as the GPT-6 models current on 2026-11-20,
  and at least the three the owner will allow (Clarifications): it sets the effort, one that each
  of them takes, sent with each request, and the request asks for a summary of the reasoning,
  which the Research tab shows. A
  model that doesn't reason fails every request it gets, as rejected, saying what OpenAI refused,
  and the next model of the sequence gets the request (Edge Cases).
- **FR-004**: The key MUST be read from the environment only, and the interface MUST neither ask
  for it nor show it. It belongs in `.env`, in the app container's environment and in the shell
  that runs `make test-integration`, and nowhere else. Nothing MUST write it to the logs, the
  library, a saved summary or a benchmark result, and no error or message MUST show it, nor any
  part of it, such as the masked end of the key that OpenAI's refusal quotes: OpenAI's error
  messages MUST be neither shown nor logged (Principle I).
- **FR-005**: `devtools/.env.sample` MUST list both settings, empty, each with a comment that says
  what it holds, and the app container MUST receive both from `.env`, as it receives Claude's.
- **FR-006**: A model name that two providers offer, or that a provider offers and is also the
  local model's name, MUST stop the app at startup, with a message that names it and where it
  appears, since a request naming it couldn't say which provider it goes to. A provider offers its
  models only with both its settings set (FR-002), so a list without its key clashes with nothing.
  The rule applies to every provider's list, Claude's included.

#### Choosing a model and its fallbacks

- **FR-007**: OpenAI's models MUST join the model choice of both tabs, the fallbacks, `--model` and
  `--fallback`, and the notices that say what goes to which provider, exactly as Claude's do: the
  local model first and preselected, then each configured provider's models, Anthropic's before
  OpenAI's, each in the order of its list, each named with its provider. A sequence MAY mix models
  of both providers, in any order, and the local model MUST end it.

#### Answers and summaries from an OpenAI model

- **FR-008**: A question answered by an OpenAI model MUST go through the same search and the same
  prompt as with the local model, its messages sent with their own roles and text, the system
  message included, and its reply MUST be read as a local one is: citations
  normalized and resolved to book, chapter and section, invented ones reported, the no-evidence
  marker shown as an abstention, and the reply check run when the profile asks for it
  (Principle VII).
- **FR-009**: A summary written by an OpenAI model MUST be made as a local one is: the same types
  and languages, one step when the chapter fits the profile's window and several otherwise,
  statements cited by lookup, those close to no passage counted, and the claims verified when the
  configuration asks.
- **FR-010**: An answer from an OpenAI model MUST stream as it is written, in the Chat tab and in
  `ask`, as a local one does.
- **FR-011**: What is sent to an OpenAI model MUST be fitted to the profile's window before it is
  sent, as it is for every model, so that nothing is cut, and the window MUST cap what one request
  sends.
- **FR-012**: A request to OpenAI MUST carry what `specs/008`'s FR-015 lists for a question or a
  summary, with the model, the token limit, the effort and the request for a reasoning summary,
  and nothing more: no identifier of the user, the machine or the library (no metadata, user or
  safety identifier, or cache key); no tool, such as web search or file search, so that the reply
  can come from the passages only; no sampling setting; and no service tier, background mode or
  reference to an earlier response or conversation. The app MUST ask OpenAI not to store the
  request and its reply for later retrieval, and not to drop part of a prompt that doesn't fit,
  where its API lets a request choose. OpenAI's own short-lived caching of a prompt's start, which
  no argument turns off, is accepted, and the README says so (Clarifications). The one other
  contact is a check that the user asks for (FR-017).
- **FR-013**: Each answer and summary from an OpenAI model MUST record the model as OpenAI reported
  it, with OpenAI as its provider, and the models that failed before it, as for every provider. A
  saved summary MUST record them, and the tokens of each cloud attempt, and `reindex-all` MUST
  leave it as it was when it regenerates the summaries, listing it, as it does Claude's.

#### Failures

- **FR-014**: An OpenAI model MUST fail, and the request move on to the next model of its sequence,
  for each failure that `specs/008`'s FR-017 lists, said with the same reasons:
  - the key refused, which only an authentication error (401) is;
  - a model OpenAI doesn't know;
  - a rate limit, an outage or an overload, or OpenAI unreachable;
  - a request rejected, with OpenAI's code and the parameter it names: for a setting the model
    doesn't take, a model the key's project may not use, a country OpenAI doesn't serve, any other
    forbidden request (403), or a stream that OpenAI won't serve to the key's organization, said
    as "OpenAI streams this model only to a verified organization" when OpenAI's error can be
    recognized as that, and never asked again without streaming;
  - a request declined, by the model or by OpenAI's moderation, with OpenAI's category when it
    gives one, even when part of the answer had already arrived, which is withdrawn;
  - a model that sends nothing at all, not even an event of the stream, for the profile's time;
  - and a reply with no text.

  An account that can't pay, out of credit or over a spending or usage limit of the organization
  or the project, MUST be said as such, not as a rate limit, and MUST NOT be tried again. A rate
  limit, an overload or a lost connection MAY be tried again twice, a few seconds apart, before
  anything has streamed; a timeout never. A reply cut off by its token limit with text in it, and
  an abstention, MUST count as answers.
- **FR-015**: An answer MUST NOT be lost because OpenAI doesn't return the model's reasoning. When
  OpenAI refuses a request for asking for the reasoning's summary, the same request MAY be sent
  again at once without asking for it, once: nothing else in it changes, it still streams, and it
  counts against none of the retries of FR-014. The answer stands, and the Research tab says that
  none came back.
- **FR-016**: Each attempt MUST be logged with its provider, its model and its outcome, and never
  with the key, a book's text, a question, or the reasoning that the model returned. The
  encrypted copy of the reasoning that comes back with an unstored response MUST be dropped:
  neither shown, logged nor recorded.

#### Checks

- **FR-017**: `doctor` and "Check again" MUST report, for OpenAI, whether its key is accepted and
  whether each allowed model exists, running no model and sending the key and the allowed models'
  names, nothing else, beside Claude's rows when Claude is configured. A refused key or OpenAI
  unreachable MUST end OpenAI's check with one row; a model that OpenAI doesn't know, or that the
  key's project may not use, fails its own row, and the check goes on. Nothing MUST contact OpenAI
  at startup, and the checks that the Research tab runs on its own after each answer MUST leave it
  out.

#### The Research tab

- **FR-018**: For an answer from an OpenAI model, the Research tab MUST name OpenAI and the model
  as OpenAI reported it, list the models that failed before it, and show the tokens read and
  generated, the generated ones counting the reasoning, the time to first token and the total
  time, and the reasoning as OpenAI returned it, in whatever language OpenAI wrote it, saying when
  that is a summary of the reasoning and when none came back. A measure that the app takes itself
  MUST say so, and one that OpenAI
  doesn't report and the app can't measure MUST be shown as unavailable, never as zero. Its final
  context MUST be exactly what was sent to the model that answered.

#### What stays as it is

- **FR-019**: An experiment or a judge that names an OpenAI model MUST be refused before the run
  starts, as one that names a Claude model is, with no request to any provider.
- **FR-020**: With OpenAI's settings set, only OpenAI's provider MUST use the key. Every client of
  OpenAI's library that the app builds MUST be given its key and its address, never left to read
  them from the environment: OpenAI's provider gets the key and OpenAI's address, and the
  benchmarks' judges, which reach Ollama through such a client, get Ollama's address and a key of
  their own. No library that the app uses MUST be given a client that reads the environment
  (Principle I).
- **FR-021**: Retrieval, the prompts, ingestion, the index, its fingerprint and the catalog MUST
  NOT change, and no reindex MUST be needed (Principles II and III). The local model and Claude
  MUST answer and summarize with their settings as today. The startup rule of FR-006 applies to
  Claude's list too, and the retry rules that Claude's provider follows MAY move to a place both
  providers share, without changing what Claude's provider does.
- **FR-022**: OpenAI MUST be added as `specs/008`'s FR-026 promised: a provider kind of its own,
  registered next to Anthropic, its profile and its two settings, with no change to the services,
  the tabs or the commands. A change that it needs anywhere else, such as in the validation of
  `config/` or in the reasons a failure can have, MUST serve every provider, not name OpenAI, and
  the plan MUST say why it was needed.
- **FR-023**: The provider MUST reach OpenAI through OpenAI's own library, against OpenAI's API,
  at OpenAI's address given to the client, so that no setting in the environment can send the key
  or a book's text elsewhere, and never through Ollama's OpenAI-compatible endpoint (Principle V).

#### Records

- **FR-024**: `README.md` MUST say that OpenAI is supported beside Anthropic, and how to configure
  it; that setting or changing either setting recreates the app container at `make up`, which
  empties the library (Principle II); what each request sends to OpenAI, and that the app asks it
  not to store them; that OpenAI handles what it is sent under its own terms for API data, and
  where to read them: abuse-monitoring logs for up to 30 days, its own short-lived caching of a
  prompt's start, and no training on it unless the organization has opted in to share its API
  data, which the owner checks in OpenAI's dashboard; that the reasoning may come back in another
  language than the answer; that the key is an API key, whose organization pays per token, and which a
  ChatGPT subscription pays for only through the API credits that some plans can claim;
  which settings of `config/generation.yaml` don't apply to an OpenAI model, and where its own
  settings are; which kind of OpenAI model the profile serves, and that the checks can't tell
  whether a model takes the profile's settings; that OpenAI streams some models only to a verified
  organization, and how to verify it; and that a model allowed later is trusted once it has passed
  the integration tests (FR-026). Its opening MUST name OpenAI beside Anthropic.
- **FR-025**: `docs/decisions.md` MUST record why OpenAI was added through the structure of
  `specs/008`, and what that structure needed, if anything (FR-022); which of OpenAI's APIs the
  provider uses and why; that requests aren't stored, and carry no tool; how an account out of
  credit is told from a rate limit; how close the app's token estimate is to OpenAI's count, as
  measured; the profile's values and what kept each; which real OpenAI models the feature was
  checked on, with what they write differently from the local models and Claude, as the entries on
  `gpt-oss` and Claude do (Principle V), and any model dropped from `OPENAI_MODELS` because the
  owner's organization can't use it, with OpenAI's reason; and, as a follow-up, that Anthropic's
  billing error still reads as a refused key.
- **FR-026**: How OpenAI's output is read MUST be checked against the real OpenAI models through
  `make test-integration`, on each model in `OPENAI_MODELS`, with the cases that Claude's models
  pass; those checks MUST be skipped when OpenAI's settings aren't set, and Claude's MUST still run
  on Claude's settings alone (Principle V). A model allowed later is trusted once it has passed
  them.
- **FR-027**: The history MUST NOT be edited: the delivered specs, `specs/001` to `specs/008`
  (Principle VIII).

#### Constraints from the constitution

- **FR-028**: The tabs and the commands MUST only read the choice and its fallbacks, and show what
  the services return. Every rule above MUST live in the services or below them (Principle IV).

### Key Entities

- **OpenAI**: a cloud provider, configured by `OPENAI_API_KEY` and `OPENAI_MODELS`, with one
  profile, `cloud_profiles.openai`. Shown as "OpenAI".
- **Allowed OpenAI model**: a model name in `OPENAI_MODELS`, offered only with the key.
- **Reported model**: the model that OpenAI says answered, which the records and the Research tab
  name, and which may be a dated version of the allowed name.
- **Sequence, attempt, answer, saved summary**: as `specs/008` defines them; a sequence may now
  hold models of both providers.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: With neither OpenAI setting, the Chat, Summarization and Research tabs look and work
  as on `main`, and `ask`, `summarize`, `reindex-all` and `doctor` print, line for line, what they
  print on `main`, with Claude's settings set and without them; the new startup rules print
  nothing when they pass. In the unit tests, with clients that count their requests, a session of
  questions and summaries makes none to OpenAI.
- **SC-002**: With both settings and a valid key, `doctor` and "Check again" report the key
  accepted and each allowed OpenAI model found. In the unit tests, with a client that counts its
  requests, building the app, and answering and summarizing with the local model or with Claude,
  make no request to OpenAI. With a refused key, `doctor` reports it refused
  in one row, and a question asked with an OpenAI model and no fallback is answered by the local
  model, the tab naming OpenAI, the refused key as the reason and the local model as the one that
  answered, with the key nowhere in the page or the logs.
- **SC-003**: With OpenAI's settings exported, `make test-integration` runs each allowed OpenAI
  model on the excerpt that Claude's models are tested on. Five questions that its passages answer
  each get an answer that cites them in a form the app recognizes, every citation resolving to a
  passage it was given; three that they don't are each read as an abstention, as the application
  reads them, the reply check included; and a short chapter is summarized, its statements cited by
  lookup. All of them pass, on each model that stays in `OPENAI_MODELS`. A model that the owner's
  organization can't use, because OpenAI doesn't know it for the key, won't let the project use
  it, or won't stream it to the organization, is dropped from the list and recorded (FR-025), not
  counted as a failure, as long as one model remains. Without OpenAI's settings, those tests are
  skipped, and the others pass.
- **SC-004**: For a question asked with an OpenAI model, what reaches OpenAI is the Research tab's
  final context, and nothing else from the library; the search returned the same passages, in the
  same order, as for the local model; and the request asks OpenAI not to store it, and enables no
  tool.
- **SC-005**: After a chapter summarized by an OpenAI model and saved,
  `reindex-all --regenerate-summaries` makes no request to any provider, leaves the summary as it
  was, byte for byte, and lists it, with its model, as not written again.
- **SC-006**: With both providers configured: an allowed name that Anthropic doesn't know, picked
  first, with a real OpenAI model as its fallback, is followed by the OpenAI model's answer, and
  the local model isn't called; an allowed name that OpenAI doesn't know, with a real Claude model
  as its fallback, is followed by Claude's answer; the two unknown names in a row are followed by
  the local model's answer. In each case, the tab, the command and the Research tab name every
  failure, in order, with its provider, and the model that answered.
- **SC-007**: In the unit tests, every failure of FR-014 is said with its reason and moves on to
  the next model; an account out of credit is said as such and tried once; a stream refused to the
  organization fails with one request, never followed by one without streaming; a rate limit is tried
  three times in all; a silent model is given up on once; a 403 is a rejection with its code, and
  only a 401 a refused key; a refusal after text is a decline, its text withdrawn; a reply cut off
  with text is kept as an answer; a reply with no text fails; and an answer whose reasoning OpenAI
  doesn't return, or refuses to summarize, is kept.
- **SC-008**: In the unit tests, with `OPENAI_API_KEY` and `OPENAI_BASE_URL`, which OpenAI's library
  reads on its own, set in the environment, the judges' client is built to reach Ollama with its
  own key; every construction of a client of OpenAI's library in `app/` passes a key and an
  address; an experiment variant and a judge that name an OpenAI model are each refused before the
  run starts, and no request reaches a provider.
- **SC-009**: On the real models, for each allowed model, the integration tests compare the app's
  estimate of the eight questions' prompts and of the short summary's prompt with the input tokens
  that OpenAI reports for each, and print the largest ratio. It is recorded in `docs/decisions.md`
  and in the profile's comments. When it exceeds what `generation.context.safety_margin` absorbs,
  1 / (1 − `safety_margin`), about 1.11 with today's 0.1, the README and the profile say what the
  window caps in OpenAI's own tokens, as they do for Claude.
- **SC-010**: After a session with an OpenAI model, failures and a refused key included, a search
  of the logs, the saved summaries and the page finds no trace of the key.
- **SC-011**: The change leaves `app/services/`, `app/interface/` and `app/main.py` as they are on
  `main` (FR-022): `git diff main --stat` lists none of them when the pull request opens, and a
  unit test keeps any of them from naming OpenAI afterwards. If the plan finds that it can't, the
  spec is corrected first, with why.
- **SC-012**: `make lint-check` is clean, and `make test` passes, with unit tests for: OpenAI's
  settings read, with both, one or neither set, spaces, a name listed twice and a name in another
  case; a name allowed by two providers, or equal to the local model's, stopping the app; the
  profile's values refused when its provider doesn't take them; OpenAI's models offered after
  Claude's, in the choice, the fallbacks and the notices; what a request carries and what it
  doesn't (FR-012); each failure of FR-014; the retry without a reasoning summary (FR-015); the
  reading of OpenAI's stream into text, reasoning, tokens and timings; the check's rows; and the
  records of an answer and a saved summary. `tests/unit/test_anthropic_provider.py` passes without
  a change to it, which shows that the shared retry rules left Claude's provider as it was
  (FR-021).

## Assumptions

- **One person, on this machine.** The owner uses the app alone, and the interface is published on
  loopback by default. Anyone who can open the interface, or call its API, can spend either key,
  which the README already says.
- **The settings take a new container.** A change to `.env` reaches the app only when `make up`
  recreates the container, which empties the library: *História*, and every summary saved from
  it, whichever model wrote it, Claude's included (Clarifications). The owner decides when;
  the integration tests need only the settings exported in the shell that runs them. A change to
  `config/` alone can be copied into the container and applied by a restart, which keeps the
  library.
- **OpenAI's models follow the prompts written for the local models**, the citation format and the
  no-evidence marker included, or write them in a form that the app already normalizes, such as
  `gpt-oss`'s `【3】`. SC-003 checks it. Without tools, OpenAI attaches no annotations, such as a
  web source, to the text, which is read as written. If a prompt has to change, that is a decision
  of its own, measured on the local models too (Principles V and VI).
- **The profile serves models that reason** (Clarifications). Settings that they don't take, such
  as a sampling temperature, are left out for them, and the README says which. The profile holds
  what they do take, such as their effort and their token limits. The plan sets the values, and
  checks them on the real models, as it did for Claude. The owner will allow `gpt-6-luna`,
  `gpt-6.1-terra` and `gpt-6.2-sol` (Clarifications), so the effort is one that all three take,
  and the integration tests and the stack checks run on them.
- **The token estimate should be close.** `o200k_base`, which the app already ships for Claude, is
  the encoding of OpenAI's recent models, so the app's estimate is expected near OpenAI's own
  count, unlike Claude's. tiktoken has no entry for GPT-6 yet, so SC-009 measures it. If the
  estimate runs low, nothing is lost, since OpenAI refuses a prompt that doesn't fit instead of
  cutting it (FR-012): the window then caps more of OpenAI's tokens than it says, and the README
  and the profile say how many.
- **Anthropic's billing error** keeps its "key refused" wording (FR-021). Moving it to the new
  "out of credit" reason is a follow-up for the owner (Clarifications, FR-025).
- **The reasoning that OpenAI returns is a summary** of the model's reasoning, when it returns one
  at all, as Anthropic's is.
- **No prices.** The app shows tokens where it shows them for Claude, and estimates no cost. With
  OpenAI's settings exported, `make test-integration` spends a few cents per allowed model.
- **Benchmarks don't compare cloud models**: a cloud model has no digest or seed, so a run couldn't
  be reproduced (Principle I). The feature claims no gain in quality or speed and changes no
  default, so no benchmark run is needed (Principle VI).
- **No constitution amendment.** Principle I already covers any cloud provider, with a single
  profile per provider.
- **The steps that `AGENTS.md` adds** apply: the feature reads a new model family's output, so it
  runs clarify, checklist and analyze.
- **The release**: a feature, so the pull request is titled `feat:`, and its merge makes a minor
  release, v0.9.0 unless another release comes first. Nothing that a user relies on breaks.

## Results of the implementation, 2026-11-20

The implementation is on `feat/openai-provider`, uncommitted. The owner put their OpenAI key and
`OPENAI_MODELS=gpt-6-luna,gpt-6.1-terra,gpt-6.2-sol` in `.env`, beside Claude's settings. The
checks on the real models ran from the host first (`quickstart.md` § 2). The checks on the stack
ran on the running stack, with the owner's *História* as `book_001`, by the owner's choice: the new
`app/` and `config/` were copied into the app container and the app restarted, which kept the
library, and OpenAI's settings were passed to each command (`docker compose exec -e`). The tabs
don't offer OpenAI until a `make up` recreates the container with the settings, so the owner's
check in the browser (T039), and the parts of the criteria that it covers, wait for that.

- **SC-001: pass.** In the container without OpenAI's settings, `doctor` printed its rows and
  Claude's as before. The unit tests show `ask` printing as before with neither provider's
  settings and with Claude's alone, and no request reaching OpenAI's client.
- **SC-002: pass.** `doctor` reported each of the three models found ("owned by system"). With a
  wrong key, in its own process, it printed one row, "OpenAI refused the API key", and Claude's
  three rows as before; with `OPENAI_MODELS` alone, a failing row naming the missing key; with
  `gpt-no-such-model` in the list, that model's row failing and `gpt-6-luna`'s passing. The unit
  tests show building the app, and answering and summarizing with the local model or Claude,
  making no request to OpenAI, and a question asked with a refused key answered by the local model
  with the failure said.
- **SC-003: pass.** The integration tests ran the three OpenAI models and Claude's three on the
  excerpt: 60 of 60 cases passed in 145 s. Each OpenAI model cited as `[n]`, every citation
  resolving to the passage that answers, wrote the marker on all three unanswerable questions, and
  summarized the short chapter in one step, its statements cited by lookup. No model was dropped.
  The whole suite on the stack (`make test-integration`, `quickstart.md` § 10a): 77 passed, 48
  skipped for local models that aren't pulled, as on `main`, and the reranker's GPU test ran out
  of memory with `gpt-oss:20b` holding 12 GB, as in 008; with the models unloaded, its 6 tests
  passed. The cloud cases passed again on all six models.
- **SC-004: pass.** On *História*, `gpt-6-luna` was given the same numbered passages as
  `gpt-oss:20b`; the unit tests show the request's input equal, role for role, to the local
  model's prompt and to the answer's final context, not stored and with no tool.
- **SC-005: pass, in the unit tests.** A saved summary from an OpenAI model is left byte for byte
  by `reindex-all --regenerate-summaries`, listed as "(gpt-a-20261101, OpenAI)", with no request to
  OpenAI, with its settings set or not. On the stack, `reindex-all` didn't run, since it would
  rebuild the owner's library; `gpt-6.1-terra` summarized *História*'s chapter 3, unsaved, in one
  step, 14 statements cited and none without a source, in 12.1 s, reading 5,151 tokens and
  generating 820.
- **SC-006: pass.** On the stack: `gpt-no-such-model` then `claude-haiku-5-5`, Haiku answered;
  `claude-no-such-model` then `gpt-6-luna`, Luna answered, and the local model made no generation;
  both unknown, `gpt-oss:20b` answered. Each notice named both providers in the sequence's order,
  each failure was said as it happened, and a name given twice was refused before any search.
- **SC-007: pass**, in the unit tests, as the criterion asks.
- **SC-008: pass.** The unit tests show the judges' client reaching Ollama with its own key with
  `OPENAI_API_KEY` and `OPENAI_BASE_URL` set, and both clients of OpenAI's library in `app/` given a
  key and an address. On the stack, an experiment whose variant names `gpt-6-luna` was refused
  before it ran ("llm_profiles has no entry for llm.model 'gpt-6-luna'", still as a traceback, the
  008 follow-up), and one whose judge names it ("not on the Ollama server").
- **SC-009: pass.** OpenAI counted 1.015 to 1.018 times the app's estimate on the eight question
  prompts and the summary's, on each model; Claude, 1.541 to 1.556. Recorded in the profile's
  comments and `docs/decisions.md`; well under 1.11, so the window caps about 64K of OpenAI's
  tokens.
- **SC-010: pass.** After the session, failures and a wrong key included, `grep` found neither key
  in the container's logs or library. The page's source is part of the owner's browser check.
- **SC-011: pass.** `git diff main --stat` lists none of `app/services/`, `app/interface/` or
  `app/main.py`, nor `tests/unit/test_anthropic_provider.py`.
- **SC-012: pass.** `make lint-check` is clean, and `make test` ran 1,319 unit tests, all passing.

What the real models showed beside the criteria: at effort `low`, OpenAI reported no reasoning
tokens for the probe's questions, so no summary of the reasoning came back, and the Research tab
says that none did; asking for one caused no error. Answers ran 31 to 57 tokens, the first token
came in 0.7 to 1.0 s, and each model reported the name it was asked for. The owner's organization
streamed all three models, so the verification refusal wasn't met.

### Corrections during implementation

- **OpenAI's settings are read in `tests/unit/test_config.py`**, beside Anthropic's, where T006
  said `test_model_choices.py`.
- **Two of 008's guard tests changed**, since the feature changes what they guard:
  `test_container.py` now expects `anthropic` and `openai` as the provider kinds, and takes
  `gemini` as its example of a provider the app doesn't implement, where it took `openai`.
- **The integration run prints the generated tokens and the finish reason, not the reasoning
  tokens**: `GenerationStats` doesn't carry them. A probe read them from OpenAI's SDK directly: none
  on all three models.
- **The fake stream keeps each word's whitespace**, so that a summary's headings and lines survive
  the fake, as they survive OpenAI's own stream.
- **The stack checks ran without `make up`**, by the owner's choice (above). The app container's
  `/app/app` and `/app/config` belong to root, so the copy rewrote the files in place
  (`tar --overwrite`), and every file then matched the working tree.
