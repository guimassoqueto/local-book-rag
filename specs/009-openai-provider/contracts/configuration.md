# Contract: configuration

What the owner sets to offer OpenAI's models, and what the app does with it at startup (FR-001 to
FR-006; `research.md`, R6 to R8). Claude's settings and profile don't change.

## `.env`

`devtools/.env.sample` gains, after Anthropic's block (FR-005):

```dotenv
# OpenAI's models, offered beside the local one only when both are set, after Claude's. Nothing
# goes to OpenAI unless a request picks one of its models. The key is an API key from
# platform.openai.com, billed per token; a ChatGPT subscription isn't one. Setting or changing
# these takes `make up`, which recreates the app container and empties the library.
OPENAI_API_KEY=
# Comma-separated, in the order the tabs list them, such as gpt-6-luna,gpt-6.1-terra,gpt-6.2-sol.
# Models that reason only: cloud_profiles.openai sends each request a reasoning effort.
OPENAI_MODELS=
```

The owner's `.env` will hold `OPENAI_MODELS=gpt-6-luna,gpt-6.1-terra,gpt-6.2-sol`
(Clarifications).

## `docker-compose.yml`

The app service's `environment` passes both, empty when `.env` doesn't set them, after Claude's:

```yaml
      OPENAI_API_KEY: ${OPENAI_API_KEY:-}
      OPENAI_MODELS: ${OPENAI_MODELS:-}
```

No other service gets them. Docker Compose recreates the app container when either changes, which
deletes the library (Principle II): the README says so (FR-024).

## `config/models.yaml`

`cloud_profiles` gains `openai`, after `anthropic`:

```yaml
  openai:
    # OpenAI's recent models count with o200k_base, which tiktoken maps to gpt-5, gpt-4.1 and
    # gpt-4o; it has no entry for the GPT-6 models yet. On the real models, OpenAI counted <ratio>
    # times the app's estimate (<date>). <What that means for context_size.>
    tokenizer:
      kind: tiktoken
      name: o200k_base

    # The window the app works with, far below the models' own (922,000 input tokens): it caps
    # what one request sends, and so what it costs.
    context_size: 65536

    # Sent as the request's reasoning effort, with a summary of the reasoning asked for. It can't
    # be empty: each model would reason at its own default. Every allowed model must take it:
    # gpt-6.2-sol refuses none, and OpenAI advises low over none or minimal. The GPT-6 models take no sampling temperature, so generation.yaml's temperature
    # doesn't apply to them.
    reasoning: low

    # Added to every request's max_output_tokens, since reasoning counts against it, and set
    # aside from context_size.
    reasoning_tokens: 4000

    # <Set from the integration run: true if a model abstained in words without the marker.>
    check_abstentions: false

    # Seconds that OpenAI may send nothing before the request counts as timed out and the next
    # model of the sequence starts. A timeout is never tried again, so this is the longest wait.
    request_timeout_seconds: 120
```

The comments in angle brackets are filled in from the integration run (research.md R6, SC-009),
and `check_abstentions` set by 008 R2's rule.

## What startup does

In order, contacting nothing (008 FR-021):

1. `config/` is validated, as today. `cloud_profiles.<name>.reasoning` must be one of `none`,
   `minimal`, `low`, `medium`, `high`, `xhigh`, `max`, or null.
2. A profile under a name that isn't in `CLOUD_PROVIDERS` stops the app (008 FR-003).
3. **New**: a profile whose effort its provider doesn't accept stops the app (FR-003), checked for
   every profile, whether its provider is configured or not:

   ```text
   cloud_profiles.anthropic.reasoning in config/models.yaml is 'minimal', which Anthropic doesn't
   take (it takes: high, low, max, medium, xhigh, or none at all)
   ```

   ```text
   cloud_profiles.openai.reasoning in config/models.yaml is empty, but OpenAI's profile must name
   an effort (it takes: high, low, max, medium, minimal, none, xhigh)
   ```

4. Each provider's settings are read. With models and no profile, the app stops (008 FR-003). With
   one setting, the provider isn't offered, and the log says which is missing:

   ```text
   cloud provider not offered provider=openai missing=OPENAI_MODELS
   ```

5. **New**: a name that two providers offer, or that a provider offers and is `llm.model`, stops
   the app (FR-006); a provider with one setting offers nothing, so its list clashes with nothing:

   ```text
   gpt-x is allowed by both ANTHROPIC_MODELS and OPENAI_MODELS, so a request naming it couldn't
   say which provider it goes to. Remove it from one of them.
   ```

   ```text
   gpt-oss:20b is in OPENAI_MODELS and is llm.model in config/models.yaml, the local model.
   Remove it from OPENAI_MODELS.
   ```

6. The choices are built: the local model, then Anthropic's models, then OpenAI's, each in its
   list's order (FR-007).

When every rule passes, startup logs nothing new (SC-001).
