"""Stand-ins for the services that need a running server."""

import hashlib
import math
import re
from dataclasses import dataclass
from types import SimpleNamespace

import anthropic
import httpx2
import openai
from openai.types import Model as OpenAIModel
from openai.types.responses import (
    Response,
    ResponseCompletedEvent,
    ResponseCreatedEvent,
    ResponseFailedEvent,
    ResponseIncompleteEvent,
    ResponseInProgressEvent,
    ResponseReasoningSummaryTextDeltaEvent,
    ResponseRefusalDeltaEvent,
    ResponseTextDeltaEvent,
)

from app.generation.base import Generation, GenerationStats, TextDelta
from app.ingestion.chunker import Chunk
from app.utils.ollama_runtime import ModelInfo


def make_chunk(
    text="Some text.",
    book_id="book_001",
    index=0,
    chapter=1,
    section="Section",
    language="en",
):
    return Chunk(
        chunk_id=f"{book_id}_chapter_{chapter:02d}_chunk_{index:04d}",
        book_id=book_id,
        book_title="Title",
        chapter_number=chapter,
        chapter_title=f"Chapter {chapter}",
        section_title=section,
        chunk_index=index,
        language=language,
        text=text,
    )


class WordCounter:
    def count(self, text):
        return len(text.split())


class FakeChunks:
    """A chunk source that counts how often it is read."""

    def __init__(self, chunks):
        self.chunks = chunks
        self.loads = 0

    def load_chunks(self, book_id, revision):
        self.loads += 1
        return [chunk for chunk in self.chunks if chunk.book_id == book_id]


class WordLocator:
    """Finds a statement's passage by the words they share, where the application compares meaning.

    For tests that read a real model's summary: a statement whose words aren't in any passage, at
    least `minimum` of them, has no source.
    """

    def __init__(self, chunks, minimum=3):
        self.chunks = chunks
        self.minimum = minimum

    def closest_chunk(self, statement, book_id, chapter_number):
        words = _words(statement)
        shared = [(len(words & _words(chunk.text)), chunk) for chunk in self.chunks]
        count, chunk = max(shared, key=lambda pair: pair[0])
        return chunk if count >= self.minimum else None


def _words(text):
    return {word for word in re.findall(r"\w+", text.casefold()) if len(word) > 3}


class FakeReranker:
    """Scores a text by how often the query's words appear in it."""

    model = "fake-reranker"

    def __init__(self):
        self.calls = 0

    def score(self, query, texts):
        self.calls += 1
        words = query.casefold().split()
        return [min(1.0, sum(text.casefold().count(word) for word in words) / 10) for text in texts]


class FakeEmbedder:
    """Deterministic unit vectors: the same text always gets the same vector."""

    def __init__(self, model="fake-embedding", dimensions=8, failure=None):
        self.model = model
        self._dimensions = dimensions
        self.failure = failure

    def dimensions(self):
        return self._dimensions

    def embed_documents(self, texts, on_batch=None):
        if self.failure:
            raise self.failure
        vectors = [self._vector(text) for text in texts]
        if on_batch:
            on_batch(len(texts))
        return vectors

    def embed_query(self, text):
        return self._vector(text)

    def _vector(self, text):
        digest = hashlib.sha256(text.encode()).digest()
        values = [value - 127.5 for value in digest[: self._dimensions]]
        norm = math.sqrt(sum(value * value for value in values))
        return [value / norm for value in values]


class FakeRuntime:
    base_url = "http://ollama.test"

    def __init__(self, dimensions=1024, digest="digest-1"):
        self.dimensions = dimensions
        self.digest = digest
        self.loaded = []
        self.unloaded = []

    def version(self):
        return "0.0.test"

    def model_info(self, name):
        return ModelInfo(name, self.digest, "family", "1B", "Q8", 32768, self.dimensions, ("embedding",))

    def loaded_models(self):
        return list(self.loaded)

    def unload(self, model):
        self.unloaded.append(model)
        self.loaded = [entry for entry in self.loaded if entry.name != model]


def make_stats(prompt_tokens=100, completion_tokens=20, finish_reason="stop", model="fake-llm", cloud=False):
    """Stats as a runtime reports them. A cloud provider reports no loading or prompt processing."""
    load, prompt = (None, None) if cloud else (0.0, 0.1)
    return GenerationStats(model, prompt_tokens, completion_tokens, 0.1, load, prompt, 0.2, 0.3, finish_reason)


class FakeLLM:
    """Replies from a script, or with functions of the prompt, and records what it was sent.

    Args:
        replies: the replies in order, the last one repeating.
        respond: computes a reply from (messages, parameters), instead of `replies`.
        context_size: the window it reports.
        finish_reasons: why each reply stopped, in order. Then "stop".
        finish: computes that from the prompt's last message, instead of `finish_reasons`.
        model: the model's name.
        provider: its provider's name.
        check_abstentions: its profile's setting.
        thinking: the reasoning each reply comes with.
        thinking_summarized: whether that reasoning is a provider's summary of it.
        fail: an error to raise instead of replying, once `fail_after_calls` calls have replied.
        fail_after_calls: how many calls reply before `fail` is raised, on every later call.
        text_before_failure: what a streamed reply yields before it raises `fail`.
        cloud: report stats as a cloud provider does, without loading or prompt processing.
        reported_model: the model its stats name, if not `model`, as a provider may report a
            dated version of the name it was asked for.
    """

    def __init__(
        self,
        replies=None,
        respond=None,
        context_size=8192,
        finish_reasons=None,
        finish=None,
        *,
        model="fake-llm",
        provider="ollama",
        check_abstentions=False,
        thinking="some reasoning",
        thinking_summarized=False,
        fail=None,
        fail_after_calls=0,
        text_before_failure="",
        cloud=False,
        reported_model=None,
    ):
        self.replies = list(replies or [])
        self.respond = respond
        self.window = context_size
        self.finish_reasons = list(finish_reasons or [])
        self.finish = finish
        self.model = model
        self.provider = provider
        self.check_abstentions = check_abstentions
        self.thinking = thinking
        self.thinking_summarized = thinking_summarized
        self.fail = fail
        self.fail_after_calls = fail_after_calls
        self.text_before_failure = text_before_failure
        self.cloud = cloud
        self.reported_model = reported_model
        self.calls = []

    def context_size(self):
        return self.window

    def count_tokens(self, text):
        return len(text.split())

    def stream(self, messages, parameters):
        if self._fails_now():
            self.calls.append((list(messages), parameters))
            for word in self.text_before_failure.split():
                yield TextDelta(word + " ")
            raise self.fail
        generation = self.generate(messages, parameters)
        for word in generation.text.split(" "):
            yield TextDelta(word + " ")
        yield generation

    def generate(self, messages, parameters):
        failing = self._fails_now()
        self.calls.append((list(messages), parameters))
        if failing:
            raise self.fail
        if self.respond is not None:
            reply = self.respond(messages, parameters)
        else:
            reply = self.replies.pop(0) if len(self.replies) > 1 else self.replies[0]
        if self.finish is not None:
            reason = self.finish(messages[-1].content)
        else:
            reason = self.finish_reasons.pop(0) if self.finish_reasons else "stop"
        stats = make_stats(finish_reason=reason, model=self.reported_model or self.model, cloud=self.cloud)
        return Generation(reply, self.thinking, stats, thinking_summarized=self.thinking_summarized)

    def _fails_now(self):
        return self.fail is not None and len(self.calls) >= self.fail_after_calls


class FakeCloud:
    """A cloud provider kind (contracts/providers.md), whose models are `FakeLLM`s.

    It is built as the container builds a real one, from credentials and a profile, or with its
    models scripted. It counts what would reach the provider: its checks, and its models' calls.
    """

    name = "fakecloud"
    label = "FakeCloud"
    # Every effort name, and none at all: the fake kind takes any profile (specs/009, research.md R6).
    efforts = frozenset({None, "none", "minimal", "low", "medium", "high", "xhigh", "max"})

    def __init__(self, credentials=None, profile=None, models=None, checks=None):
        self.credentials = credentials
        self.profile = profile
        self.scripted = dict(models or {})
        self.checks = checks
        self.check_calls = []
        self.built = []

    def model(self, name):
        if name not in self.scripted:
            self.scripted[name] = FakeLLM(["A cloud answer [1]."], model=name, provider=self.name, cloud=True)
        self.built.append(name)
        return self.scripted[name]

    def check(self, models):
        from app.generation.cloud import ProviderCheck  # imported late: the module comes with the feature

        self.check_calls.append(list(models))
        if self.checks is not None:
            return list(self.checks)
        return [ProviderCheck(f"{self.name} {model}", True, "a fake model") for model in models]

    @property
    def requests(self):
        """What reached the provider: every check, and every call of a model."""
        return len(self.check_calls) + sum(len(llm.calls) for llm in self.scripted.values())


# Anthropic's SDK, as far as the provider reads it (specs/008, research.md R4)

ANTHROPIC_REQUEST = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
EFFORTS = ("low", "medium", "high", "xhigh", "max")


def anthropic_status_error(error_class, status, headers=None, error_type=None):
    """An SDK error for an HTTP status, built as the SDK builds it, with the API's error type if given."""
    response = httpx2.Response(status, request=ANTHROPIC_REQUEST, headers=headers or {})
    body = {"type": "error", "error": {"type": error_type, "message": "A message."}} if error_type else None
    return error_class(f"Error code: {status}", response=response, body=body)


def anthropic_connection_error():
    return anthropic.APIConnectionError(request=ANTHROPIC_REQUEST)


def anthropic_timeout_error():
    return anthropic.APITimeoutError(request=ANTHROPIC_REQUEST)


def anthropic_model_info(name, window=1_000_000, efforts=EFFORTS, adaptive=True):
    """What `client.models.retrieve()` returns for a model, built as the SDK's own type."""

    def support(supported):
        return {"supported": supported}

    tools = {"supported": False, "code_execution": support(False), "web_search": support(False)}
    capabilities = {
        "effort": {"supported": bool(efforts)} | {effort: support(effort in efforts) for effort in EFFORTS},
        "thinking": {
            "supported": True,
            "types": {kind: support(adaptive if kind == "adaptive" else True) for kind in THINKING_TYPES},
        },
        "context_management": {"supported": False},
        "server_tools": tools,
    } | {feature: support(True) for feature in FEATURES}
    return anthropic.types.ModelInfo.model_validate(
        {
            "id": name,
            "type": "model",
            "display_name": f"Display {name}",
            "created_at": "2026-11-01T00:00:00Z",
            "lifecycle": "active",
            "max_input_tokens": window,
            "capabilities": capabilities,
        }
    )


THINKING_TYPES = ("adaptive", "between_tools", "disabled", "enabled")
FEATURES = ("batch", "citations", "code_execution", "image_input", "pdf_input", "structured_outputs")


@dataclass
class FakeReply:
    """One scripted reply of `FakeAnthropicClient`.

    Attributes:
        text: streamed word by word, as text deltas.
        thinking: streamed before the text, as thinking deltas.
        error: an SDK error to raise.
        error_after: how many deltas come before `error`; None raises it when the stream opens.
    """

    text: str = "An answer [1]."
    thinking: str = ""
    model: str = "claude-test-1"
    input_tokens: int = 120
    output_tokens: int = 30
    stop_reason: str = "end_turn"
    category: str | None = None
    error: Exception | None = None
    error_after: int | None = None


class _FakeMessageStream:
    def __init__(self, reply):
        self.reply = reply

    def __enter__(self):
        if self.reply.error is not None and self.reply.error_after is None:
            raise self.reply.error
        return self

    def __exit__(self, *exc_info):
        return False

    def __iter__(self):
        events = [_delta("thinking_delta", thinking=word + " ") for word in self.reply.thinking.split()]
        events += [_delta("text_delta", text=word + " ") for word in self.reply.text.split()]
        for position, event in enumerate(events):
            if self.reply.error is not None and position == self.reply.error_after:
                raise self.reply.error
            yield SimpleNamespace(type="message_start")  # an event the provider skips
            yield event
        if self.reply.error is not None and self.reply.error_after is not None:
            raise self.reply.error

    def get_final_message(self):
        reply = self.reply
        details = SimpleNamespace(category=reply.category, explanation=None) if reply.category else None
        usage = SimpleNamespace(input_tokens=reply.input_tokens, output_tokens=reply.output_tokens)
        return SimpleNamespace(model=reply.model, usage=usage, stop_reason=reply.stop_reason, stop_details=details)


def _delta(kind, **fields):
    return SimpleNamespace(type="content_block_delta", index=0, delta=SimpleNamespace(type=kind, **fields))


class FakeAnthropicClient:
    """The part of `anthropic.Anthropic` that the provider uses, scripted, counting its calls.

    Args:
        replies: the `FakeReply`s that `messages.stream()` gives, in order, the last one repeating.
        models: what `models.retrieve()` returns per name, a model or an error to raise. A name
            missing here is unknown, a 404.
    """

    def __init__(self, replies=None, models=None):
        self.replies = list(replies or [FakeReply()])
        self.model_infos = dict(models or {})
        self.options = None
        self.stream_calls = []
        self.retrieve_calls = []
        self.messages = SimpleNamespace(stream=self._stream)
        self.models = SimpleNamespace(retrieve=self._retrieve)

    def factory(self, **options):
        """Stands for `anthropic.Anthropic`: records the client's options and returns this client."""
        self.options = options
        return self

    @property
    def calls(self):
        return len(self.stream_calls) + len(self.retrieve_calls)

    def _stream(self, **request):
        self.stream_calls.append(request)
        reply = self.replies.pop(0) if len(self.replies) > 1 else self.replies[0]
        return _FakeMessageStream(reply)

    def _retrieve(self, model_id, **options):
        self.retrieve_calls.append(model_id)
        info = self.model_infos.get(model_id)
        if isinstance(info, Exception):
            raise info
        if info is None:
            raise anthropic_status_error(anthropic.NotFoundError, 404)
        return info


# OpenAI's SDK, as far as the provider reads it (specs/009, research.md R1 to R4). The events and
# responses are the installed SDK's own types, validated, so that an SDK release that changes them
# fails here before it reaches the provider.

OPENAI_REQUEST = httpx2.Request("POST", "https://api.openai.com/v1/responses")


def openai_error_body(code=None, param=None, message="A message.", error_type=None):
    """The error object of OpenAI's API, which the SDK hands to its errors as their body."""
    return {"message": message, "type": error_type, "param": param, "code": code}


def openai_status_error(error_class, status, code=None, param=None, message="A message.", headers=None):
    """An SDK error for an HTTP status, built as the SDK builds it, with the API's code and parameter."""
    response = httpx2.Response(status, request=OPENAI_REQUEST, headers=headers or {})
    body = openai_error_body(code, param, message)
    return error_class(f"Error code: {status} - {message}", response=response, body=body)


def openai_stream_error(code, message="A message.", param=None):
    """What the SDK raises when a stream carries an `error` event: an APIError with the error's body."""
    return openai.APIError(message, OPENAI_REQUEST, body=openai_error_body(code, param, message))


def openai_connection_error():
    return openai.APIConnectionError(request=OPENAI_REQUEST)


def openai_timeout_error():
    return openai.APITimeoutError(request=OPENAI_REQUEST)


def openai_model(name, owned_by="openai"):
    """What `client.models.retrieve()` returns for a model, built as the SDK's own type."""
    return OpenAIModel.model_validate({"id": name, "created": 1, "object": "model", "owned_by": owned_by})


@dataclass
class FakeResponse:
    """One scripted response of `FakeOpenAIClient`.

    Attributes:
        text: streamed word by word, as text deltas.
        reasoning: streamed before the text, word by word, as reasoning summary deltas.
        refusal: streamed after the text, as refusal deltas.
        model: the model the response names.
        input_tokens, output_tokens, reasoning_tokens: its usage.
        status: `completed`, `incomplete` or `failed`: the terminal event.
        incomplete_reason: for `incomplete`, `max_output_tokens` or `content_filter`.
        error_code: for `failed`, the response's error code.
        terminal: False ends the stream without a terminal event.
        error: an SDK error to raise.
        error_after: how many deltas come before `error`; None raises it when the request is made.
    """

    text: str = "An answer [1]."
    reasoning: str = ""
    refusal: str = ""
    model: str = "gpt-test-1"
    input_tokens: int = 120
    output_tokens: int = 30
    reasoning_tokens: int = 10
    status: str = "completed"
    incomplete_reason: str | None = None
    error_code: str | None = None
    terminal: bool = True
    error: Exception | None = None
    error_after: int | None = None


def _openai_response(reply, status):
    output = []
    if reply.reasoning:
        summary = [{"type": "summary_text", "text": reply.reasoning}]
        output.append({"id": "rs_1", "type": "reasoning", "summary": summary, "encrypted_content": "ENCRYPTED"})
    content = []
    if reply.text:
        content.append({"type": "output_text", "text": reply.text, "annotations": []})
    if reply.refusal:
        content.append({"type": "refusal", "refusal": reply.refusal})
    if content:
        message = {"id": "msg_1", "type": "message", "role": "assistant", "status": "completed"}
        output.append(message | {"content": content})
    usage = {
        "input_tokens": reply.input_tokens,
        "input_tokens_details": {"cached_tokens": 0, "cache_write_tokens": 0},
        "output_tokens": reply.output_tokens,
        "output_tokens_details": {"reasoning_tokens": reply.reasoning_tokens},
        "total_tokens": reply.input_tokens + reply.output_tokens,
    }
    data = {
        "id": "resp_1",
        "created_at": 0,
        "model": reply.model,
        "object": "response",
        "output": output if status != "in_progress" else [],
        "parallel_tool_calls": False,
        "tool_choice": "auto",
        "tools": [],
        "status": status,
        "usage": usage if status != "in_progress" else None,
        "incomplete_details": {"reason": reply.incomplete_reason} if status == "incomplete" else None,
        "error": {"code": reply.error_code, "message": "A message."} if status == "failed" else None,
    }
    return Response.model_validate(data)


_TERMINAL_EVENTS = {
    "completed": (ResponseCompletedEvent, "response.completed"),
    "incomplete": (ResponseIncompleteEvent, "response.incomplete"),
    "failed": (ResponseFailedEvent, "response.failed"),
}


def openai_events(reply):
    """The events of a streamed response, in the order the API sends them."""
    number = iter(range(1_000_000))
    start = _openai_response(reply, "in_progress")
    events = [
        ResponseCreatedEvent.model_validate(
            {"type": "response.created", "sequence_number": next(number), "response": start}
        ),
        ResponseInProgressEvent.model_validate(
            {"type": "response.in_progress", "sequence_number": next(number), "response": start}
        ),
    ]
    deltas = [
        ResponseReasoningSummaryTextDeltaEvent.model_validate(
            {
                "type": "response.reasoning_summary_text.delta",
                "sequence_number": next(number),
                "item_id": "rs_1",
                "output_index": 0,
                "summary_index": 0,
                "delta": word + " ",
            }
        )
        for word in reply.reasoning.split()
    ]
    deltas += [
        ResponseTextDeltaEvent.model_validate(
            {
                "type": "response.output_text.delta",
                "sequence_number": next(number),
                "item_id": "msg_1",
                "output_index": 1,
                "content_index": 0,
                "delta": piece,
                "logprobs": [],
            }
        )
        for piece in re.findall(r"\s*\S+\s*", reply.text)  # each word with its whitespace, line breaks kept
    ]
    deltas += [
        ResponseRefusalDeltaEvent.model_validate(
            {
                "type": "response.refusal.delta",
                "sequence_number": next(number),
                "item_id": "msg_1",
                "output_index": 1,
                "content_index": 1,
                "delta": word + " ",
            }
        )
        for word in reply.refusal.split()
    ]
    terminal = []
    if reply.terminal:
        event_class, kind = _TERMINAL_EVENTS[reply.status]
        terminal.append(
            event_class.model_validate(
                {"type": kind, "sequence_number": next(number), "response": _openai_response(reply, reply.status)}
            )
        )
    return events, deltas, terminal


class _FakeResponseStream:
    def __init__(self, reply):
        self.reply = reply
        self.closed = False

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        self.close()
        return False

    def close(self):
        self.closed = True

    def __iter__(self):
        events, deltas, terminal = openai_events(self.reply)
        yield from events
        for position, delta in enumerate(deltas):
            if self.reply.error is not None and position == self.reply.error_after:
                raise self.reply.error
            yield delta
        if self.reply.error is not None and self.reply.error_after is not None:
            raise self.reply.error
        yield from terminal


class FakeOpenAIClient:
    """The part of `openai.OpenAI` that the provider uses, scripted, counting its calls.

    Args:
        responses: the `FakeResponse`s that `responses.create()` gives, in order, the last one
            repeating.
        models: what `models.retrieve()` returns per name, a model or an error to raise. A name
            missing here is unknown, a 404.
    """

    def __init__(self, responses=None, models=None):
        self.scripted = list(responses or [FakeResponse()])
        self.model_infos = dict(models or {})
        self.options = None
        self.create_calls = []
        self.retrieve_calls = []
        self.responses = SimpleNamespace(create=self._create)
        self.models = SimpleNamespace(retrieve=self._retrieve)

    def script(self, *responses, models=None):
        """Replaces the scripted responses, and the models' descriptions when given."""
        self.scripted = list(responses)
        if models is not None:
            self.model_infos = dict(models)

    def factory(self, **options):
        """Stands for `openai.OpenAI`: records the client's options and returns this client."""
        self.options = options
        return self

    @property
    def calls(self):
        return len(self.create_calls) + len(self.retrieve_calls)

    def _create(self, **request):
        self.create_calls.append(request)
        reply = self.scripted.pop(0) if len(self.scripted) > 1 else self.scripted[0]
        if reply.error is not None and reply.error_after is None:
            raise reply.error
        return _FakeResponseStream(reply)

    def _retrieve(self, model, **options):
        self.retrieve_calls.append(model)
        info = self.model_infos.get(model)
        if isinstance(info, Exception):
            raise info
        if info is None:
            raise openai_status_error(openai.NotFoundError, 404, code="model_not_found")
        return info
