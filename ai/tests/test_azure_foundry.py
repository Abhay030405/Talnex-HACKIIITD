import json

import httpx
import pytest

from talnex_ai import settings
from talnex_ai.llm.azure_foundry import AzureFoundryClient, AzureFoundryError
from talnex_ai.llm.openrouter import OpenRouterClient, OpenRouterError
from talnex_ai.llm.provider import build_llm_client
from tests.test_openrouter import ENV, FakeServer, answer

AZURE = dict(ENV, LLM_PROVIDER="azure_foundry", AZURE_FOUNDRY_ENDPOINT="https://talnex.azure.test/models/",
             AZURE_FOUNDRY_API_KEY="az-key", AZURE_FOUNDRY_MODEL="gpt-deploy",
             AZURE_FOUNDRY_PRICE_IN_PER_M="2.5", AZURE_FOUNDRY_PRICE_OUT_PER_M="10")


def azure_client(server, env=AZURE, logged=None):
    cfg = settings.load(env).llm
    return AzureFoundryClient(cfg, (lambda **row: logged.append(row)) if logged is not None else None,
                              http=httpx.Client(transport=httpx.MockTransport(server)), sleep=lambda s: None)


def test_azure_call_uses_its_own_address_key_and_deployment():
    server, logged = FakeServer((200, answer(cost=None, model="gpt-deploy"))), []
    result = azure_client(server, logged=logged).chat("claim_reader", [{"role": "user", "content": "hi"}])

    request = server.requests[0]
    sent = json.loads(request.content)
    assert request.url == "https://talnex.azure.test/models/chat/completions"
    assert request.headers["api-key"] == "az-key" and "authorization" not in request.headers
    assert sent["model"] == "gpt-deploy" and "usage" not in sent
    # 100 tokens in at $2.5/M + 20 out at $10/M
    assert result.cost_usd == pytest.approx(0.00045)
    assert logged[0]["service"] == "azure_foundry"


def test_no_price_means_no_cost_rather_than_a_guess():
    env = dict(AZURE, AZURE_FOUNDRY_PRICE_OUT_PER_M="")
    assert azure_client(FakeServer((200, answer(cost=None))), env).chat("agent", []).cost_usd is None


def test_azure_errors_are_also_openrouter_errors():
    server = FakeServer((400, {"error": "bad request"}))
    with pytest.raises(AzureFoundryError) as err:
        azure_client(server).chat("agent", [])
    assert isinstance(err.value, OpenRouterError)


def test_azure_still_rejects_unknown_roles():
    with pytest.raises(ValueError, match="unknown model role"):
        azure_client(FakeServer()).chat("poet", [])


def test_missing_azure_settings_are_all_named():
    env = dict(AZURE, AZURE_FOUNDRY_API_KEY="", AZURE_FOUNDRY_MODEL="")
    with pytest.raises(settings.SettingsError, match="AZURE_FOUNDRY_API_KEY, AZURE_FOUNDRY_MODEL"):
        azure_client(FakeServer(), env)


def test_provider_setting_picks_the_client():
    assert type(build_llm_client(settings.load(AZURE))) is AzureFoundryClient
    assert type(build_llm_client(settings.load(dict(AZURE, LLM_PROVIDER="openrouter")))) is OpenRouterClient
    assert type(build_llm_client(settings.load(ENV))) is OpenRouterClient
