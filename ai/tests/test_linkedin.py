"""The LinkedIn BQL client: login decided by the session cookie, profile decided by where LinkedIn sent us."""
import json

import httpx
import pytest

from talnex_ai.browser.linkedin import LinkedInClient, LinkedInError, LinkedInSession, read_profile


def client(answer: dict, seen: list):
    def handle(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=answer)
    return LinkedInClient("https://bql.test/stealth/bql/", "tok", http=httpx.Client(transport=httpx.MockTransport(handle)))


def login_answer(url, cookies):
    return {"data": {"url": {"url": url}, "solve": {"found": False, "solved": False}, "cookies": {"cookies": cookies}}}


def test_login_ok_when_li_at_is_set_and_password_stays_out_of_the_query():
    seen = []
    cookies = [{"name": "li_at", "value": "abc", "domain": ".linkedin.com", "path": "/", "expires": None}]
    s = client(login_answer("https://www.linkedin.com/feed/", cookies), seen).login("me@x.com", "s3cret")
    assert s.ok and s.cookies == cookies
    body = json.loads(seen[0].content)
    assert "s3cret" not in body["query"] and body["variables"]["password"] == "s3cret"
    assert seen[0].url.params["proxy"] == "residential" and seen[0].url.params["token"] == "tok"


def test_login_stuck_on_a_checkpoint_is_not_ok():
    s = client(login_answer("https://www.linkedin.com/checkpoint/challenge/x", []), []).login("a", "b")
    assert not s.ok and s.reason == "checkpoint"


def test_bql_errors_raise_instead_of_guessing():
    with pytest.raises(LinkedInError, match="boom"):
        client({"errors": [{"message": "boom"}], "data": None}, []).login("a", "b")


def test_profile_check_sends_cookies_without_nulls():
    seen = []
    c = client({"data": {"url": {"url": "https://www.linkedin.com/in/jane/"}, "title": {"title": "Jane Doe - Engineer | LinkedIn"}}}, seen)
    r = c.check_profile(LinkedInSession(True, "", [{"name": "li_at", "value": "v", "expires": None}]), "https://www.linkedin.com/in/jane")
    assert r.status == "found" and r.name == "Jane Doe"
    assert json.loads(seen[0].content)["variables"]["cookies"] == [{"name": "li_at", "value": "v"}]


@pytest.mark.parametrize("url,title,status,name", [
    ("https://www.linkedin.com/in/jane/", "(3) Jane Doe | LinkedIn", "found", "Jane Doe"),
    ("https://www.linkedin.com/404/", "Page not found | LinkedIn", "not_found", ""),
    ("https://www.linkedin.com/authwall?trk=x", "Sign Up | LinkedIn", "session_expired", ""),
    ("https://www.linkedin.com/feed/", "Feed | LinkedIn", "not_found", ""),
])
def test_read_profile(url, title, status, name):
    r = read_profile(url, title)
    assert (r.status, r.name) == (status, name)
