"""A cloud provider kind: what the container builds once from a provider's settings and its profile.

Each kind is registered in one place, `CLOUD_PROVIDERS` in `app/container.py`, under the name that
prefixes its settings (`ANTHROPIC_API_KEY`, `ANTHROPIC_MODELS`) and keys its profile in
`cloud_profiles` (specs/008-cloud-llm-providers, research.md R3).
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import ClassVar, Protocol

from app.config.settings import CloudProfile, ProviderCredentials
from app.generation.base import LLMProvider


@dataclass(frozen=True)
class ProviderCheck:
    """A row of a provider's check, which the health checks show as their own.

    Attributes:
        name: what was checked: the provider, or the provider and one of its models.
        ok: whether it passed.
        detail: what was found, or what is wrong. Never the key.
    """

    name: str
    ok: bool
    detail: str


class CloudProvider(Protocol):
    """A provider kind, built from its credentials and its profile. Building it contacts nothing.

    Attributes:
        name: "anthropic": its profile's key, and its settings' prefix.
        label: "Anthropic", as the interface shows it.
    """

    name: ClassVar[str]
    label: ClassVar[str]

    def __init__(self, credentials: ProviderCredentials, profile: CloudProfile) -> None: ...

    def model(self, name: str) -> LLMProvider:
        """The provider of one allowed model. Contacts nothing."""
        ...

    def check(self, models: Sequence[str]) -> list[ProviderCheck]:
        """Check the key and each model: sends the key and the models' names, and runs no inference."""
        ...
