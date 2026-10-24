"""The browser providers and the TinyFish -> Browserless fallback."""
import pytest

from talnex_ai.browser import BrowserlessProvider, BrowserlessSession, FallbackBrowser


class FakeProvider:
    def __init__(self, cdp=None, error=None):
        self.cdp, self.error, self.calls = cdp, error, 0

    def open_session(self, url=None, *, timeout_seconds=None, job_id=None):
        self.calls += 1
        if self.error:
            raise self.error
        return BrowserlessSession(self.cdp)


def test_browserless_session_carries_the_cdp_url_and_no_cost():
    with BrowserlessProvider("ws://browserless:3000", "tok").open_session("https://x") as s:
        assert s.cdp_url == "ws://browserless:3000?token=tok" and s.account == "browserless" and s.cost_usd == 0.0


def test_browserless_url_without_a_token_is_left_as_is():
    assert BrowserlessProvider("ws://browserless:3000/").cdp_url() == "ws://browserless:3000"


def test_the_primary_is_used_when_it_works_and_the_backup_is_untouched():
    primary, backup = FakeProvider(cdp="ws://primary"), FakeProvider(cdp="ws://backup")
    s = FallbackBrowser(primary, backup).open_session("https://x")
    assert s.cdp_url == "ws://primary" and backup.calls == 0


def test_the_backup_is_used_when_the_primary_is_unavailable():
    primary = FakeProvider(error=RuntimeError("tinyfish down"))
    backup = FakeProvider(cdp="ws://backup")
    s = FallbackBrowser(primary, backup, errors=(RuntimeError,)).open_session("https://x")
    assert s.cdp_url == "ws://backup" and backup.calls == 1


def test_an_error_the_fallback_does_not_catch_is_not_swallowed():
    primary = FakeProvider(error=KeyError("other"))
    with pytest.raises(KeyError):
        FallbackBrowser(primary, FakeProvider(cdp="ws://backup"), errors=(RuntimeError,)).open_session()


def test_when_both_fail_the_primary_error_is_raised():
    primary = FakeProvider(error=RuntimeError("primary"))
    backup = FakeProvider(error=ValueError("backup"))
    with pytest.raises(RuntimeError, match="primary"):
        FallbackBrowser(primary, backup, errors=(RuntimeError, ValueError)).open_session()
