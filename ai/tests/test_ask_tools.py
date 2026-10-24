"""Ask TalNex's read-only tools: the allow-list, the GitHub reader, and the tool loop."""
import base64

import httpx
import pytest

from talnex_ai.reports.ask_tools import GitHubReader, Scope, ToolRefused, Tools, repo_of
from talnex_ai.worker.handlers.report_answer import Answer, ToolCall, answer_with_tools, parse_reply


def github(routes):
    def handle(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path not in routes:
            return httpx.Response(404, json={"message": "Not Found"})
        return httpx.Response(200, json=routes[path])
    return GitHubReader("https://api.github.test", "tok", http=httpx.Client(transport=httpx.MockTransport(handle)))


COMMITS = [{"sha": "abc1234567", "commit": {"author": {"name": "Asha", "date": "2026-10-23T10:00:00Z"},
                                             "message": "fix login bug\n\nlonger body"}}]
SCOPE = Scope(repos={"asha/notebox"}, hosts={"notebox.example.com"}, handles={"leetcode": "asha_lc"})


def test_repo_of_reads_owner_and_name():
    assert repo_of("https://github.com/Asha/NoteBox.git") == "asha/notebox"
    assert repo_of("https://example.com/x") is None


def test_github_reader_commits_file_and_unreadable():
    gh = github({"/repos/asha/notebox/commits": COMMITS,
                 "/repos/asha/notebox/contents/README.md": {"type": "file", "content": base64.b64encode(b"# NoteBox").decode()}})
    assert gh.commits("asha/notebox") == "abc1234 2026-10-23T10:00:00Z Asha: fix login bug"
    assert gh.file("asha/notebox", "README.md") == "# NoteBox"
    with pytest.raises(ToolRefused):
        gh.contributors("asha/notebox")          # 404 is "could not read", never a crash
    with pytest.raises(ToolRefused):
        gh.file("asha/notebox", "../../etc/passwd")


def test_tools_stay_inside_the_subjects_scope():
    tools = Tools(SCOPE, github=github({"/repos/asha/notebox/commits": COMMITS}))
    text, what = tools.run("github", {"repo": "https://github.com/asha/notebox", "what": "commits"})
    assert "fix login bug" in text and what == "latest commits of asha/notebox"
    for name, args in [("github", {"repo": "someone/else"}), ("fetch_page", {"url": "https://evil.example/x"}),
                       ("coding_profile", {"site": "codeforces"}), ("shell", {})]:
        with pytest.raises(ToolRefused):
            tools.run(name, args)


def test_parse_reply_tells_a_tool_call_from_an_answer():
    assert isinstance(parse_reply('{"tool": "github", "args": {"repo": "a/b"}}'), ToolCall)
    assert isinstance(parse_reply('{"answer": "It works.", "action": null}'), Answer)


class FakeModel:
    """Replies with tool calls first, then an answer; keeps every prompt it was shown."""

    def __init__(self, *replies):
        self.replies, self.prompts = list(replies), []

    def __call__(self, user):
        self.prompts.append(user)
        return self.replies.pop(0) if self.replies else ToolCall(tool="github", args={"repo": "asha/notebox"})


def test_the_loop_uses_a_tool_wraps_its_result_and_cites_it():
    tools = Tools(SCOPE, github=github({"/repos/asha/notebox/commits": COMMITS}))
    model = FakeModel(ToolCall(tool="github", args={"repo": "asha/notebox", "what": "commits"}),
                      Answer(answer="Latest commit: fix login bug (GitHub, checked just now)."))
    got, sources = answer_with_tools(model, tools, "question + report")
    assert got.answer.startswith("Latest commit") and [s["tool"] for s in sources] == ["github"]
    assert "<untrusted_data" in model.prompts[1] and "fix login bug" in model.prompts[1]


def test_the_loop_stops_after_four_tool_calls_and_refusals_are_told_not_run():
    tools = Tools(SCOPE, github=github({"/repos/asha/notebox/commits": COMMITS}))
    model = FakeModel(ToolCall(tool="github", args={"repo": "other/repo"}))   # then keeps calling tools forever
    got, sources = answer_with_tools(model, tools, "q", max_calls=4)
    assert len(model.prompts) == 5 and "used all your tool calls" in model.prompts[-1]
    assert "refused: only the subject's repositories" in model.prompts[1]
    assert got.answer.startswith("I could not finish")
    assert len(sources) == 3   # 4 calls, the refused one is not a source
