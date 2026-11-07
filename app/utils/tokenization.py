"""Token counting. Each model family counts differently, so the model's profile picks the tokenizer."""

from functools import cached_property
from typing import Protocol

import tiktoken
from huggingface_hub import hf_hub_download
from huggingface_hub.errors import LocalEntryNotFoundError
from tokenizers import Tokenizer

from app.config.settings import TokenizerConfig

_TOKENIZER_FILE = "tokenizer.json"


class TokenCounter(Protocol):
    def count(self, text: str) -> int: ...


class TiktokenCounter:
    """Loads its encoding on first use: the first load may need a download."""

    def __init__(self, encoding: str) -> None:
        self._name = encoding

    @cached_property
    def _encoding(self) -> tiktoken.Encoding:
        return tiktoken.get_encoding(self._name)

    def count(self, text: str) -> int:
        return len(self._encoding.encode(text, disallowed_special=()))


class HuggingFaceCounter:
    """Loads its tokenizer on first use. Only the very first load reaches the network."""

    def __init__(self, repository: str) -> None:
        self._repository = repository

    @cached_property
    def _tokenizer(self) -> Tokenizer:
        try:
            path = hf_hub_download(self._repository, _TOKENIZER_FILE, local_files_only=True)
        except LocalEntryNotFoundError:
            path = hf_hub_download(self._repository, _TOKENIZER_FILE)
        return Tokenizer.from_file(path)

    def count(self, text: str) -> int:
        return len(self._tokenizer.encode(text, add_special_tokens=False).ids)


def create_token_counter(config: TokenizerConfig) -> TokenCounter:
    match config.kind:
        case "tiktoken":
            return TiktokenCounter(config.name)
        case "huggingface":
            return HuggingFaceCounter(config.name)
