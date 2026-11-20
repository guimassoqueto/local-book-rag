# Contract: providers and choices

The interfaces between the services and the models (FR-022, FR-026; `research.md`, R3 to R6).
Signatures are the contract; bodies belong to the tasks.

## `LLMProvider` (`app/generation/base.py`)

One model, through one provider. Today's protocol, with two attributes more:

```python
class LLMProvider(Protocol):
    model: str
    provider: str                 # new: "ollama", "anthropic"
    check_abstentions: bool       # new: from the model's profile, or its provider's

    def context_size(self) -> int: ...
    def count_tokens(self, text: str) -> int: ...
    def stream(self, messages: Sequence[Message], parameters: GenerationParameters) -> Iterator[TextDelta | Generation]: ...
    def generate(self, messages: Sequence[Message], parameters: GenerationParameters) -> Generation: ...
```

- `stream()` yields text as it arrives, then one `Generation`. A cloud provider raises
  `ModelFailedError` for any failure of its own (the table below); the local provider raises the
  errors it raises today.
- `Generation.thinking_summarized` is true when `thinking` is a summary of the reasoning.
- `GenerationStats.load_seconds` and `prompt_seconds` are None when the provider doesn't report
  them.

`check_abstention(llm, question, reply, parameters)` reads `llm.check_abstentions`; its `settings`
argument goes.

## `CloudProvider` (`app/generation/cloud.py`)

A provider kind, built once from its credentials and its profile:

```python
class CloudProvider(Protocol):
    name: str                     # "anthropic", the key of its profile and its settings' prefix
    label: str                    # "Anthropic", as the interface shows it

    def model(self, name: str) -> LLMProvider: ...
    def check(self, models: Sequence[str]) -> list[ProviderCheck]: ...
```

`check()` may contact the provider, sending the key and the models' names and running no
inference. Nothing else in this protocol contacts it, building it included.

## Factory (`app/generation/factory.py`)

```python
def create_llm_provider(settings: Settings, runtime: OllamaRuntime) -> LLMProvider: ...  # unchanged
def create_cloud_providers(settings: Settings, environ: Mapping[str, str]) -> CloudSetup: ...
```

`CloudSetup` holds the configured `CloudProvider`s with their allowed models, the setting problems
of the providers with one setting only, and the names of every implemented kind. The kinds are one
mapping, `CLOUD_PROVIDERS: dict[str, type[CloudProvider]]`, `{"anthropic": AnthropicCloud}` now,
and the settings' names derive from its keys (`ANTHROPIC_API_KEY`, `ANTHROPIC_MODELS`).
`create_cloud_providers` raises `ConfigurationError` for a profile whose name isn't a key of
`CLOUD_PROVIDERS`, and for an allowed model whose provider has no profile (FR-003). It is the one
place, with `create_llm_provider`, that knows the concrete classes.

## `ModelChoices` (`app/generation/choices.py`)

```python
class ModelChoices:
    @classmethod
    def local_only(cls, llm: LLMProvider) -> "ModelChoices": ...

    def offered(self) -> list[ModelOption]: ...
    def has_cloud(self) -> bool: ...
    def describe(self, model: str | None, fallbacks: Sequence[str]) -> list[ModelOption]: ...
    def sequence(self, model: str | None, fallbacks: Sequence[str]) -> list[LLMProvider]: ...
    def is_cloud_provider(self, provider: str | None) -> bool: ...
    def label_of(self, provider: str) -> str: ...
    def check(self) -> list[ProviderCheck]: ...
    def setting_problems(self) -> list[ProviderCheck]: ...
```

- `describe()` and `sequence()` apply `data-model.md`'s rules, and raise `ModelChoiceError`.
  `describe()` builds no provider.
- `is_cloud_provider()` is true for the name of a provider kind in `CLOUD_PROVIDERS`, configured
  or not, and false for None and the local provider.
- `label_of(provider)` gives a provider's label, `local` for the local one, for messages and the
  interface.
- `check()` runs every configured provider's `check()`. `setting_problems()` contacts nothing.

## The Anthropic provider (`app/generation/anthropic_provider.py`)

### The request

| The app's                                  | Sent to `client.messages.stream()` |
| ------------------------------------------ | ---------------------------------- |
| the `model`                                | `model` |
| `system` messages                          | `system`: their contents, joined by a blank line |
| `user` and `assistant` messages            | `messages`, in order |
| `parameters.max_tokens`                    | `max_tokens`: plus the profile's `reasoning_tokens` |
| the profile's `reasoning`                  | `output_config={"effort": reasoning}`; nothing when null |
| (always)                                   | `thinking={"type": "adaptive", "display": "summarized"}` |
| `parameters.temperature`, `parameters.seed` | not sent |

No server-side `fallbacks`, and no tools.

### The reply

| From the stream                                         | Becomes |
| ------------------------------------------------------- | ------- |
| `content_block_delta` with a `text_delta`               | `TextDelta(delta.text)` |
| `content_block_delta` with a `thinking_delta`           | appended to `Generation.thinking` |
| the first delta of either kind                          | `time_to_first_token` |
| `get_final_message().model`                             | `GenerationStats.model` |
| `get_final_message().usage.input_tokens`, `.output_tokens` | `prompt_tokens`, `completion_tokens` |
| `stop_reason` `end_turn`                                | `finish_reason` `stop` |
| `stop_reason` `max_tokens`                              | `finish_reason` `length` (`FINISHED_BY_LENGTH`) |
| `stop_reason` `refusal`                                 | `ModelFailedError`, `declined`, its detail `stop_details.category` |

`Generation.thinking_summarized` is true. `load_seconds` and `prompt_seconds` are None;
`generation_seconds` runs from the first delta to the end.

### Failures

| From the SDK                                    | `FailureReason` | Message ("claude-x (Anthropic) failed: …") |
| ----------------------------------------------- | --------------- | ------------------------------------------ |
| `AuthenticationError`, 402, `PermissionDeniedError` | `key refused` | "it refused the API key" |
| `NotFoundError`                                 | `unknown model` | "it doesn't know this model" |
| `RateLimitError`                                | `rate limited`  | "it limited the rate" |
| `APITimeoutError`                               | `timed out`     | "it sent nothing for 120 s" |
| `APIConnectionError`                            | `unreachable`   | "it can't be reached" |
| `InternalServerError`                           | `outage`        | "it is down or overloaded (529)" |
| any other `APIStatusError`                      | `rejected`      | "it rejected the request: invalid_request_error" |
| `stop_reason` `refusal`                         | `declined`      | "it declined the request (cyber)" |

The client is built with `max_retries=0`. Before the stream has yielded anything, the provider
tries a request again itself, at most twice, after a `RateLimitError`, an `InternalServerError` or
an `APIConnectionError` that isn't a timeout, waiting 2 s, then 6 s, or the API's `retry-after`
when it is shorter than 10 s. A timeout is never tried again, so a silent model holds the request
for `request_timeout_seconds` once (FR-017). After a delta has arrived, any failure is final.

`no answer` is not the provider's: the services raise it when a reply has no text. A reply that
stops at `max_tokens` with text in it is an answer.

No message holds the key: the SDK's errors carry the API's words, not the request's headers.

### The check

For each allowed model, `client.models.retrieve(name)`, which reads:
- `display_name` and `max_input_tokens`, for the row's detail;
- `capabilities["effort"][reasoning]["supported"]` and
  `capabilities["thinking"]["types"]["adaptive"]["supported"]`, which the profile needs;
- `max_input_tokens` against the profile's `context_size`.

A refused key stops the check at the first model, with one row.
