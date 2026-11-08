import pytest

from app.config.settings import TokenizerConfig
from app.utils import tokenization
from app.utils.tokenization import HuggingFaceCounter, TiktokenCounter, create_token_counter


class FakeTokenizer:
    def encode(self, text, add_special_tokens):
        return type("Encoding", (), {"ids": text.split()})()


@pytest.fixture
def downloads(monkeypatch):
    """Record each hub lookup, with the cache holding nothing until the network was used."""
    calls = []
    cached = []

    def download(repository, filename, local_files_only=False):
        calls.append(local_files_only)
        if local_files_only and not cached:
            raise tokenization.LocalEntryNotFoundError("not cached")
        cached.append(filename)
        return "/cache/tokenizer.json"

    monkeypatch.setattr(tokenization, "hf_hub_download", download)
    monkeypatch.setattr(tokenization.Tokenizer, "from_file", lambda path: FakeTokenizer())
    return calls


def test_the_first_use_downloads_the_tokenizer(downloads):
    assert HuggingFaceCounter("org/model").count("two words") == 2
    assert downloads == [True, False]


def test_later_uses_never_reach_the_network(downloads):
    HuggingFaceCounter("org/model").count("first")
    downloads.clear()

    HuggingFaceCounter("org/model").count("second")

    assert downloads == [True]


def test_creating_a_counter_downloads_nothing(downloads):
    create_token_counter(TokenizerConfig(kind="huggingface", name="org/model"))

    assert downloads == []


def test_the_configuration_picks_the_implementation():
    assert isinstance(create_token_counter(TokenizerConfig(kind="tiktoken", name="o200k_base")), TiktokenCounter)
