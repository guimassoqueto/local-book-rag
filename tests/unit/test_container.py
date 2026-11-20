from app.config.settings import EnvironmentSettings
from app.container import assemble


def test_the_container_builds_one_provider_for_the_configured_model(settings, tmp_path):
    container = assemble(settings, EnvironmentSettings(data_dir=tmp_path))

    llm = container.questions._llm
    assert llm is container.summaries._llm
    assert llm.model == settings.llm.model
    assert llm._profile == settings.llm_profile
