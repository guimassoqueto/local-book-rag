"""A cloud provider kind: what the container builds once from a provider's settings and its profile.

Each kind is registered in one place, `CLOUD_PROVIDERS` in `app/container.py`, under the name that
prefixes its settings (`ANTHROPIC_API_KEY`, `ANTHROPIC_MODELS`; `OPENAI_API_KEY`, `OPENAI_MODELS`)
and keys its profile in `cloud_profiles` (specs/008-cloud-llm-providers, research.md R3). The
retry rules that every provider follows live here too (specs/009-openai-provider, research.md R9).
"""

from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from typing import ClassVar, Protocol

from app.config.settings import CloudProfile, ProviderCredentials
from app.generation.base import FailureReason, LLMProvider

# A rate limit, an overload or a lost connection is tried again, before anything has streamed,
# after each of these waits. A timeout never is: the profile's timeout is the longest wait.
RETRY_WAITS = (2.0, 6.0)
RETRIED = frozenset({FailureReason.RATE_LIMITED, FailureReason.OUTAGE, FailureReason.UNREACHABLE})
# The provider's retry-after replaces a wait only when it is shorter than this.
LONGEST_RETRY_AFTER = 10.0


def retry_wait(headers: Mapping[str, str] | None, reason: FailureReason, waits: Iterator[float]) -> float | None:
    """How long to wait before trying again, or None when the failure is final.

    Args:
        headers: the failed response's headers, for its retry-after; None without a response.
        reason: why the request failed.
        waits: what is left of RETRY_WAITS for this request.
    """
    if reason not in RETRIED:
        return None
    wait = next(waits, None)
    if wait is None:
        return None
    retry_after = headers.get("retry-after") if headers is not None else None
    try:
        seconds = float(retry_after) if retry_after is not None else None
    except ValueError:
        seconds = None
    return seconds if seconds is not None and 0 <= seconds < LONGEST_RETRY_AFTER else wait


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
        efforts: the reasoning efforts its profile may hold, None meaning that it sends none. A
            profile with another one stops the app at startup (specs/009, research.md R6).
    """

    name: ClassVar[str]
    label: ClassVar[str]
    efforts: ClassVar[frozenset[str | None]]

    def __init__(self, credentials: ProviderCredentials, profile: CloudProfile) -> None: ...

    def model(self, name: str) -> LLMProvider:
        """The provider of one allowed model. Contacts nothing."""
        ...

    def check(self, models: Sequence[str]) -> list[ProviderCheck]:
        """Check the key and each model: sends the key and the models' names, and runs no inference."""
        ...
