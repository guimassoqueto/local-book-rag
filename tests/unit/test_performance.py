import pytest

from app.evaluation import performance
from app.evaluation.performance import free_memory, measure
from app.utils.gpu import GpuStatus
from app.utils.ollama_runtime import LoadedModel
from tests.fakes import FakeLLM, FakeRuntime


class FakeGpu:
    """Reports memory in steps: each reading moves on to the next one, the last one repeating."""

    def __init__(self, *readings):
        self.readings = list(readings)
        self.reads = 0

    def __call__(self):
        self.reads += 1
        used = self.readings.pop(0) if len(self.readings) > 1 else self.readings[0]
        return GpuStatus(name="gpu", memory_used_mb=used, memory_total_mb=16000)


def loaded(name="old"):
    return LoadedModel(name=name, size_bytes=100, vram_bytes=100, context_length=8192)


@pytest.fixture(autouse=True)
def no_waiting(monkeypatch):
    monkeypatch.setattr(performance.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(performance, "_used_ram_mb", lambda: 8000)


def test_memory_is_measured_only_after_the_last_model_has_released_it(monkeypatch):
    runtime = FakeRuntime()
    runtime.loaded = [loaded()]
    gpu = FakeGpu(13000, 13000, 5000, 500, 500)
    monkeypatch.setattr(performance, "query_gpu", gpu)

    free_memory(runtime)

    assert runtime.unloaded == ["old"]
    assert gpu.readings == [500]


def test_a_model_on_the_cpu_holds_no_gpu_memory_to_wait_for(monkeypatch):
    runtime = FakeRuntime()
    runtime.loaded = [LoadedModel(name="embedding", size_bytes=100, vram_bytes=0, context_length=4096)]
    gpu = FakeGpu(500)
    monkeypatch.setattr(performance, "query_gpu", gpu)

    free_memory(runtime)

    assert gpu.reads <= 3


def test_a_model_still_listed_keeps_the_wait_going(monkeypatch):
    runtime = FakeRuntime()
    answers = [[loaded()], [loaded()], []]
    runtime.loaded_models = lambda: answers.pop(0) if len(answers) > 1 else answers[0]
    runtime.unload = lambda model: None
    monkeypatch.setattr(performance, "query_gpu", FakeGpu(13000, 500))

    free_memory(runtime)

    assert answers == [[]]


def test_a_machine_without_a_gpu_only_waits_for_the_model_list(monkeypatch):
    monkeypatch.setattr(performance, "query_gpu", lambda: None)

    free_memory(FakeRuntime())


def test_memory_that_never_settles_doesnt_hang_a_run(monkeypatch):
    readings = iter(range(0, 10**9, 1000))
    monkeypatch.setattr(performance, "query_gpu", lambda: GpuStatus("gpu", next(readings), 16000))
    clock = iter(range(0, 10**6, 10))
    monkeypatch.setattr(performance.time, "monotonic", lambda: float(next(clock)))

    free_memory(FakeRuntime())


def test_the_idle_reading_comes_before_the_model_loads(monkeypatch):
    monkeypatch.setattr(performance, "query_gpu", FakeGpu(500, 500, 500, 500, 9000))

    result = measure(FakeLLM(["A reply."]), FakeRuntime(), "A prompt.", runs=1, max_tokens=10)

    assert result.idle_vram_mb == 500
    assert result.peak_vram_mb == 9000
    assert result.idle_ram_mb == 8000
