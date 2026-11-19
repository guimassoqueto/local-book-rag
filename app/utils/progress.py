"""What an operation on the library reports as it runs: its stages, counts, time left and outcome.

An operation declares its stages before it starts and opens each one as it reaches it. The
embedding batches count chunks, and a reindex counts books. The Library tab asks `snapshot()`,
and a command gives a sink, and both only show what they get (specs/004-library-progress).

Nothing here raises into the operation: a mistake in reporting is logged, so that showing progress
can never fail or change what an operation does.
"""

import logging
import threading
import time
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any

from app.utils.logging import get_logger, log_event

logger = get_logger("progress")

# A stage has a pace, and shows a time left, once it has run this long and done this share of its
# items: a stage's first items include its start-up (research.md, R6).
PACE_SECONDS = 3.0
PACE_SHARE = 0.10


@dataclass(frozen=True)
class StageSpec:
    """A stage an operation declares before it starts.

    Attributes:
        key: the name in the log, such as "extract".
        label: the name on screen, such as "Extracting the text".
        unit: what a count counts: chunks, books, summaries or originals.
        estimate: whether a count shows a time left. Not for books or summaries, whose sizes vary
            too much for the ones done to say anything about the ones left.
        steps: the stages inside each item, for the books of a reindex.
    """

    key: str
    label: str
    unit: str | None = None
    estimate: bool = False
    steps: tuple["StageSpec", ...] = ()


@dataclass(frozen=True)
class StageView:
    """A stage as shown: its position is None for a stage that wasn't declared."""

    key: str
    label: str
    position: int | None
    stages: int | None
    done: int | None = None
    total: int | None = None
    unit: str | None = None
    time_left: float | None = None
    note: str | None = None


@dataclass(frozen=True)
class Outcome:
    """How an operation ended, and where, when it failed."""

    succeeded: bool
    stage: str | None = None
    step: str | None = None
    item: str | None = None
    error: str | None = None


@dataclass(frozen=True)
class ProgressView:
    """What an operation reports: the spec's "progress update"."""

    operation: str
    subject: str | None
    stage: StageView | None
    step: StageView | None
    elapsed: float
    meanwhile: str | None
    outcome: Outcome | None


class _State:
    """A stage while it runs. Only the Progress that owns it reads or writes it, under its lock."""

    def __init__(
        self, spec: StageSpec | None, key: str, position: int | None, stages: int | None, started: float
    ) -> None:
        self.spec = spec
        self.key = key
        self.label = spec.label if spec else key
        self.position = position
        self.stages = stages
        self.started = started
        self.open = True  # closed stages stay shown until the next one opens
        self.done: int | None = None
        self.total: int | None = None
        self.counted: tuple[int, int] | None = None  # (done, total), kept for the log line
        self.note: str | None = None
        self.item_id: str | None = None
        self.last_advance = started
        self.paces: list[tuple[float, int]] = []  # seconds per item, and how many items it was for
        self.warned_past_total = False

    def view(self, now: float) -> StageView:
        return StageView(
            key=self.key,
            label=self.label,
            position=self.position,
            stages=self.stages,
            done=self.done,
            total=self.total,
            unit=self.spec.unit if self.spec and self.total is not None else None,
            time_left=self._time_left(now),
            note=self.note,
        )

    def _time_left(self, now: float) -> float | None:
        if not (self.spec and self.spec.estimate) or self.total is None or self.done is None or not self.paces:
            return None
        if now - self.started < PACE_SECONDS or self.done < PACE_SHARE * self.total:
            return None
        return max((self.total - self.done) * _weighted_median(self.paces) - (now - self.last_advance), 0.0)

    def log_fields(self, now: float, within: "_State | None") -> dict[str, Any]:
        fields: dict[str, Any] = {"stage": self.key}
        if self.counted is not None:
            fields.update(done=self.counted[0], total=self.counted[1], unit=self.spec.unit if self.spec else None)
        fields["duration_seconds"] = now - self.started
        if within is not None:
            fields.update(within=within.key, item=within.item_id)
        return fields


def _weighted_median(paces: Sequence[tuple[float, int]]) -> float:
    """The pace of most items, which one stalled advance can't move (research.md, R6)."""
    ordered = sorted(paces)
    half = sum(weight for _, weight in ordered) / 2
    seen = 0
    for pace, weight in ordered:
        seen += weight
        if seen >= half:
            return pace
    return ordered[-1][0]


class Stage:
    """What the code inside a stage reports to. Outside an operation, every method does nothing."""

    def __init__(self, progress: "Progress | None", state: _State | None) -> None:
        self._progress = progress
        self._state = state

    def count(self, total: int) -> None:
        """Start counting the stage's items, from 0 to `total`."""
        if self._progress is not None and self._state is not None:
            self._progress._count(self._state, total)

    def advance(self, items: int = 1) -> None:
        """Count `items` more as done."""
        if self._progress is not None and self._state is not None:
            self._progress._advance(self._state, items)

    def note(self, text: str | None) -> None:
        """Set the line shown beside the stage."""
        if self._progress is not None and self._state is not None:
            self._progress._note(self._state, text)

    def item(self, item_id: str, note: str | None = None) -> None:
        """Mark what the stage's steps are now about, such as the book a reindex is indexing."""
        if self._progress is not None and self._state is not None:
            self._progress._item(self._state, item_id, note)


_IDLE = Stage(None, None)


class Progress:
    """The progress of one operation, written by the thread that runs it and read by any other.

    Args:
        sink: told of each stage's start, a counted stage's end, a new item, and the outcome,
            and, while a stage counts or notes, at most once every `interval` seconds. A sink that
            raises is logged and dropped.
        interval: the least time between two calls of the sink for a stage's advances.
        clock: seconds, for the tests.
    """

    def __init__(
        self,
        sink: Callable[[ProgressView], None] | None = None,
        interval: float = 0.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._sink = sink
        self._interval = interval
        self._clock = clock
        self._lock = threading.Lock()
        self._active = False
        self._label: str | None = None
        self._stages: tuple[StageSpec, ...] = ()
        self._subject: str | None = None
        self._meanwhile: str | None = None
        self._started = 0.0
        self._ended: float | None = None
        self._top: _State | None = None
        self._step: _State | None = None
        self._failed: dict[str, str | None] = {}
        self._outcome: Outcome | None = None
        self._last_sink = float("-inf")

    @contextmanager
    def operation(
        self,
        label: str,
        stages: Sequence[StageSpec],
        subject: str | None = None,
        meanwhile: str | None = None,
    ) -> Iterator[None]:
        """Begin the operation's progress, with its stages declared up front, and record how it ends."""
        with self._lock:
            self._active = True
            self._label, self._stages, self._subject, self._meanwhile = label, tuple(stages), subject, meanwhile
            self._started, self._ended = self._clock(), None
            self._top = self._step = None
            self._failed, self._outcome = {}, None
        try:
            yield
        except Exception as exc:
            self._finish(Outcome(succeeded=False, error=str(exc), **self._failed))
            raise
        else:
            self._finish(Outcome(succeeded=True))

    @contextmanager
    def stage(self, key: str) -> Iterator[Stage]:
        """Open the declared stage of that key: a top-level one, or a step of the open stage that has steps."""
        state, parent = self._open(key)
        if state is None:
            yield _IDLE
            return
        try:
            yield Stage(self, state)
        except Exception:
            self._close(state, parent, failed=True)
            raise
        else:
            self._close(state, parent, failed=False)

    def snapshot(self) -> ProgressView | None:
        """The operation as it stands, or None before it begins. Safe to call from any thread."""
        with self._lock:
            if self._label is None:
                return None
            return self._view(self._clock())

    # Below, everything runs in the operation's thread, and nothing raises out of it.

    def _view(self, now: float) -> ProgressView:
        """The current view. The caller holds the lock."""
        return ProgressView(
            operation=self._label or "",
            subject=self._subject,
            stage=self._top.view(now) if self._top else None,
            step=self._step.view(now) if self._step else None,
            elapsed=(self._ended if self._ended is not None else now) - self._started,
            meanwhile=self._meanwhile,
            outcome=self._outcome,
        )

    def _open(self, key: str) -> tuple[_State | None, _State | None]:
        try:
            with self._lock:
                if not self._active:
                    return None, None
                now = self._clock()
                top = self._top
                parent = top if top is not None and top.open and top.spec and top.spec.steps else None
                declared = parent.spec.steps if parent is not None and parent.spec else self._stages
                spec = next((candidate for candidate in declared if candidate.key == key), None)
                position = declared.index(spec) + 1 if spec is not None else None
                state = _State(spec, key, position, len(declared) if spec is not None else None, now)
                if parent is not None:
                    self._step = state
                else:
                    self._top, self._step = state, None
            if spec is None:
                log_event(logger, "undeclared stage", logging.WARNING, stage=key)
            self._tell(force=True)
            return state, parent
        except Exception:
            logger.exception("progress not reported", extra={"fields": {"stage": key}})
            return None, None

    def _close(self, state: _State, parent: _State | None, failed: bool) -> None:
        try:
            with self._lock:
                now = self._clock()
                state.open = False
                fields = state.log_fields(now, parent)
                if failed:
                    if parent is not None:
                        self._failed.update(step=state.label, item=_item(parent))
                    else:
                        self._failed["stage"] = state.label
            log_event(logger, "stage failed" if failed else "stage finished", **fields)
            if not failed and state.counted is not None:
                self._tell(force=True)  # its final count: a stage without one has nothing new to say
        except Exception:
            logger.exception("progress not reported", extra={"fields": {"stage": state.key}})

    def _finish(self, outcome: Outcome) -> None:
        try:
            with self._lock:
                self._active = False
                self._ended = self._clock()
                self._outcome = outcome
            self._tell(force=True)
        except Exception:
            logger.exception("progress not reported")

    def _count(self, state: _State, total: int) -> None:
        self._update(state, lambda now: _start_count(state, total, now), force=False)

    def _advance(self, state: _State, items: int) -> None:
        past = self._update(state, lambda now: _advance(state, items, now), force=False)
        if past:
            log_event(logger, "advance past the total", logging.WARNING, stage=state.key, total=state.total)

    def _note(self, state: _State, text: str | None) -> None:
        # Throttled like a count: a summary can report often. A new item is what forces a line.
        self._update(state, lambda now: setattr(state, "note", text), force=False)

    def _item(self, state: _State, item_id: str, note: str | None) -> None:
        def mark(now: float) -> None:
            state.item_id, state.note = item_id, note
            if self._step is not None and state is self._top:
                self._step = None

        self._update(state, mark, force=True)

    def _update(self, state: _State, change: Callable[[float], Any], force: bool) -> Any:
        try:
            with self._lock:
                if not self._active:
                    return None
                result = change(self._clock())
            self._tell(force=force)
            return result
        except Exception:
            logger.exception("progress not reported", extra={"fields": {"stage": state.key}})
            return None

    def _tell(self, force: bool) -> None:
        """Give the sink the current view: always when forced, otherwise at most once an interval."""
        if self._sink is None:
            return
        with self._lock:
            now = self._clock()
            if not force and now - self._last_sink < self._interval:
                return
            self._last_sink = now
            view = self._view(now)
        try:
            self._sink(view)
        except Exception as exc:
            log_event(logger, "progress sink dropped", logging.WARNING, error=str(exc))
            self._sink = None


def _item(state: _State) -> str | None:
    if state.item_id is None:
        return None
    return f"{state.item_id}, {state.note}" if state.note else state.item_id


def _start_count(state: _State, total: int, now: float) -> None:
    state.done, state.total = 0, total
    state.counted = (0, total)
    state.last_advance = now


def _advance(state: _State, items: int, now: float) -> bool:
    """Count items as done, holding the count at its total. True when it would have passed it."""
    if state.done is None or state.total is None or state.counted is None:
        return False
    done = state.done + items
    past = done > state.total
    state.done = min(done, state.total)
    state.counted = (state.done, state.counted[1])
    if items > 0:
        state.paces.append(((now - state.last_advance) / items, items))
    state.last_advance = now
    first_warning = past and not state.warned_past_total
    state.warned_past_total = state.warned_past_total or past
    return first_warning
