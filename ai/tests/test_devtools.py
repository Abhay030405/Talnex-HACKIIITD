"""The developer-tools watcher: it collects browser events per step and hands them back on drain()."""
from talnex_ai.testing.runner.devtools import DevtoolsWatch, bare_url


def test_bare_url_drops_the_query_string_which_can_hold_tokens():
    assert bare_url("https://x.app/api/search?token=secret&q=1#top") == "https://x.app/api/search"
    assert bare_url("not a url ?a=b") == "not a url "


def test_an_api_call_keeps_its_status_and_response_time():
    w = DevtoolsWatch()
    w.response(1, "POST", "https://x.app/api/save?k=1", 200, "fetch")
    w.finished(1, 842.6)
    out = w.drain()
    assert out["api_calls"] == [{"method": "POST", "url": "https://x.app/api/save", "status": 200, "type": "fetch", "ms": 843}]
    assert out["slow_api_calls"] == 0


def test_a_slow_api_call_is_counted():
    w = DevtoolsWatch()
    w.response(1, "GET", "https://x.app/api/slow", 200, "xhr")
    w.finished(1, 3200)
    assert w.drain()["slow_api_calls"] == 1


def test_error_responses_and_failed_requests_and_console_errors_are_kept():
    w = DevtoolsWatch()
    w.response(1, "POST", "https://x.app/api/save", 500, "fetch")
    w.finished(1, 120)
    w.failed_request("GET", "https://x.app/img.png", "net::ERR_CONNECTION_REFUSED")
    w.console_message("error", "Uncaught TypeError: x is undefined")
    w.console_message("log", "just a log")  # ordinary logs are ignored
    w.page_error("ReferenceError: foo is not defined")
    out = w.drain()
    assert out["error_responses"][0]["status"] == 500
    assert out["failed_requests"][0]["url"] == "https://x.app/img.png"
    assert out["console_errors"] == ["[error] Uncaught TypeError: x is undefined"]
    assert out["page_errors"] == ["ReferenceError: foo is not defined"]


def test_a_quiet_step_drains_to_none():
    w = DevtoolsWatch()
    w.response(1, "GET", "https://x.app/style.css", 200, "stylesheet")  # not an API call, no error
    w.finished(1, 30)
    assert w.drain() is None


def test_drain_clears_so_the_next_step_starts_fresh_but_keeps_requests_in_flight():
    w = DevtoolsWatch()
    w.response(1, "GET", "https://x.app/api/a", 500, "fetch")
    w.finished(1, 10)
    w.response(2, "GET", "https://x.app/api/b", 200, "fetch")  # started, not finished this step
    assert w.drain()["error_responses"][0]["status"] == 500
    w.finished(2, 90)  # finishes in the next step
    out = w.drain()
    assert out["error_responses"] == [] and out["api_calls"][0]["url"] == "https://x.app/api/b"


def test_lists_cannot_grow_without_bound():
    w = DevtoolsWatch()
    for i in range(40):
        w.console_message("error", f"error {i}")
    assert len(w.drain()["console_errors"]) == 15
