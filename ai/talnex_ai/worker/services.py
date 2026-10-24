"""The outside services a stage uses, built once per worker process from the settings.

Stages call `get_services(pool)`. Tests install stand-ins with `set_services(...)`, so no stage
ever needs the network in a test.
"""
from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional

from psycopg_pool import ConnectionPool

from talnex_ai import settings as settings_module
from talnex_ai.testing.runner import driver as driver_module

log = logging.getLogger("talnex.services")


@dataclass
class Services:
    cfg: Any                                         # settings.Settings
    pool: ConnectionPool
    model: Any                                       # chat client (OpenRouter or Azure, by LLM_PROVIDER)
    tinyfish: Any                                    # TinyFishClient
    files: Any                                       # storage.Store
    mailbox_for: Callable[[str], Optional[Any]]      # site host -> the sign-up inbox reader, or None
    uploads_root: Optional[Path]                     # the only folder the agent may upload test files from
    connect: Callable = driver_module.connect        # how to attach Playwright to a remote browser
    smsbox_for: Optional[Callable[[str], Optional[Any]]] = None  # site host -> the team phone's texts, or None
    sandbox: Optional[Any] = None                    # SandboxClient for the VM host, None when it is not set up


_lock = threading.Lock()
_services: Optional[Services] = None


def set_services(services: Optional[Services]) -> None:
    """Install (or clear) the services. For tests."""
    global _services
    with _lock:
        _services = services


def get_services(pool: ConnectionPool) -> Services:
    """The shared services, built on first use."""
    global _services
    with _lock:
        if _services is None:
            _services = build_services(pool)
        return _services


def build_services(pool: ConnectionPool, cfg: Optional[settings_module.Settings] = None) -> Services:
    """Every real client, from the settings. A missing optional service (email, phone, sandbox) is
    switched off with a log line; a missing required one stops the worker with a clear message."""
    from talnex_ai.db.usage import log_usage
    from talnex_ai.llm.provider import build_llm_client
    from talnex_ai.login.email.agentmail import AgentMailClient, MailError, Mailbox
    from talnex_ai.login.phone.inbox import SmsBox
    from talnex_ai.sandbox.client import SandboxClient
    from talnex_ai.storage import Store
    from talnex_ai.tinyfish.budget import Budget
    from talnex_ai.tinyfish.client import TinyFishClient

    cfg = cfg or settings_module.load()
    model = build_llm_client(cfg, lambda **usage: log_usage(pool, **usage))
    tinyfish = TinyFishClient(cfg.tinyfish, Budget(cfg.tinyfish, pool))
    files = Store(cfg.s3)
    files.ensure_bucket()

    mail: Optional[AgentMailClient] = None
    try:
        mail = AgentMailClient(cfg.email)
    except MailError as err:
        log.info("email sign-up is off: %s", err)

    def mailbox_for(site_host: str) -> Optional[Mailbox]:
        return Mailbox(mail, site_host) if mail is not None else None

    def smsbox_for(site_host: str) -> Optional[SmsBox]:
        if not cfg.phone.enabled:
            return None
        return SmsBox(pool, site_host, wait_seconds=cfg.phone.wait_seconds, poll_seconds=cfg.phone.poll_seconds)

    if not cfg.sandbox.enabled:
        log.info("the sandbox host is not set up (SANDBOXD_URL), so repositories are not run")
    # Built even when off: the sandbox stages check the setting and skip, and any other call gets a clear error.
    return Services(cfg, pool, model, tinyfish, files, mailbox_for, Path(cfg.runner.uploads_dir),
                    smsbox_for=smsbox_for, sandbox=SandboxClient(cfg.sandbox))
