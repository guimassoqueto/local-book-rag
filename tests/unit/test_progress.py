"""The progress an operation on the library reports (specs/004-library-progress, contracts/progress.md)."""

import logging
import threading

import pytest

from app.utils.progress import Outcome, Progress, ProgressView, StageSpec

EXTRACT = StageSpec("extract", "Extracting the text", unit="chunks", estimate=True)  # a counted stage, for the tests
PREPARE = StageSpec("prepare", "Preparing the chunks")
EMBED = StageSpec("embed", "Embedding the chunks", unit="chunks", estimate=True)
SAVE = StageSpec("save", "Saving to the index")
STEPS = (EXTRACT, PREPARE, EMBED, SAVE)
BOOKS = StageSpec("books", "Indexing the books", unit="books", steps=STEPS)
SWITCH = StageSpec("switch", "Switching to the new index")


class Clock:
    def __init__(self) -> None:
        self.now = 100.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


@pytest.fixture
def clock():
    return Clock()


class Records(logging.Handler):
    def __init__(self) -> None:
        super().__init__(logging.INFO)
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


@pytest.fixture
def caplog():
    """The progress logger's records. The application's logger doesn't propagate once configured."""
    logger = logging.getLogger("book_rag.progress")
    handler, level = Records(), logger.level
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    yield handler
    logger.removeHandler(handler)
    logger.setLevel(level)


def stage_lines(caplog):
    return [record for record in caplog.records if record.getMessage() in ("stage finished", "stage failed")]


def fields(record):
    return getattr(record, "fields", {})


def warnings(caplog):
    return [record for record in caplog.records if record.levelno >= logging.WARNING]


# Before, during and after


def test_there_is_nothing_to_show_before_the_operation_begins(clock):
    assert Progress(clock=clock).snapshot() is None


def test_a_running_operation_shows_its_stage_and_position(clock):
    progress = Progress(clock=clock)

    with progress.operation("Adding a book", STEPS, subject="book_003"), progress.stage("prepare"):
        clock.advance(2)
        view = progress.snapshot()

    assert view.operation == "Adding a book" and view.subject == "book_003"
    assert (view.stage.key, view.stage.label, view.stage.position, view.stage.stages) == (
        "prepare",
        "Preparing the chunks",
        2,
        4,
    )
    assert view.elapsed == 2 and view.step is None and view.outcome is None


def test_the_last_stage_stays_shown_between_stages(clock):
    progress = Progress(clock=clock)

    with progress.operation("Adding a book", STEPS):
        with progress.stage("extract"):
            pass
        between = progress.snapshot()

    assert between.stage.key == "extract"


def test_a_finished_operation_keeps_its_outcome_and_its_time(clock):
    progress = Progress(clock=clock)

    with progress.operation("Adding a book", STEPS), progress.stage("extract"):
        clock.advance(5)
    clock.advance(30)
    view = progress.snapshot()

    assert view.outcome == Outcome(succeeded=True) and view.elapsed == 5


def test_a_snapshot_is_a_frozen_copy(clock):
    progress = Progress(clock=clock)

    with progress.operation("Adding a book", STEPS), progress.stage("embed") as stage:
        stage.count(10)
        before = progress.snapshot()
        stage.advance(5)

    assert isinstance(before, ProgressView) and before.stage.done == 0
    with pytest.raises(AttributeError):
        before.stage.done = 3


# Counts


def test_a_count_starts_at_zero_grows_and_reaches_its_total(clock):
    progress = Progress(clock=clock)
    seen = []

    with progress.operation("Adding a book", STEPS), progress.stage("embed") as stage:
        stage.count(3)
        for _ in range(3):
            seen.append(progress.snapshot().stage.done)
            stage.advance()
        seen.append(progress.snapshot().stage.done)

    assert seen == [0, 1, 2, 3] and progress.snapshot().stage.total == 3
    assert progress.snapshot().stage.unit == "chunks"


def test_an_advance_past_the_total_is_held_and_warned_about(clock, caplog):
    progress = Progress(clock=clock)

    with progress.operation("Adding a book", STEPS), progress.stage("embed") as stage:
        stage.count(2)
        stage.advance(5)
        done = progress.snapshot().stage.done

    assert done == 2
    assert any("past" in record.getMessage() for record in warnings(caplog))


def test_a_total_of_zero_is_allowed(clock):
    progress = Progress(clock=clock)

    with progress.operation("Adding a book", STEPS), progress.stage("embed") as stage:
        stage.count(0)
        view = progress.snapshot()

    assert (view.stage.done, view.stage.total) == (0, 0)


# The time left


def run_stage(progress, clock, total, paces):
    """Advance a stage one item at a time, each taking its pace; return the views after each advance."""
    views = []
    with progress.operation("Adding a book", STEPS), progress.stage("embed") as stage:
        stage.count(total)
        for pace in paces:
            clock.advance(pace)
            stage.advance()
            views.append(progress.snapshot())
    return views


def test_no_time_left_before_three_seconds(clock):
    views = run_stage(Progress(clock=clock), clock, 10, [0.5] * 10)

    assert [view.stage.time_left is not None for view in views][:5] == [False] * 5  # 2.5 s and less


def test_no_time_left_before_a_tenth_of_the_items(clock):
    views = run_stage(Progress(clock=clock), clock, 100, [1.0] * 12)

    assert views[8].stage.time_left is None  # 9 s, 9 of 100
    assert views[9].stage.time_left == pytest.approx(90.0)  # 10 s, 10 of 100


def test_no_time_left_for_a_stage_that_doesnt_estimate(clock):
    progress = Progress(clock=clock)

    with progress.operation("Reindexing the library", (BOOKS, SWITCH)), progress.stage("books") as stage:
        stage.count(4)
        for _ in range(3):
            clock.advance(10)
            stage.advance()
        view = progress.snapshot()

    assert view.stage.done == 3 and view.stage.time_left is None


def test_a_single_stall_doesnt_throw_the_time_left_off(clock):
    paces = [0.2] * 5 + [2.0] + [0.2] * 44  # one advance ten times slower than the rest
    views = run_stage(Progress(clock=clock), clock, 50, paces)

    for index, view in enumerate(views[5:], start=5):
        actual = sum(paces[index + 1 :])
        if view.stage.time_left is not None and actual > 0:
            assert 0.5 * actual <= view.stage.time_left <= 2 * actual, (index, view.stage.time_left, actual)


def test_the_time_left_counts_down_between_advances_and_stops_at_zero(clock):
    progress = Progress(clock=clock)

    with progress.operation("Adding a book", STEPS), progress.stage("embed") as stage:
        stage.count(10)
        for _ in range(5):
            clock.advance(1)
            stage.advance()
        right_after = progress.snapshot().stage.time_left
        clock.advance(2)
        later = progress.snapshot().stage.time_left
        clock.advance(10)
        stalled = progress.snapshot().stage.time_left

    assert right_after == pytest.approx(5.0) and later == pytest.approx(3.0) and stalled == 0


# The sink


def test_the_sink_hears_of_each_stage_its_advances_at_most_once_an_interval_and_the_outcome(clock):
    heard = []
    progress = Progress(sink=heard.append, interval=2.0, clock=clock)

    with progress.operation("Adding a book", STEPS):
        with progress.stage("embed") as stage:
            stage.count(10)
            for _ in range(10):
                clock.advance(0.5)
                stage.advance()
        with progress.stage("save"):
            pass

    embedding = [view for view in heard if view.stage and view.stage.key == "embed"]
    advances = [view for view in embedding if view.stage.done is not None and 0 < view.stage.done < 10]
    assert len(advances) <= 3
    assert heard[0].stage.key == "embed" and heard[0].stage.done is None  # its start
    assert embedding[-1].stage.done == 10  # its end
    assert any(view.stage.key == "save" for view in heard if view.stage)
    assert heard[-1].outcome == Outcome(succeeded=True)


def test_a_sink_that_raises_is_dropped_and_the_operation_goes_on(clock, caplog):
    calls = []

    def broken(view):
        calls.append(view)
        raise BrokenPipeError("the terminal is gone")

    progress = Progress(sink=broken, clock=clock)

    with progress.operation("Adding a book", STEPS):
        with progress.stage("extract"):
            pass
        with progress.stage("prepare"):
            pass

    assert len(calls) == 1 and progress.snapshot().outcome.succeeded
    assert len([record for record in warnings(caplog) if "sink" in record.getMessage()]) == 1


# Mistakes in reporting


def test_an_undeclared_stage_is_warned_about_and_shown_without_a_position(clock, caplog):
    progress = Progress(clock=clock)

    with progress.operation("Adding a book", STEPS), progress.stage("bogus"):
        view = progress.snapshot()

    assert view.stage.key == "bogus" and view.stage.position is None and view.outcome is None
    assert any("undeclared stage" in record.getMessage() for record in warnings(caplog))


def test_outside_an_operation_nothing_is_tracked_or_logged(clock, caplog):
    progress = Progress(clock=clock)

    with progress.stage("extract") as stage:
        stage.count(3)
        stage.advance()
        stage.note("a note")
        stage.item("book_001", "A title")

    assert progress.snapshot() is None and caplog.records == []


# Failures


def test_an_exception_goes_through_unchanged_and_the_outcome_names_the_stage(clock, caplog):
    progress = Progress(clock=clock)
    error = ConnectionError("Ollama is down")

    with pytest.raises(ConnectionError) as raised:
        with progress.operation("Adding a book", STEPS), progress.stage("embed"):
            clock.advance(3)
            raise error

    assert raised.value is error
    assert progress.snapshot().outcome == Outcome(succeeded=False, stage="Embedding the chunks", error="Ollama is down")
    [line] = stage_lines(caplog)
    assert line.getMessage() == "stage failed"


def test_a_failed_step_names_the_stage_the_step_and_the_item(clock):
    progress = Progress(clock=clock)

    with pytest.raises(ConnectionError):
        with progress.operation("Reindexing the library", (BOOKS, SWITCH)), progress.stage("books") as books:
            books.count(2)
            books.item("book_002", "Quincas Borba")
            with progress.stage("embed"):
                raise ConnectionError("Ollama is down")

    assert progress.snapshot().outcome == Outcome(
        succeeded=False,
        stage="Indexing the books",
        step="Embedding the chunks",
        item="book_002, Quincas Borba",
        error="Ollama is down",
    )


def test_a_failure_outside_any_stage_names_none(clock):
    progress = Progress(clock=clock)

    with pytest.raises(ValueError), progress.operation("Adding a book", STEPS):
        raise ValueError("no")

    assert progress.snapshot().outcome == Outcome(succeeded=False, error="no")


# Steps


def test_a_step_shows_beside_its_stage_with_its_own_position(clock):
    progress = Progress(clock=clock)

    with progress.operation("Reindexing the library", (BOOKS, SWITCH)), progress.stage("books") as books:
        books.count(5)
        books.advance()
        books.item("book_002", "Quincas Borba")
        with progress.stage("embed") as embed:
            embed.count(454)
            view = progress.snapshot()

    assert (view.stage.key, view.stage.done, view.stage.total, view.stage.note) == ("books", 1, 5, "Quincas Borba")
    assert (view.step.key, view.step.position, view.step.stages, view.step.total) == ("embed", 3, 4, 454)


def test_a_new_item_clears_the_last_step(clock):
    progress = Progress(clock=clock)

    with progress.operation("Reindexing the library", (BOOKS, SWITCH)), progress.stage("books") as books:
        books.count(2)
        books.item("book_001", "Think Python")
        with progress.stage("save"):
            pass
        books.advance()
        books.item("book_002", "Quincas Borba")
        view = progress.snapshot()

    assert view.step is None and view.stage.note == "Quincas Borba"


def test_meanwhile_is_part_of_the_view(clock):
    progress = Progress(clock=clock)

    with progress.operation("Reindexing the library", (BOOKS,), meanwhile="Questions keep working."):
        view = progress.snapshot()

    assert view.meanwhile == "Questions keep working." and view.stage is None


# The log


def test_each_stage_line_carries_only_its_fields(clock, caplog):
    progress = Progress(clock=clock)

    with progress.operation("Reindexing the library", (BOOKS, SWITCH)):
        with progress.stage("books") as books:
            books.count(1)
            books.item("book_001", "Think Python")
            with progress.stage("embed") as embed:
                embed.count(2)
                clock.advance(1.5)
                embed.advance(2)
            books.advance()
        with progress.stage("switch"):
            clock.advance(0.5)

    embed, books, switch = (fields(line) for line in stage_lines(caplog))
    assert embed == {
        "stage": "embed",
        "done": 2,
        "total": 2,
        "unit": "chunks",
        "duration_seconds": 1.5,
        "within": "books",
        "item": "book_001",
    }
    assert books == {"stage": "books", "done": 1, "total": 1, "unit": "books", "duration_seconds": 1.5}
    assert switch == {"stage": "switch", "duration_seconds": 0.5}


def test_the_snapshot_can_be_read_from_another_thread(clock):
    progress = Progress()
    views = []

    def read():
        for _ in range(200):
            views.append(progress.snapshot())

    with progress.operation("Adding a book", STEPS), progress.stage("embed") as stage:
        stage.count(1000)
        reader = threading.Thread(target=read)
        reader.start()
        for _ in range(1000):
            stage.advance()
        reader.join()

    done = [view.stage.done for view in views if view and view.stage and view.stage.done is not None]
    assert done == sorted(done)
