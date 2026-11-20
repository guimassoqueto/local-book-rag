# Contract: the OpenAI provider

The provider kind and the model provider that this feature adds behind 008's interfaces
(`specs/008-cloud-llm-providers/contracts/providers.md`), and the shared pieces it changes. Nothing
above `app/generation` changes (FR-022, SC-011).

## `app/generation/cloud.py`

```python
class CloudProvider(Protocol):
    name: ClassVar[str]
    label: ClassVar[str]
    efforts: ClassVar[frozenset[str | None]]   # new: the efforts its profile may hold; None = send none (research.md R6)

    def __init__(self, credentials: ProviderCredentials, profile: CloudProfile) -> None: ...
    def model(self, name: str) -> LLMProvider: ...
    def check(self, models: Sequence[str]) -> list[ProviderCheck]: ...


# Moved from anthropic_provider.py, unchanged in behavior (research.md R9)
RETRY_WAITS: tuple[float, ...] = (2.0, 6.0)
RETRIED: frozenset[FailureReason]   # RATE_LIMITED, OUTAGE, UNREACHABLE

def retry_wait(headers: Mapping[str, str] | None, reason: FailureReason, waits: Iterator[float]) -> float | None:
    """How long to wait before trying again, or None when the failure is final: the next wait, or
    the provider's retry-after when it is shorter than 10 seconds."""
```

## `app/generation/openai_provider.py`

```python
class OpenAICloud:
    name = "openai"
    label = "OpenAI"
    efforts = frozenset({"none", "minimal", "low", "medium", "high", "xhigh", "max"})   # not None
    # AnthropicCloud.efforts = frozenset({None, "low", "medium", "high", "xhigh", "max"})

    def __init__(self, credentials, profile, client_factory=None, sleep=None) -> None:
        """Builds openai.OpenAI(api_key=<key>, base_url="https://api.openai.com/v1",
        timeout=profile.request_timeout_seconds, max_retries=0). Contacts nothing."""

    def model(self, name: str) -> "OpenAILLMProvider": ...

    def check(self, models: Sequence[str]) -> list[ProviderCheck]:
        """client.models.retrieve(name) for each: the key and the name, no inference."""


class OpenAILLMProvider:
    provider = "openai"
    model: str
    check_abstentions: bool            # the profile's

    def context_size(self) -> int:     # profile.context_size - profile.reasoning_tokens
    def count_tokens(self, text: str) -> int:   # the profile's tokenizer
    def stream(self, messages, parameters) -> Iterator[TextDelta | Generation]:
    def generate(self, messages, parameters) -> Generation:
```

Every failure of its own raises `ModelFailedError(model, "openai", reason, detail, "OpenAI")`,
raised `from None`, never the SDK's errors.

### The request (research.md R2)

```python
client.responses.create(
    model=<name>,
    input=[{"role": m.role, "content": m.content} for m in messages],   # roles and text as written
    max_output_tokens=parameters.max_tokens + profile.reasoning_tokens,
    reasoning={"effort": profile.reasoning, "summary": "auto"},   # the profile always names an effort
    store=False,
    truncation="disabled",
    stream=True,
)
```

After a 400 whose `param` is `reasoning.summary`, the same call without `"summary"`, once, at once;
it counts against none of the retries below. Nothing else is ever sent: no `tools`,
`temperature`, `top_p`, `metadata`, `user`, `safety_identifier`, `prompt_cache_key`,
`service_tier`, `background`, `previous_response_id`, `conversation` or `include`.

### The stream (research.md R3)

| Event | Effect |
| --- | --- |
| `response.output_text.delta` | `yield TextDelta(delta)`; the first token's time if unset |
| `response.reasoning_summary_text.delta` | appended to the reasoning; the first token's time if unset |
| `response.refusal.delta` | the reply is declined |
| `response.completed` / `.incomplete` / `.failed` | the terminal response; the loop ends |
| anything else | ignored |

Reasoning items, and their encrypted copy, are dropped. Then: declined → `DECLINED`, even after
text has been yielded (the services withdraw it); failed → by its `error.code`; incomplete for
`content_filter` → `DECLINED`; otherwise `yield Generation(text, reasoning, stats, thinking_summarized=True)` with:

| `GenerationStats` | From |
| --- | --- |
| `model` | `response.model` |
| `prompt_tokens` | `response.usage.input_tokens` |
| `completion_tokens` | `response.usage.output_tokens` |
| `time_to_first_token` | first text or reasoning delta, from the request's start |
| `load_seconds`, `prompt_seconds` | `None` |
| `generation_seconds` | first delta to the end |
| `total_seconds` | the request's start to the end |
| `finish_reason` | `stop` when completed; `length` when incomplete for `max_output_tokens` |

The inference log's `generation finished` event, as for Claude.

### Failures (research.md R4)

| Raised by the SDK, or found in the stream | `FailureReason` | detail | tried again |
| --- | --- | --- | --- |
| `APITimeoutError` | `TIMED_OUT` | `120 s` | no |
| `APIConnectionError`; no terminal event | `UNREACHABLE` | | yes |
| `AuthenticationError` (401) | `KEY_REFUSED` | code | no |
| `PermissionDeniedError` (403), other than the verification refusal | `REJECTED` | code, and `param` when given | no |
| `NotFoundError` (404), code `model_not_found` | `UNKNOWN_MODEL` | | no |
| `RateLimitError` (429) with a credit code (research.md R4) | `OUT_OF_CREDIT` | code | no |
| `RateLimitError` (429), other codes | `RATE_LIMITED` | code | yes |
| `InternalServerError` (5xx); failed `server_error` | `OUTAGE` | status or code | yes |
| failed `rate_limit_exceeded` | `RATE_LIMITED` | code | yes |
| refusal; failed `invalid_prompt`, `bio_policy`; incomplete `content_filter` | `DECLINED` | code, or none | no |
| a stream refused to an unverified organization | `REJECTED` | `OpenAI streams this model only to a verified organization` | no |
| any other 400 or failed code | `REJECTED` | code, and `param` when given | no |
| an `error` event, raised as `APIError` | by its body's code, as above | | as above |

"Tried again" means before any text or reasoning has arrived, by `retry_wait()`. "Timed out" means
nothing at all arrived for the profile's time, events included: the client's read timeout. OpenAI's
message is read only to recognize the verification refusal, and never shown or logged.

### The check (research.md R10)

| Outcome of `models.retrieve` | Rows |
| --- | --- |
| found | `[ ok ] openai gpt-6-luna   gpt-6-luna, owned by <owned_by>` |
| unknown | `[fail] openai gpt-x        OpenAI doesn't know this model` |
| forbidden (403): the project may not use it | `[fail] openai gpt-x        OpenAI rejected the request: <code>`; the check goes on |
| refused key (401), unreachable, timed out | one row, ending the check: `[fail] openai   OpenAI refused the API key` |

## What the user sees

The interfaces word OpenAI's models and failures with 008's code, through the label and
`FailureReason.describe()`:

| Where | Text |
| --- | --- |
| choice, fallbacks | `gpt-6.2-sol (OpenAI)` |
| Chat tab's notice, OpenAI alone | "The question and the passages found go to OpenAI: gpt-6.2-sol. If it fails, gpt-oss:20b answers, locally." |
| Chat tab's notice, a mixed sequence | "The question and the passages found go to Anthropic: claude-sonnet-5-5, then OpenAI: gpt-6.2-sol. If they fail, gpt-oss:20b answers, locally." |
| Summarization tab's notice | "The chapter's text goes to OpenAI: gpt-6.2-sol. If it fails, gpt-oss:20b summarizes it, locally." |
| status, then a failure | "Found 5 passages. Asking gpt-6-luna (OpenAI)…", then "⚠️ gpt-6-luna (OpenAI) failed: its account is out of credit or over a spending or usage limit (credit_balance_exhausted). Asking gpt-oss:20b…" |
| `ask --model` on standard error | the notice, before anything is sent |
| Chat tab, answered | "Answered by gpt-6.2-sol (OpenAI) in **4.2 s** · …" |
| Research tab | the reasoning under "A summary of the reasoning, as OpenAI returns it", or "None came back." |
| `reindex-all` | "Kept as they were, written by a cloud model: book_001, chapter_04_standard (gpt-6.2-sol, OpenAI)" |

The wording is 008's (`specs/008-cloud-llm-providers/contracts/interface.md`,
`app/interface/formatting.py`), with OpenAI's label; only the out-of-credit words are new. The
unit tests check it through the label.
