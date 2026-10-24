"""The leak scanner: real secrets are found and masked, placeholders are not, and the secret is never kept."""
import json

from talnex_ai.safety.leaks import mask, scan

STRIPE = "sk_live_" + "51HxQ2aBcDeFgHiJkLmNoPqRsTuV"
AWS = "AKIA" + "IOSFODNN7EXAMPLQ"
GOOGLE = "AIza" + "SyD-1234567890abcdefghijklmnopqrstu"
JWT = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U"


def kinds(text, **kw):
    return {f["type"] for f in scan(text, **kw)}


def test_real_secrets_are_found_in_json_and_console_text():
    body = json.dumps({"config": {"stripe": STRIPE, "aws": AWS, "maps": GOOGLE}, "token": JWT, "password": "hunter22secret"})
    assert {"stripe_live_key", "aws_access_key", "google_api_key", "jwt", "secret_field"} <= kinds(body)
    assert "private_key" in kinds("-----BEGIN RSA PRIVATE KEY-----\nMIIE...")
    assert "env_line" in kinds("DATABASE_PASSWORD=s3cr3tvalue99\nPORT=3000")
    assert "stack_trace" in kinds("Traceback (most recent call last):\n  File \"app.py\", line 3")


def test_placeholders_and_test_keys_are_not_leaks():
    assert kinds('{"api_key": "YOUR_API_KEY_HERE", "stripe": "sk_test_51HxQ2aBcDeFgHiJkLmNoPq"}') == set()
    assert kinds("password: ********") == set()


def test_the_secret_itself_is_never_returned():
    out = json.dumps(scan(json.dumps({"k": STRIPE, "aws": AWS, "token": JWT})))
    for secret in (STRIPE, AWS, JWT):
        assert secret not in out
    assert mask(STRIPE) == STRIPE[:4] + "••••" + STRIPE[-4:] and mask("short") == "••••"


def test_many_other_peoples_emails_count_but_the_test_account_does_not():
    people = " ".join(f"user{i}@mail.com" for i in range(6))
    assert "bulk_emails" in kinds(people)
    assert "bulk_emails" not in kinds(people, ignore_emails=["user0@mail.com"])


def test_console_and_api_answers_reach_the_step_record_masked():
    from types import SimpleNamespace

    from talnex_ai.testing.runner.driver import PlaywrightDriver

    class Page:
        def __init__(self):
            self.handlers = {}

        def on(self, name, fn):
            self.handlers.setdefault(name, []).append(fn)

    page = Page()
    driver = PlaywrightDriver(page)
    answer = SimpleNamespace(request=SimpleNamespace(resource_type="fetch", method="GET"), status=200,
                             url="https://site.dev/api/config?x=1", headers={"content-type": "application/json"},
                             body=lambda: ('{"key": "' + STRIPE + '"}').encode())
    for fn in page.handlers["response"]:
        fn(answer)
    for fn in page.handlers["console"]:
        fn(SimpleNamespace(type="log", text="token " + JWT))
    leaks = driver.devtools()["leaks"]
    assert {(l["type"], l["where"]) for l in leaks} == {("stripe_live_key", "response GET https://site.dev/api/config"),
                                                       ("jwt", "console")}
    assert STRIPE not in json.dumps(leaks) and JWT not in json.dumps(leaks)
