import json
import re
from collections import Counter

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
from app.evaluation.dataset import CATEGORY_COUNTS
from app.evaluation.generation_metrics import JudgeScores
from app.evaluation.performance import PerformanceResult
from app.evaluation.quiz_metrics import load_known_cases, read_reading
from app.generation.base import GenerationParameters
from app.generation.question_answering import QuestionAnsweringService
from app.generation.quiz import QuizWriter
from app.ingestion.chunker import Chunker
from app.services.health_service import HealthService
from app.services.quiz_service import QuizService
from app.services.reset_service import CONFIRM_RESET_EVERYTHING, ResetService
from app.storage.catalog import BookStatus
from app.utils.hashing import file_checksum
from tests.fakes import FakeEmbedder, FakeLLM, FakeRuntime, WordCounter
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


QUIZ_DRAFT = json.dumps(
    {
        "question": "Why does the fox go back to the forest, according to the book?",
        "correct": "To rest there for the rest of the day.",
        "wrong": [
            "To hunt for food in the evening.",
            "To hide from the farmer and his dog.",
            "To meet the other foxes of the valley.",
            "To sleep through the cold winter months.",
        ],
        "explanation": "The book says that the fox goes back to the forest to rest for the day.",
    }
)


def quiz_reply(messages, parameters):
    return QUIZ_DRAFT


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
        if not hasattr(library, "quiz_llm"):  # the quiz's writer, scripted apart from the summaries'
            library.quiz_llm = FakeLLM(respond=quiz_reply)
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
            quizzes=QuizService(
                variant_settings.generation.quiz,
                variant_settings.generation.response_languages,
                library.catalog,
                library.processed,
                QuizWriter(variant_settings.generation.quiz, 0.1, library.quiz_llm),
                environment.data_dir / "quiz_downloads",
            ),
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
    assert json.loads((directory / "rows.jsonl").read_text(encoding="utf-8"))["variant"] == "bm25"


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


# The quiz measurement (specs/003-chapter-quiz, contracts/quiz-experiments.md)


def quiz_experiment(variants=None, **fields):
    variants = variants or (VariantConfig(name="writer"),)
    values = {"targets": ({"book": "a_book", "chapter": "One", "questions": 1},), "seed": 3} | fields
    return Experiment.model_validate(
        {"name": "quiz", "kind": "quiz", "description": "Measures questions.", "variants": variants, **values}
    )


@pytest.fixture
def answers(monkeypatch):
    """The writer's closed-book answers: each reply in turn, the last one repeating."""
    replies = ['{"answer": "A"}']

    def create(settings, runtime, **options):
        return FakeLLM(list(replies))

    monkeypatch.setattr(benchmark, "create_llm_provider", create)
    return replies


def local_book(root, text=None, **fields):
    path = root / "books" / "mine.md"
    path.write_text(text or MARKDOWN.replace("fox", "cat"), encoding="utf-8")
    entry = {"key": "mine", "title": "Mine", "language": "en", "filename": "mine.md", "sha256": file_checksum(path)}
    return entry | fields


def test_a_quiz_experiment_takes_targets_local_books_and_a_seed():
    experiment = quiz_experiment(
        local_books=({"key": "mine", "title": "Mine", "language": "pt", "filename": "m.pdf", "sha256": "abc"},),
        targets=({"book": "mine", "chapter": None, "questions": None},),
        seed=7,
    )

    assert experiment.kind == "quiz"
    assert experiment.local_books[0].key == "mine"
    assert experiment.targets[0].chapter is None
    assert experiment.targets[0].questions is None
    assert experiment.seed == 7


@pytest.mark.parametrize(
    "fields",
    [
        {"targets": ({"book": "a_book", "chapter": "One", "questions": 1, "count": 3},)},
        {"local_books": ({"key": "m", "title": "M", "language": "pt", "filename": "m", "sha256": "a", "url": "x"},)},
        {"seeds": 3},
    ],
)
def test_unknown_quiz_keys_are_refused(fields):
    with pytest.raises(ValueError):
        quiz_experiment(**fields)


def test_the_seed_defaults_to_zero():
    experiment = Experiment.model_validate(
        {"name": "q", "kind": "quiz", "description": "d", "variants": [{"name": "v"}], "targets": []}
    )

    assert experiment.seed == 0


@pytest.mark.parametrize("problem", ["missing", "checksum"])
def test_a_local_book_that_isnt_the_owners_copy_stops_the_run_before_any_work(lab, answers, problem):
    runner, _, libraries, _ = lab
    root = runner._root
    entry = local_book(root)
    if problem == "missing":
        (root / "books" / "mine.md").unlink()
    else:
        entry["sha256"] = "0" * 64

    with pytest.raises(ConfigurationError, match="mine.md"):
        runner.run(quiz_experiment(local_books=(entry,)))

    assert libraries == {}
    assert not (root / "results").exists()


def test_local_books_are_indexed_in_the_workspace_beside_the_datasets(lab, answers):
    runner, _, libraries, _ = lab
    entry = local_book(runner._root)

    directory = runner.run(quiz_experiment(local_books=(entry,), targets=({"book": "mine", "chapter": "One"},)))

    [library] = libraries.values()
    assert {book.original_filename for book in library.books.list_books()} == {"a.md", "mine.md"}
    assert report_of(directory)["rows"][0]["book"] == "mine"


def question_rows(report):
    return [row for row in report["rows"] if row["row"] == "question"]


def quiz_rows(report):
    return [row for row in report["rows"] if row["row"] == "quiz"]


def test_a_quiz_run_writes_question_and_quiz_rows(lab, answers):
    runner, *_ = lab

    report = report_of(runner.run(quiz_experiment()))

    [question] = question_rows(report)
    assert question["variant"] == "writer"
    assert question["question"] == "a_book:One:1"
    assert (question["book"], question["chapter"]) == ("a_book", "One")
    assert 0 <= question["relative_position"] <= 1
    assert question["third"] in (0, 1, 2)
    assert question["letter"] in "ABCDE"
    assert question["key_is_longest"] in (True, False)
    assert not (question["key_is_shortest"] and question["key_is_longest"])
    assert question["closed_book_correct"] == (question["letter"] == "A")
    assert question["attempts"] == 1
    assert question["refusals"] == 0
    assert question["refused_unreadable"] == 0
    assert question["checked"] is False
    assert question["check_accepted"] is None
    assert question["question_seconds"] >= 0
    [quiz] = quiz_rows(report)
    assert (quiz["asked"], quiz["delivered"], quiz["delivered_share"]) == (1, 1, 1.0)
    assert quiz["seconds"] >= quiz["first_question_seconds"] >= 0
    assert (quiz["skipped_passages"], quiz["passed_over_passages"], quiz["ruled_out_chapters"]) == (0, 0, 0)
    assert quiz["check_unreadable"] == 0
    summary = report["summary"][0]
    assert summary["delivered_share"] == 1.0
    assert summary["closed_book_unreadable"] == 0


def test_the_default_count_is_used_when_a_target_has_none(lab, answers):
    runner, *_ = lab

    report = report_of(runner.run(quiz_experiment(targets=({"book": "a_book", "chapter": "One"},))))

    assert quiz_rows(report)[0]["asked"] == 1  # the chapter's few words give the minimum


def test_a_closed_book_answer_that_cant_be_read_is_left_out_and_counted(lab, answers):
    runner, *_ = lab
    answers[:] = ["A resposta é A"]

    report = report_of(runner.run(quiz_experiment()))

    assert question_rows(report)[0]["closed_book_correct"] is None
    assert report["summary"][0]["closed_book_correct"] is None
    assert report["summary"][0]["closed_book_unreadable"] == 1


def test_the_same_seed_pairs_variants_question_by_question(lab, answers):
    runner, *_ = lab
    variants = (VariantConfig(name="one"), VariantConfig(name="two"))

    report = report_of(runner.run(quiz_experiment(variants=variants, targets=({"book": "a_book", "chapter": None},))))

    by_variant = {}
    for row in question_rows(report):
        by_variant.setdefault(row["variant"], []).append((row["question"], row["letter"]))
    assert by_variant["one"] == by_variant["two"]


def test_a_quiz_run_writes_its_reading(lab, answers):
    runner, *_ = lab

    directory = runner.run(quiz_experiment())

    [row] = read_reading(directory / "reading.csv")
    assert row["variant"] == "writer"
    assert row["question"] == "a_book:One:1"
    assert row["text"].startswith("Why does the fox")
    assert row["passage"]
    assert row[row["key"]] == "To rest there for the rest of the day."
    assert (row["mark"], row["reasons"], row["note"]) == ("", "", "")


def test_a_failed_target_is_reported_and_the_run_goes_on(lab, answers):
    runner, _, libraries, _ = lab

    def refuse(messages, parameters):
        return "Não consigo."

    experiment = quiz_experiment(targets=({"book": "a_book", "chapter": "One"}, {"book": "a_book", "chapter": "Two"}))
    runner.run(quiz_experiment())  # builds the workspace
    [library] = libraries.values()
    library.quiz_llm.respond = refuse

    report = report_of(runner.run(experiment))

    assert [row["failed"] for row in quiz_rows(report)] == [True, True]


def test_the_environment_records_the_commit_and_every_books_checksum(lab, answers):
    runner, *_ = lab
    entry = local_book(runner._root)

    report = report_of(runner.run(quiz_experiment(local_books=(entry,)), commit="abc1234"))

    environment = report["environment"]
    assert environment["commit"] == "abc1234"
    dataset_book = file_checksum(runner._root / "books" / "a.md")
    assert environment["book_sha256"] == {"a_book": dataset_book, "mine": entry["sha256"]}


# The key check's proof (kind quiz_check, FR-026 and FR-027)

FOX = "The quick brown fox jumps over the lazy dog"


def known_case(identifier, label="sound", case_set="test", quote=FOX, **fields):
    return {
        "id": identifier,
        "source": "probe",
        "book": "a_book",
        "chapter": "One",
        "quote": quote,
        "question": f"What does the fox do? ({identifier})",
        "options": {"A": "It rests.", "B": "It hunts.", "C": "It sleeps.", "D": "It runs.", "E": "It hides."},
        "key": "A",
        "label": label,
        "reasons": ["wrong_key"] if label == "flawed" else [],
        "note": None,
        "set": case_set,
        **fields,
    }


def check_experiment(tmp_path, cases, case_set="test", variants=None):
    path = tmp_path / "key_cases.yaml"
    path.write_text(yaml.safe_dump(cases, allow_unicode=True), encoding="utf-8")
    return Experiment.model_validate(
        {
            "name": "quiz_check",
            "kind": "quiz_check",
            "description": "Proves the key check.",
            "variants": variants or [{"name": "medium"}],
            "known_cases": str(path),
            "case_set": case_set,
        }
    )


@pytest.fixture
def check_models(monkeypatch):
    """The checker and the comparator, scripted by case: replies keyed by the case's ID in the prompt."""
    verdicts, answers = {}, {}

    def reply(table, default):
        def respond(messages, parameters):
            prompt = messages[-1].content
            case = re.search(r"\(([^)]+)\)", prompt.split("Question:")[1]).group(1)
            return table.get(case, default)

        return respond

    def create(settings, runtime, **options):
        if "reasoning" in options:
            return FakeLLM(respond=reply(verdicts, '{"supported": ["A"]}'))
        return FakeLLM(respond=reply(answers, '{"answer": "A"}'))

    monkeypatch.setattr(benchmark, "create_llm_provider", create)
    return verdicts, answers


def cases_of(flawed, sound, case_set="test"):
    return [known_case(f"f{n}", "flawed", case_set) for n in range(flawed)] + [
        known_case(f"s{n}", "sound", case_set) for n in range(sound)
    ]


def check_summary(runner, experiment):
    report = report_of(runner.run(experiment))
    return report, report["summary"][0]


def test_a_check_experiment_needs_its_case_set():
    with pytest.raises(ValueError, match="case_set"):
        Experiment.model_validate(
            {"name": "c", "kind": "quiz_check", "description": "d", "variants": [{"name": "v"}], "known_cases": "k"}
        )


def test_the_known_cases_are_read_beside_the_experiment(tmp_path):
    (tmp_path / "quiz_check.yaml").write_text(
        yaml.safe_dump(
            {
                "name": "c",
                "kind": "quiz_check",
                "description": "d",
                "variants": [{"name": "v"}],
                "known_cases": "key_cases.yaml",
                "case_set": "development",
            }
        ),
        encoding="utf-8",
    )

    assert load_experiment(tmp_path / "quiz_check.yaml").known_cases == tmp_path / "key_cases.yaml"


@pytest.mark.parametrize(
    "change",
    [
        {"quote": " ".join(["word"] * 31)},
        {"label": "flawed", "reasons": []},
        {"label": "sound", "reasons": ["wrong_key"]},
        {"reasons": ["typo"], "label": "flawed"},
        {"key": "F"},
        {"set": "training"},
        {"options": {"A": "a", "B": "b", "C": "c", "D": "d"}},
        {"passage": "No passage text is stored."},
    ],
)
def test_a_known_case_outside_its_rules_is_refused(tmp_path, change):
    path = tmp_path / "cases.yaml"
    path.write_text(yaml.safe_dump([known_case("c1") | change]), encoding="utf-8")

    with pytest.raises(ConfigurationError, match="c1|cases.yaml"):
        load_known_cases(path)


def test_two_known_cases_with_one_id_are_refused(tmp_path):
    path = tmp_path / "cases.yaml"
    path.write_text(yaml.safe_dump([known_case("c1"), known_case("c1")]), encoding="utf-8")

    with pytest.raises(ConfigurationError, match="c1"):
        load_known_cases(path)


def test_only_the_cases_of_the_set_run(lab, check_models, tmp_path):
    runner, *_ = lab
    cases = [known_case("d1", case_set="development"), known_case("t1"), known_case("t2", "flawed")]

    report, summary = check_summary(runner, check_experiment(tmp_path, cases, case_set="test"))

    assert sorted(row["case"] for row in report["rows"]) == ["t1", "t2"]
    assert (summary["flawed_cases"], summary["sound_cases"]) == (1, 1)


def test_a_quote_found_nowhere_is_counted_and_not_run(lab, check_models, tmp_path):
    runner, *_ = lab
    cases = [known_case("t1"), known_case("t2", quote="A sentence the book never says")]

    report, summary = check_summary(runner, check_experiment(tmp_path, cases))

    assert summary["missing_quotes"] == 1
    assert summary["samples"] == 1
    missing = next(row for row in report["rows"] if row["case"] == "t2")
    assert missing["located"] is False
    assert "rejected" not in missing


def test_each_case_gets_a_check_row(lab, check_models, tmp_path):
    runner, *_ = lab
    verdicts, answers = check_models
    verdicts["t2"] = '{"supported": ["A", "C"]}'
    answers["t2"] = '{"answer": "C"}'
    cases = [known_case("t1"), known_case("t2", "flawed")]

    report, summary = check_summary(runner, check_experiment(tmp_path, cases))

    rows = {row["case"]: row for row in report["rows"]}
    assert {key: rows["t2"][key] for key in ("variant", "label", "rejected", "supported", "readable")} == {
        "variant": "medium",
        "label": "flawed",
        "rejected": True,
        "supported": "AC",
        "readable": True,
    }
    assert (rows["t2"]["open_book_answer"], rows["t2"]["open_book_caught"]) == ("C", True)
    assert (rows["t1"]["rejected"], rows["t1"]["open_book_caught"]) == (False, False)
    assert (summary["flawed_caught"], summary["sound_rejected"], summary["comparator_flawed_caught"]) == (1, 0, 1)


def test_an_unreadable_verdict_is_counted_and_lets_the_question_through(lab, check_models, tmp_path):
    runner, *_ = lab
    verdicts, _ = check_models
    verdicts["t1"] = "I can't tell."

    report, summary = check_summary(runner, check_experiment(tmp_path, [known_case("t1", "flawed")]))

    assert report["rows"][0]["readable"] is False
    assert report["rows"][0]["rejected"] is False
    assert summary["unreadable"] == 1


def test_development_runs_decide_nothing(lab, check_models, tmp_path):
    runner, *_ = lab
    verdicts, _ = check_models
    verdicts.update({f"f{n}": '{"supported": []}' for n in range(10)})

    _, summary = check_summary(runner, check_experiment(tmp_path, cases_of(10, 30, "development"), "development"))

    assert summary["rule_passes"] is None
    assert "Development" in summary["rule_reason"]


def test_too_few_test_cases_give_no_verdict(lab, check_models, tmp_path):
    runner, *_ = lab
    verdicts, _ = check_models
    verdicts.update({f"f{n}": '{"supported": []}' for n in range(9)})

    _, summary = check_summary(runner, check_experiment(tmp_path, cases_of(9, 30)))

    assert summary["rule_passes"] is None
    assert "10" in summary["rule_reason"]


def test_the_check_passes_when_it_catches_more_and_rejects_few_sound(lab, check_models, tmp_path):
    runner, *_ = lab
    verdicts, answers = check_models
    verdicts.update({f"f{n}": '{"supported": []}' for n in range(10)})
    verdicts.update({f"s{n}": '{"supported": ["B"]}' for n in range(3)})  # 3 of 30 sound: 0.10
    answers.update({f"f{n}": '{"answer": "B"}' for n in range(2)})

    _, summary = check_summary(runner, check_experiment(tmp_path, cases_of(10, 30)))

    assert (summary["flawed_caught"], summary["comparator_flawed_caught"], summary["sound_rejected"]) == (10, 2, 3)
    assert summary["difference"]["low"] > 0
    assert summary["rule_passes"] is True


def test_a_tie_with_the_comparator_fails(lab, check_models, tmp_path):
    runner, *_ = lab
    verdicts, answers = check_models
    verdicts.update({f"f{n}": '{"supported": []}' for n in range(5)})
    answers.update({f"f{n}": '{"answer": "B"}' for n in range(5)})

    _, summary = check_summary(runner, check_experiment(tmp_path, cases_of(10, 30)))

    assert summary["difference"]["mean"] == 0
    assert summary["rule_passes"] is False


def test_rejecting_more_than_a_tenth_of_sound_cases_fails(lab, check_models, tmp_path):
    runner, *_ = lab
    verdicts, _ = check_models
    verdicts.update({f"f{n}": '{"supported": []}' for n in range(10)})
    verdicts.update({f"s{n}": '{"supported": []}' for n in range(4)})  # 4 of 30

    _, summary = check_summary(runner, check_experiment(tmp_path, cases_of(10, 30)))

    assert summary["difference"]["low"] > 0
    assert summary["rule_passes"] is False


def test_flawed_cases_whose_comparator_answer_cant_be_read_are_left_out_of_the_comparison(lab, check_models, tmp_path):
    runner, *_ = lab
    verdicts, answers = check_models
    verdicts.update({f"f{n}": '{"supported": []}' for n in range(10)})
    answers.update({f"f{n}": "A resposta é B" for n in range(3)})

    _, summary = check_summary(runner, check_experiment(tmp_path, cases_of(10, 30)))

    assert summary["comparator_unreadable"] == 3
    assert summary["difference"]["pairs"] == 7


def test_the_key_being_the_shortest_option_is_measured_too(lab, answers):
    runner, _, libraries, _ = lab
    runner.run(quiz_experiment())  # builds the workspace
    [library] = libraries.values()
    short_key = json.loads(QUIZ_DRAFT) | {"correct": "To rest."}
    library.quiz_llm.respond = lambda messages, parameters: json.dumps(short_key)

    report = report_of(runner.run(quiz_experiment()))

    [question] = question_rows(report)
    assert (question["key_is_shortest"], question["key_is_longest"]) == (True, False)
    assert report["summary"][0]["key_is_shortest"] == 1.0
