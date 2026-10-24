from datetime import datetime, timezone

import httpx
import pytest

from talnex_ai.login.email.agentmail import AgentMailClient, Mail, Mailbox, MailError, related_to_site
from talnex_ai.login.email.extract import find_code, find_link, find_sms_code, hint_from_parts, html_to_text
from talnex_ai.settings import EmailSettings

CFG = EmailSettings(api_key="am-key", base_url="https://mail.test", inbox="talnex@agentmail.to", wait_seconds=10,
                    poll_seconds=1, login_secret="s")


@pytest.mark.parametrize("text, code", [
    ("Your verification code is 482913", "482913"),
    ("OTP: 4829. Valid for 10 minutes.", "4829"),
    ("Welcome! 551203 is all you need.", "551203"),
    ("Order 2024-11-03 total 1500.00", None),
])
def test_codes_in_emails(text, code):
    assert find_code(text) == code


def test_links_must_be_verification_links_on_the_site():
    markup = ('<a href="https://shop.test/unsubscribe">x</a> <a href="https://evil.test/verify?t=1">y</a> '
              '<a href="https://shop.test/verify?token=abc&amp;u=1">Confirm</a>')
    assert find_link("", markup, "shop.test") == "https://shop.test/verify?token=abc&u=1"
    assert find_link("see https://shop.test/about", "", "shop.test") is None


def test_html_emails_become_text_and_hints():
    html = "<style>p{}</style><p>Hello</p><p>Your code is <b>7731</b></p>"
    assert "Your code is 7731" in html_to_text(html)
    hint = hint_from_parts("Welcome", "", html, "shop.test")
    assert hint.found and hint.code == "7731" and hint.link is None


@pytest.mark.parametrize("text, code", [
    ("Your Acme code is 123456", "123456"),
    ("G-482913 is your Google verification code.", "482913"),
    ("Code 123-456", "123456"),
    ("Call us at 800 555 1234 if this wasn't you. Code: 9921", "9921"),
    ("Happy 2025! Use 7788 to log in", "7788"),
    ("Call 800 555 1234 now", None),
])
def test_codes_in_text_messages(text, code):
    assert find_sms_code(text) == code


def mail(subject="Verify your account", sender="no-reply@shoppy.test", text="Your code is 482913", mid="m1"):
    return Mail(mid, subject, sender, ("talnex@agentmail.to",), text, "", "2026-10-24T10:00:00Z")


def test_emails_are_matched_to_the_site_being_tested():
    assert related_to_site(mail(), "shoppy.test")
    assert related_to_site(mail(text="Welcome to Shoppy"), "shoppy.vercel.app")  # by the site's name
    assert not related_to_site(mail(sender="x@y.test", subject="Hi", text="welcome to our app"), "app.test")  # "app" is too generic
    assert not related_to_site(mail(sender="x@other.test", subject="Hi", text="code 1234"), "app.test")


class FakeAgentMail:
    def __init__(self, listings, bodies, status=200):
        self.listings, self.bodies, self.status, self.requests = list(listings), bodies, status, []

    def __call__(self, request):
        self.requests.append(request)
        if self.status != 200:
            return httpx.Response(self.status, json={})
        if request.url.path.endswith("/messages"):
            return httpx.Response(200, json={"messages": self.listings.pop(0) if len(self.listings) > 1 else self.listings[0]})
        message_id = request.url.path.rsplit("/", 1)[1]
        return httpx.Response(200, json=self.bodies[message_id])


def client(server, clock=None):
    ticks = iter(clock or range(0, 1000, 5))
    return AgentMailClient(CFG, http=httpx.Client(transport=httpx.MockTransport(server)), sleep=lambda s: None,
                           clock=lambda: next(ticks))


def test_the_sites_email_is_picked_even_when_another_site_wrote_later():
    server = FakeAgentMail(
        [[{"message_id": "other"}, {"message_id": "ours"}]],
        {"other": {"subject": "Welcome to Otherapp", "from": "x@otherapp.test", "extracted_text": "code 111111"},
         "ours": {"subject": "Verify", "from": "no-reply@shoppy.test", "extracted_text": "Your code is 222222"}})
    hint = Mailbox(client(server), "shoppy.test").wait_for_hint(datetime.now(timezone.utc))
    assert hint.code == "222222"
    assert server.requests[0].headers["authorization"] == "Bearer am-key"
    assert server.requests[0].url.params["include_spam"] == "true"


def test_a_single_unrelated_email_with_a_code_is_used_when_time_runs_out():
    server = FakeAgentMail([[{"message_id": "only"}]],
                           {"only": {"subject": "Hi", "from": "x@mailer.test", "extracted_text": "code 333333"}})
    assert Mailbox(client(server), "shoppy.test").wait_for_hint(datetime.now(timezone.utc)).code == "333333"


def test_nothing_arriving_means_no_hint():
    server = FakeAgentMail([[]], {})
    assert Mailbox(client(server), "shoppy.test").wait_for_hint(datetime.now(timezone.utc)) is None


def test_mail_errors_are_clear():
    with pytest.raises(MailError, match="refused the key"):
        client(FakeAgentMail([[]], {}, status=401)).recent()
    with pytest.raises(MailError, match="AGENTMAIL_API_KEY"):
        AgentMailClient(EmailSettings("", "https://m", "i", 1, 1, ""))
