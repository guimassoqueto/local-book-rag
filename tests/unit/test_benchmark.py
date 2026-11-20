import csv
import json
import re
from collections import Counter
from dataclasses import replace

import pytest
import yaml
from pydantic import ValidationError

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
from app.evaluation.dataset import CATEGORY_COUNTS, relevant_chunks
from app.evaluation.generation_metrics import JudgeScores
from app.evaluation.performance import PerformanceResult
from app.evaluation.retrieval_metrics import (
    context_precision,
    context_recall,
    ndcg_at_k,
    recall_at_k,
    reciprocal_rank,
)
from app.generation.base import GenerationParameters
from app.generation.question_answering import QuestionAnsweringService
from app.services.health_service import HealthService
from app.services.reset_service import CONFIRM_RESET_EVERYTHING, ResetService
from app.services.retrieval_service import RetrievalService
from app.storage.catalog import BookStatus
from app.utils.hashing import file_checksum
from tests.fakes import FakeEmbedder, FakeLLM, FakeRuntime
from tests.library import MARKDOWN, Library


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


def test_two_variants_with_the_same_name_are_refused():
    variants = (VariantConfig(name="same"), VariantConfig(name="same"))

    with pytest.raises(ValueError, match="variant names"):
        Experiment(name="test", kind="retrieval", description="A test.", variants=variants)


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


def _question(book, category, number):
    answerable = category != "unanswerable"
    return {
        "id": f"{book}_{category}_{number:02d}",
        "book": book,
        "category": category,
        "question": "What jumps over the dog?",
        "expected_answer": "A fox." if answerable else None,
        "chapter": "One" if category == "chapter_specific" else None,
        "evidence": ["quick brown fox"] if answerable else [],
        "answerable": answerable,
        "language": "en",
    }


def test_a_quick_pass_takes_the_same_share_of_each_category(settings, tmp_path):
    datasets = tmp_path / "benchmarks" / "datasets"
    datasets.mkdir(parents=True)
    books = ("a_book", "b_book")
    questions = [_question(book, category, n) for book in books for category in CATEGORY_COUNTS for n in range(3)]
    (datasets / "books.yaml").write_text(yaml.safe_dump({"books": []}), encoding="utf-8")
    (datasets / "questions.jsonl").write_text("".join(json.dumps(q) + "\n" for q in questions), encoding="utf-8")
    (datasets / "chapter_key_points.jsonl").write_text("", encoding="utf-8")
    runner = BenchmarkRunner(settings, EnvironmentSettings(benchmarks_dir=tmp_path / "benchmarks"), say=lambda m: None)

    shares = Counter((question.book, question.category) for question in runner._questions(limit=1))

    assert shares == {(book, category): 1 for book in books for category in CATEGORY_COUNTS}
    assert len(runner._questions(limit=None)) == len(questions)


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
        "sha256": file_checksum(root / "books" / "a.md"),
        "original": {"url": "https://example.test/a.pdf", "sha256": "1" * 64},
        "conversion": "MarkItDown 0.1.9 (ed17895)",
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
    assert "relevant_pages" not in report["rows"][0]
    assert report["environment"]["dataset_sha256"]
    assert report["environment"]["configuration"]["chunking"]


def the_row_in_each_file(directory):
    """A one-row run's row, as rows.jsonl, results.json and rows.csv each hold it."""
    [written] = [json.loads(line) for line in (directory / "rows.jsonl").read_text(encoding="utf-8").splitlines()]
    [reported] = report_of(directory)["rows"]
    with (directory / "rows.csv").open(encoding="utf-8", newline="") as file:
        [tabled] = list(csv.DictReader(file))
    return written, reported, tabled


def test_a_retrieval_row_records_its_ranking_and_its_context_in_the_three_files(lab):
    runner, *_ = lab

    directory = runner.run(retrieval_experiment())

    written, reported, tabled = the_row_in_each_file(directory)
    assert written == reported
    for key in ("ranking", "context"):
        assert written[key]
        assert all(isinstance(chunk_id, str) for chunk_id in written[key])
        assert tabled[key] == "; ".join(written[key])  # one cell, as relevant_chunks is
    assert list(written)[-3:] == ["rerank_seconds", "ranking", "context"]
    assert list(tabled)[-2:] == ["ranking", "context"]
    header = (directory / "summary.csv").read_text(encoding="utf-8").splitlines()[0].split(",")
    assert "ranking" not in header and "context" not in header


def test_a_rows_scores_are_computed_from_the_lists_it_records(lab, settings):
    runner, *_ = lab
    [variant] = retrieval_experiment().variants

    [row] = report_of(runner.run(retrieval_experiment()))["rows"]

    workspace = runner._open(apply_overrides(settings, variant.overrides))
    [question] = runner._dataset.questions
    evidence = relevant_chunks(question, workspace.chunks[question.book])
    assert row["recall_at_5"] == recall_at_k(row["ranking"], evidence, 5)
    assert row["recall_at_10"] == recall_at_k(row["ranking"], evidence, 10)
    assert row["mrr"] == reciprocal_rank(row["ranking"], evidence)
    assert row["ndcg_at_10"] == ndcg_at_k(row["ranking"], evidence, 10)
    assert row["context_precision"] == context_precision(row["context"], evidence)
    assert row["context_recall"] == context_recall(row["context"], evidence)


def test_a_row_records_the_lists_as_the_search_returned_them(lab, monkeypatch):
    runner, *_ = lab
    real_search = RetrievalService.search
    returned = []

    def reordered(service, query, filters, config=None):
        """As a reranker would: another order, and a passage without the evidence first."""
        result = real_search(service, query, filters, config)
        first = result.candidates[0]
        stranger = replace(first, chunk=replace(first.chunk, chunk_id="book_001_chapter_09_chunk_0099", text="No."))
        candidates = (stranger, *reversed(result.candidates))
        returned.append(replace(result, candidates=candidates, passages=candidates[1:3]))
        return returned[-1]

    monkeypatch.setattr(RetrievalService, "search", reordered)

    [row] = report_of(runner.run(retrieval_experiment()))["rows"]

    [result] = returned
    assert row["ranking"] == [passage.chunk.chunk_id for passage in result.candidates]
    assert row["context"] == [passage.chunk.chunk_id for passage in result.passages]
    assert row["ranking"][0] == "book_001_chapter_09_chunk_0099"
    assert row["mrr"] == 0.5  # read from the order recorded: the evidence comes second


@pytest.mark.parametrize("reranking", [False, True], ids=["reranking off", "reranking on"])
def test_the_context_is_the_rankings_first_passages(lab, reranking):
    runner, *_ = lab
    overrides = {"retrieval": {"strategy": "bm25", "reranker": {"enabled": reranking, "top_k": 1}}}
    variant = VariantConfig(name="bm25", overrides=overrides)
    experiment = Experiment(name="test", kind="retrieval", description="A test.", variants=(variant,))

    [row] = report_of(runner.run(experiment))["rows"]

    assert len(row["ranking"]) == 3  # the book's three chunks, all found
    assert row["context"] == row["ranking"][:1]


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


def test_a_workspace_whose_index_went_stale_is_rebuilt(lab):
    runner, _, libraries, _ = lab
    runner.run(retrieval_experiment())
    [library] = libraries.values()
    library.runtime.digest = "digest-2"  # the embedding model, pulled again

    runner.run(retrieval_experiment())

    assert library.catalog.active_index().embedding_digest == "digest-2"


def test_only_a_new_workspace_clears_what_a_deleted_one_left_on_the_server(lab, monkeypatch):
    runner, *_ = lab
    confirmations = []
    real_reset = ResetService.reset_everything

    def reset(service, confirmation):
        confirmations.append(confirmation)
        real_reset(service, confirmation)

    monkeypatch.setattr(ResetService, "reset_everything", reset)

    runner.run(retrieval_experiment())
    runner.run(retrieval_experiment())

    assert confirmations == [CONFIRM_RESET_EVERYTHING]


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
    row = json.loads((directory / "rows.jsonl").read_text(encoding="utf-8"))
    assert row["variant"] == "bm25"
    assert row["ranking"] and row["context"]


def test_a_package_left_out_with_its_extra_is_recorded_as_missing(lab, monkeypatch):
    runner, *_ = lab
    real_version = benchmark.metadata.version

    def version(name):
        if name == "ragas":
            raise benchmark.metadata.PackageNotFoundError(name)
        return real_version(name)

    monkeypatch.setattr(benchmark.metadata, "version", version)

    report = json.loads((runner.run(retrieval_experiment()) / "results.json").read_text(encoding="utf-8"))

    assert report["environment"]["packages"]["ragas"] is None


def test_the_environment_is_read_before_the_work_starts(lab, monkeypatch):
    runner, *_ = lab

    def unavailable(url, timeout):
        raise ServiceUnavailableError("Ollama is down")

    monkeypatch.setattr(benchmark, "OllamaRuntime", unavailable)

    with pytest.raises(ServiceUnavailableError):
        runner.run(retrieval_experiment())

    assert not (runner._root / "results").exists()


def test_the_environment_records_the_commit_and_the_books_checksums(lab):
    runner, *_ = lab

    directory = runner.run(retrieval_experiment(), commit="abc1234")

    environment = json.loads((directory / "results.json").read_text(encoding="utf-8"))["environment"]
    assert environment["commit"] == "abc1234"
    assert environment["book_sha256"] == {"a_book": file_checksum(runner._root / "books" / "a.md")}


def test_an_experiment_file_is_read_and_validated(tmp_path):
    fields = {"name": "r", "kind": "retrieval", "description": "d", "variants": [{"name": "v"}]}
    (tmp_path / "retrieval.yaml").write_text(yaml.safe_dump(fields), encoding="utf-8")

    assert load_experiment(tmp_path / "retrieval.yaml") == Experiment.model_validate(fields)


def test_an_unknown_key_in_an_experiment_is_refused():
    with pytest.raises(ValueError, match="seeds"):
        Experiment.model_validate(
            {"name": "r", "kind": "retrieval", "description": "d", "variants": [{"name": "v"}], "seeds": 3}
        )


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
    assert "ranking" not in row and "context" not in row  # its search records nothing new
    assert json.loads((directory / "rows.jsonl").read_text(encoding="utf-8"))["question"] == "q1"


def test_an_abstention_records_whether_the_evidence_reached_the_model(lab, models):
    runner, *_ = lab
    models["gemma4:12b"] = (None, FakeLLM(["[NO-EVIDENCE] The passages don't say."]))

    [row] = report_of(runner.run(experiment_of("generation", judge=JUDGE)))["rows"]

    assert row["abstained"] is True
    assert row["abstention_quality"] == 0.0
    assert row["evidence_in_context"] == 1.0
    assert "faithfulness" not in row


def test_an_abstention_without_the_marker_is_recognized_as_the_application_does(lab, models):
    runner, *_ = lab
    models["gemma4:12b"] = (None, FakeLLM(["The passages don't say who did it [1].", "NO"]))
    overrides = {"llm": {"model": "gemma4:12b"}, "llm_profiles": {"gemma4:12b": {"check_abstentions": True}}}
    variant = VariantConfig(name="candidate", overrides=overrides)
    experiment = Experiment(name="test", kind="generation", description="A test.", variants=(variant,), judge=JUDGE)

    [row] = report_of(runner.run(experiment))["rows"]

    assert row["abstained"] is True
    assert row["answer"] == "The passages don't say who did it [1]."
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


def test_an_extraction_experiment_is_refused_naming_the_kinds_left():
    """The extraction kind went with the readers it compared (specs/005-markdown-only, FR-017)."""
    with pytest.raises(ValidationError) as refused:
        experiment_of("extraction")

    allowed = str(refused.value).split("Input should be ")[1].split(" [type=")[0]
    kinds = set(re.findall(r"'(\w+)'", allowed))
    assert kinds == {"retrieval", "generation", "summarization", "performance"}


# The dataset's books, checked where the work starts (specs/005-markdown-only, FR-018, contracts/benchmark.md)


@pytest.mark.parametrize("step", ["run", "validate"])
def test_a_missing_dataset_book_stops_before_any_work(lab, step):
    runner, _, libraries, _ = lab
    (runner._root / "books" / "a.md").unlink()

    with pytest.raises(ConfigurationError, match=r"a_book: .*a\.md is missing\. The benchmark's books are Markdown"):
        runner.run(retrieval_experiment()) if step == "run" else runner.validate()

    assert libraries == {}
    assert not (runner._root / "results").exists()


@pytest.mark.parametrize("step", ["run", "validate"])
def test_a_dataset_book_that_isnt_the_one_named_stops_before_any_work(lab, step):
    runner, _, libraries, _ = lab
    (runner._root / "books" / "a.md").write_text(MARKDOWN + "\nA reconversion changed this.\n", encoding="utf-8")

    with pytest.raises(ConfigurationError, match="isn't the file the dataset names") as stopped:
        runner.run(retrieval_experiment()) if step == "run" else runner.validate()

    assert "Its evidence quotes may not be found in it." in str(stopped.value)
    assert libraries == {}
    assert not (runner._root / "results").exists()
