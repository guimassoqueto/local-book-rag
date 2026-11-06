import json
import logging

import pytest

from app.utils.logging import INFERENCE_LOGGER, configure_logging, get_logger, log_event, operation


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


def test_inference_logs_have_their_own_file_and_level(logs_dir):
    inference = logging.getLogger(INFERENCE_LOGGER)

    log_event(inference, "below the inference threshold")
    log_event(inference, "above it", level=logging.WARNING)

    entries = read_entries(logs_dir / "inference.jsonl")
    assert [entry["message"] for entry in entries] == ["above it"]
    assert not (logs_dir / "app.jsonl").read_text(encoding="utf-8")
