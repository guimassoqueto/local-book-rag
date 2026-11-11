from app.config.settings import EnvironmentSettings
from app.container import assemble


def test_the_quiz_checker_reasons_at_its_own_level_on_the_writers_model(settings, tmp_path):
    container = assemble(settings, EnvironmentSettings(data_dir=tmp_path))

    writer = container.quizzes._writer
    assert writer.model == writer.checker_model == settings.llm.model
    assert writer._llm._profile.reasoning == settings.llm_profile.reasoning
    assert writer._checker._profile.reasoning == settings.generation.quiz.check.reasoning
    assert writer._checker is not writer._llm


def test_a_checker_model_of_its_own_gets_its_own_profile(settings, tmp_path):
    quiz = settings.generation.quiz
    check = quiz.check.model_copy(update={"model": "qwen3:14b"})
    generation = settings.generation.model_copy(update={"quiz": quiz.model_copy(update={"check": check})})

    container = assemble(settings.model_copy(update={"generation": generation}), EnvironmentSettings(data_dir=tmp_path))

    assert container.quizzes._writer.checker_model == "qwen3:14b"


def test_quiz_downloads_go_to_the_data_directory(settings, tmp_path):
    assemble(settings, EnvironmentSettings(data_dir=tmp_path))

    assert (tmp_path / "quiz_downloads").is_dir()
