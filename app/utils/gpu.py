"""GPU inspection through nvidia-smi, which works without loading torch."""

import subprocess
from dataclasses import dataclass


@dataclass(frozen=True)
class GpuStatus:
    name: str
    memory_used_mb: int
    memory_total_mb: int


def query_gpu() -> GpuStatus | None:
    """Return the first GPU's state, or None where no GPU is visible."""
    command = ["nvidia-smi", "--query-gpu=name,memory.used,memory.total", "--format=csv,noheader,nounits"]
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=10, check=True)
        name, used, total = result.stdout.splitlines()[0].rsplit(", ", 2)
        return GpuStatus(name=name, memory_used_mb=int(used), memory_total_mb=int(total))
    except (OSError, subprocess.SubprocessError, ValueError, IndexError):
        return None
