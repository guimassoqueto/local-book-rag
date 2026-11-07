"""Checks that the deployment can do its work, reported instead of raised."""

from collections.abc import Callable
from dataclasses import dataclass

from app.config.settings import Settings
from app.errors import BookRagError
from app.services.index_service import IndexService
from app.storage.chroma import ChromaServer
from app.utils.gpu import GpuStatus, query_gpu
from app.utils.ollama_runtime import ModelInfo, OllamaRuntime

_PROBE_PROMPT = "Reply with the single word: ready"


@dataclass(frozen=True)
class CheckResult:
    name: str
    ok: bool
    detail: str


class HealthService:
    def __init__(
        self,
        settings: Settings,
        runtime: OllamaRuntime,
        chroma: ChromaServer,
        indexes: IndexService,
        gpu_probe: Callable[[], GpuStatus | None] = query_gpu,
    ) -> None:
        self._settings = settings
        self._runtime = runtime
        self._chroma = chroma
        self._indexes = indexes
        self._gpu_probe = gpu_probe

    def run(self, inference: bool = False) -> list[CheckResult]:
        """Run every check, without stopping at the first failure.

        Args:
            inference: also run both models for real, which loads them into memory.
        """
        checks = [self._ollama, self._chromadb, self._llm_model, self._embedding_model, self._gpu, self._index]
        if inference:
            checks += [self._embedding_inference, self._llm_inference]
        return [self._guarded(check) for check in checks]

    def _guarded(self, check: Callable[[], CheckResult]) -> CheckResult:
        try:
            return check()
        except BookRagError as exc:
            return CheckResult(check.__name__.strip("_").replace("_", " "), False, str(exc))

    def _ollama(self) -> CheckResult:
        return CheckResult("ollama", True, f"version {self._runtime.version()} at {self._runtime.base_url}")

    def _chromadb(self) -> CheckResult:
        return CheckResult("chromadb", True, f"version {self._chroma.version()} at {self._chroma.address}")

    def _llm_model(self) -> CheckResult:
        llm = self._settings.llm
        info = self._runtime.model_info(llm.model)
        if llm.reasoning is not None and "thinking" not in info.capabilities:
            return CheckResult("llm model", False, f"{llm.model} has no reasoning mode, but llm.reasoning is set")
        if info.context_length and llm.context_size > info.context_length:
            detail = f"llm.context_size {llm.context_size} exceeds the {info.context_length} of {llm.model}"
            return CheckResult("llm model", False, detail)
        return CheckResult("llm model", True, _describe(info))

    def _embedding_model(self) -> CheckResult:
        embedding = self._settings.embedding
        info = self._runtime.model_info(embedding.model)
        if info.embedding_length != embedding.dimensions:
            detail = f"{embedding.model} produces {info.embedding_length} dimensions, the config says "
            return CheckResult("embedding model", False, f"{detail}{embedding.dimensions}")
        return CheckResult("embedding model", True, _describe(info))

    def _gpu(self) -> CheckResult:
        status = self._gpu_probe()
        if status is None:
            return CheckResult("gpu", False, "no GPU visible to the application: reranking and Docling stay on CPU")
        memory = f"{status.memory_used_mb}/{status.memory_total_mb} MiB used"
        return CheckResult("gpu", True, f"{status.name}, {memory}")

    def _index(self) -> CheckResult:
        active = self._indexes.active()
        if active is None:
            return CheckResult("index", True, "no index yet: the first book creates it")
        detail = f"v{active.version} in {active.collection}, built with {active.embedding_model}"
        if self._indexes.needs_reindex():
            return CheckResult("index", False, f"{detail}, which the configuration no longer matches: run reindex-all")
        return CheckResult("index", True, detail)

    def _embedding_inference(self) -> CheckResult:
        embedding = self._settings.embedding
        with self._runtime.translate_errors(embedding.model):
            result = self._runtime.client.embed(model=embedding.model, input=_PROBE_PROMPT)
        size = len(result.embeddings[0])
        return CheckResult("embedding inference", size == embedding.dimensions, f"{size}-dimensional vector")

    def _llm_inference(self) -> CheckResult:
        llm = self._settings.llm
        with self._runtime.translate_errors(llm.model):
            response = self._runtime.client.chat(
                model=llm.model,
                messages=[{"role": "user", "content": _PROBE_PROMPT}],
                think=llm.reasoning,
                options={"num_ctx": llm.context_size, "temperature": 0, "num_predict": llm.max_tokens},
            )
        answer = (response.message.content or "").strip()
        loaded = next((model for model in self._runtime.loaded_models() if model.name == llm.model), None)
        placement = f"{loaded.gpu_fraction:.0%} of {loaded.size_bytes / 1e9:.1f} GB on GPU" if loaded else "not loaded"
        return CheckResult("llm inference", bool(answer), f"answered {answer!r}, {placement}")


def _describe(info: ModelInfo) -> str:
    return f"{info.name} ({info.family}, {info.parameter_size}, {info.quantization})"
