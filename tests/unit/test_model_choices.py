"""The models a request may go to, and the rules of a sequence (specs/008, research.md R6)."""

import logging
import re

import pytest

from app.config.settings import CloudProfile, TokenizerConfig
from app.errors import ConfigurationError, ModelChoiceError
from app.generation.base import FailureReason
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


# The real kinds together: OpenAI beside Anthropic (specs/009-openai-provider)

BOTH = {
    "ANTHROPIC_API_KEY": "sk-ant-test",
    "ANTHROPIC_MODELS": "claude-a,claude-b",
    "OPENAI_API_KEY": "sk-test",
    "OPENAI_MODELS": "gpt-a,gpt-b",
}


def real_kinds():
    from app.container import CLOUD_PROVIDERS

    return CLOUD_PROVIDERS


def with_effort(settings, provider, reasoning):
    profile = settings.cloud_profiles[provider].model_copy(update={"reasoning": reasoning})
    return settings.model_copy(update={"cloud_profiles": settings.cloud_profiles | {provider: profile}})


def test_openais_models_come_after_anthropics_each_in_its_lists_order(settings):
    choices = ModelChoices(local_llm(), create_cloud_providers(settings, BOTH, real_kinds()))

    assert [(option.name, option.provider_label) for option in choices.offered()] == [
        ("gpt-oss:20b", "local"),
        ("claude-a", "Anthropic"),
        ("claude-b", "Anthropic"),
        ("gpt-a", "OpenAI"),
        ("gpt-b", "OpenAI"),
    ]


def test_openai_alone_offers_its_models_after_the_local_one(settings):
    environ = {"OPENAI_API_KEY": "sk-test", "OPENAI_MODELS": "gpt-a"}

    choices = ModelChoices(local_llm(), create_cloud_providers(settings, environ, real_kinds()))

    assert [option.name for option in choices.offered()] == ["gpt-oss:20b", "gpt-a"]


@pytest.mark.parametrize(
    ("environ", "detail"),
    [
        ({"OPENAI_MODELS": "gpt-a"}, "OPENAI_MODELS is set and OPENAI_API_KEY isn't: no model of OpenAI's is offered"),
        (
            {"OPENAI_API_KEY": "sk-test"},
            "OPENAI_API_KEY is set and OPENAI_MODELS isn't: no model of OpenAI's is offered",
        ),
    ],
)
def test_one_openai_setting_alone_offers_nothing_and_is_a_failing_row(settings, environ, detail):
    choices = ModelChoices(local_llm(), create_cloud_providers(settings, environ, real_kinds()))

    assert not choices.has_cloud()
    assert choices.setting_problems() == [ProviderCheck("openai", False, detail)]


def test_an_effort_anthropic_doesnt_take_stops_the_setup_configured_or_not(settings):
    message = (
        "cloud_profiles.anthropic.reasoning in config/models.yaml is 'minimal', which Anthropic doesn't take "
        "(it takes: high, low, max, medium, xhigh, or none at all)"
    )

    with pytest.raises(ConfigurationError, match=re.escape(message)):
        create_cloud_providers(with_effort(settings, "anthropic", "minimal"), {}, real_kinds())


def test_openais_profile_must_name_an_effort(settings):
    message = (
        "cloud_profiles.openai.reasoning in config/models.yaml is empty, but OpenAI's profile must name an effort "
        "(it takes: high, low, max, medium, minimal, none, xhigh)"
    )

    with pytest.raises(ConfigurationError, match=re.escape(message)):
        create_cloud_providers(with_effort(settings, "openai", None), {}, real_kinds())


@pytest.mark.parametrize("reasoning", ["none", "minimal", "low", "medium", "high", "xhigh", "max"])
def test_openais_profile_takes_each_of_its_efforts(settings, reasoning):
    setup = create_cloud_providers(with_effort(settings, "openai", reasoning), BOTH, real_kinds())

    assert [provider.name for provider, _ in setup.providers] == ["anthropic", "openai"]


def test_a_name_offered_by_two_providers_stops_the_setup(settings):
    environ = BOTH | {"ANTHROPIC_MODELS": "claude-a,gpt-x", "OPENAI_MODELS": "gpt-x"}
    message = (
        "gpt-x is allowed by both ANTHROPIC_MODELS and OPENAI_MODELS, so a request naming it couldn't say which "
        "provider it goes to. Remove it from one of them."
    )

    with pytest.raises(ConfigurationError, match=re.escape(message)):
        create_cloud_providers(settings, environ, real_kinds())


@pytest.mark.parametrize("setting", ["OPENAI_MODELS", "ANTHROPIC_MODELS"])
def test_a_name_offered_that_is_the_local_models_stops_the_setup(settings, setting):
    environ = BOTH | {setting: "gpt-oss:20b"}
    message = (
        f"gpt-oss:20b is in {setting} and is llm.model in config/models.yaml, the local model. "
        f"Remove it from {setting}."
    )

    with pytest.raises(ConfigurationError, match=re.escape(message)):
        create_cloud_providers(settings, environ, real_kinds())


def test_a_list_without_its_key_clashes_with_nothing(settings):
    environ = {"ANTHROPIC_MODELS": "gpt-x,gpt-oss:20b", "OPENAI_API_KEY": "sk-test", "OPENAI_MODELS": "gpt-x"}

    choices = ModelChoices(local_llm(), create_cloud_providers(settings, environ, real_kinds()))

    assert [option.name for option in choices.offered()] == ["gpt-oss:20b", "gpt-x"]


def test_the_rules_log_nothing_when_they_pass(settings, caplog):
    with caplog.at_level(logging.DEBUG):
        create_cloud_providers(settings, BOTH, real_kinds())

    assert caplog.records == []


OUT_OF_CREDIT = "its account is out of credit or over a spending or usage limit"


@pytest.mark.parametrize(
    ("detail", "words"),
    [
        ("credit_balance_exhausted", f"{OUT_OF_CREDIT} (credit_balance_exhausted)"),
        ("", OUT_OF_CREDIT),
    ],
)
def test_out_of_credit_says_so(detail, words):
    assert FailureReason.OUT_OF_CREDIT.describe(detail) == words
    assert FailureReason.OUT_OF_CREDIT.value == "out of credit"


# Sequences across providers (specs/009-openai-provider, US3, FR-007)


def both(settings):
    return ModelChoices(local_llm(), create_cloud_providers(settings, BOTH, real_kinds()))


def test_a_claude_models_fallbacks_include_openais_and_the_reverse(settings):
    choices = both(settings)

    assert [option.name for option in choices.fallback_options("claude-a")] == ["claude-b", "gpt-a", "gpt-b"]
    assert [option.name for option in choices.fallback_options("gpt-b")] == ["claude-a", "claude-b", "gpt-a"]


@pytest.mark.parametrize(
    ("model", "fallbacks", "sequence"),
    [
        ("claude-a", ["gpt-a"], [("claude-a", "anthropic"), ("gpt-a", "openai"), ("gpt-oss:20b", "ollama")]),
        (
            "gpt-b",
            ["claude-b", "gpt-a"],
            [("gpt-b", "openai"), ("claude-b", "anthropic"), ("gpt-a", "openai"), ("gpt-oss:20b", "ollama")],
        ),
    ],
)
def test_a_sequence_may_mix_providers_in_any_order_and_ends_with_the_local_model(settings, model, fallbacks, sequence):
    options = both(settings).describe(model, fallbacks)

    assert [(option.name, option.provider) for option in options] == sequence


def test_a_name_given_twice_across_providers_is_refused(settings):
    with pytest.raises(ModelChoiceError, match="gpt-a is given more than once"):
        both(settings).describe("gpt-a", ["claude-a", "gpt-a"])
