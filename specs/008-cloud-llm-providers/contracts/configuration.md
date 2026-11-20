# Contract: configuration

What the owner sets to offer cloud models, and what the app does with it at startup (FR-001 to
FR-005; `research.md`, R1 and R2).

## `.env`

```dotenv
# Cloud models, offered beside the local one only when both are set. The local model stays the
# default, and nothing goes to Anthropic unless a request picks one of its models. Setting or
# changing these takes `make up`, which recreates the app container and empties the library.
ANTHROPIC_API_KEY=
# Comma-separated, in the order the tabs list them, such as claude-sonnet-5-5,claude-opus-5-5.
ANTHROPIC_MODELS=
```

`devtools/.env.sample` holds this block, both settings empty (FR-005). `make env` copies it to
`.env` as today.

## `docker-compose.yml`

The app service's `environment` passes both, empty when `.env` doesn't set them:

```yaml
      ANTHROPIC_API_KEY: ${ANTHROPIC_API_KEY:-}
      ANTHROPIC_MODELS: ${ANTHROPIC_MODELS:-}
```

No other service gets them. Docker Compose recreates the app container when either changes, which
deletes the library (Principle II): the README says so where it explains them (FR-029).

## `config/models.yaml`

A new top-level key, after `embedding_profiles`:

```yaml
# What every model of a cloud provider shares, by provider. A provider's models are offered only
# when its API key and allowed models are set in .env (ANTHROPIC_API_KEY, ANTHROPIC_MODELS), and
# none answers unless the user picks it for a request.
cloud_profiles:
  anthropic:
    # Claude's tokenizer isn't public, so this is an approximation, which
    # generation.context.safety_margin absorbs. The API refuses a prompt that doesn't fit the
    # model, where Ollama cuts it.
    tokenizer:
      kind: tiktoken
      name: o200k_base

    # The window the app works with, far below the models' own: it caps what one request sends.
    context_size: 65536

    # Sent as the request's effort. The current Claude models reason whatever they are told,
    # and Claude Opus 5.5 can't be told not to. They take no sampling temperature either, so
    # generation.yaml's temperature doesn't apply to them.
    reasoning: low

    # Added to every request's max_tokens, since reasoning counts against it, and set aside from
    # context_size.
    reasoning_tokens: 4000

    check_abstentions: false

    # Seconds that Anthropic may send nothing before the request counts as timed out and the next
    # model of the sequence starts. A timeout is never tried again, so this is the longest wait.
    request_timeout_seconds: 120
```

## Validation at startup

| Configuration | Outcome |
| ------------- | ------- |
| `cloud_profiles` absent | valid: no provider can be offered |
| a profile under a name the app doesn't implement, such as `openai` | the app doesn't start: `cloud_profiles.openai`, as any unknown key |
| a profile with an unknown key, or a value out of range | the app doesn't start, naming it |
| a task's `max_tokens` plus `reasoning_tokens` not smaller than `context_size` | the app doesn't start: "max_tokens and reasoning_tokens leave no room for the prompt in cloud_profiles.anthropic.context_size" |
| `ANTHROPIC_MODELS` set and `cloud_profiles.anthropic` absent | the app doesn't start: "ANTHROPIC_MODELS allows claude-…, but cloud_profiles in config/models.yaml has no profile for anthropic" (FR-003) |
| one of the two settings set | the app starts; the provider isn't offered; the log says which setting is missing (FR-002) |
| both set, with a profile | the app starts, offering the provider's models; nothing contacts Anthropic (FR-021) |

Every check above reads files and the environment only. None contacts a provider, so the app
starts without a network.

## Where the key goes

- It belongs in `.env`, in the app container's environment, which `docker inspect` and
  `docker compose config` show to anyone who can run Docker, and in the shell that exports it for
  `make test-integration` (FR-004).
- Read from the environment into a `SecretStr`, held by the provider's client and nowhere else.
- Never in `Settings` or `EnvironmentSettings`, so never in a benchmark result, which records
  `Settings`.
- Never in a log event, an error message, a saved summary, the interface or a command's output
  (FR-004, SC-011).
