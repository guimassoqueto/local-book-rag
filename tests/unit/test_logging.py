import json
import logging

import anthropic
import pytest
from pydantic import SecretStr

from app.config.settings import ProviderCredentials
from app.errors import BookRagError, ServiceUnavailableError
from app.generation.anthropic_provider import AnthropicCloud
from app.generation.choices import ModelChoices
from app.generation.factory import CloudSetup
from app.generation.question_answering import QuestionAnsweringService
from app.retrieval.base import Passage, RetrievalFilters
from app.retrieval.pipeline import RetrievalResult
from app.utils.logging import INFERENCE_LOGGER, configure_logging, get_logger, log_event, operation
from tests.fakes import (
    FakeAnthropicClient,
    FakeLLM,
    FakeReply,
    anthropic_connection_error,
    anthropic_model_info,
    anthropic_status_error,
    make_chunk,
)


def read_entries(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


@pytest.fixture
def logs_dir(tmp_path):
    directory = tmp_path / "logs"
    configure_logging("INFO", "WARNING", directory)
    yield directory
    for name in ("book_rag", INFERENCE_LOGGER):
        for handler in logging.getLogger(name).handlers:
            handler.close()
        logging.getLogger(name).handlers.clear()


def test_operation_tags_every_line_with_its_execution_id(logs_dir):
    logger = get_logger("test")

    with operation(logger, "add_book", book_id="book_001") as execution_id:
        log_event(logger, "chunked", chunks=12)

    entries = read_entries(logs_dir / "app.jsonl")
    assert [entry["message"] for entry in entries] == ["operation started", "chunked", "operation finished"]
    assert {entry["execution_id"] for entry in entries} == {execution_id}
    assert {entry["book_id"] for entry in entries} == {"book_001"}
    assert entries[1]["chunks"] == 12
    assert entries[2]["duration_seconds"] >= 0


def test_failed_operation_logs_the_error_and_propagates_it(logs_dir):
    logger = get_logger("test")

    with pytest.raises(RuntimeError), operation(logger, "add_book"):
        raise RuntimeError("extraction failed")

    failure = read_entries(logs_dir / "app.jsonl")[-1]
    assert failure["level"] == "ERROR"
    assert "extraction failed" in failure["error"]


def test_lines_after_an_operation_are_not_tagged(logs_dir):
    logger = get_logger("test")

    with operation(logger, "add_book"):
        pass
    log_event(logger, "afterwards")

    assert "execution_id" not in read_entries(logs_dir / "app.jsonl")[-1]


def test_commands_keep_their_output_clean(tmp_path, capsys):
    configure_logging("INFO", "INFO", tmp_path / "quiet", console=False)

    log_event(get_logger("test"), "goes to the file only")

    assert capsys.readouterr().out == ""
    assert read_entries(tmp_path / "quiet" / "app.jsonl")[0]["message"] == "goes to the file only"


def test_inference_logs_have_their_own_file_and_level(logs_dir):
    inference = logging.getLogger(INFERENCE_LOGGER)

    log_event(inference, "below the inference threshold")
    log_event(inference, "above it", level=logging.WARNING)

    entries = read_entries(logs_dir / "inference.jsonl")
    assert [entry["message"] for entry in entries] == ["above it"]
    assert not (logs_dir / "app.jsonl").read_text(encoding="utf-8")


# The API key (specs/008-cloud-llm-providers, FR-004, SC-011)

SENTINEL = "sk-ant-sentinel-must-never-appear-0123456789"


class OnePassage:
    def search(self, query, filters, config=None):
        passage = Passage(make_chunk("Mill defends the liberty of thought."), rerank_score=0.9)
        return RetrievalResult(query, (passage,), (passage,), 0.1, 0.2)


def test_a_session_of_cloud_questions_leaves_the_key_nowhere(settings, tmp_path):
    directory = tmp_path / "logs"
    configure_logging("DEBUG", "DEBUG", directory, console=False)
    client = FakeAnthropicClient(
        replies=[
            FakeReply(text="Mill defends liberty [1]."),
            FakeReply(error=anthropic_status_error(anthropic.AuthenticationError, 401)),
            FakeReply(text="", stop_reason="refusal", category="cyber"),
            FakeReply(error=anthropic_connection_error()),
            FakeReply(error=anthropic_connection_error()),
            FakeReply(error=anthropic_connection_error()),
            FakeReply(text="Liberty of thought [1].", stop_reason="max_tokens"),
            FakeReply(error=anthropic_status_error(anthropic.InternalServerError, 529)),
        ],
        models={"claude-a": anthropic_model_info("claude-a")},
    )
    credentials = ProviderCredentials("anthropic", SecretStr(SENTINEL), ("claude-a",))
    cloud = AnthropicCloud(credentials, settings.cloud_profiles["anthropic"], client.factory, lambda seconds: None)
    local = FakeLLM(["The local answer [1]."], model=settings.llm.model)
    models = ModelChoices(local, CloudSetup(((cloud, ("claude-a",)),), (), {"anthropic": "Anthropic"}))
    questions = QuestionAnsweringService(settings, OnePassage(), models)

    try:
        answers = [questions.answer("What does Mill defend?", RetrievalFilters(), model="claude-a") for _ in range(5)]
        local.fail = ServiceUnavailableError("Ollama is down.")
        with pytest.raises(BookRagError) as everything_failed:
            questions.answer("What does Mill defend?", RetrievalFilters(), model="claude-a")
        client.model_infos["claude-a"] = anthropic_status_error(anthropic.AuthenticationError, 401)
        rows = models.check()
    finally:
        for name in ("book_rag", INFERENCE_LOGGER):
            for handler in logging.getLogger(name).handlers:
                handler.close()
            logging.getLogger(name).handlers.clear()

    assert [len(answer.attempts) for answer in answers] == [0, 1, 1, 1, 0]
    assert client.options["api_key"] == SENTINEL  # it reached the SDK's client, and only that
    written = (directory / "app.jsonl").read_text(encoding="utf-8") + (directory / "inference.jsonl").read_text(
        encoding="utf-8"
    )
    assert "model failed" in written and "generation finished" in written
    assert SENTINEL not in written
    assert all(SENTINEL not in repr(answer) for answer in answers)
    assert SENTINEL not in str(everything_failed.value) and SENTINEL not in repr(everything_failed.value.attempts)
    assert all(SENTINEL not in repr(row) for row in rows)
    assert SENTINEL not in repr(credentials) and SENTINEL not in repr(models.cloud_setup)
