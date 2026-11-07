"""Inference performance, measured the way the spec asks: warm-up first, then the median of runs."""

import statistics
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from app.generation.base import GenerationParameters, LLMProvider, Message
from app.utils.gpu import query_gpu
from app.utils.ollama_runtime import OllamaRuntime

_SAMPLE_SECONDS = 0.5
_SETTLE_TIMEOUT_SECONDS = 30.0
_SETTLED_MB = 64  # how far an idle GPU's memory moves on its own
_KIB_PER_MIB = 1024


@dataclass(frozen=True)
class PerformanceResult:
    model: str
    context_size: int
    runs: int
    load_seconds: float
    time_to_first_token: float
    prompt_tokens_per_second: float
    generation_tokens_per_second: float
    total_seconds: float
    idle_vram_mb: int | None
    peak_vram_mb: int | None
    idle_ram_mb: int
    peak_ram_mb: int
    gpu_fraction: float | None


def _used_ram_mb() -> int:
    fields = {}
    for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
        name, _, rest = line.partition(":")
        fields[name] = int(rest.split()[0])
    return (fields["MemTotal"] - fields["MemAvailable"]) // _KIB_PER_MIB


def _used_vram_mb() -> int | None:
    gpu = query_gpu()
    return gpu.memory_used_mb if gpu else None


def free_memory(runtime: OllamaRuntime) -> None:
    """Unload every model, and wait until the GPU has the memory back.

    A model leaves Ollama's list some 200 ms before its memory is free, and the list understates
    what it holds, so only the GPU can tell. Measuring any sooner would report the last model's
    memory as the peak of the next one.
    """
    models = runtime.loaded_models()
    held = _used_vram_mb()
    for model in models:
        runtime.unload(model.name)
    on_gpu = held is not None and any(model.vram_bytes for model in models)

    deadline = time.monotonic() + _SETTLE_TIMEOUT_SECONDS
    previous = held if on_gpu else None
    while time.monotonic() < deadline:
        used = _used_vram_mb()
        released = not on_gpu or (used is not None and used < held - _SETTLED_MB)
        settled = used is None or (previous is not None and abs(used - previous) <= _SETTLED_MB)
        if released and settled and not runtime.loaded_models():
            return
        previous = used
        time.sleep(_SAMPLE_SECONDS)


@contextmanager
def peak_memory() -> Iterator[dict[str, int | None]]:
    """Sample GPU and system memory in the background, for the peaks of what runs inside.

    Ollama runs in another container, so nothing inside it can be read from here. Memory is
    read for the whole machine instead, which a benchmark has to itself: what a model costs is
    its peak minus the idle reading taken before it loaded.
    """
    peaks: dict[str, int | None] = {"vram": None, "ram": 0}
    stop = threading.Event()

    def sample() -> None:
        while not stop.is_set():
            gpu = query_gpu()
            if gpu is not None:
                peaks["vram"] = max(peaks["vram"] or 0, gpu.memory_used_mb)
            peaks["ram"] = max(peaks["ram"] or 0, _used_ram_mb())
            stop.wait(_SAMPLE_SECONDS)

    thread = threading.Thread(target=sample, daemon=True)
    thread.start()
    try:
        yield peaks
    finally:
        stop.set()
        thread.join()


def measure(
    llm: LLMProvider,
    runtime: OllamaRuntime,
    prompt: str,
    runs: int,
    max_tokens: int,
    say: Callable[[str], None] = lambda message: None,
) -> PerformanceResult:
    """Measure one model at its configured context size.

    Args:
        llm: the model.
        runtime: the server, to unload what is loaded and read the placement.
        prompt: what to send. Each run opens with its own number, because Ollama caches a
            repeated prompt and its processing speed would mean nothing.
        runs: measured runs, after a cold start and a warm-up.
        max_tokens: how much to generate per run.
        say: told what is happening.
    """
    parameters = GenerationParameters(temperature=0.0, max_tokens=max_tokens, seed=0)
    free_memory(runtime)
    idle_vram = _used_vram_mb()
    idle_ram = _used_ram_mb()

    with peak_memory() as peaks:
        say("cold start")
        cold = llm.generate([Message("user", f"Cold start.\n\n{prompt}")], parameters).stats
        say("warm-up")
        llm.generate([Message("user", f"Warm-up.\n\n{prompt}")], parameters)
        measured = []
        for number in range(1, runs + 1):
            say(f"run {number} of {runs}")
            measured.append(llm.generate([Message("user", f"Run {number}.\n\n{prompt}")], parameters).stats)

    loaded = next((model for model in runtime.loaded_models() if model.name == llm.model), None)
    return PerformanceResult(
        model=llm.model,
        context_size=llm.context_size(),
        runs=runs,
        load_seconds=cold.load_seconds,
        time_to_first_token=statistics.median(stats.time_to_first_token for stats in measured),
        prompt_tokens_per_second=statistics.median(
            stats.prompt_tokens / stats.prompt_seconds for stats in measured if stats.prompt_seconds
        ),
        generation_tokens_per_second=statistics.median(stats.tokens_per_second for stats in measured),
        total_seconds=statistics.median(stats.total_seconds for stats in measured),
        idle_vram_mb=idle_vram,
        peak_vram_mb=peaks["vram"],
        idle_ram_mb=idle_ram,
        peak_ram_mb=peaks["ram"] or 0,
        gpu_fraction=loaded.gpu_fraction if loaded else None,
    )
