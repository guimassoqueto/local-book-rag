import json
from pathlib import Path

import pytest
import yaml

from app.config.settings import EnvironmentSettings, JudgeConfig
from app.container import Container
from app.errors import ConfigurationError, ServiceUnavailableError
from app.evaluation import benchmark
from app.evaluation.benchmark import (
    BenchmarkRunner,
    Experiment,
    VariantConfig,
    apply_overrides,
    index_key,
    load_experiment,
    summarize,
)
from app.evaluation.dataset import CATEGORY_COUNTS, load_dataset
from app.evaluation.generation_metrics import JudgeScores
from app.evaluation.performance import PerformanceResult
from app.generation.base import GenerationParameters
from app.generation.question_answering import QuestionAnsweringService
from app.ingestion.chunker import Chunker
from app.services.health_service import HealthService
from app.storage.catalog import BookStatus
from app.utils.hashing import file_checksum
from tests.fakes import FakeEmbedder, FakeLLM, FakeRuntime, WordCounter
from tests.library import MARKDOWN, Library

PROJECT = Path(__file__).resolve().parents[2]
EXPERIMENTS = sorted((PROJECT / "benchmarks" / "experiments").glob("*.yaml"))


def test_there_are_experiments_for_everything_the_spec_compares():
    assert {load_experiment(path).kind for path in EXPERIMENTS} == {
        "extraction",
        "retrieval",
        "generation",
        "summarization",
        "performance",
    }


@pytest.mark.parametrize("path", EXPERIMENTS, ids=lambda path: path.stem)
def test_every_variant_is_a_valid_configuration(settings, path):
    experiment = load_experiment(path)

    for variant in experiment.variants:
        apply_overrides(settings, variant.overrides)


def test_the_retrieval_experiment_covers_the_specs_comparisons(settings):
    experiment = load_experiment(PROJECT / "benchmarks" / "experiments" / "retrieval.yaml")

    strategies = {
        variant.name: apply_overrides(settings, variant.overrides).retrieval.strategy for variant in experiment.variants
    }
    assert strategies["qwen3_dense"] == strategies["bge_m3_dense"] == "dense"
    assert strategies["bm25"] == "bm25"
    sizes = {apply_overrides(settings, v.overrides).chunking.target_size for v in experiment.variants}
    assert sizes == {300, 500, 800}


def test_the_generation_experiment_compares_the_four_candidates(settings):
    experiment = load_experiment(PROJECT / "benchmarks" / "experiments" / "generation.yaml")

    models = {apply_overrides(settings, variant.overrides).llm.model for variant in experiment.variants}

    assert models == {"gpt-oss:20b", "gemma4:12b", "qwen3.5:9b", "qwen3:14b"}


def test_overrides_merge_into_the_configuration(settings):
    changed = apply_overrides(settings, {"retrieval": {"strategy": "bm25"}})

    assert changed.retrieval.strategy == "bm25"
    assert changed.retrieval.dense.top_k == settings.retrieval.dense.top_k
    assert settings.retrieval.strategy == "hybrid"


def test_an_override_with_a_typo_fails(settings):
    with pytest.raises(ValueError, match="stratgy"):
        apply_overrides(settings, {"retrieval": {"stratgy": "bm25"}})


def test_a_malformed_experiment_is_reported(tmp_path):
    path = tmp_path / "broken.yaml"
    path.write_text("name: broken\nkind: nonsense\n", encoding="utf-8")

    with pytest.raises(ConfigurationError):
        load_experiment(path)


def test_variants_that_index_the_same_way_share_a_workspace(settings):
    llm_only = apply_overrides(settings, {"llm": {"model": "gemma4:12b"}})
    retrieval_only = apply_overrides(settings, {"retrieval": {"strategy": "bm25"}})

    assert index_key(settings) == index_key(llm_only) == index_key(retrieval_only)


def test_variants_that_index_differently_dont(settings):
    assert index_key(settings) != index_key(apply_overrides(settings, {"chunking": {"target_size": 300}}))
    assert index_key(settings) != index_key(apply_overrides(settings, {"embedding": {"model": "bge-m3"}}))


def test_metrics_are_averaged_per_variant():
    rows = [
        {"variant": "a", "category": "x", "score": 1.0},
        {"variant": "a", "category": "y", "score": 0.0},
        {"variant": "b", "category": "x", "score": 0.5},
    ]

    assert summarize(rows, ["score"]) == [
        {"variant": "a", "samples": 2, "score": 0.5, "score_samples": 2},
        {"variant": "b", "samples": 1, "score": 0.5, "score_samples": 1},
    ]


def test_missing_values_are_left_out_and_counted():
    rows = [{"variant": "a", "score": 1.0}, {"variant": "a", "score": None}, {"variant": "a"}]

    [entry] = summarize(rows, ["score"])

    assert entry["score"] == 1.0
    assert entry["score_samples"] == 1
    assert entry["samples"] == 3


def test_failures_are_reported():
    [entry] = summarize([{"variant": "a", "failed": True}, {"variant": "a", "failed": False}], [])

    assert entry["failed"] == 1


def test_results_can_be_split_by_a_field():
    rows = [{"variant": "a", "category": "x", "score": 1.0}, {"variant": "a", "category": "y", "score": 0.0}]

    assert {entry["category"]: entry["score"] for entry in summarize(rows, ["score"], "category")} == {
        "x": 1.0,
        "y": 0.0,
    }


def test_the_real_dataset_is_loadable_and_complete():
    dataset = load_dataset(PROJECT / "benchmarks" / "datasets")

    assert len(dataset.books) == 3
    assert len(dataset.questions) == 3 * sum(CATEGORY_COUNTS.values())
    assert len(dataset.key_points) >= 3


def test_a_quick_pass_takes_the_same_share_of_each_category(settings, tmp_path):
    runner = BenchmarkRunner(settings, EnvironmentSettings(benchmarks_dir=PROJECT / "benchmarks"), say=lambda m: None)

    selected = runner._questions(limit=1)

    assert len(selected) == 3 * len(CATEGORY_COUNTS)
    assert len(runner._questions(limit=None)) == 90


@pytest.fixture
def lab(settings, tmp_path, monkeypatch):
    """A one-book benchmark over an embedded library, so that a run needs no servers."""
    root = tmp_path / "benchmarks"
    (root / "datasets").mkdir(parents=True)
    (root / "books").mkdir()
    (root / "books" / "a.md").write_text(MARKDOWN, encoding="utf-8")
    book = {
        "key": "a_book",
        "role": "English book",
        "title": "A Book",
        "author": "Someone",
        "language": "en",
        "filename": "a.md",
        "url": "https://example.test/a.md",
        "sha256": file_checksum(root / "books" / "a.md"),
        "license": "Public domain",
    }
    question = {
        "id": "q1",
        "book": "a_book",
        "category": "factual",
        "question": "What jumps over the dog?",
        "expected_answer": "A fox.",
        "chapter": None,
        "evidence": ["quick brown fox"],
        "answerable": True,
        "language": "en",
    }
    (root / "datasets" / "books.yaml").write_text(yaml.safe_dump({"books": [book]}), encoding="utf-8")
    (root / "datasets" / "questions.jsonl").write_text(json.dumps(question) + "\n", encoding="utf-8")
    points = {"book": "a_book", "chapter": "One", "key_points": ["A fox jumps."]}
    (root / "datasets" / "chapter_key_points.jsonl").write_text(json.dumps(points) + "\n", encoding="utf-8")

    embedder = FakeEmbedder()
    libraries = {}

    def assemble(variant_settings, environment, collection_prefix="book_chunks_v"):
        key = str(environment.data_dir)
        library = libraries.setdefault(key, Library(variant_settings, environment.data_dir, embedder))
        return Container(
            settings=variant_settings,
            environment=environment,
            runtime=library.runtime,
            health=HealthService(variant_settings, library.runtime, library.server, library.indexes),
            indexes=library.indexes,
            books=library.books,
            library=library.library,
            resets=library.resets,
            retrieval=library.retrieval,
            questions=QuestionAnsweringService(variant_settings, library.retrieval, library.llm),
            summaries=library.summarizer,
        )

    monkeypatch.setattr(benchmark, "assemble", assemble)
    monkeypatch.setattr(benchmark, "OllamaRuntime", lambda url, timeout: FakeRuntime())
    data = tmp_path / "real_library"
    environment = EnvironmentSettings(benchmarks_dir=root, data_dir=data)
    runner = BenchmarkRunner(settings, environment, say=lambda message: None)
    return runner, embedder, libraries, data


def retrieval_experiment():
    off = {"retrieval": {"strategy": "bm25", "reranker": {"enabled": False}}}
    return Experiment(
        name="test", kind="retrieval", description="A test.", variants=(VariantConfig(name="bm25", overrides=off),)
    )


def test_a_run_writes_machine_readable_results(lab):
    runner, *_ = lab

    directory = runner.run(retrieval_experiment())

    assert sorted(path.name for path in directory.iterdir()) == [
        "results.json",
        "rows.csv",
        "rows.jsonl",
        "summary.csv",
    ]
    report = json.loads((directory / "results.json").read_text(encoding="utf-8"))
    assert report["complete"] is True
    assert report["summary"][0]["recall_at_5"] == 1.0
    assert report["rows"][0]["relevant_chapters"]
    assert report["environment"]["dataset_sha256"]
    assert report["environment"]["configuration"]["chunking"]


def test_a_benchmark_never_touches_the_real_library(lab):
    runner, _, _, data = lab

    runner.run(retrieval_experiment())

    assert not data.exists()


def test_a_book_left_failed_in_a_workspace_is_indexed_again(lab):
    runner, embedder, libraries, _ = lab
    embedder.failure = ServiceUnavailableError("Ollama is down")
    with pytest.raises(ServiceUnavailableError):
        runner.run(retrieval_experiment())
    [library] = libraries.values()
    assert library.books.list_books()[0].status is BookStatus.FAILED

    embedder.failure = None
    directory = runner.run(retrieval_experiment())

    assert json.loads((directory / "results.json").read_text(encoding="utf-8"))["summary"][0]["samples"] == 1


def test_rows_reach_the_disk_before_a_run_fails(lab, monkeypatch):
    runner, *_ = lab
    two_variants = retrieval_experiment().model_copy(
        update={"variants": (*retrieval_experiment().variants, VariantConfig(name="broken", overrides={}))}
    )
    real_open = runner._open

    def fail_on_the_second(settings):
        if settings.retrieval.strategy != "bm25":
            raise ServiceUnavailableError("Ollama is down")
        return real_open(settings)

    monkeypatch.setattr(runner, "_open", fail_on_the_second)

    with pytest.raises(ServiceUnavailableError):
        runner.run(two_variants)

    [directory] = (runner._root / "results").iterdir()
    assert json.loads((directory / "rows.jsonl").read_text(encoding="utf-8"))["variant"] == "bm25"


def test_the_environment_is_read_before_the_work_starts(lab, monkeypatch):
    runner, *_ = lab

    def unavailable(url, timeout):
        raise ServiceUnavailableError("Ollama is down")

    monkeypatch.setattr(benchmark, "OllamaRuntime", unavailable)

    with pytest.raises(ServiceUnavailableError):
        runner.run(retrieval_experiment())

    assert not (runner._root / "results").exists()


JUDGE = JudgeConfig(model="gpt-oss:20b", embedding_model="qwen3-embedding:0.6b", max_tokens=6000, reasoning="high")


class FakeJudge:
    def __init__(self, llm, parameters, config, ollama_base_url, timeout):
        self.parameters = parameters

    def score(self, question, answer, contexts, reference):
        return JudgeScores(faithfulness=1.0, answer_correctness=0.5, answer_relevance=None)


def experiment_of(kind, **fields):
    variant = VariantConfig(name="candidate", overrides={"llm": {"model": "gemma4:12b"}})
    return Experiment(name="test", kind=kind, description="A test.", variants=(variant,), **fields)


def report_of(directory):
    return json.loads((directory / "results.json").read_text(encoding="utf-8"))


@pytest.fixture
def models(monkeypatch):
    """Every model the runner asks for, by the settings it asked with."""
    created = {}

    def create(settings, runtime):
        return created.setdefault(settings.llm.model, (settings, FakeLLM(["{}"])))[1]

    monkeypatch.setattr(benchmark, "create_llm_provider", create)
    monkeypatch.setattr(benchmark, "RagasJudge", FakeJudge)
    return created


def test_a_generation_run_reports_every_answer(lab, models):
    runner, *_ = lab

    directory = runner.run(experiment_of("generation", judge=JUDGE))

    report = report_of(directory)
    [row] = report["rows"]
    assert row["question"] == "q1"
    assert row["answer"] == "{}"
    assert row["model"] == "gemma4:12b"
    assert report["summary"][0]["samples"] == 1
    assert report["summary"][0]["faithfulness"] == 1.0
    assert report["summary"][0]["answer_relevance_samples"] == 0
    assert row["evidence_in_context"] == 1.0
    assert json.loads((directory / "rows.jsonl").read_text(encoding="utf-8"))["question"] == "q1"


def test_an_abstention_records_whether_the_evidence_reached_the_model(lab, models):
    runner, *_ = lab
    models["gemma4:12b"] = (None, FakeLLM(["[NO-EVIDENCE] The passages don't say."]))

    [row] = report_of(runner.run(experiment_of("generation", judge=JUDGE)))["rows"]

    assert row["abstained"] is True
    assert row["abstention_quality"] == 0.0
    assert row["evidence_in_context"] == 1.0
    assert "faithfulness" not in row


def test_candidates_answer_at_their_own_settings(lab, models):
    runner, *_ = lab

    runner.run(experiment_of("generation", judge=JUDGE))

    settings, llm = models["gemma4:12b"]
    assert settings.llm.context_size == runner._settings.llm.context_size
    assert llm.calls[0][1].max_tokens == runner._settings.generation.question_answering.max_tokens


def test_the_judge_reads_at_the_widest_window_with_its_own_reasoning(lab, models):
    runner, *_ = lab

    runner.run(experiment_of("generation", judge=JUDGE))

    settings, _ = models[JUDGE.model]
    assert settings.llm.context_size == runner._settings.generation.context.max_size
    assert settings.llm_profiles[JUDGE.model].reasoning == "high"
    assert runner._settings.llm_profiles[JUDGE.model].reasoning != "high"


def test_a_summarization_run_reports_every_chapter(lab, models):
    runner, *_ = lab
    verdict = {"covered": True, "concept_preservation": 5, "factual_consistency": 4, "coherence": 3, "completeness": 2}
    models[JUDGE.model] = (None, FakeLLM([json.dumps(verdict)]))

    directory = runner.run(experiment_of("summarization", judge=JUDGE))

    report = report_of(directory)
    [row] = report["rows"]
    assert row["chapter"] == "One"
    assert row["summary"]
    assert row["argument_coverage"] == 1.0
    assert report["summary"][0]["concept_preservation"] == 1.0
    assert report["summary"][0]["completeness"] == 0.25
    assert models[JUDGE.model][1].calls[0][1] == GenerationParameters(0.0, JUDGE.max_tokens, 0)


def test_the_performance_summary_holds_its_metrics(lab, models, monkeypatch):
    runner, *_ = lab
    measured = PerformanceResult("gemma4:12b", 8192, 3, 2.0, 0.5, 2000.0, 100.0, 3.0, 500, 9000, 8000, 12000, 1.0)
    monkeypatch.setattr(benchmark, "measure", lambda *args, **kwargs: measured)

    directory = runner.run(experiment_of("performance", prompt_book="a_book"))

    [entry] = report_of(directory)["summary"]
    assert entry["peak_vram_mb"] == 9000
    assert entry["generation_tokens_per_second"] == 100.0
    assert "peak_vram_mb" in (directory / "summary.csv").read_text(encoding="utf-8").splitlines()[0]


def test_the_extraction_summary_holds_its_metrics(lab, monkeypatch):
    runner, *_ = lab
    real_build = benchmark.build_pipeline

    def build(settings):
        pipeline = real_build(settings)
        pipeline._chunker = Chunker(settings.chunking, WordCounter())
        return pipeline

    monkeypatch.setattr(benchmark, "build_pipeline", build)

    directory = runner.run(experiment_of("extraction"))

    [entry] = report_of(directory)["summary"]
    assert entry["chapters"] == 2
    assert entry["chunks"] >= 2
    assert entry["toc_coverage_samples"] == 0
