import json

import httpx
import pytest

from talnex_ai import settings
from talnex_ai.settings import TinyFishKey, parse_tinyfish_keys
from talnex_ai.tinyfish.budget import Budget, BudgetExceeded
from talnex_ai.tinyfish.client import TinyFishClient, TinyFishError

FETCH = "https://fetch.tf.test"
BROWSER = "https://browser.tf.test"
SEARCH = "https://search.tf.test"


def tf_settings(keys="main=key-1", **overrides):
    env = {
        "DATABASE_URL": "postgres://x", "S3_ENDPOINT": "http://s3:9000", "S3_REGION": "auto", "S3_BUCKET": "b",
        "S3_ACCESS_KEY": "a", "S3_SECRET_KEY": "s", "OPENROUTER_BASE_URL": "https://or.test",
        "TINYFISH_AGENT_BASE_URL": "https://agent.tf.test", "TINYFISH_BROWSER_BASE_URL": BROWSER,
        "TINYFISH_FETCH_BASE_URL": FETCH, "TINYFISH_SEARCH_BASE_URL": SEARCH, "TINYFISH_API_KEYS": keys,
        "TINYFISH_BUDGET_USD": "1", "TINYFISH_BUDGET_RESERVE_USD": "0.5",
    }
    return settings.load(dict(env, **overrides)).tinyfish


class FakeTinyFish:
    """Answers like TinyFish: Fetch reports each address as loaded or failed, sessions open and close."""

    def __init__(self, dead=(), fail_first=0, status=None):
        self.dead = set(dead)
        self.fail_first = fail_first
        self.status = status
        self.requests = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.fail_first:
            self.fail_first -= 1
            return httpx.Response(503, json={"error": {"message": "busy"}})
        if self.status:
            return httpx.Response(self.status, json={"error": {"message": "no"}})
        url = str(request.url)
        if url.startswith(FETCH):
            asked = json.loads(request.content)["urls"]
            return httpx.Response(200, json={
                "results": [{"url": u + "/", "title": "ok", "text": "hello"} for u in asked if u not in self.dead],
                "errors": [{"url": u, "error": "page_not_found", "status": 404} for u in asked if u in self.dead],
            })
        if url.startswith(SEARCH):
            return httpx.Response(200, json={"results": [{"title": f"t{i}", "url": f"https://r{i}.test"}
                                                         for i in range(10)] + [{"title": "no url"}]})
        if request.method == "POST" and url.startswith(BROWSER):
            return httpx.Response(201, json={"session_id": "s1", "cdp_url": "wss://cdp.test/s1"})
        if request.method == "DELETE":
            return httpx.Response(204)
        return httpx.Response(404)


def make_client(server, cfg=None, budget=None, clock=None):
    waits = []
    c = TinyFishClient(cfg or tf_settings(), budget, http=httpx.Client(transport=httpx.MockTransport(server)),
                       sleep=waits.append, clock=clock or (lambda: 0.0))
    return c, waits


def test_fetch_keeps_order_batches_by_ten_and_reports_dead_pages():
    urls = [f"https://site{i}.test" for i in range(12)]
    server = FakeTinyFish(dead={urls[3]})
    results = make_client(server)[0].fetch(urls)
    assert len(server.requests) == 2
    assert json.loads(server.requests[0].content)["ttl"] == 0
    assert [r.url for r in results] == urls
    assert results[0].ok and results[0].text == "hello"
    assert not results[3].ok and results[3].error_code == "page_not_found" and results[3].http_status == 404


def test_fetch_matches_addresses_written_slightly_differently():
    server = FakeTinyFish()
    result = make_client(server)[0].fetch(["https://Shop.TEST/cart"])[0]
    assert result.ok and result.url == "https://Shop.TEST/cart"


def test_fetch_missing_answer_is_no_result():
    def silent(request):
        return httpx.Response(200, json={"results": [], "errors": []})

    assert make_client(silent)[0].fetch(["https://a.test"])[0].error_code == "no_result"


def test_busy_server_is_retried_then_works():
    server = FakeTinyFish(fail_first=2)
    client, waits = make_client(server)
    assert client.fetch(["https://a.test"])[0].ok
    assert waits == [2.0, 4.0]


def test_refused_key_is_not_retried():
    server = FakeTinyFish(status=401)
    client, waits = make_client(server)
    with pytest.raises(TinyFishError, match="refused the key"):
        client.fetch(["https://a.test"])
    assert waits == [] and len(server.requests) == 1


def test_search_returns_hits_and_skips_bad_items():
    hits = make_client(FakeTinyFish())[0].search("todo app tutorial", limit=3)
    assert [h.url for h in hits] == ["https://r0.test", "https://r1.test", "https://r2.test"]
    with pytest.raises(TinyFishError, match="search is off"):
        make_client(FakeTinyFish(), cfg=tf_settings(TINYFISH_SEARCH_BASE_URL=""))[0].search("x")


def test_search_is_retried_too():
    server = FakeTinyFish(fail_first=1)
    client, waits = make_client(server)
    assert len(client.search("x")) == 8
    assert waits == [2.0]


def test_session_closes_once_and_costs_by_the_minute():
    times = iter([100.0, 190.0])
    server = FakeTinyFish()
    client, _ = make_client(server, clock=lambda: next(times))
    with client.open_session("https://shop.test", job_id="j1") as session:
        assert session.cdp_url == "wss://cdp.test/s1" and session.account == "main"
    assert session.closed and session.cost_usd == pytest.approx(0.003)  # 90 s at $0.002 a minute
    assert session.close() == pytest.approx(0.003)
    assert [r.method for r in server.requests] == ["POST", "DELETE"]
    assert json.loads(server.requests[0].content) == {"timeout_seconds": 300, "url": "https://shop.test"}


def test_a_failed_end_does_not_raise():
    def flaky(request):
        if request.method == "DELETE":
            return httpx.Response(500)
        return httpx.Response(201, json={"session_id": "s1", "cdp_url": "wss://x"})

    session = make_client(flaky)[0].open_session()
    assert session.close() == 0.0 and session.closed


def test_no_key_is_a_clear_error():
    with pytest.raises(TinyFishError, match="no TinyFish key"):
        make_client(FakeTinyFish(), cfg=tf_settings(keys=""))[0].fetch(["https://a.test"])


def test_key_list_parsing():
    assert parse_tinyfish_keys("main=k1, spare=k2") == (TinyFishKey("main", "k1"), TinyFishKey("spare", "k2"))
    assert parse_tinyfish_keys("k-one,k-two") == (TinyFishKey("k1", "k-one"), TinyFishKey("k2", "k-two"))
    assert parse_tinyfish_keys("", "solo") == (TinyFishKey("main", "solo"),)
    with pytest.raises(settings.SettingsError, match="same label"):
        parse_tinyfish_keys("a=1,a=2")
    with pytest.raises(settings.SettingsError, match="entry 1"):
        parse_tinyfish_keys("bad label=1")


def test_bad_key_list_is_reported_with_other_problems():
    with pytest.raises(settings.SettingsError) as err:
        tf_settings(keys="a=1,a=2", TINYFISH_BUDGET_USD="lots")
    assert "same label" in str(err.value) and "TINYFISH_BUDGET_USD" in str(err.value)


def test_budget_picks_the_key_with_most_left_and_stops_at_the_reserve(pool):
    cfg = tf_settings(keys="main=k1,spare=k2")
    budget = Budget(cfg, pool)
    budget.record("main", "browser", 0.40)
    budget.record("spare", "browser", 0.10)
    assert budget.spent("main") == pytest.approx(0.40)
    assert budget.pick(0.05).label == "spare"          # 0.5 limit: main has 0.10 left, spare 0.40

    budget.record("spare", "agent", 0.39)
    with pytest.raises(BudgetExceeded, match="main: \\$0.100 left, spare: \\$0.010 left"):
        budget.pick(0.2)


def test_opening_a_session_respects_the_budget(pool):
    budget = Budget(tf_settings(), pool)
    budget.record("main", "browser", 0.4999)
    client, _ = make_client(FakeTinyFish(), budget=budget)
    with pytest.raises(BudgetExceeded):
        client.open_session()
