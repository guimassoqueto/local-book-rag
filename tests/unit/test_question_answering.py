import pytest

from app.errors import GenerationError
from app.generation.base import FINISHED_BY_LENGTH, TextDelta
from app.generation.prompts import NO_EVIDENCE_MARKER
from app.generation.question_answering import NOTHING_RETRIEVED, Answer, QuestionAnsweringService
from app.retrieval.base import Passage, RetrievalFilters
from app.retrieval.pipeline import RetrievalResult
from tests.fakes import FakeLLM, make_chunk

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
        Passage(make_chunk(text, index=index, chapter=4, section="Costs", page_start=85 + index), rerank_score=0.9)
        for index, text in enumerate(texts)
    ]


def service(settings, llm, found=PASSAGE):
    return QuestionAnsweringService(settings, FakeRetrieval(passages(*found)), llm)


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
    assert citation.page_start == 85
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
    assert "[1] Book: Title | Chapter: Chapter 4 | Section: Costs | Pages: 85-85" in prompt
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


def test_formats_without_pages_leave_them_out(settings):
    chunk = make_chunk("Text.", section=None)
    llm = FakeLLM(["Answer [1]."])

    QuestionAnsweringService(settings, FakeRetrieval([Passage(chunk)]), llm).answer("Q?", RetrievalFilters())

    assert "Pages" not in user_message(llm)
    assert "Section" not in user_message(llm)


def test_the_language_follows_the_question_by_default(settings):
    llm = FakeLLM(["Answer [1]."])

    ask(settings, llm)

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


def test_the_marker_never_reaches_the_reader_while_streaming(settings):
    llm = FakeLLM([f"{NO_EVIDENCE_MARKER} The source does not cover this."])

    events = service(settings, llm).stream("Q?", RetrievalFilters())
    text = "".join(event.text for event in events if isinstance(event, TextDelta))

    assert NO_EVIDENCE_MARKER not in text
    assert "The source does not cover this." in text


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

    QuestionAnsweringService(settings, retrieval, FakeLLM(["Answer [1]."])).answer(
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


def test_reasoning_that_consumes_the_limit_is_an_error_not_an_empty_answer(settings):
    llm = FakeLLM([""], finish_reasons=[FINISHED_BY_LENGTH])

    with pytest.raises(GenerationError, match="max_tokens"):
        ask(settings, llm)


def test_an_empty_answer_is_an_error(settings):
    with pytest.raises(GenerationError, match="without an answer"):
        ask(settings, FakeLLM(["  "]))
