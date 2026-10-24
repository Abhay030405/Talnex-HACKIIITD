"""The guided tour: the code VM's three fixed tools, the guide agent, the plan check, the browser driver, and one whole
message from question to saved answer (architecture section 32).

Cases are general shapes (a command injected through a path, a proof that does not exist, a step the safety rules refuse),
not one app's. The whole-message test runs the real fixed commands in a local folder standing in for the VM."""
import io
import json
import shutil
import subprocess
import tarfile
import uuid
from pathlib import Path

import httpx
import pytest

from talnex_ai import settings
from talnex_ai.formats import FormatError
from talnex_ai.formats.tour import TourPlan
from talnex_ai.reports.walkthrough.tour import answer as tour_answer
from talnex_ai.reports.walkthrough.tour.check import check_plan
from talnex_ai.reports.walkthrough.tour.driver import TourBrowser
from talnex_ai.reports.walkthrough.tour.guide import GuideError, parse_turn, run_guide
from talnex_ai.sandbox.client import ExecResult
from talnex_ai.sandbox.code_vm import CODE_DIR, CodeReadError, CodeVm, Tool, build_command, clean_path, fetch_repo, repack
from talnex_ai.testing.runner.executor import ExecConfig
from talnex_ai.worker.services import Services
from tests.fakes import FakeDriver, FakeFiles, FakeTinyFish, ScriptedModel, act, connector, done

SHA = "a" * 40
APP_JS = """const items = [];
function addItem(text) {
  items.push({ text, done: false });
  save();
}
function save() {
  localStorage.setItem("items", JSON.stringify(items));
}
"""

BASH = shutil.which("bash")  # the full path: on Windows a bare "bash" can mean WSL
HAS_BASH = BASH is not None
needs_bash = pytest.mark.skipif(not HAS_BASH, reason="the stand-in VM runs the fixed commands with bash")


class DirVm:
    """A folder standing in for the VM: runs the real fixed commands against it with bash."""

    id = "vm-test"

    def __init__(self, root: Path):
        self.root = root
        self.commands: list[str] = []
        self.destroyed = False

    def exec(self, command, timeout_seconds=None, **_):
        self.commands.append(command)
        proc = subprocess.run([BASH, "-c", command.replace(CODE_DIR, self.root.as_posix())], capture_output=True, text=True)
        return ExecResult(proc.returncode, proc.stdout, proc.stderr, 0, False, False)

    def upload(self, archive, directory="/work"):
        with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
            tar.extractall(self.root, filter="data")

    def destroy(self):
        self.destroyed = True


def make_tar(files: dict[str, bytes], top: str = f"o-r-{SHA}", header_commit: str = "") -> bytes:
    """A GitHub-style download: one top folder holding the files, and (for HEAD or a branch) the commit in the header."""
    out = io.BytesIO()
    pax = {"comment": header_commit} if header_commit else {}
    with tarfile.open(fileobj=out, mode="w:gz", format=tarfile.PAX_FORMAT, pax_headers=pax) as tar:
        for name, body in files.items():
            info = tarfile.TarInfo(f"{top}/{name}")
            info.size = len(body)
            tar.addfile(info, io.BytesIO(body))
    return out.getvalue()


@pytest.fixture
def code_dir(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.js").write_text(APP_JS)
    (tmp_path / ".github").mkdir()
    (tmp_path / ".github" / "ci.yml").write_text("name: ci\n")
    return tmp_path


# ------------------------------------------------------------------ the three fixed tools


@pytest.mark.parametrize("path", ["../etc/passwd", "/etc/passwd", "a/../../b", "src/app.js; rm -rf /", "$(id)", "a`id`"])
def test_a_path_that_could_leave_the_code_or_run_something_is_refused(path):
    with pytest.raises(CodeReadError):
        clean_path(path)


def test_a_plain_path_keeps_its_leading_dot_folder():
    assert clean_path("./.github/ci.yml") == ".github/ci.yml" and clean_path(".") == "" and clean_path("") == ""


def test_text_to_search_for_is_quoted_so_it_stays_one_argument():
    command = build_command(Tool("search", text="x'; rm -rf / #"))
    assert "grep -rIn -F" in command and "'x'\"'\"'; rm -rf / #'" in command


@pytest.mark.parametrize("tool", [Tool("search", text=""), Tool("search", text="a\nb"), Tool("search", text="x" * 200),
                                  Tool("read", path=""), Tool("delete", path="a")])
def test_a_bad_tool_call_is_refused_before_any_command_exists(tool):
    with pytest.raises(CodeReadError):
        build_command(tool)


def test_a_read_is_capped_and_numbers_are_whole_numbers():
    assert "sed -n '1,160p'" in build_command(Tool("read", path="a.js", start=1, end=9999))
    assert "sed -n '5,5p'" in build_command(Tool("read", path="a.js", start=5, end=1))


@needs_bash
def test_the_tools_find_and_read_real_code(code_dir):
    code = CodeVm(DirVm(code_dir))
    assert "src/app.js" in code.run(Tool("list")).splitlines()
    assert code.run(Tool("search", text="localStorage")).strip().startswith("src/app.js:7:")
    assert code.run(Tool("search", text="nothing like this")) == ""
    assert code.run(Tool("read", path="src/app.js", start=2, end=3)).splitlines()[0].startswith("function addItem")
    assert code.line_count("src/app.js") == 8


@needs_bash
def test_a_file_that_is_not_there_has_no_line_count(code_dir):
    code = CodeVm(DirVm(code_dir))
    assert code.line_count("src/missing.js") is None
    with pytest.raises(CodeReadError):
        code.line_count("../x")


# ------------------------------------------------------------------ putting a repository in the VM


def test_only_readable_code_is_kept_and_the_commit_is_read_from_the_download():
    archive = make_tar({"src/app.js": b"x = 1\n", "node_modules/dep/index.js": b"y", "logo.png": b"\x89PNG", "big.js": b"z" * 5000,
                        "data.bin": b"ab\x00cd", ".github/ci.yml": b"name: ci\n", "README.md": b"# hi\n"})
    packed, commit = repack(archive, file_max_kb=2, max_files=10)
    names = sorted(m.name for m in tarfile.open(fileobj=io.BytesIO(packed)))
    assert names == [".github/ci.yml", "README.md", "src/app.js"] and commit == SHA


def test_the_commit_of_a_download_of_head_comes_from_githubs_own_header():
    other = "b" * 40
    archive = make_tar({"a.js": b"1"}, top="o-r-main", header_commit=other)
    assert repack(archive, file_max_kb=10, max_files=10)[1] == other
    assert repack(make_tar({"a.js": b"1"}, top="o-r-main"), file_max_kb=10, max_files=10)[1] is None


def test_a_repository_with_no_code_or_too_many_files_is_refused_with_a_reason():
    with pytest.raises(CodeReadError, match="no readable code"):
        repack(make_tar({"logo.png": b"x"}), file_max_kb=10, max_files=10)
    with pytest.raises(CodeReadError, match="more than 1"):
        repack(make_tar({"a.js": b"1", "b.js": b"2"}), file_max_kb=10, max_files=1)


def test_a_download_that_fails_or_is_too_big_says_why():
    def client(status=200, body=b""):
        return httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(status, content=body)))

    with pytest.raises(CodeReadError, match="may be private"):
        fetch_repo("o/r", None, max_mb=1, file_max_kb=10, max_files=10, client=client(404))
    with pytest.raises(CodeReadError, match="bigger than 1 MB"):
        fetch_repo("o/r", None, max_mb=1, file_max_kb=10, max_files=10, client=client(200, b"x" * (2 * 1024 * 1024)))
    archive, commit = fetch_repo("o/r", None, max_mb=1, file_max_kb=10, max_files=10, client=client(200, make_tar({"a.js": b"1"})))
    assert commit == SHA and tarfile.open(fileobj=io.BytesIO(archive)).getnames() == ["a.js"]


# ------------------------------------------------------------------ the guide agent


class ListVm:
    """A VM that answers each tool with a fixed text, and counts the calls."""

    def __init__(self, outputs):
        self.outputs, self.calls = list(outputs), []

    def exec(self, command, timeout_seconds=None, **_):
        self.calls.append(command)
        out = self.outputs.pop(0) if self.outputs else ""
        return ExecResult(0, out, "", 0, False, False)


PLAN = {"plan": {"steps": [{"say": "Items are added in addItem.", "proof": [{"kind": "code", "file": "src/app.js", "start": 2, "end": 5}],
                            "show": "click the button Add", "expect": "the item is listed"}]}}


def guide(model, vm, **kw):
    return run_guide(model, CodeVm(vm), question="how are items added?", claims=["Add items"], has_live=True, history=[],
                     max_calls=kw.pop("max_calls", 3), **kw)


def test_the_guide_reads_with_tools_then_gives_the_plan():
    model = ScriptedModel({"tool": "search", "text": "addItem"}, {"tool": "read", "path": "src/app.js", "start": 1, "end": 9}, PLAN)
    seen, code_text = [], []
    plan = guide(model, ListVm(["src/app.js:2:function addItem", "const items = [];"]),
                 on_read=lambda tool, what: seen.append((tool, what)), on_code_text=code_text.append)
    assert plan.steps[0].say.startswith("Items are added") and len(model.calls) == 3
    assert seen == [("search", '"addItem"'), ("read", "src/app.js lines 1 to 9")]
    assert code_text == ["src/app.js:2:function addItem", "const items = [];"]
    # what was read reaches the next turn as data, framed as untrusted
    assert "<untrusted_data" in model.user_text(2) and "function addItem" in model.user_text(2)


def test_a_failed_tool_call_is_shown_to_the_guide_not_raised():
    model = ScriptedModel({"tool": "read", "path": "../secret"}, PLAN)
    plan = guide(model, ListVm([]))
    assert plan.steps and "that did not work: that path is not allowed" in model.user_text(1)


def test_the_guide_must_give_the_plan_when_its_calls_run_out():
    model = ScriptedModel({"tool": "list"}, {"tool": "list"}, PLAN)
    vm = ListVm(["a", "b"])
    assert guide(model, vm, max_calls=1).steps and len(vm.calls) == 1
    assert "Give the plan now" in model.user_text(2)


def test_a_guide_that_never_gives_a_plan_is_an_error_not_a_guess():
    with pytest.raises(GuideError):
        guide(ScriptedModel(*[{"tool": "list"}] * 5), ListVm([]), max_calls=1)


@pytest.mark.parametrize("reply", ['{"tool": "delete"}', "[1]", '{"plan": {"steps": [{"say": "x"}]}}', "no json"])
def test_a_reply_that_is_neither_a_tool_nor_a_plan_is_a_format_error(reply):
    with pytest.raises(FormatError):
        parse_turn(reply)


# ------------------------------------------------------------------ checking the plan against the real code


@needs_bash
def test_only_sentences_with_real_proof_survive_and_each_carries_its_lines(code_dir):
    code = CodeVm(DirVm(code_dir))
    plan = TourPlan.model_validate({"steps": [
        {"say": "Real.", "proof": [{"kind": "code", "file": "src/app.js", "start": 2, "end": 99}], "show": "click Add"},
        {"say": "No such file.", "proof": [{"kind": "code", "file": "src/ghost.js", "start": 1, "end": 4}]},
        {"say": "Past the end.", "proof": [{"kind": "code", "file": "src/app.js", "start": 500, "end": 510}]},
        {"say": "No proof at all."},
        {"say": "A screenshot the guide cannot know.", "proof": [{"kind": "screenshot", "key": "screens/x/y/1"}]},
        {"say": "Risky.", "proof": [{"kind": "code", "file": "src/app.js", "start": 1, "end": 1}], "show": "click Delete account"},
    ]})
    steps, dropped = check_plan(plan, code, repo="o/r", commit=SHA, snippet_lines=3)
    assert [s.say for s in steps] == ["Real.", "Risky."] and len(dropped) == 4
    real = steps[0].snippets[0]
    assert (real.file, real.start, real.end) == ("src/app.js", 2, 8)        # the end is trimmed to the file's last line
    assert len(real.lines) == 3 and real.lines[0].startswith("function addItem")  # a few lines are shown
    assert real.url == f"https://github.com/o/r/blob/{SHA}/src/app.js#L2-L8"
    assert steps[1].show is None and "Delete" in steps[1].notes[0]          # the safety rules refuse it; the sentence stays



class RoleModel(ScriptedModel):
    """The guide's replies are scripted. For a browser step the agent role clicks once, then calls the step done (when steps
    that name one clear action are done without the model, it is simply never asked)."""

    def __init__(self, *guide_replies):
        super().__init__(*guide_replies)
        self.agent_calls = 0

    def chat(self, role, messages, **options):
        if role == "agent":
            self.agent_calls += 1
            first = "- nothing yet" in messages[1]["content"]
            from tests.fakes import Reply
            return Reply(json.dumps(act(type="click", target={"kind": "role", "role": "button", "name": "Add"}) if first
                                    else done("it worked")))
        return super().chat(role, messages, **options)

    @property
    def guide_calls(self):
        return len(self.calls)  # the agent role's calls are not recorded in .calls


# ------------------------------------------------------------------ the browser driver


def browser(driver, model=None, **kw):
    cfg = ExecConfig()
    return TourBrowser(provider=FakeTinyFish(), connect=connector(driver), files=FakeFiles(), model=model or RoleModel(),
                       site_url="https://demo.example.com/", subject_id="proj-1", uploads_root=Path("."), exec_config=cfg,
                       max_actions=kw.pop("max_actions", 5), **kw)


def test_a_simple_step_is_shown_with_no_model_call_and_its_picture_is_saved_under_the_project():
    driver, events = FakeDriver(), []
    with browser(driver, on_event=lambda kind, **data: events.append((kind, data))) as b:
        assert b.show('click the button "Add"', "the item is listed", question="how?") is None
    assert [type(a).__name__ for a in driver.performed] == ["Click"]
    keys = [d["proof_key"] for k, d in events if k == "step.record"]
    assert keys and all(k.startswith("screens/proj-1/tour-") for k in keys)


class FlakyReach(FakeDriver):
    """A browser whose first connections fail (a proxy problem on its side), then works."""

    def __init__(self, failures):
        super().__init__()
        self.failures, self.reaches = failures, 0

    def reach(self, url):
        self.reaches += 1
        return self.reaches > self.failures


def test_a_browser_that_cannot_connect_is_replaced_by_a_fresh_one_before_giving_up():
    provider = FakeTinyFish()
    flaky = FlakyReach(failures=2)
    with TourBrowser(provider=provider, connect=connector(flaky), files=FakeFiles(), model=RoleModel(), site_url="https://demo.example.com/",
                     subject_id="p", uploads_root=Path("."), exec_config=ExecConfig(), max_actions=3):
        pass
    assert flaky.reaches == 3 and len(provider.sessions) == 3 and all(s.closed for s in provider.sessions)
    hopeless = FlakyReach(failures=9)
    with pytest.raises(RuntimeError, match="could not reach the site"):
        with TourBrowser(provider=FakeTinyFish(), connect=connector(hopeless), files=FakeFiles(), model=RoleModel(),
                         site_url="https://demo.example.com/", subject_id="p", uploads_root=Path("."), exec_config=ExecConfig(), max_actions=3):
            pass
    assert hopeless.reaches == 3


def test_a_step_that_cannot_be_shown_is_a_plain_note_and_two_misses_stop_the_browser():
    driver = FakeDriver(fail=frozenset({1, 2, 3, 4, 5, 6, 7, 8}))
    model = ScriptedModel(*[{"thought": "x", "step_result": "blocked", "observed": "nothing responds"}] * 6)
    with browser(driver, model) as b:
        first = b.show("look around the page", None, question="how?")
        second = b.show("look again", None, question="how?")
        third = b.show("and again", None, question="how?")
    assert first.startswith("I couldn't show this on the live site") and second.startswith("I couldn't show")
    assert "explained from the code only" in third and len(model.calls) == 2   # the third was not even tried


def test_the_tour_stops_using_the_browser_when_its_actions_run_out():
    with browser(FakeDriver(), max_actions=1) as b:
        assert b.show('click "Add"', None, question="q") is None
        assert "used its browser steps" in b.show('click "Add"', None, question="q")


# ------------------------------------------------------------------ one whole message


def services(pool, model, vm_root, driver, monkeypatch, *, repo_files=None, extra_env=None):
    env = {"DATABASE_URL": "postgres://u:p@h:5432/d", "S3_ENDPOINT": "http://s3:9000", "S3_REGION": "auto", "S3_BUCKET": "t",
           "S3_ACCESS_KEY": "a", "S3_SECRET_KEY": "b", "OPENROUTER_BASE_URL": "https://o", "TINYFISH_AGENT_BASE_URL": "https://a",
           "TINYFISH_BROWSER_BASE_URL": "https://b", "TINYFISH_FETCH_BASE_URL": "https://f", "AGENTMAIL_BASE_URL": "https://m",
           "SANDBOXD_URL": "http://sandboxd", "SANDBOXD_TOKEN": "t", **(extra_env or {})}
    vms: list[DirVm] = []

    class Sandbox:
        def open_vm(self, image, **kw):
            vms.append(DirVm(vm_root))
            return vms[-1]

        def attach(self, vm_id):
            return vms[0]

    files = FakeFiles()
    tarball = make_tar(repo_files if repo_files is not None else {"src/app.js": APP_JS.encode()})
    monkeypatch.setattr(tour_answer, "fetch_repo", lambda repo, ref, **kw: repack(tarball, file_max_kb=200, max_files=100))
    sv = Services(settings.load(env), pool, model, FakeTinyFish(), files, lambda host: None, Path("testdata"),
                  connect=connector(driver), sandbox=Sandbox())
    return sv, vms, files


def project(pool, *, live="https://demo.example.com", repo="https://github.com/o/r"):
    with pool.connection() as conn:
        user = conn.execute("INSERT INTO users (email) VALUES (%s) RETURNING id", (f"tour-{uuid.uuid4().hex[:8]}@t.example",)).fetchone()[0]
        event = conn.execute("""INSERT INTO events (owner_id, name, mode, starts_at, ends_at)
                                VALUES (%s, 'E', 'open_theme', now(), now() + interval '1 day') RETURNING id""", (user,)).fetchone()[0]
        pid = conn.execute("INSERT INTO projects (event_id, team_name, live_url, repo_url) VALUES (%s, 'T', %s, %s) RETURNING id::text",
                           (event, live, repo)).fetchone()[0]
        sid = conn.execute("INSERT INTO tour_sessions (owner_id, project_id) VALUES (%s, %s::uuid) RETURNING id::text", (user, pid)).fetchone()[0]
    return pid, sid, user


def ask(pool, session_id, question="How are items added?"):
    with pool.connection() as conn:
        return conn.execute("INSERT INTO tour_messages (session_id, question) VALUES (%s::uuid, %s) RETURNING id::text",
                            (session_id, question)).fetchone()[0]


def saved(pool, message_id):
    with pool.connection() as conn:
        return conn.execute("SELECT status, answer, error FROM tour_messages WHERE id = %s::uuid", (message_id,)).fetchone()


@needs_bash
def test_a_whole_message_reads_the_code_says_each_step_and_shows_it_on_the_site(db_pool, tmp_path, monkeypatch):
    (tmp_path / "src").mkdir()
    model = RoleModel({"tool": "search", "text": "addItem"}, PLAN)
    driver = FakeDriver()
    sv, vms, files = services(db_pool, model, tmp_path, driver, monkeypatch)
    pid, sid, _ = project(db_pool)
    mid = ask(db_pool, sid)
    with db_pool.connection() as conn:
        results_before = conn.execute("SELECT count(*) FROM results").fetchone()[0]

    result = tour_answer.answer_message(sv, mid)

    status, answer, error = saved(db_pool, mid)
    assert status == "done" and error is None and result == {"steps": 1, "mode": "full"}
    (item,) = answer["say"]
    code = next(p for p in item["proof"] if p["kind"] == "code")
    assert (code["file"], code["start"], code["commit"]) == ("src/app.js", 2, SHA) and code["lines"][0].startswith("function addItem")
    assert item["shown"] is True and any(p["kind"] == "screenshot" and p["key"].startswith(f"screens/{pid}/") for p in item["proof"])
    assert "AI explanation of the evidence" in answer["label"]
    assert [type(a).__name__ for a in driver.performed] == ["Click"]           # the guide's "click the button Add"
    with db_pool.connection() as conn:                                          # one code VM kept for the chat, one browser used
        row = conn.execute("SELECT vm_id, commit_sha, browser_runs FROM tour_sessions WHERE id = %s::uuid", (sid,)).fetchone()
        verdicts = conn.execute("SELECT count(*) FROM results").fetchone()[0]
    assert row == ("vm-test", SHA, 1) and len(vms) == 1
    assert verdicts == results_before                                            # a tour never creates a verdict


@needs_bash
def test_a_follow_up_reuses_the_code_vm_and_the_chat_history(db_pool, tmp_path, monkeypatch):
    (tmp_path / "src").mkdir()
    model = RoleModel(PLAN, {"plan": {"steps": [{"say": "Saving happens in save.", "proof": [{"kind": "code", "file": "src/app.js", "start": 6, "end": 8}]}]}})
    sv, vms, _ = services(db_pool, model, tmp_path, FakeDriver(), monkeypatch)
    _, sid, _ = project(db_pool)
    tour_answer.answer_message(sv, ask(db_pool, sid))
    second = ask(db_pool, sid, "And where is it saved?")
    tour_answer.answer_message(sv, second)
    assert len(vms) == 1 and saved(db_pool, second)[0] == "done"
    assert "Reviewer: How are items added?" in model.user_text(1) and "You said: Items are added in addItem." in model.user_text(1)


@needs_bash
def test_a_question_the_code_cannot_answer_says_so_and_invents_nothing(db_pool, tmp_path, monkeypatch):
    (tmp_path / "src").mkdir()
    model = RoleModel({"plan": {"steps": [], "not_found": "no code saves chats between sessions"}})
    sv, _, _ = services(db_pool, model, tmp_path, FakeDriver(), monkeypatch)
    _, sid, _ = project(db_pool)
    mid = ask(db_pool, sid, "How are chats remembered?")
    tour_answer.answer_message(sv, mid)
    _, answer, _ = saved(db_pool, mid)
    assert answer["say"][0]["text"].startswith("I couldn't find that in the code: no code saves chats") and answer["say"][0]["proof"] == []


@needs_bash
def test_a_plan_whose_proof_is_made_up_is_not_said(db_pool, tmp_path, monkeypatch):
    (tmp_path / "src").mkdir()
    fake = {"plan": {"steps": [{"say": "It uses a database.", "proof": [{"kind": "code", "file": "db/models.py", "start": 1, "end": 9}]}]}}
    sv, _, _ = services(db_pool, RoleModel(fake), tmp_path, FakeDriver(), monkeypatch)
    _, sid, _ = project(db_pool)
    mid = ask(db_pool, sid)
    tour_answer.answer_message(sv, mid)
    text = saved(db_pool, mid)[1]["say"][0]["text"]
    assert text.startswith("I couldn't find that in the code") and "database" not in text


def test_a_project_with_no_code_link_gets_the_live_site_and_a_plain_sentence(db_pool, tmp_path, monkeypatch):
    sv, vms, _ = services(db_pool, RoleModel(), tmp_path, FakeDriver(), monkeypatch)
    _, sid, _ = project(db_pool, repo=None)
    mid = ask(db_pool, sid)
    result = tour_answer.answer_message(sv, mid)
    (item,) = saved(db_pool, mid)[1]["say"]
    assert result["mode"] == "live_only" and "no code link" in item["text"] and item["shown"] is True and vms == []


def test_a_project_with_no_live_link_is_a_code_only_tour_and_the_browser_is_never_opened(db_pool, tmp_path, monkeypatch):
    if not HAS_BASH:
        pytest.skip("needs bash")
    (tmp_path / "src").mkdir()
    sv, _, _ = services(db_pool, RoleModel(PLAN), tmp_path, FakeDriver(), monkeypatch)
    _, sid, _ = project(db_pool, live=None)
    mid = ask(db_pool, sid)
    result = tour_answer.answer_message(sv, mid)
    assert result["mode"] == "code_only" and sv.tinyfish.sessions == []
    assert saved(db_pool, mid)[1]["say"][0]["shown"] is None


def test_unreadable_code_is_said_plainly_and_the_message_still_ends_done(db_pool, tmp_path, monkeypatch):
    sv, _, _ = services(db_pool, RoleModel(), tmp_path, FakeDriver(), monkeypatch)
    monkeypatch.setattr(tour_answer, "fetch_repo", lambda *a, **k: (_ for _ in ()).throw(CodeReadError("it may be private")))
    _, sid, _ = project(db_pool)
    mid = ask(db_pool, sid)
    tour_answer.answer_message(sv, mid)
    status, answer, _ = saved(db_pool, mid)
    assert status == "done" and "I couldn't read the code for this project (it may be private)" in answer["say"][0]["text"]


def test_a_crash_never_leaves_the_message_stuck_on_working(db_pool, tmp_path, monkeypatch):
    sv, _, _ = services(db_pool, RoleModel(), tmp_path, FakeDriver(), monkeypatch)
    monkeypatch.setattr(tour_answer, "run_guide", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    _, sid, _ = project(db_pool)
    mid = ask(db_pool, sid)
    with pytest.raises(RuntimeError):
        tour_answer.answer_message(sv, mid)
    status, _, error = saved(db_pool, mid)
    assert status == "failed" and "Please ask again" in error


@needs_bash
def test_an_answered_message_is_not_answered_twice(db_pool, tmp_path, monkeypatch):
    (tmp_path / "src").mkdir()
    model = RoleModel(PLAN)
    sv, _, _ = services(db_pool, model, tmp_path, FakeDriver(), monkeypatch)
    _, sid, _ = project(db_pool)
    mid = ask(db_pool, sid)
    tour_answer.answer_message(sv, mid)
    assert tour_answer.answer_message(sv, mid) == {"skipped": True, "reason": "already answered"} and model.guide_calls == 1
