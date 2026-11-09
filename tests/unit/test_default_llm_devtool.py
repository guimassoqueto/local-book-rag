"""devtools/default_llm.py: the confirmation that chooses the default LLM (specs/002-gemma4-default-llm).

The script is piped to the app container's Python, so it isn't a package: it is loaded here by
path. What it does against the stack is checked by running it. What decides the verdict, the
recorder, the reading and the rule, is checked here.
"""

import importlib.util
import sys
from pathlib import Path

import pytest

import app.container
import app.evaluation.benchmark
from app.evaluation.benchmark import load_experiment
from app.evaluation.report import paired_difference
from app.generation.base import Generation, GenerationParameters, Message
from tests.fakes import FakeLLM

PROJECT = Path(__file__).resolve().parents[2]
EXPERIMENTS = PROJECT / "benchmarks" / "experiments"

_spec = importlib.util.spec_from_file_location("default_llm", PROJECT / "devtools" / "default_llm.py")
default_llm = importlib.util.module_from_spec(_spec)
sys.modules["default_llm"] = default_llm
_spec.loader.exec_module(default_llm)

BASELINE, CANDIDATE = "gpt_oss_20b", "gemma4_12b"
MODELS = {BASELINE: "gpt-oss:20b", CANDIDATE: "gemma4:12b"}
GENERATION_METRICS = (
    "faithfulness",
    "answer_correctness",
    "answer_relevance",
    "citation_accuracy",
    "language_consistency",
    "abstention_quality",
)
SUMMARY_METRICS = (
    "argument_coverage",
    "concept_preservation",
    "factual_consistency",
    "coherence",
    "completeness",
    "citation_traceability",
)
CHAPTERS = (
    ("quincas_borba", "CAPITULO L"),
    ("quincas_borba", "CAPITULO CXVIII"),
    ("think_python", "Fruitful functions"),
    ("think_python", "Inheritance"),
    ("on_liberty", "CHAPTER II."),
    ("on_liberty", "CHAPTER V."),
)
TRAP = "quincas_borba_unanswerable_04"


# The confirmation's experiments


@pytest.mark.parametrize("kind", ["generation", "summarization"])
def test_the_confirmation_keeps_its_sources_judge_and_compares_two_models(kind):
    confirmation = load_experiment(EXPERIMENTS / f"default_llm_{kind}.yaml")
    source = load_experiment(EXPERIMENTS / f"{kind}.yaml")

    assert confirmation.kind == kind
    assert confirmation.judge == source.judge
    assert tuple(variant.name for variant in confirmation.variants) == (BASELINE, CANDIDATE)
    overrides = {variant.name: variant.overrides for variant in source.variants}
    for variant in confirmation.variants:
        assert variant.overrides == overrides[variant.name]


def test_an_unknown_subcommand_is_a_usage_error():
    with pytest.raises(SystemExit) as stopped:
        default_llm.main(["bogus"])

    assert stopped.value.code == 2


# The recorder


def _messages():
    return [Message("system", "a b c"), Message("user", "d e")]


def test_the_recorder_passes_a_generation_through_and_records_its_prompt():
    sink = []
    recorder = default_llm.RecordingLLM(FakeLLM(replies=["hello world"]), sink, lambda: (CANDIDATE, "Inheritance"))

    generation = recorder.generate(_messages(), GenerationParameters(temperature=0, max_tokens=50))

    assert generation == FakeLLM(replies=["hello world"]).generate(_messages(), GenerationParameters(0, 50))
    assert sink == [
        {
            "variant": CANDIDATE,
            "chapter": "Inheritance",
            "model": "fake-llm",
            "estimate_tokens": 5,
            "prompt_tokens": 100,
            "window": 8192,
            "max_tokens": 50,
            "finish_reason": "stop",
        }
    ]


def test_the_recorder_streams_what_its_provider_streams():
    parameters = GenerationParameters(temperature=0, max_tokens=50)
    sink = []
    recorder = default_llm.RecordingLLM(FakeLLM(replies=["hello world"]), sink, lambda: (None, "x"))

    assert list(recorder.stream(_messages(), parameters)) == list(
        FakeLLM(replies=["hello world"]).stream(_messages(), parameters)
    )
    assert len(sink) == 1


def test_the_recorder_delegates_what_it_doesnt_record():
    inner = FakeLLM(replies=["x"], context_size=4096)
    recorder = default_llm.RecordingLLM(inner, [], lambda: (None, None))

    assert recorder.model == "fake-llm"
    assert recorder.context_size() == 4096
    assert recorder.count_tokens("one two three") == 3


def test_the_recorder_records_nothing_without_a_label():
    sink = []
    recorder = default_llm.RecordingLLM(FakeLLM(replies=["x"]), sink, lambda: None)

    recorder.generate(_messages(), GenerationParameters(temperature=0, max_tokens=5))

    assert sink == []


def test_recording_wraps_what_the_container_builds_and_never_the_judge(monkeypatch):
    monkeypatch.setattr(app.container, "create_llm_provider", lambda settings, runtime: FakeLLM(replies=["x"]))
    factory = app.container.create_llm_provider
    judge_factory = app.evaluation.benchmark.create_llm_provider

    with default_llm.recording_llms([], lambda: (None, None)):
        assert isinstance(app.container.create_llm_provider(None, None), default_llm.RecordingLLM)
        assert app.evaluation.benchmark.create_llm_provider is judge_factory

    assert app.container.create_llm_provider is factory


def test_recording_puts_the_factory_back_after_an_error(monkeypatch):
    monkeypatch.setattr(app.container, "create_llm_provider", lambda settings, runtime: FakeLLM(replies=["x"]))
    factory = app.container.create_llm_provider

    with pytest.raises(RuntimeError), default_llm.recording_llms([], lambda: (None, None)):
        raise RuntimeError("a run failed")

    assert app.container.create_llm_provider is factory


# Preflight


def _environment(version="0.40.15", **digests):
    return {"ollama_version": version, "models": {name: {"digest": digest} for name, digest in digests.items()}}


def _compare(expected, actual, dataset_expected="abc", dataset_actual="abc"):
    return default_llm.compare_environment(
        expected, actual, ["gemma4:12b", "gpt-oss:20b"], dataset_expected, dataset_actual
    )


def _digests(**overrides):
    return {"gemma4:12b": "6114", "gpt-oss:20b": "f38a"} | overrides


def test_preflight_passes_identical_versions():
    checks = _compare(_environment(**_digests()), _environment(**_digests()))

    assert checks and all(check.ok for check in checks)


@pytest.mark.parametrize(
    ("expected", "actual", "dataset_actual", "differs"),
    [
        (_environment(**_digests()), _environment(**_digests(**{"gemma4:12b": "9999"})), "abc", "gemma4:12b"),
        (_environment(**{"gpt-oss:20b": "f38a"}), _environment(**_digests()), "abc", "gemma4:12b"),
        (_environment(**_digests()), _environment("0.41.0", **_digests()), "abc", "ollama"),
        (_environment(**_digests()), _environment(**_digests()), "def", "dataset"),
    ],
    ids=["a digest", "a model missing from the reference", "ollama", "the dataset"],
)
def test_preflight_names_what_differs(expected, actual, dataset_actual, differs):
    failed = [check for check in _compare(expected, actual, dataset_actual=dataset_actual) if not check.ok]

    assert len(failed) == 1
    assert differs in failed[0].name


# The reading record


def _write(tmp_path, text):
    path = tmp_path / "reading.yaml"
    path.write_text(text, encoding="utf-8")
    return path


def test_a_reading_entry_is_loaded_with_its_errors(tmp_path):
    path = _write(
        tmp_path,
        """
- item: on_liberty_multi_section_01
  kind: answer
  model: gemma4:12b
  errors: [unanswered_part]
  note: Passage 3 holds the second part.
- item: think_python_unanswerable_03@French
  kind: probe_reply
  model: gemma4:12b
  label: abstains
  errors: []
  note: ""
""",
    )

    entries = default_llm.load_reading(path)

    assert entries[0].errors == ("unanswered_part",)
    assert entries[1].label == "abstains"


@pytest.mark.parametrize(
    "entry",
    [
        "{item: q, kind: answer, model: m, errors: [rude], note: x}",
        "{item: q, kind: essay, model: m, errors: [], note: ''}",
        "{item: q@French, kind: probe_reply, model: m, errors: [], note: ''}",
        "{item: q@French, kind: probe_reply, model: m, label: maybe, errors: [], note: ''}",
        "{item: q, kind: answer, model: m, label: abstains, errors: [], note: ''}",
        "{item: q, kind: answer, model: m, errors: [misattribution], note: ''}",
    ],
    ids=[
        "an unknown error kind",
        "an unknown kind",
        "a probe reply without a label",
        "an unknown label",
        "a label on an answer",
        "errors without a note",
    ],
)
def test_an_invalid_reading_is_refused(tmp_path, entry):
    with pytest.raises(default_llm.ReadingError):
        default_llm.load_reading(_write(tmp_path, f"- {entry}\n"))


def test_a_duplicate_entry_is_refused(tmp_path):
    entry = "- {item: q, kind: answer, model: m, errors: [], note: ''}\n"

    with pytest.raises(default_llm.ReadingError):
        default_llm.load_reading(_write(tmp_path, entry * 2))


def test_missing_entries_are_named():
    entries = [default_llm.ReadingEntry("q1", "answer", "gemma4:12b", (), None, "")]
    required = [("q1", "answer", "gemma4:12b"), ("q1", "answer", "gpt-oss:20b")]

    assert default_llm.missing_entries(entries, required) == [("q1", "answer", "gpt-oss:20b")]


# The rule


def _some_multi_section(i):
    return "multi_section" if i >= 25 else "factual"


def _generation_rows(score=lambda variant, i: 0.8, abstained=lambda variant, i: False, category=_some_multi_section):
    rows = []
    for variant, model in MODELS.items():
        for i in range(30):
            row = {
                "variant": variant,
                "model": model,
                "question": f"q{i}",
                "book": "on_liberty",
                "category": category(i),
                "failed": False,
                "abstained": abstained(variant, i),
            }
            rows.append(row | {metric: score(variant, i) for metric in GENERATION_METRICS})
    return rows


def _baseline_abstains_three(variant, i):
    return variant == BASELINE and i < 3


def _summary_rows(**overrides):
    """The candidate faster, in fewer steps, and better on the novel, unless overridden."""
    seconds = overrides.get("seconds", {BASELINE: (100, 150, 60, 200, 70, 270), CANDIDATE: (20, 15, 27, 28, 65, 54)})
    steps = overrides.get("steps", {BASELINE: (1, 1, 5, 20, 8, 24), CANDIDATE: (1, 1, 3, 3, 8, 5)})
    novel = overrides.get("novel", {BASELINE: 0.2, CANDIDATE: 0.6})
    score = overrides.get("score", lambda variant, metric, i: 0.75)
    rows = []
    for variant, model in MODELS.items():
        for i, (book, chapter) in enumerate(CHAPTERS):
            row = {"variant": variant, "model": model, "book": book, "chapter": chapter, "failed": False}
            row |= {metric: score(variant, metric, i) for metric in SUMMARY_METRICS}
            if book == "quincas_borba":
                row["argument_coverage"] = novel[variant]
            row |= {"total_seconds": seconds[variant][i], "steps": steps[variant][i]}
            rows.append(row)
    return rows


def _probe(trap_answers=None, waits=None, analytical_errors=None, markers=()):
    trap_answers = trap_answers or {BASELINE: 1, CANDIDATE: 0}
    waits = waits or {BASELINE: 0.5, CANDIDATE: 1.0}
    analytical_errors = analytical_errors or {}
    records = []
    for variant, model in MODELS.items():
        for run in range(3):
            for item in (TRAP, "think_python_multi_section_04"):
                answered = item == TRAP and run < trap_answers[variant]
                records.append(
                    {
                        "kind": "whole_library",
                        "model": model,
                        "item": item,
                        "language": None,
                        "run": run + 1,
                        "insufficient_evidence": item == TRAP and not answered,
                        "text": "...",
                        "citations": [],
                        "invented_citations": [],
                        "wait_seconds": waits[variant],
                    }
                )
        records.append(
            {
                "kind": "analytical",
                "model": model,
                "item": "Inheritance",
                "text": "...",
                "steps": 4,
                "incomplete_steps": 0,
                "detected_language": "en",
                "book_language": "en",
                "error": analytical_errors.get(variant),
            }
        )
    for variant, item, language in markers:
        records.append(
            {
                "kind": "marker",
                "model": MODELS[variant],
                "item": item,
                "language": language,
                "run": None,
                "insufficient_evidence": False,
                "text": "...",
                "citations": [],
                "invented_citations": [],
                "wait_seconds": 1.0,
            }
        )
    return records


def _prompt(variant, undercount, window=8192):
    return {
        "variant": variant,
        "chapter": "Inheritance",
        "model": MODELS[variant],
        "estimate_tokens": 4000,
        "prompt_tokens": 4000 + undercount,
        "window": window,
        "max_tokens": 3000,
        "finish_reason": "stop",
    }


def _entry(item, kind, variant, errors=(), label=None):
    return default_llm.ReadingEntry(item, kind, MODELS[variant], tuple(errors), label, "read" if errors else "")


def _decide(
    generation=None, summarization=None, prompts=None, probe=None, reading=(), integration="pending", margin=0.1
):
    return default_llm.decide(
        _generation_rows(abstained=_baseline_abstains_three) if generation is None else generation,
        _summary_rows() if summarization is None else summarization,
        [_prompt(BASELINE, 120), _prompt(CANDIDATE, 60)] if prompts is None else prompts,
        _probe() if probe is None else probe,
        list(reading),
        margin,
        integration,
    )


def test_a_confirmation_that_passes_every_condition_waits_for_the_real_model_checks():
    verdict = _decide()

    assert all(verdict.conditions[name].passed for name in "abcd")
    assert verdict.outcome == "pending"


def test_a_gated_metric_worse_for_the_candidate_fails_a():
    rows = _generation_rows(
        score=lambda variant, i: 0.5 if variant == CANDIDATE else 0.8, abstained=_baseline_abstains_three
    )

    verdict = _decide(generation=rows)

    assert not verdict.conditions["a"].passed
    assert "faithfulness" in verdict.conditions["a"].failures
    assert verdict.outcome == "keep"


def test_the_intervals_are_the_reports_own():
    rows = _generation_rows(score=lambda variant, i: (i % 7) / 10 + (0.05 if variant == CANDIDATE else 0))
    summaries = _summary_rows(score=lambda variant, metric, i: (i % 4) / 4 + (0.1 if variant == BASELINE else 0))

    differences = _decide(generation=rows, summarization=summaries).conditions["a"].differences

    for metric in GENERATION_METRICS:
        assert differences[metric] == paired_difference(rows, BASELINE, CANDIDATE, metric)
    for metric in SUMMARY_METRICS:
        assert differences[metric] == paired_difference(summaries, BASELINE, CANDIDATE, metric)


def test_multi_section_correctness_pairs_only_multi_section_answers_both_models_gave():
    def score(variant, i):
        if i < 5 and variant == CANDIDATE:
            return 0.2
        return None if i == 4 and variant == BASELINE else 0.8

    rows = _generation_rows(
        score=score, abstained=_baseline_abstains_three, category=lambda i: "multi_section" if i < 5 else "factual"
    )

    difference = _decide(generation=rows).conditions["a"].differences["multi_section_answer_correctness"]

    assert difference.pairs == 4
    assert difference.mean == pytest.approx(-0.6)


def test_the_wrong_abstentions_have_to_be_fewer_again():
    verdict = _decide(generation=_generation_rows())

    assert not verdict.conditions["b"].passed
    assert "wrong_abstentions" in verdict.conditions["b"].failures


def test_unanswerable_questions_dont_count_as_wrong_abstentions():
    rows = _generation_rows(
        abstained=lambda variant, i: variant == BASELINE and i < 3,
        category=lambda i: "unanswerable" if i < 3 else "factual",
    )

    assert "wrong_abstentions" in _decide(generation=rows).conditions["b"].failures


def test_summaries_have_to_be_faster_with_an_interval_that_excludes_zero():
    same = {BASELINE: (30, 40, 50, 60, 70, 80), CANDIDATE: (31, 39, 52, 58, 71, 79)}

    verdict = _decide(summarization=_summary_rows(seconds=same))

    assert "total_seconds" in verdict.conditions["b"].failures
    assert "steps" not in verdict.conditions["b"].failures


def test_summaries_have_to_take_fewer_steps_with_an_interval_that_excludes_zero():
    same = {BASELINE: (1, 1, 3, 3, 8, 5), CANDIDATE: (1, 1, 3, 3, 8, 5)}

    assert "steps" in _decide(summarization=_summary_rows(steps=same)).conditions["b"].failures


def test_the_novel_has_to_be_covered_better():
    verdict = _decide(summarization=_summary_rows(novel={BASELINE: 0.6, CANDIDATE: 0.6}))

    assert "novel_coverage" in verdict.conditions["b"].failures


def _answers_with(errors_in, kind="answer"):
    entries = []
    for i in range(errors_in):
        item = f"multi_{i}" if kind == "answer" else f"chapter_{i}@run"
        entries += [_entry(item, kind, CANDIDATE, ["unanswered_part"]), _entry(item, kind, BASELINE)]
    return entries


def test_one_error_kind_in_three_multi_section_answers_is_a_systematic_weakness():
    verdict = _decide(reading=_answers_with(3))

    assert not verdict.conditions["c"].passed
    assert "unanswered_part" in verdict.conditions["c"].failures


def test_two_answers_with_it_are_not_systematic():
    assert _decide(reading=_answers_with(2)).conditions["c"].passed


@pytest.mark.parametrize("kind", ["summary", "probe_summary"])
def test_one_error_kind_in_two_summaries_is_a_systematic_weakness(kind):
    assert not _decide(reading=_answers_with(2, kind=kind)).conditions["c"].passed


def test_an_error_both_models_make_is_not_the_candidates_weakness():
    entries = [_entry(f"multi_{i}", "answer", variant, ["unanswered_part"]) for i in range(3) for variant in MODELS]

    assert _decide(reading=entries).conditions["c"].passed


def test_answering_the_trap_more_often_blocks():
    verdict = _decide(probe=_probe(trap_answers={BASELINE: 1, CANDIDATE: 2}))

    assert "trap" in verdict.conditions["d"].failures


def test_answering_the_trap_as_often_as_the_baseline_doesnt_block():
    assert _decide(probe=_probe(trap_answers={BASELINE: 1, CANDIDATE: 1})).conditions["d"].passed


def _marker_reading(*variants):
    return [_entry(f"u{i}@French", "probe_reply", variant, label="abstains") for i, variant in enumerate(variants)]


def test_more_unrecognized_abstentions_block():
    probe = _probe(markers=[(CANDIDATE, "u0", "French")])

    verdict = _decide(probe=probe, reading=_marker_reading(CANDIDATE))

    assert "unrecognized_abstentions" in verdict.conditions["d"].failures


def test_a_reply_that_answers_is_not_an_unrecognized_abstention():
    probe = _probe(markers=[(CANDIDATE, "u0", "French")])
    reading = [_entry("u0@French", "probe_reply", CANDIDATE, label="answers")]

    assert _decide(probe=probe, reading=reading).conditions["d"].passed


def test_as_many_unrecognized_abstentions_as_the_baseline_dont_block():
    probe = _probe(markers=[(CANDIDATE, "u0", "French"), (BASELINE, "u1", "French")])

    assert _decide(probe=probe, reading=_marker_reading(CANDIDATE, BASELINE)).conditions["d"].passed


def test_an_analytical_summary_that_fails_only_for_the_candidate_blocks():
    verdict = _decide(probe=_probe(analytical_errors={CANDIDATE: "no text"}))

    assert "analytical" in verdict.conditions["d"].failures


def test_an_analytical_summary_that_fails_for_both_doesnt_block():
    errors = {CANDIDATE: "no text", BASELINE: "no text"}

    assert _decide(probe=_probe(analytical_errors=errors)).conditions["d"].passed


def test_an_analytical_summary_in_the_wrong_language_blocks():
    probe = _probe()
    next(r for r in probe if r["kind"] == "analytical" and r["model"] == MODELS[CANDIDATE])["detected_language"] = "pt"

    assert "analytical" in _decide(probe=probe).conditions["d"].failures


def test_a_candidate_prompt_undercounted_beyond_the_margin_blocks():
    verdict = _decide(prompts=[_prompt(CANDIDATE, 60), _prompt(CANDIDATE, 900)])

    assert "undercount" in verdict.conditions["d"].failures


def test_the_baselines_prompts_dont_count_against_the_candidate():
    assert _decide(prompts=[_prompt(BASELINE, 900), _prompt(CANDIDATE, 60)]).conditions["d"].passed


def test_a_wait_over_a_second_longer_blocks():
    verdict = _decide(probe=_probe(waits={BASELINE: 0.5, CANDIDATE: 1.6}))

    assert "wait" in verdict.conditions["d"].failures


def test_a_wait_within_a_second_doesnt_block():
    assert _decide(probe=_probe(waits={BASELINE: 0.5, CANDIDATE: 1.4})).conditions["d"].passed


@pytest.mark.parametrize(("integration", "outcome"), [("pending", "pending"), ("failed", "keep"), ("passed", "switch")])
def test_the_real_model_checks_decide_last(integration, outcome):
    assert _decide(integration=integration).outcome == outcome


@pytest.mark.parametrize("integration", ["pending", "failed", "passed"])
def test_a_failed_condition_keeps_the_baseline_whatever_the_checks_say(integration):
    verdict = _decide(generation=_generation_rows(), integration=integration)

    assert verdict.outcome == "keep"


def test_the_verdict_is_written_with_every_condition():
    verdict = _decide()

    text = default_llm.render_verdict(verdict, {"commit": "abc1234"})

    for heading in ("(a)", "(b)", "(c)", "(d)", "(e)", "Verdict", "Follow-ups"):
        assert heading in text
    assert "abc1234" in text


def test_a_keep_names_only_the_conditions_that_failed_and_leaves_unrun_checks_pending():
    verdict = _decide(generation=_generation_rows(), integration="pending")

    text = default_llm.render_verdict(verdict, {"commit": "abc1234"})

    checks = text.split("## (e)")[1].split("## Verdict")[0]
    outcome = text.split("## Verdict")[1].split("## Follow-ups")[0]
    assert "**Pending" in checks
    assert "Failed" not in checks
    assert "Keep" in outcome
    assert "(e)" not in outcome


def test_a_generation_reply_is_recorded_only_once_per_call():
    sink = []
    recorder = default_llm.RecordingLLM(FakeLLM(replies=["x"]), sink, lambda: (None, "y"))

    events = list(recorder.stream(_messages(), GenerationParameters(temperature=0, max_tokens=5)))

    assert sum(isinstance(event, Generation) for event in events) == 1
    assert len(sink) == 1
