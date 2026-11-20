"""Stand-ins for the services that need a running server."""

import hashlib
import math
import re
from dataclasses import dataclass
from types import SimpleNamespace

import anthropic
import httpx2

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
