import subprocess

from app.utils import gpu


def test_parses_nvidia_smi_output(monkeypatch):
    completed = subprocess.CompletedProcess([], 0, stdout="NVIDIA GeForce RTX 5060 Ti, 587, 16311\n")
    monkeypatch.setattr(gpu.subprocess, "run", lambda *args, **kwargs: completed)

    assert gpu.query_gpu() == gpu.GpuStatus("NVIDIA GeForce RTX 5060 Ti", 587, 16311)


def test_a_missing_tool_means_no_gpu(monkeypatch):
    def run(*args, **kwargs):
        raise FileNotFoundError("nvidia-smi")

    monkeypatch.setattr(gpu.subprocess, "run", run)

    assert gpu.query_gpu() is None
