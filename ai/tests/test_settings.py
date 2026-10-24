import pytest

from talnex_ai import settings

MINIMAL = {
    "DATABASE_URL": "postgres://talnex@localhost/talnex",
    "S3_ENDPOINT": "http://localhost:9000/",
    "S3_REGION": "auto",
    "S3_BUCKET": "talnex",
    "S3_ACCESS_KEY": "access",
    "S3_SECRET_KEY": "secret",
    "OPENROUTER_BASE_URL": "https://openrouter.ai/api/v1/",
}


def test_minimal_env_loads_with_defaults():
    s = settings.load(MINIMAL)
    assert s.s3.endpoint == "http://localhost:9000"
    assert s.llm.base_url == "https://openrouter.ai/api/v1"
    assert s.llm.provider == "openrouter"
    assert s.worker.concurrency == 5
    assert s.limits.max_tries_per_claim == 3
    assert s.limits.max_agent_runs_per_project == 30
    assert s.llm.azure.price_in_per_m is None


def test_every_missing_value_is_named_at_once():
    with pytest.raises(settings.SettingsError) as err:
        settings.load({})
    message = str(err.value)
    for name in MINIMAL:
        assert name in message


def test_model_roles_come_from_env():
    s = settings.load(dict(MINIMAL, MODEL_TEST_PLANNER="some/planner"))
    assert s.llm.models["test_planner"] == "some/planner"
    assert s.llm.models["agent"] == ""
    assert set(s.llm.models) == set(settings.MODEL_ROLES)


@pytest.mark.parametrize("name, value", [
    ("MAX_TRIES_PER_CLAIM", "0"),
    ("MAX_TRIES_PER_CLAIM", "-2"),
    ("AI_WORKER_CONCURRENCY", "five"),
    ("LLM_TEMPERATURE", "3"),
    ("LLM_TEMPERATURE", "warm"),
    ("LLM_PROVIDER", "gpt"),
    ("AZURE_FOUNDRY_PRICE_IN_PER_M", "-1"),
])
def test_bad_values_are_rejected(name, value):
    with pytest.raises(settings.SettingsError, match=name):
        settings.load(dict(MINIMAL, **{name: value}))


def test_azure_provider_and_prices():
    s = settings.load(dict(MINIMAL, LLM_PROVIDER="Azure_Foundry", AZURE_FOUNDRY_PRICE_IN_PER_M="0.4",
                           AZURE_FOUNDRY_ENDPOINT="https://x.azure.com/"))
    assert s.llm.provider == "azure_foundry"
    assert s.llm.azure.price_in_per_m == 0.4
    assert s.llm.azure.endpoint == "https://x.azure.com"


def test_secrets_never_appear_in_errors():
    with pytest.raises(settings.SettingsError) as err:
        settings.load(dict(MINIMAL, S3_SECRET_KEY="", OPENROUTER_API_KEY="sk-very-secret", MAX_TRIES_PER_CLAIM="x"))
    assert "sk-very-secret" not in str(err.value)
