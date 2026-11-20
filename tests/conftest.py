import shutil
from collections.abc import Callable
from pathlib import Path

import pytest
import yaml

from app.config.loader import load_settings
from app.config.settings import Settings
from tests.fakes import FakeOpenAIClient

PROJECT_CONFIG = Path(__file__).resolve().parents[1] / "config"


@pytest.fixture
def settings() -> Settings:
    return load_settings(PROJECT_CONFIG)


@pytest.fixture
def config_dir(tmp_path: Path) -> Path:
    """A private copy of config/ that a test can edit."""
    target = tmp_path / "config"
    shutil.copytree(PROJECT_CONFIG, target)
    return target


@pytest.fixture
def edit_config(config_dir: Path) -> Callable[[str, Callable[[dict], None]], None]:
    """Change one file of the private config/ copy through a function on its parsed content."""

    def edit(name: str, change: Callable[[dict], None]) -> None:
        path = config_dir / name
        content = yaml.safe_load(path.read_text(encoding="utf-8"))
        change(content)
        path.write_text(yaml.safe_dump(content), encoding="utf-8")

    return edit


@pytest.fixture
def openai_client(monkeypatch: pytest.MonkeyPatch) -> FakeOpenAIClient:
    """The client that every OpenAI provider the test builds gets, as the container builds them.

    It replaces `openai.OpenAI`, which the provider calls, records the client's options, and is
    scripted by the test (specs/009, research.md R11).
    """
    import openai

    client = FakeOpenAIClient()
    monkeypatch.setattr(openai, "OpenAI", client.factory)
    return client
