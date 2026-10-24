"""The Azure AI Foundry client: the same job as the OpenRouter client, for a model deployed on Azure.

It inherits the retries, token limit and usage logging, and changes only the provider details:
- the address and key come from the AZURE_FOUNDRY_* settings, and the key goes in an `api-key` header;
- one deployment (AZURE_FOUNDRY_MODEL) answers every role;
- Azure doesn't report cost, so we work it out from the token counts and the price settings,
  and leave it empty when no price is set rather than inventing one.
"""
from __future__ import annotations

from typing import Any, Mapping, Optional

from talnex_ai.llm.models import check_role
from talnex_ai.llm.openrouter.client import OpenRouterClient, OpenRouterError
from talnex_ai.settings import SettingsError


class AzureFoundryError(OpenRouterError):
    """A failed Azure call. It's a kind of OpenRouterError, so one `except` covers both providers."""


class AzureFoundryClient(OpenRouterClient):
    service = "azure_foundry"
    label = "Azure Foundry"
    error_class = AzureFoundryError

    def _check_settings(self) -> None:
        azure = self.cfg.azure
        missing = [name for name, value in (("AZURE_FOUNDRY_ENDPOINT", azure.endpoint),
                                            ("AZURE_FOUNDRY_API_KEY", azure.api_key),
                                            ("AZURE_FOUNDRY_MODEL", azure.model)) if not value]
        if missing:
            raise SettingsError(f"LLM_PROVIDER is azure_foundry but these are not set: {', '.join(missing)}")

    def _model(self, role: str) -> str:
        check_role(role)  # one deployment serves every role, but a typo in a role is still a bug
        return self.cfg.azure.model

    def _url(self) -> str:
        return f"{self.cfg.azure.endpoint}/chat/completions"

    def _headers(self) -> dict[str, str]:
        return {"api-key": self.cfg.azure.api_key, "Content-Type": "application/json"}

    def _extra_body(self) -> dict[str, Any]:
        return {}

    def _cost(self, usage: Mapping[str, Any], tokens_in: Optional[int], tokens_out: Optional[int]) -> Optional[float]:
        price_in, price_out = self.cfg.azure.price_in_per_m, self.cfg.azure.price_out_per_m
        if None in (price_in, price_out, tokens_in, tokens_out):
            return None
        return (tokens_in * price_in + tokens_out * price_out) / 1_000_000
