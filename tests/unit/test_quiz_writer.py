import json

import pytest

from app.config.settings import QuizConfig
from app.generation.base import Generation
from app.generation.prompts import QuizSource, quiz_answer_messages, quiz_check_messages, quiz_question_messages
from app.generation.quiz import (
    CheckVerdict,
    Draft,
    PassedOver,
    QuizWriter,
    Refusal,
    Skip,
    read_answer,
    read_check,
    read_draft,
)
from tests.fakes import FakeLLM, make_chunk, make_stats

PORTUGUESE_DRAFT = {
    "question": "Segundo o autor, por que a Revolução Industrial começou na Grã-Bretanha?",
    "correct": "Porque os salários altos e a energia barata tornaram as máquinas lucrativas.",
    "wrong": [
        "Porque a escassez de carvão obrigou os ingleses a importar tecnologia.",
        "Porque o comércio com a Ásia trouxe máquinas prontas para a ilha.",
        "Porque a abundância de crédito barato financiou as guerras do continente.",
        "Porque as guerras napoleônicas destruíram a indústria dos concorrentes.",
    ],
    "explanation": "O autor explica que salários altos e energia barata tornaram lucrativo inventar máquinas.",
}

SPANISH_DRAFT = {
    "question": "Según el autor, ¿por qué la Revolución Industrial comenzó en Gran Bretaña?",
    "correct": "Porque los salarios altos y la energía barata hicieron rentables las máquinas.",
    "wrong": [
        "Porque la escasez de carbón obligó a los ingleses a importar tecnología.",
        "Porque el comercio con Asia trajo máquinas listas para la isla.",
        "Porque la abundancia de crédito barato financió las guerras del continente.",
        "Porque las guerras napoleónicas destruyeron la industria de los competidores.",
    ],
    "explanation": "El autor explica que los salarios altos y la energía barata hicieron rentable inventar máquinas.",
}


def generation(text, finish="stop"):
    return Generation(text, "", make_stats(finish_reason=finish))


def draft_reply(**changes):
    return json.dumps(PORTUGUESE_DRAFT | changes, ensure_ascii=False)


def read(text, finish="stop", language="Portuguese", titles=()):
    return read_draft(generation(text, finish), language, titles)


def with_option(option, field="correct"):
    if field == "correct":
        return read(draft_reply(correct=option))
    return read(draft_reply(wrong=[option, *PORTUGUESE_DRAFT["wrong"][1:]]))


# read_draft: reading


@pytest.mark.parametrize(
    "text",
    [
        draft_reply(),
        f"```json\n{draft_reply()}\n```",
        f"Aqui está a questão:\n{draft_reply()}\nBoa sorte!",
    ],
)
def test_a_draft_is_read_alone_in_fences_or_among_text(text):
    draft = read(text)

    assert isinstance(draft, Draft)
    assert draft.question == PORTUGUESE_DRAFT["question"]
    assert draft.correct == PORTUGUESE_DRAFT["correct"]
    assert draft.wrong == tuple(PORTUGUESE_DRAFT["wrong"])
    assert draft.explanation == PORTUGUESE_DRAFT["explanation"]


def test_a_skip_is_read_with_its_reason():
    assert read('{"skip": "Só lista referências bibliográficas."}') == Skip("Só lista referências bibliográficas.")


@pytest.mark.parametrize("text", ["Não consigo escrever uma questão.", '{"question": "Por que', "[1, 2, 3]", ""])
def test_a_reply_without_an_object_is_unreadable(text):
    assert read(text) == Refusal("unreadable")


def test_a_reply_stopped_at_its_limit_is_cut_off_whatever_it_holds():
    assert read(draft_reply(), finish="length") == Refusal("cut_off")


@pytest.mark.parametrize("field", ["question", "correct", "explanation"])
@pytest.mark.parametrize("value", ["", "   ", None])
def test_a_blank_or_missing_field_is_refused(field, value):
    content = dict(PORTUGUESE_DRAFT)
    if value is None:
        del content[field]
    else:
        content[field] = value

    assert read(json.dumps(content)).kind == "blank_field"


@pytest.mark.parametrize("count", [3, 5])
def test_anything_but_four_wrong_answers_is_refused(count):
    wrong = (PORTUGUESE_DRAFT["wrong"] * 2)[:count]
    wrong = [f"{answer} ({position})" for position, answer in enumerate(wrong)]

    assert read(draft_reply(wrong=wrong)).kind == "wrong_count"


def test_an_empty_extra_wrong_answer_is_no_answer():
    draft = read(draft_reply(wrong=[*PORTUGUESE_DRAFT["wrong"], ""]))

    assert isinstance(draft, Draft)
    assert draft.wrong == tuple(PORTUGUESE_DRAFT["wrong"])


def test_a_blank_among_four_wrong_answers_leaves_three():
    assert read(draft_reply(wrong=[*PORTUGUESE_DRAFT["wrong"][:3], "  "])).kind == "wrong_count"


@pytest.mark.parametrize(
    "repeat",
    [
        PORTUGUESE_DRAFT["correct"].upper(),
        PORTUGUESE_DRAFT["correct"].replace(" ", "   "),
        PORTUGUESE_DRAFT["correct"].rstrip("."),
    ],
)
def test_two_options_with_the_same_text_are_refused(repeat):
    assert with_option(repeat, field="wrong").kind == "repeated_option"


# read_draft: options that depend on the others (FR-009)


@pytest.mark.parametrize(
    "option",
    ["Todas as anteriores", "None of the above.", "Ninguna de las anteriores", "Both A and B", "A opção C", "A e B"],
)
def test_an_option_referring_to_the_others_is_refused(option):
    assert with_option(option, field="wrong").kind == "cross_reference"


@pytest.mark.parametrize(
    "option",
    [
        "A falta de vitamina A na dieta dos trabalhadores urbanos.",
        "A economia britânica cresceu com a energia barata das minas.",
        "Keine der Kolonien war vor 1800 unabhängig.",
    ],
)
def test_a_letter_or_an_article_alone_is_no_cross_reference(option):
    assert isinstance(with_option(option, field="wrong"), Draft)


# read_draft: questions that point to where their answer is (FR-004)


@pytest.mark.parametrize(
    "question",
    [
        "Segundo o trecho, por que a indústria cresceu?",
        "De acordo com a passagem 2, por que a indústria cresceu?",
        "O que diz o trecho 3 sobre a indústria?",
        "According to the passage, why did industry grow?",
        "Why, in the passage, did industry grow?",
        "What does page 12 say about industry?",
        "O que o autor afirma na página 12 sobre a indústria?",
        "O que o texto acima diz sobre a indústria?",
        "Según el fragmento, ¿por qué creció la industria?",
        "Selon le passage, pourquoi l'industrie a-t-elle grandi ?",
        "O que Palha decide ao fim do trecho?",
        "O que o autor conclui no final do texto?",
    ],
)
def test_a_question_pointing_to_its_passage_is_refused(question):
    assert read(draft_reply(question=question)).kind == "passage_reference"


def test_an_option_pointing_to_its_passage_is_refused():
    assert with_option("O trecho 2 não diz nada sobre salários.", field="wrong").kind == "passage_reference"


def test_the_explanation_may_point_to_the_passage():
    explanation = "Segundo o trecho, salários altos e energia barata tornaram lucrativo inventar máquinas."

    assert isinstance(read(draft_reply(explanation=explanation)), Draft)


@pytest.mark.parametrize(
    "question",
    [
        "Por que o trecho da ferrovia entre Londres e Birmingham foi o mais lucrativo?",
        "What did the passage of the Reform Act change?",
        "Por que, segundo o autor, a indústria cresceu?",
        "Neste capítulo, por que o autor diz que a indústria cresceu?",
    ],
)
def test_words_for_a_passage_without_a_pointer_pass(question):
    assert isinstance(read(draft_reply(question=question)), Draft)


@pytest.mark.parametrize(
    "question",
    [
        "Na seção “Salários reais”, o que o autor compara?",
        'O que a seção "Salários reais" compara?',
        "Na seção Salários reais, o que o autor compara?",
    ],
)
def test_a_question_naming_its_section_is_refused(question):
    assert read(draft_reply(question=question), titles=("Salários reais",)).kind == "passage_reference"


def test_a_section_title_used_as_an_ordinary_phrase_passes():
    question = "Por que os salários reais de Londres superavam os de Beijing, segundo o autor?"

    assert isinstance(read(draft_reply(question=question), titles=("Salários reais",)), Draft)


@pytest.mark.parametrize(
    "question",
    [
        "O que o Capítulo 3: A Revolução Industrial diz sobre o algodão?",
        "No capítulo 3, por que o algodão importava?",
        "No capítulo “A Revolução Industrial”, por que o algodão importava?",
    ],
)
def test_a_question_naming_its_chapter_is_refused_when_the_title_is_forbidden(question):
    titles = ("Capítulo 3: A Revolução Industrial",)

    assert read(draft_reply(question=question), titles=titles).kind == "passage_reference"


def test_the_chapter_may_be_named_when_its_title_is_not_forbidden():
    question = "No capítulo 3, por que o algodão importava?"

    assert isinstance(read(draft_reply(question=question)), Draft)


def test_a_topic_that_is_also_a_chapter_title_passes():
    question = "Segundo o autor, por que a Revolução Industrial começou na Grã-Bretanha?"

    assert isinstance(read(draft_reply(question=question), titles=("Capítulo 3: A Revolução Industrial",)), Draft)


# read_draft: language (FR-003)


def test_a_draft_in_another_language_than_the_one_named_is_refused():
    assert read(json.dumps(SPANISH_DRAFT, ensure_ascii=False)).kind == "wrong_language"


def test_a_draft_in_the_named_language_passes():
    assert isinstance(read(json.dumps(SPANISH_DRAFT, ensure_ascii=False), language="Spanish"), Draft)


def test_a_short_ambiguous_draft_passes():
    content = {
        "question": "Quem?",
        "correct": "Ricardo",
        "wrong": ["Smith", "Marx", "Mill", "Hume"],
        "explanation": "Ricardo.",
    }

    assert isinstance(read(json.dumps(content)), Draft)


def test_a_language_the_reader_cannot_identify_is_not_checked():
    assert isinstance(read(draft_reply(), language="Dutch"), Draft)


# read_check (the checker)


@pytest.mark.parametrize("supported", [["C"], ["C", "C"], ["C", "x"], ["c"]])
def test_a_verdict_supporting_only_the_key_accepts(supported):
    verdict = read_check(json.dumps({"supported": supported}), "C")

    assert verdict == CheckVerdict(supported=("C",), accepted=True, readable=True)


@pytest.mark.parametrize("supported", [[], ["B"], ["B", "C"]])
def test_a_verdict_supporting_anything_else_rejects(supported):
    verdict = read_check(json.dumps({"supported": supported}), "C")

    assert verdict.readable
    assert not verdict.accepted
    assert verdict.supported == tuple(supported)


@pytest.mark.parametrize("text", ['{"answer": "C"}', '{"supported": "C"}', "C", "The passage supports C."])
def test_a_verdict_without_a_list_is_unreadable(text):
    assert read_check(text, "C") == CheckVerdict(supported=(), accepted=False, readable=False)


# read_answer (the comparator)


@pytest.mark.parametrize("text", ['{"answer": "c"}', '{"answer": " C "}', 'A resposta é:\n{"answer": "C"}'])
def test_an_answer_is_read_from_its_object(text):
    assert read_answer(text) == "C"


@pytest.mark.parametrize("text", ["A resposta é C", '{"answer": "F"}', '{"answer": "C e D"}', '{"letter": "C"}'])
def test_an_answer_outside_its_object_or_not_a_letter_is_unreadable(text):
    assert read_answer(text) is None


# The messages (contracts/model-replies.md)

CHUNK = make_chunk(
    text="Wages were high in Britain and energy was cheap.",
    section="Salários reais",
    page_start=12,
    page_end=13,
    index=7,
)
SOURCE = QuizSource(
    book_title="História econômica global", author="Robert C. Allen", chapter_title="A grande divergência"
)


def text_of(messages):
    return "\n".join(message.content for message in messages)


def test_the_writer_gets_the_passage_under_the_book_without_pointers():
    text = text_of(quiz_question_messages(CHUNK.text, SOURCE, "Portuguese"))

    assert CHUNK.text in text
    assert "História econômica global" in text
    assert "Robert C. Allen" in text
    assert "Salários reais" not in text
    assert "12" not in text
    assert "[1]" not in text
    assert "[8]" not in text


def test_the_chapter_title_goes_only_into_a_one_chapter_quiz():
    one_chapter = text_of(quiz_question_messages(CHUNK.text, SOURCE, "Portuguese"))
    whole_book_source = QuizSource(SOURCE.book_title, SOURCE.author, None)
    whole_book = text_of(quiz_question_messages(CHUNK.text, whole_book_source, "Portuguese"))

    assert "A grande divergência" in one_chapter
    assert "A grande divergência" not in whole_book
    assert "chapter" in whole_book.casefold()  # told not to name it


def test_the_writer_is_told_the_language_by_name():
    assert "in Portuguese" in text_of(quiz_question_messages(CHUNK.text, SOURCE, "Portuguese"))


def test_the_writer_gets_the_rules_and_the_reply_format_without_sample_values():
    text = text_of(quiz_question_messages(CHUNK.text, SOURCE, "Portuguese"))

    for field in ('"question"', '"correct"', '"wrong"', '"explanation"', '"skip"'):
        assert field in text
    assert "all of the above" in text
    assert "the author" in text
    assert "four wrong answers" in text
    assert '": "' not in text  # a key followed by a value would be a sample


def test_the_checker_and_the_comparator_get_lettered_options():
    options = ("um", "dois", "três", "quatro", "cinco")

    check = text_of(quiz_check_messages(CHUNK.text, SOURCE, "Qual?", options))
    with_passage = text_of(quiz_answer_messages("Qual?", options, CHUNK.text, SOURCE))
    without_passage = text_of(quiz_answer_messages("Qual?", options, None, SOURCE))

    for text in (check, with_passage, without_passage):
        assert "A) um" in text
        assert "E) cinco" in text
    assert '"supported"' in check
    assert '"answer"' in with_passage
    assert CHUNK.text in check
    assert CHUNK.text in with_passage
    assert CHUNK.text not in without_passage


# QuizWriter


def writer(llm, checker=None, **config):
    return QuizWriter(QuizConfig(**config), safety_margin=0.1, llm=llm, checker=checker)


def test_the_writer_writes_with_the_quiz_parameters_and_the_seed():
    llm = FakeLLM(replies=[draft_reply()])

    result = writer(llm).write(CHUNK, SOURCE, "Portuguese", seed=7)

    assert isinstance(result, Draft)
    parameters = llm.calls[0][1]
    assert (parameters.temperature, parameters.max_tokens, parameters.seed) == (0.2, 1500, 7)


def test_the_writer_forbids_the_passage_section_and_the_titles_it_is_given():
    question = "Na seção “Salários reais”, o que o autor compara?"
    llm = FakeLLM(replies=[draft_reply(question=question)])

    assert writer(llm).write(CHUNK, SOURCE, "Portuguese").kind == "passage_reference"


def test_a_passage_too_long_for_the_window_is_passed_over_before_sending():
    llm = FakeLLM(replies=[draft_reply()], context_size=2000)
    long_chunk = make_chunk(text="palavra " * 400)

    result = writer(llm).write(long_chunk, SOURCE, "Portuguese")

    assert isinstance(result, PassedOver)
    assert not isinstance(result, Refusal)
    assert llm.calls == []


def test_the_check_runs_on_the_checkers_provider_at_temperature_zero():
    llm = FakeLLM(replies=["unused"])
    checker = FakeLLM(replies=['{"supported": ["B"]}'])

    verdict = writer(llm, checker).check("Qual?", ("a", "b", "c", "d", "e"), "B", CHUNK, SOURCE, seed=3)

    assert verdict.accepted
    assert llm.calls == []
    parameters = checker.calls[0][1]
    assert (parameters.temperature, parameters.max_tokens, parameters.seed) == (0, 2000, 3)


def test_an_unreadable_verdict_is_asked_again_once_by_sampling():
    checker = FakeLLM(replies=["Não sei.", '{"supported": ["B"]}'])

    verdict = writer(FakeLLM(replies=["x"]), checker).check("Qual?", ("a", "b", "c", "d", "e"), "B", CHUNK, SOURCE)

    assert verdict.accepted
    assert [call[1].temperature for call in checker.calls] == [0, 0.5]


def test_a_verdict_unreadable_twice_is_reported_unreadable():
    checker = FakeLLM(replies=["Não sei."])

    verdict = writer(FakeLLM(replies=["x"]), checker).check(
        "Qual?", ("a", "b", "c", "d", "e"), "B", CHUNK, SOURCE, seed=3
    )

    assert not verdict.readable
    assert len(checker.calls) == 2
    assert checker.calls[1][1].seed != 3


def test_the_comparator_answers_on_the_writers_provider_at_temperature_zero():
    llm = FakeLLM(replies=['{"answer": "D"}'])

    answer = writer(llm).answer("Qual?", ("a", "b", "c", "d", "e"), None, SOURCE)

    assert answer == "D"
    assert llm.calls[0][1].temperature == 0
