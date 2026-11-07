from app.ingestion.language import question_language


def test_a_question_is_named_in_its_language():
    assert question_language("Por que Rubião enlouquece no fim do romance?") == "Portuguese"
    assert question_language("Why does Mill defend the liberty of thought and discussion?") == "English"


def test_no_language_is_named_when_it_would_be_a_guess():
    assert question_language("Why?") is None
    assert question_language("What does ao vencedor, as batatas mean?") is None


def test_a_language_without_a_name_here_is_left_to_the_model():
    assert question_language("Wat zegt Mill over de vrijheid van meningsuiting?") is None
