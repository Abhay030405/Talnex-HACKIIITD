"""Picks the service that answers model calls, from LLM_PROVIDER (openrouter or azure_foundry).

Both clients have the same `chat(role, messages, ...)`, so no other code knows or cares which
one is in use. Switching back is one setting.
"""
from __future__ import annotations

from typing import Optional

from talnex_ai.llm.azure_foundry import AzureFoundryClient
from talnex_ai.llm.openrouter import OpenRouterClient
from talnex_ai.llm.openrouter.client import UsageLogger
from talnex_ai.settings import Settings

_CLIENTS = {"openrouter": OpenRouterClient, "azure_foundry": AzureFoundryClient}


def build_llm_client(cfg: Settings, usage_logger: Optional[UsageLogger] = None) -> OpenRouterClient:
    return _CLIENTS[cfg.llm.provider](cfg.llm, usage_logger)
