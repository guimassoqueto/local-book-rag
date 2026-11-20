import json
import logging

import pytest

from app.errors import (
    AllModelsFailedError,
    GenerationError,
    ModelChoiceError,
    ModelFailedError,
    ServiceUnavailableError,
)
from app.generation.base import FINISHED_BY_LENGTH, Attempt, AttemptFailed, FailureReason, TextDelta
from app.generation.choices import ModelChoices
from app.generation.factory import CloudSetup
from app.generation.prompts import NO_EVIDENCE_MARKER
from app.generation.question_answering import NOTHING_RETRIEVED, Answer, QuestionAnsweringService, _MarkerFilter
from app.retrieval.base import Passage, RetrievalFilters
from app.retrieval.pipeline import RetrievalResult
from app.utils.logging import INFERENCE_LOGGER, configure_logging
from tests.fakes import FakeCloud, FakeLLM, make_chunk

PASSAGE = ("Opportunity cost is what you give up.",)


class FakeRetrieval:
    def __init__(self, passages):
        self.passages = passages
        self.calls = []

    def search(self, query, filters, config=None):
        self.calls.append((query, filters, config))
        return RetrievalResult(query, tuple(self.passages), tuple(self.passages), 0.1, 0.2)


def passages(*texts):
    return [
        Passage(make_chunk(text, index=index, chapter=4, section="Costs"), rerank_score=0.9)
        for index, text in enumerate(texts)
    ]


def service(settings, llm, found=PASSAGE):
    """The service, on the local model alone, or on given choices."""
    models = llm if isinstance(llm, ModelChoices) else ModelChoices.local_only(llm)
    return QuestionAnsweringService(settings, FakeRetrieval(passages(*found)), models)


def ask(
    settings, llm, question="What is opportunity cost?", found=("Opportunity cost is what you give up.",), **options
):
    return service(settings, llm, found).answer(question, RetrievalFilters(), **options)


def user_message(llm):
    return llm.calls[0][0][-1].content


def system_message(llm):
    return llm.calls[0][0][0].content


def test_an_answer_cites_the_passages_it_used(settings):
    answer = ask(settings, FakeLLM(["It is what you give up [1]."]))

    assert answer.text == "It is what you give up [1]."
    [citation] = answer.citations
    assert citation.chapter_title == "Chapter 4"
    assert citation.section_title == "Costs"
    assert citation.reference == "Title, Chapter 4, Costs"
    assert not answer.insufficient_evidence


def test_gpt_oss_citations_are_understood(settings):
    answer = ask(settings, FakeLLM(["It is what you give up【1】."]))

    assert answer.text == "It is what you give up[1]."
    assert len(answer.citations) == 1


def test_code_in_an_answer_is_not_mistaken_for_citations(settings):
    answer = ask(settings, FakeLLM(["Use `t = [1, 2, 3]`, as the book shows [1]."]), found=("One.", "Two.", "Three."))

    assert [citation.number for citation in answer.citations] == [1]


def test_invented_citations_are_reported(settings):
    answer = ask(settings, FakeLLM(["A claim [1], and an invented one [9]."]))

    assert answer.invented_citations == (9,)


def test_passages_reach_the_prompt_with_their_sources(settings):
    llm = FakeLLM(["Answer [1]."])

    ask(settings, llm)

    prompt = user_message(llm)
    assert "[1] Book: Title | Chapter: Chapter 4 | Section: Costs\n" in prompt
    assert "Pages" not in prompt
    assert "Opportunity cost is what you give up." in prompt
    assert prompt.endswith("Question: What is opportunity cost?")


def test_the_prompt_carries_the_spec_requirements(settings):
    llm = FakeLLM(["Answer [1]."])

    ask(settings, llm)

    system = system_message(llm)
    assert "Never add facts from memory" in system
    assert "square brackets" in system
    assert "inference" in system
    assert "Preserve the author's meaning" in system
    assert NO_EVIDENCE_MARKER in system


def test_a_passage_without_a_section_leaves_it_out(settings):
    chunk = make_chunk("Text.", section=None)
    llm = FakeLLM(["Answer [1]."])

    QuestionAnsweringService(settings, FakeRetrieval([Passage(chunk)]), ModelChoices.local_only(llm)).answer(
        "Q?", RetrievalFilters()
    )

    assert "Section" not in user_message(llm)


def test_the_answer_is_asked_for_in_the_language_of_the_question(settings):
    llm = FakeLLM(["Resposta [1]."])

    ask(settings, llm, question="O que é o custo de oportunidade, segundo o autor?")

    assert "Write your reply in Portuguese" in system_message(llm)


def test_a_question_in_no_clear_language_gets_the_general_rule(settings):
    llm = FakeLLM(["Answer [1]."])

    ask(settings, llm, question="Why?")

    assert "language of the question" in system_message(llm)


def test_a_language_can_be_requested(settings):
    llm = FakeLLM(["Resposta [1]."])

    ask(settings, llm, language="Portuguese")

    assert "Write your reply in Portuguese" in system_message(llm)


def test_a_model_without_evidence_says_so(settings):
    answer = ask(settings, FakeLLM([f"{NO_EVIDENCE_MARKER} The source does not cover this."]))

    assert answer.insufficient_evidence
    assert answer.text == "The source does not cover this."
    assert NO_EVIDENCE_MARKER not in answer.text


def test_the_marker_is_recognized_whatever_dash_it_is_written_with(settings):
    marker = NO_EVIDENCE_MARKER.replace("-", "\u2011")  # as gpt-oss writes it, at times

    answer = ask(settings, FakeLLM([f"{marker} The source does not cover this."]))

    assert answer.insufficient_evidence
    assert answer.text == "The source does not cover this."


def test_the_marker_never_reaches_the_reader_while_streaming(settings):
    llm = FakeLLM([f"{NO_EVIDENCE_MARKER} The source does not cover this."])

    events = service(settings, llm).stream("Q?", RetrievalFilters())
    text = "".join(event.text for event in events if isinstance(event, TextDelta))

    assert NO_EVIDENCE_MARKER not in text
    assert "The source does not cover this." in text


def test_a_marker_written_with_another_dash_is_held_back_too(settings):
    llm = FakeLLM([f"{NO_EVIDENCE_MARKER.replace('-', '\u2011')} The source does not cover this."])

    events = service(settings, llm).stream("Q?", RetrievalFilters())
    text = "".join(event.text for event in events if isinstance(event, TextDelta))

    assert text.strip() == "The source does not cover this."


@pytest.mark.parametrize("marker", ["[NO-EVIDÊNCIA]", "[NO-EVIDENCIA]", "[no-evidence]", "[NO\u2011EVIDÊNCIA]"])
def test_a_translated_marker_is_recognized(settings, marker):
    # gemma4 wrote [NO-EVIDÊNCIA] in a Portuguese answer, and the reader saw it as an answer.
    answer = ask(settings, FakeLLM([f"{marker} O texto não contém essa informação."]))

    assert answer.insufficient_evidence
    assert answer.text == "O texto não contém essa informação."


def test_a_translated_marker_arriving_in_pieces_is_held_back(settings):
    pieces = ["[NO", "-EVID", "ÊN", "CIA]", " O texto", " não diz."]
    filter_ = _MarkerFilter()

    held = [filter_.feed(piece) for piece in pieces[:4]]
    text = "".join(held) + "".join(filter_.feed(piece) for piece in pieces[4:]) + filter_.flush()

    assert held == ["", "", "", ""]
    assert text.strip() == "O texto não diz."


def test_a_bracket_that_only_starts_like_the_marker_is_streamed(settings):
    filter_ = _MarkerFilter()

    text = "".join(filter_.feed(piece) for piece in ["[NO", "TE] a note", " follows."]) + filter_.flush()

    assert text == "[NOTE] a note follows."


def streamed(settings, reply):
    events = service(settings, FakeLLM([reply])).stream("Q?", RetrievalFilters())
    return [event.text for event in events if isinstance(event, TextDelta)]


def test_citations_are_streamed_the_way_the_answer_writes_them(settings):
    assert "".join(streamed(settings, "It is what you give up【 1】, twice【2†L3】.")).strip() == (
        "It is what you give up[1], twice[2]."
    )


def test_a_bracket_that_never_closes_is_not_held_back_to_the_end(settings):
    reply = "A【 bracket that never closes, in an answer that goes on for a while after it."

    deltas = streamed(settings, reply)

    assert "".join(deltas).strip() == reply
    assert "【" in "".join(deltas[:-1])


def test_an_answer_starting_like_the_marker_is_streamed_whole(settings):
    llm = FakeLLM(["[1] says this."])

    events = service(settings, llm).stream("Q?", RetrievalFilters())
    text = "".join(event.text for event in events if isinstance(event, TextDelta))

    assert text.strip() == "[1] says this."


def test_a_short_answer_is_not_lost_while_waiting_for_the_marker(settings):
    events = service(settings, FakeLLM(["["])).stream("Q?", RetrievalFilters())

    assert "".join(event.text for event in events if isinstance(event, TextDelta)).strip() == "["


def test_nothing_retrieved_answers_without_the_model(settings):
    llm = FakeLLM(["never used"])

    answer = ask(settings, llm, found=())

    assert answer.text == NOTHING_RETRIEVED
    assert answer.insufficient_evidence
    assert answer.generation is None
    assert llm.calls == []


def test_the_search_is_reported_first(settings):
    events = list(service(settings, FakeLLM(["Answer [1]."])).stream("Q?", RetrievalFilters()))

    assert isinstance(events[0], RetrievalResult)
    assert isinstance(events[-1], Answer)


def test_everything_needed_for_inspection_is_kept(settings):
    answer = ask(settings, FakeLLM(["Answer [1]."]))

    assert answer.retrieval.query == "What is opportunity cost?"
    assert len(answer.passages) == 1
    assert answer.messages[-1].role == "user"
    assert answer.thinking == "some reasoning"
    assert answer.generation.stats.prompt_tokens == 100
    assert answer.total_seconds >= 0


def test_filters_and_strategy_reach_the_search(settings):
    retrieval = FakeRetrieval(passages("Text."))
    filters = RetrievalFilters(book_ids=("book_002",), chapter_numbers=(4,))

    QuestionAnsweringService(settings, retrieval, ModelChoices.local_only(FakeLLM(["Answer [1]."]))).answer(
        "Q?", filters, retrieval_config=settings.retrieval
    )

    assert retrieval.calls[0] == ("Q?", filters, settings.retrieval)


def test_the_task_parameters_are_used(settings):
    llm = FakeLLM(["Answer [1]."])

    ask(settings, llm)

    parameters = llm.calls[0][1]
    assert parameters.max_tokens == settings.generation.question_answering.max_tokens
    assert parameters.temperature == settings.generation.question_answering.temperature


def test_passages_that_dont_fit_are_left_out_rather_than_cut_by_ollama(settings):
    llm = FakeLLM(["Answer [1]."], context_size=3000)
    words = " ".join(["word"] * 500)

    answer = ask(settings, llm, found=(words, words, words, words, words))

    window = 3000 * (1 - settings.generation.context.safety_margin)
    budget = window - settings.generation.question_answering.max_tokens
    sent = sum(llm.count_tokens(message.content) for message in llm.calls[0][0])
    assert len(answer.passages) == 2
    assert sent <= budget


def test_the_best_passages_are_the_ones_kept(settings):
    llm = FakeLLM(["Answer [1]."], context_size=2500)
    long_text = " ".join(["word"] * 500)

    answer = ask(settings, llm, found=(f"best {long_text}", f"second {long_text}", f"third {long_text}"))

    assert answer.passages[0].chunk.text.startswith("best")


def test_a_context_too_small_for_any_passage_needs_no_model(settings):
    llm = FakeLLM(["never used"], context_size=1600)

    answer = ask(settings, llm, found=(" ".join(["word"] * 500),))

    assert answer.text == NOTHING_RETRIEVED


def test_an_answer_is_logged_with_its_numbers_and_never_its_text(settings, tmp_path):
    configure_logging("INFO", "INFO", tmp_path / "logs", console=False)
    secret = "A question whose text must stay out of the logs"

    ask(settings, FakeLLM(["The answer text, also private [1]."]), question=secret)

    entries = [json.loads(line) for line in (tmp_path / "logs" / "app.jsonl").read_text().splitlines()]
    [event] = [entry for entry in entries if entry["message"] == "question answered"]
    assert event["operation"] == "answer_question"
    assert event["execution_id"]
    assert event["prompt_tokens"] == 100
    assert event["context_passages"] == 1
    logged = (tmp_path / "logs" / "app.jsonl").read_text()
    assert secret not in logged
    assert "also private" not in logged
    logging.getLogger("book_rag").handlers.clear()


def test_reasoning_that_consumes_the_limit_is_an_error_not_an_empty_answer(settings):
    llm = FakeLLM([""], finish_reasons=[FINISHED_BY_LENGTH])

    with pytest.raises(GenerationError, match="max_tokens"):
        ask(settings, llm)


def test_an_empty_answer_is_an_error(settings):
    with pytest.raises(GenerationError, match="without an answer"):
        ask(settings, FakeLLM(["  "]))


# An abstention written without the marker (.specify/bugs/unmarked-abstentions)

UNMARKED = "The passages say only that someone made the denunciation [1]; they don't name who."


def checking(replies=None, respond=None):
    """A model whose profile asks for the abstention check."""
    return FakeLLM(replies, respond=respond, check_abstentions=True)


def test_an_abstention_without_the_marker_is_recognized_when_the_profile_asks(settings):
    answer = ask(settings, checking([UNMARKED, "NO"]), question="Who made the denunciation?")

    assert answer.insufficient_evidence
    assert answer.text == UNMARKED
    assert [citation.number for citation in answer.citations] == [1]


def test_the_check_reads_the_question_and_the_reply_but_not_the_passages(settings):
    llm = checking([UNMARKED, "NO"])

    ask(settings, llm, question="Who made the denunciation?")

    messages, parameters = llm.calls[1]
    assert "Who made the denunciation?" in messages[-1].content
    assert UNMARKED in messages[-1].content
    assert not any("Opportunity cost is what you give up." in message.content for message in messages)
    assert parameters.temperature == 0
    assert parameters.max_tokens == llm.calls[0][1].max_tokens


def test_a_reply_the_check_reads_as_an_answer_stays_one(settings):
    answer = ask(settings, checking(["Opportunity cost is what you give up [1].", "YES"]))

    assert not answer.insufficient_evidence


@pytest.mark.parametrize("verdict", ["**No**", "no.\n\nThe reply says only that the passages don't name who.", '"NO"'])
def test_the_verdict_is_its_first_word(settings, verdict):
    assert ask(settings, checking([UNMARKED, verdict])).insufficient_evidence


@pytest.mark.parametrize("verdict", ["Maybe.", "The answer is no.", "Nope", ""])
def test_a_verdict_that_cant_be_read_leaves_the_answer(settings, verdict):
    assert not ask(settings, checking([UNMARKED, verdict])).insufficient_evidence


def test_a_failed_check_leaves_the_answer(settings):
    def respond(messages, parameters):
        if len(llm.calls) > 1:
            raise GenerationError("Ollama went away.")
        return UNMARKED

    llm = checking(respond=respond)

    answer = ask(settings, llm)

    assert not answer.insufficient_evidence
    assert answer.text == UNMARKED


def test_a_check_too_long_for_the_context_is_skipped_rather_than_cut(settings):
    llm = checking(["word " * 7000, "NO"])

    answer = ask(settings, llm)

    assert len(llm.calls) == 1
    assert not answer.insufficient_evidence


def test_no_check_is_made_unless_the_profile_asks(settings):
    llm = FakeLLM([UNMARKED, "NO"])

    answer = ask(settings, llm)

    assert len(llm.calls) == 1
    assert not answer.insufficient_evidence


def test_a_marked_reply_needs_no_check(settings):
    llm = checking([f"{NO_EVIDENCE_MARKER} The source does not cover this.", "YES"])

    answer = ask(settings, llm)

    assert answer.insufficient_evidence
    assert len(llm.calls) == 1


def test_a_skipped_check_is_logged_without_any_text(settings, tmp_path):
    configure_logging("INFO", "INFO", tmp_path / "logs", console=False)

    ask(settings, checking([UNMARKED, "Perhaps."]), question="A private question")

    logged = (tmp_path / "logs" / "app.jsonl").read_text()
    entries = [json.loads(line) for line in logged.splitlines()]
    [event] = [entry for entry in entries if entry["message"] == "abstention check skipped"]
    assert event["reason"] == "unreadable"
    assert event["level"] == "WARNING"
    assert "A private question" not in logged
    assert "someone" not in logged
    assert "Perhaps" not in logged
    logging.getLogger("book_rag").handlers.clear()


# Cloud models (specs/008-cloud-llm-providers, research.md R7)

LOCAL_ANSWER = "Opportunity cost is the next best thing given up [1]."
CLOUD_ANSWER = "It is what you give up for a choice [1]."


def local(replies=(LOCAL_ANSWER,), **options):
    return FakeLLM(list(replies), model="gpt-oss:20b", **options)


def cloud(name="fc-a", replies=(CLOUD_ANSWER,), **options):
    return FakeLLM(list(replies), model=name, provider="fakecloud", cloud=True, **options)


def choices(local_llm, *cloud_llms):
    """The local model, and FakeCloud offering each given model, scripted."""
    provider = FakeCloud(models={llm.model: llm for llm in cloud_llms})
    names = tuple(llm.model for llm in cloud_llms)
    setup = CloudSetup(providers=((provider, names),), kinds={"fakecloud": "FakeCloud"})
    return ModelChoices(local_llm, setup)


def failure(reason, model="fc-a", detail=""):
    return ModelFailedError(model, "fakecloud", reason, detail, label="FakeCloud")


def events_of(settings, models, found=PASSAGE, **options):
    return list(service(settings, models, found).stream("What is opportunity cost?", RetrievalFilters(), **options))


def test_without_a_model_the_answer_is_the_local_models_and_says_so(settings):
    local_llm, cloud_llm = local(), cloud()

    answer = ask(settings, choices(local_llm, cloud_llm))

    assert answer.text == LOCAL_ANSWER
    assert (answer.model, answer.provider, answer.attempts) == ("gpt-oss:20b", "ollama", ())
    assert cloud_llm.calls == []


def test_a_cloud_model_gets_the_passages_and_the_prompt_the_local_one_would(settings):
    found = ("First passage.", "Second passage.", "Third passage.")
    local_llm, cloud_llm = local(), cloud(reported_model="fc-a-20261101")

    by_local = ask(settings, ModelChoices.local_only(local()), found=found)
    by_cloud = ask(settings, choices(local_llm, cloud_llm), found=found, model="fc-a")

    assert [passage.chunk.chunk_id for passage in by_cloud.passages] == [
        passage.chunk.chunk_id for passage in by_local.passages
    ]
    assert by_cloud.messages == by_local.messages
    assert cloud_llm.calls[0][0] == list(by_local.messages)
    assert (by_cloud.model, by_cloud.provider, by_cloud.attempts) == ("fc-a-20261101", "fakecloud", ())
    assert by_cloud.text == CLOUD_ANSWER
    assert local_llm.calls == []


@pytest.mark.parametrize("reason", [reason for reason in FailureReason if reason is not FailureReason.NO_ANSWER])
def test_each_failure_moves_on_to_the_local_model_which_lists_it(settings, reason):
    local_llm = local()

    events = events_of(settings, choices(local_llm, cloud(fail=failure(reason, detail="why"))), model="fc-a")

    failed = [event for event in events if isinstance(event, AttemptFailed)]
    attempt = Attempt("fc-a", "fakecloud", reason, "why")
    assert failed == [AttemptFailed(attempt, "gpt-oss:20b", "ollama")]
    answer = events[-1]
    assert answer.text == LOCAL_ANSWER
    assert (answer.model, answer.provider, answer.attempts) == ("gpt-oss:20b", "ollama", (attempt,))
    assert len(local_llm.calls) == 1


def test_a_reply_without_text_is_no_answer_and_moves_on(settings):
    answer = ask(settings, choices(local(), cloud(replies=["   "])), model="fc-a")

    assert answer.text == LOCAL_ANSWER
    [attempt] = answer.attempts
    assert attempt.reason == FailureReason.NO_ANSWER
    assert attempt.detail.startswith("The model finished without an answer")


def test_a_reply_cut_off_with_text_and_an_abstention_are_answers(settings):
    cut_off = ask(settings, choices(local(), cloud(finish_reasons=[FINISHED_BY_LENGTH])), model="fc-a")
    abstained = ask(
        settings, choices(local(), cloud(replies=[f"{NO_EVIDENCE_MARKER} The passages don't say."])), model="fc-a"
    )

    assert (cut_off.model, cut_off.text, cut_off.attempts) == ("fc-a", CLOUD_ANSWER, ())
    assert (abstained.model, abstained.insufficient_evidence, abstained.attempts) == ("fc-a", True, ())


def test_text_from_a_model_that_fails_is_withdrawn_and_the_next_starts_afresh(settings):
    failing = cloud(fail=failure(FailureReason.RATE_LIMITED), text_before_failure="Opportunity cost")

    events = events_of(settings, choices(local(), failing), model="fc-a")

    kinds = [type(event).__name__ for event in events]
    assert kinds[:4] == ["RetrievalResult", "TextDelta", "TextDelta", "AttemptFailed"]
    assert [event.text for event in events[1:3]] == ["Opportunity ", "cost "]
    after = [event.text for event in events[4:] if isinstance(event, TextDelta)]
    assert "".join(after).strip() == LOCAL_ANSWER
    assert events[-1].text == LOCAL_ANSWER


def test_the_fallbacks_are_asked_in_order_before_the_local_model(settings):
    first = cloud("fc-a", fail=failure(FailureReason.OUTAGE, "fc-a", "529"))
    second = cloud("fc-b", fail=failure(FailureReason.DECLINED, "fc-b", "cyber"))
    third = cloud("fc-c")

    events = events_of(settings, choices(local(), first, second, third), model="fc-a", fallbacks=["fc-b", "fc-c"])

    failed = [(event.attempt.model, event.next_model) for event in events if isinstance(event, AttemptFailed)]
    assert failed == [("fc-a", "fc-b"), ("fc-b", "fc-c")]
    assert (events[-1].model, len(events[-1].attempts)) == ("fc-c", 2)


def test_when_the_local_model_fails_after_a_cloud_one_every_failure_is_listed(settings):
    local_llm = local(fail=ServiceUnavailableError("Ollama is not reachable at http://ollama:11434."))

    with pytest.raises(AllModelsFailedError) as failed:
        ask(settings, choices(local_llm, cloud(fail=failure(FailureReason.KEY_REFUSED))), model="fc-a")

    assert [(attempt.model, attempt.reason) for attempt in failed.value.attempts] == [
        ("fc-a", FailureReason.KEY_REFUSED),
        ("gpt-oss:20b", FailureReason.UNREACHABLE),
    ]
    assert str(failed.value) == (
        "No model could answer. fc-a (FakeCloud) failed: it refused the API key. "
        "gpt-oss:20b (local) failed: Ollama is not reachable at http://ollama:11434."
    )


def test_the_local_model_failing_alone_raises_its_own_error(settings):
    with pytest.raises(ServiceUnavailableError, match="Ollama is down"):
        ask(settings, choices(local(fail=ServiceUnavailableError("Ollama is down.")), cloud()))


def test_a_refused_sequence_stops_before_the_search(settings):
    retrieval = FakeRetrieval(passages(*PASSAGE))
    questions = QuestionAnsweringService(settings, retrieval, choices(local(), cloud()))

    with pytest.raises(ModelChoiceError, match="fc-x isn't offered"):
        next(questions.stream("Q?", RetrievalFilters(), model="fc-x"))

    assert retrieval.calls == []


def test_with_nothing_retrieved_no_model_is_called(settings):
    local_llm, cloud_llm = local(), cloud()

    answer = ask(settings, choices(local_llm, cloud_llm), found=(), model="fc-a")

    assert answer.text == NOTHING_RETRIEVED
    assert (answer.model, answer.provider, answer.attempts) == ("fc-a", "fakecloud", ())
    assert cloud_llm.calls == [] and local_llm.calls == []


def test_a_cloud_model_whose_profile_asks_reads_its_own_reply_again(settings):
    local_llm, cloud_llm = local(), cloud(replies=[UNMARKED, "NO"], check_abstentions=True)

    answer = ask(settings, choices(local_llm, cloud_llm), model="fc-a")

    assert answer.insufficient_evidence
    assert len(cloud_llm.calls) == 2 and local_llm.calls == []


def test_the_failures_and_the_answer_are_logged_without_the_question(settings, tmp_path):
    configure_logging("INFO", "INFO", tmp_path / "logs", console=False)
    try:
        ask(
            settings,
            choices(local(), cloud(fail=failure(FailureReason.RATE_LIMITED))),
            question="A private question",
            model="fc-a",
        )
    finally:
        for name in ("book_rag", INFERENCE_LOGGER):
            for handler in logging.getLogger(name).handlers:
                handler.close()
            logging.getLogger(name).handlers.clear()

    logged = (tmp_path / "logs" / "app.jsonl").read_text()
    entries = [json.loads(line) for line in logged.splitlines()]
    [failed] = [entry for entry in entries if entry["message"] == "model failed"]
    assert (failed["provider"], failed["model"], failed["reason"], failed["position"]) == (
        "fakecloud",
        "fc-a",
        "rate limited",
        1,
    )
    [answered] = [entry for entry in entries if entry["message"] == "question answered"]
    assert (answered["model"], answered["provider"], answered["failed_attempts"]) == ("gpt-oss:20b", "ollama", 1)
    assert answered["execution_id"] == failed["execution_id"]
    assert "A private question" not in logged


# Sequences of fallbacks (specs/008-cloud-llm-providers, US3, SC-006)


def test_a_working_fallback_answers_and_the_local_model_isnt_called(settings):
    local_llm = local()
    unknown = cloud("fc-a", fail=failure(FailureReason.UNKNOWN_MODEL, "fc-a"))

    answer = ask(settings, choices(local_llm, unknown, cloud("fc-b")), model="fc-a", fallbacks=["fc-b"])

    assert (answer.model, [attempt.model for attempt in answer.attempts]) == ("fc-b", ["fc-a"])
    assert local_llm.calls == []


def test_when_every_fallback_fails_the_local_model_answers_listing_them_in_order(settings):
    first = cloud("fc-a", fail=failure(FailureReason.UNKNOWN_MODEL, "fc-a"))
    second = cloud("fc-b", fail=failure(FailureReason.UNKNOWN_MODEL, "fc-b"))

    answer = ask(settings, choices(local(), first, second), model="fc-a", fallbacks=["fc-b"])

    assert answer.model == "gpt-oss:20b"
    assert [(attempt.model, attempt.reason) for attempt in answer.attempts] == [
        ("fc-a", FailureReason.UNKNOWN_MODEL),
        ("fc-b", FailureReason.UNKNOWN_MODEL),
    ]
