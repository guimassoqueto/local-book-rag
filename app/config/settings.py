"""Typed view of the files in config/ and of the deployment environment."""

from pathlib import Path
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, PositiveFloat, PositiveInt, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]


class ConfigModel(BaseModel):
    """Rejects unknown keys: a typo in a YAML file has to fail at startup, not be ignored."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class ApplicationConfig(ConfigModel):
    name: str


class ServerConfig(ConfigModel):
    host: str
    port: int = Field(ge=1, le=65535)


class UploadsConfig(ConfigModel):
    max_size_mb: PositiveInt


class OllamaConfig(ConfigModel):
    request_timeout_seconds: PositiveFloat


class LoggingConfig(ConfigModel):
    inference_level: LogLevel


class TokenizerConfig(ConfigModel):
    kind: Literal["tiktoken", "huggingface"]
    name: str


class LLMConfig(ConfigModel):
    provider: Literal["ollama"]
    model: str
    context_size: PositiveInt
    temperature: float = Field(ge=0)
    max_tokens: PositiveInt


class LLMProfile(ConfigModel):
    """What is specific to one LLM: its tokenizer and what it accepts as a reasoning setting."""

    tokenizer: TokenizerConfig
    reasoning: bool | Literal["low", "medium", "high"] | None = None


class EmbeddingConfig(ConfigModel):
    provider: Literal["ollama"]
    model: str
    dimensions: PositiveInt
    batch_size: PositiveInt
    document_device: Literal["cpu", "gpu"]
    query_device: Literal["cpu", "gpu"]


class RerankerModelConfig(ConfigModel):
    provider: Literal["transformers"]
    model: str
    device: Literal["cpu", "cuda"]
    batch_size: PositiveInt


class EmbeddingProfile(ConfigModel):
    """What is specific to one embedding model: its tokenizer and the prompts around its input."""

    tokenizer: TokenizerConfig
    query_template: str = "{text}"
    document_template: str = "{text}"

    @field_validator("query_template", "document_template")
    @classmethod
    def has_text_placeholder(cls, template: str) -> str:
        if "{text}" not in template:
            raise ValueError("the template needs a {text} placeholder")
        return template


class ChunkPreservation(ConfigModel):
    chapters: Literal[True]  # a chunk's metadata names one chapter
    sections: bool
    paragraphs: bool
    page_numbers: bool


class ChunkingConfig(ConfigModel):
    strategy: Literal["structural", "fixed"]
    target_size: PositiveInt
    overlap: int = Field(ge=0)
    unit: Literal["tokens"]
    preserve: ChunkPreservation


class PdfOcrConfig(ConfigModel):
    enabled: bool


class PdfConfig(ConfigModel):
    extractor: Literal["pymupdf", "docling"]
    extract_tables: bool
    ocr: PdfOcrConfig


class NormalizationConfig(ConfigModel):
    remove_repeated_margins: bool


class LanguagesConfig(ConfigModel):
    supported: tuple[str, ...]


class DenseConfig(ConfigModel):
    top_k: PositiveInt


class BM25Config(ConfigModel):
    top_k: PositiveInt
    k1: PositiveFloat
    b: float = Field(ge=0, le=1)
    stemming: bool
    # Portuguese books: old spellings (Sophia, elle, facto) match modern ones (Sofia, ele, fato).
    historical_spelling: bool

    @model_validator(mode="after")
    def check_historical_spelling(self) -> Self:
        # The words kept apart from the patterns were found among stemmed keys, and would
        # protect nothing without stemming.
        if self.historical_spelling and not self.stemming:
            raise ValueError("bm25.historical_spelling needs bm25.stemming")
        return self


class FusionConfig(ConfigModel):
    method: Literal["rrf", "weighted"]
    rrf_k: PositiveInt
    dense_weight: float = Field(ge=0, le=1)


class RerankingConfig(ConfigModel):
    enabled: bool
    top_k: PositiveInt


class RetrievalConfig(ConfigModel):
    strategy: Literal["dense", "bm25", "hybrid"]
    dense: DenseConfig
    bm25: BM25Config
    fusion: FusionConfig
    reranker: RerankingConfig


class GenerationTaskConfig(ConfigModel):
    """Overrides llm.temperature and llm.max_tokens for one kind of work."""

    temperature: float | None = Field(default=None, ge=0)
    max_tokens: PositiveInt | None = None


class SummaryTypeConfig(ConfigModel):
    target_words: PositiveInt
    style: str
    max_tokens: PositiveInt | None = None


class SummarizationConfig(GenerationTaskConfig):
    map_max_tokens: PositiveInt
    min_source_score: float = Field(ge=0, le=1)
    verify_claims: bool
    types: dict[str, SummaryTypeConfig]


class ContextConfig(ConfigModel):
    max_size: PositiveInt
    safety_margin: float = Field(ge=0, lt=1)


class GenerationConfig(ConfigModel):
    question_answering: GenerationTaskConfig
    summarization: SummarizationConfig
    context: ContextConfig
    response_languages: tuple[str, ...]


class JudgeConfig(ConfigModel):
    """The model that scores answers in benchmarks. The same one judges every candidate.

    Attributes:
        model: the model. Needs an entry in llm_profiles.
        embedding_model: for the RAGAS metrics that compare by similarity.
        max_tokens: its limit for a reply, reasoning included.
        reasoning: replaces its profile's setting. A judge should read before it rates.
    """

    model: str
    embedding_model: str
    max_tokens: PositiveInt
    reasoning: Literal["low", "medium", "high"] | None = None


class Settings(ConfigModel):
    """Everything in config/, merged: each top-level key lives in exactly one file."""

    application: ApplicationConfig
    server: ServerConfig
    uploads: UploadsConfig
    ollama: OllamaConfig
    logging: LoggingConfig
    llm: LLMConfig
    embedding: EmbeddingConfig
    reranker: RerankerModelConfig
    embedding_profiles: dict[str, EmbeddingProfile]
    llm_profiles: dict[str, LLMProfile]
    pdf: PdfConfig
    normalization: NormalizationConfig
    languages: LanguagesConfig
    chunking: ChunkingConfig
    retrieval: RetrievalConfig
    generation: GenerationConfig

    @model_validator(mode="after")
    def check_rules_across_files(self) -> Self:
        if self.embedding.model not in self.embedding_profiles:
            raise ValueError(f"embedding_profiles has no entry for embedding.model '{self.embedding.model}'")
        if self.llm.model not in self.llm_profiles:
            raise ValueError(f"llm_profiles has no entry for llm.model '{self.llm.model}'")
        if self.chunking.overlap >= self.chunking.target_size:
            raise ValueError("chunking.overlap must be smaller than chunking.target_size")
        if self.llm.context_size > self.generation.context.max_size:
            raise ValueError("llm.context_size exceeds generation.context.max_size")
        for task in (self.generation.question_answering, self.generation.summarization):
            if (task.max_tokens or self.llm.max_tokens) >= self.llm.context_size:
                raise ValueError("max_tokens leaves no room for the prompt in llm.context_size")
        return self

    @property
    def embedding_profile(self) -> EmbeddingProfile:
        return self.embedding_profiles[self.embedding.model]

    @property
    def llm_profile(self) -> LLMProfile:
        return self.llm_profiles[self.llm.model]


class EnvironmentSettings(BaseSettings):
    """Where this deployment finds its services and directories.

    The defaults are the Compose service names: nothing depends on localhost.
    """

    model_config = SettingsConfigDict(extra="ignore", frozen=True)

    ollama_base_url: str = "http://ollama:11434"
    chroma_host: str = "chromadb"
    chroma_port: int = 8000
    config_dir: Path = Path("config")
    data_dir: Path = Path("data")
    logs_dir: Path = Path("logs")
    benchmarks_dir: Path = Path("benchmarks")
    log_level: LogLevel = "INFO"
