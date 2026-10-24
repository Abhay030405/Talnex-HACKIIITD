from datetime import datetime, timedelta, timezone

import pytest

from talnex_ai.login.phone.inbox import SmsBox, site_hint, wait_for_sms_code


@pytest.mark.parametrize("host, hint", [
    ("www.shoppy.com", "shoppy"), ("myapp.vercel.app", "myapp"), ("app.acme.io", "acme"), ("go.to", None),
    ("", None),
])
def test_site_hints(host, hint):
    assert site_hint(host) == hint


@pytest.fixture
def texts(pool):
    with pool.connection() as conn:
        conn.execute("DELETE FROM inbound_sms")

    def add(sender, body, seconds_ago=0):
        with pool.connection() as conn:
            conn.execute("""INSERT INTO inbound_sms (from_number, body, received_at, created_at)
                            VALUES (%s, %s, now(), now() - make_interval(secs => %s))""", (sender, body, seconds_ago))

    yield add
    with pool.connection() as conn:
        conn.execute("DELETE FROM inbound_sms")


def waiting(pool, hint, ticks=(0, 1, 2, 99)):
    clock = iter(ticks)
    since = datetime.now(timezone.utc) - timedelta(seconds=60)
    return wait_for_sms_code(pool, since, sender_hint=hint, wait_seconds=10, poll_seconds=1,
                             sleep=lambda s: None, clock=lambda: next(clock))


def test_the_sites_own_text_wins_over_others(pool, texts):
    texts("+1555", "Your Otherapp code is 111111")
    texts("SHOPPY", "Your verification code is 222222")
    assert waiting(pool, "shoppy").code == "222222"


def test_old_texts_never_count(pool, texts):
    texts("SHOPPY", "Shoppy code 333333", seconds_ago=600)
    assert waiting(pool, "shoppy") is None


def test_one_unrelated_code_is_used_only_when_time_runs_out(pool, texts):
    texts("+1555", "Code: 444444")
    assert waiting(pool, "shoppy").code == "444444"


def test_two_different_unrelated_codes_are_never_guessed_between(pool, texts):
    texts("+1555", "Code: 555555")
    texts("+1666", "Code: 666666")
    assert waiting(pool, "shoppy") is None
    assert waiting(pool, None) is None


def test_without_a_hint_a_single_code_is_still_found(pool, texts):
    texts("+1555", "OTP 7777 for your login")
    assert waiting(pool, None).code == "7777"


def test_texts_without_codes_are_ignored_and_the_box_works(pool, texts):
    texts("SHOPPY", "Welcome to Shoppy! Reply STOP to opt out")
    texts("SHOPPY", "Shoppy: G-882211 is your code")
    clock = iter([0, 99])
    box = SmsBox(pool, "www.shoppy.com", wait_seconds=10, poll_seconds=1, sleep=lambda s: None, clock=lambda: next(clock))
    assert box.wait_for_code(datetime.now(timezone.utc) - timedelta(seconds=60)).code == "882211"
