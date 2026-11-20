"""The models a request may go to, and the rules of a sequence (specs/008, research.md R6)."""

import pytest

from app.config.settings import CloudProfile, TokenizerConfig
from app.errors import ModelChoiceError
from app.generation.choices import ModelChoices, ModelOption
from app.generation.cloud import ProviderCheck
from app.generation.factory import create_cloud_providers
from tests.fakes import FakeCloud, FakeLLM

PROFILE = CloudProfile(
    tokenizer=TokenizerConfig(kind="tiktoken", name="o200k_base"),
    context_size=65536,
    reasoning="low",
    reasoning_tokens=4000,
    request_timeout_seconds=120,
)
KINDS = {"fakecloud": FakeCloud}
OFFERED = "Offered: gpt-oss:20b (local), fc-a (FakeCloud), fc-b (FakeCloud), fc-c (FakeCloud)."


def local_llm():
    return FakeLLM(["A local answer [1]."], model="gpt-oss:20b")


def with_profile(settings):
    return settings.model_copy(update={"cloud_profiles": {"fakecloud": PROFILE}})


def make_choices(settings, environ=None, kinds=KINDS):
    """Choices from the local model and FakeCloud, offered with fc-a, fc-b and fc-c unless told otherwise."""
    if environ is None:
        environ = {"FAKECLOUD_API_KEY": "fake-key", "FAKECLOUD_MODELS": "fc-a, fc-b, fc-c"}
    return ModelChoices(local_llm(), create_cloud_providers(with_profile(settings), environ, kinds))


def the_cloud(choices):
    [(cloud, _)] = choices.cloud_setup.providers
    return cloud


# What is offered


def test_the_local_model_comes_first_then_the_allowed_models_in_their_order(settings):
    choices = make_choices(settings)

    assert choices.offered() == [
        ModelOption("gpt-oss:20b", "ollama", "local", True),
        ModelOption("fc-a", "fakecloud", "FakeCloud", False),
        ModelOption("fc-b", "fakecloud", "FakeCloud", False),
        ModelOption("fc-c", "fakecloud", "FakeCloud", False),
    ]
    assert choices.has_cloud()


def test_without_cloud_models_only_the_local_one_is_offered(settings):
    choices = ModelChoices.local_only(local_llm())

    assert choices.offered() == [ModelOption("gpt-oss:20b", "ollama", "local", True)]
    assert not choices.has_cloud()


# Sequences


def test_no_model_or_the_local_one_is_the_local_model_alone(settings):
    choices = make_choices(settings)

    assert choices.sequence(None, ()) == [choices.local]
    assert choices.sequence("gpt-oss:20b", ()) == [choices.local]


def test_a_cloud_model_is_followed_by_the_local_one(settings):
    choices = make_choices(settings)

    [cloud, local] = choices.sequence("fc-b", ())

    assert (cloud.model, cloud.provider) == ("fc-b", "fakecloud")
    assert local is choices.local


def test_the_fallbacks_come_in_order_between_them(settings):
    choices = make_choices(settings)

    sequence = choices.sequence("fc-c", ["fc-a", "fc-b"])

    assert [llm.model for llm in sequence] == ["fc-c", "fc-a", "fc-b", "gpt-oss:20b"]


@pytest.mark.parametrize(
    ("model", "fallbacks", "problem"),
    [
        ("fc-x", [], "fc-x isn't offered."),
        ("fc-a", ["fc-y"], "fc-y isn't offered."),
        ("FC-A", [], "FC-A isn't offered."),
        ("fc-a", ["fc-b", "fc-b"], "fc-b is given more than once."),
        ("fc-a", ["fc-a"], "fc-a is given more than once."),
        ("fc-a", ["gpt-oss:20b"], "gpt-oss:20b answers last in every sequence, so it can't be a fallback."),
        ("gpt-oss:20b", ["fc-a"], "gpt-oss:20b answers alone, so it takes no fallback."),
        (None, ["fc-a"], "gpt-oss:20b answers alone, so it takes no fallback."),
    ],
)
def test_a_refused_sequence_says_why_and_lists_the_models_offered(settings, model, fallbacks, problem):
    choices = make_choices(settings)

    with pytest.raises(ModelChoiceError) as refused:
        choices.sequence(model, fallbacks)

    assert str(refused.value) == f"{problem} {OFFERED}"


def test_describe_gives_the_sequences_options_and_builds_no_provider(settings):
    choices = make_choices(settings)

    options = choices.describe("fc-b", ["fc-a"])

    assert [(option.name, option.local) for option in options] == [
        ("fc-b", False),
        ("fc-a", False),
        ("gpt-oss:20b", True),
    ]
    assert the_cloud(choices).built == []
    with pytest.raises(ModelChoiceError):
        choices.describe("fc-b", ["fc-b"])


# Providers and their labels


def test_a_cloud_provider_is_one_the_app_implements_configured_or_not(settings):
    configured = make_choices(settings)
    unconfigured = make_choices(settings, environ={})

    for choices in (configured, unconfigured):
        assert choices.is_cloud_provider("fakecloud")
        assert not choices.is_cloud_provider("ollama")
        assert not choices.is_cloud_provider(None)
        assert choices.label_of("fakecloud") == "FakeCloud"
        assert choices.label_of("ollama") == "local"


# Checks


def test_the_check_gathers_each_configured_providers_rows(settings):
    choices = make_choices(settings)

    rows = choices.check()

    assert [row.name for row in rows] == ["fakecloud fc-a", "fakecloud fc-b", "fakecloud fc-c"]
    assert the_cloud(choices).check_calls == [["fc-a", "fc-b", "fc-c"]]


def test_without_a_configured_provider_the_checks_have_no_row(settings):
    choices = make_choices(settings, environ={})

    assert choices.check() == []
    assert choices.setting_problems() == []


@pytest.mark.parametrize(
    ("environ", "detail"),
    [
        (
            {"FAKECLOUD_MODELS": "fc-a"},
            "FAKECLOUD_MODELS is set and FAKECLOUD_API_KEY isn't: no model of FakeCloud's is offered",
        ),
        (
            {"FAKECLOUD_API_KEY": "fake-key"},
            "FAKECLOUD_API_KEY is set and FAKECLOUD_MODELS isn't: no model of FakeCloud's is offered",
        ),
    ],
)
def test_one_setting_alone_offers_nothing_and_is_a_failing_row_contacting_nothing(settings, environ, detail):
    choices = make_choices(settings, environ=environ)

    assert not choices.has_cloud()
    assert choices.setting_problems() == [ProviderCheck("fakecloud", False, detail)]
    assert choices.cloud_setup.providers == ()


# Fallback options (specs/008, Phase 8: Convergence, T073; FR-007, FR-032)


def test_a_cloud_models_fallback_options_are_the_other_cloud_models_offered(settings):
    choices = make_choices(settings)

    assert [option.name for option in choices.fallback_options("fc-b")] == ["fc-a", "fc-c"]
    assert all(not option.local for option in choices.fallback_options("fc-b"))


@pytest.mark.parametrize("model", ["gpt-oss:20b", None, "fc-x"])
def test_the_local_model_or_a_name_not_offered_takes_no_fallback_option(settings, model):
    assert make_choices(settings).fallback_options(model) == []
