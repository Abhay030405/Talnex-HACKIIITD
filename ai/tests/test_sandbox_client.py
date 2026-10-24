"""The sandbox client: the one place that talks to sandboxd. Uses a fake transport; the last test uses the real host."""
import base64
import io
import json
import os
import tarfile

import httpx
import pytest

from talnex_ai.sandbox.client import (
    SandboxBusy,
    SandboxClient,
    SandboxError,
    SandboxUnavailable,
    tar_folder,
)
from talnex_ai.settings import SandboxSettings

CFG = SandboxSettings("http://sandbox.test", "tok", 900, 600, 20)


class Host:
    """A pretend sandboxd. `script` maps (method, path) to a list of replies given in turn."""

    def __init__(self, **script):
        self.script = {k: list(v) for k, v in script.items()}
        self.seen: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.seen.append(request)
        key = f"{request.method} {request.url.path}"
        replies = self.script.get(key)
        if not replies:
            return httpx.Response(500, json={"error": f"unscripted call {key}"})
        reply = replies.pop(0) if len(replies) > 1 else replies[0]
        return reply if isinstance(reply, httpx.Response) else httpx.Response(200, json=reply)


def make(host: Host, cfg: SandboxSettings = CFG):
    clock = {"t": 0.0}
    slept: list[float] = []

    def sleep(s):
        slept.append(s)
        clock["t"] += s

    client = SandboxClient(cfg, httpx.Client(transport=httpx.MockTransport(host)), sleep=sleep, clock=lambda: clock["t"])
    return client, slept


VM = httpx.Response(201, json={"id": "vm1", "image": "talnex-sandbox-full", "expires_at": "2026-01-01T00:00:00Z"})


def test_a_host_that_is_not_set_up_says_so_instead_of_blaming_a_project():
    client = SandboxClient(SandboxSettings("", "", 900, 600, 20))
    with pytest.raises(SandboxUnavailable, match="not set up"):
        client.create_vm("talnex-sandbox-full")
    with pytest.raises(SandboxUnavailable):
        client.health()


def test_a_host_that_does_not_answer_is_unavailable():
    def refuse(request):
        raise httpx.ConnectError("refused")

    client = SandboxClient(CFG, httpx.Client(transport=httpx.MockTransport(refuse)))
    with pytest.raises(SandboxUnavailable, match="did not answer"):
        client.create_vm("talnex-sandbox-full")


def test_every_call_carries_the_token_and_a_wrong_token_is_a_clear_error():
    host = Host(**{"POST /v1/vms": [VM]})
    client, _ = make(host)
    client.create_vm("talnex-sandbox-full")
    assert host.seen[0].headers["Authorization"] == "Bearer tok"
    body = json.loads(host.seen[0].content)
    assert body["image"] == "talnex-sandbox-full" and body["time_limit_seconds"] == 900

    client, _ = make(Host(**{"POST /v1/vms": [httpx.Response(401, json={"error": "a valid token is required"})]}))
    with pytest.raises(SandboxError, match="refused the token"):
        client.create_vm("talnex-sandbox-full")


def test_a_full_host_is_waited_for_and_then_used():
    full = httpx.Response(429, json={"error": "full"})
    client, slept = make(Host(**{"POST /v1/vms": [full, full, VM]}))
    assert client.create_vm("talnex-sandbox-full").id == "vm1"
    assert slept == [5, 5]


def test_a_host_that_stays_full_gives_up_with_busy_not_with_a_project_problem():
    client, slept = make(Host(**{"POST /v1/vms": [httpx.Response(429, json={"error": "full"})]}))
    with pytest.raises(SandboxBusy, match="stayed full"):
        client.create_vm("talnex-sandbox-full")
    assert sum(slept) >= 20


def test_exec_returns_the_exit_code_and_the_output():
    host = Host(**{"POST /v1/vms/vm1/exec": [{"exit_code": 2, "stdout": "out", "stderr": "npm ERR!", "duration_ms": 5,
                                                "timed_out": False, "truncated": False}]})
    client, _ = make(host)
    res = client.exec("vm1", "npm test", timeout_seconds=90, env={"CI": "1"}, workdir="/work/app")
    assert (res.exit_code, res.ok, res.output) == (2, False, "out\nnpm ERR!")
    sent = json.loads(host.seen[0].content)
    assert sent == {"command": "npm test", "timeout_seconds": 90, "env": {"CI": "1"}, "workdir": "/work/app", "detach": False}


def test_a_timed_out_command_is_not_ok_even_with_exit_code_zero():
    client, _ = make(Host(**{"POST /v1/vms/vm1/exec": [{"exit_code": 0, "timed_out": True}]}))
    assert client.exec("vm1", "sleep 99").ok is False


def test_a_response_from_the_app_is_decoded_and_a_silent_app_is_a_result_not_an_exception():
    body = base64.b64encode(b'{"id": 7}').decode()
    host = Host(**{"POST /v1/vms/vm1/request": [
        {"status": 201, "headers": {"Content-Type": ["application/json"]}, "body": body, "duration_ms": 12},
        {"status": 0, "error": "connection refused: nothing is listening on port 3000"}]})
    client, _ = make(host)
    res = client.request("vm1", "POST", 3000, "/items", headers={"X-A": "1"}, body=b'{"a":1}')
    assert res.status == 201 and res.json() == {"id": 7} and res.header("content-type") == "application/json" and res.answered
    sent = json.loads(host.seen[0].content)
    assert sent["method"] == "POST" and sent["port"] == 3000 and base64.b64decode(sent["body"]) == b'{"a":1}'
    silent = client.request("vm1", "GET", 3000, "/")
    assert not silent.answered and "connection refused" in silent.error


def test_a_vm_that_has_ended_gets_a_plain_message():
    client, _ = make(Host(**{"POST /v1/vms/gone/exec": [httpx.Response(404, json={"error": "no such VM"})]}))
    with pytest.raises(SandboxError, match="no longer exists"):
        client.exec("gone", "ls")


def test_the_vm_block_destroys_the_vm_even_when_the_work_inside_fails():
    host = Host(**{"POST /v1/vms": [VM], "DELETE /v1/vms/vm1": [httpx.Response(204)]})
    client, _ = make(host)
    with pytest.raises(ValueError):
        with client.vm("talnex-sandbox-full") as vm:
            assert vm.id == "vm1"
            raise ValueError("the work failed")
    assert [f"{r.method} {r.url.path}" for r in host.seen] == ["POST /v1/vms", "DELETE /v1/vms/vm1"]


def test_a_failed_destroy_never_hides_the_real_result():
    host = Host(**{"POST /v1/vms": [VM], "DELETE /v1/vms/vm1": [httpx.Response(500, json={"error": "x"})]})
    client, _ = make(host)
    with client.vm("talnex-sandbox-full") as vm:
        assert vm.id == "vm1"  # leaving the block must not raise: the reaper cleans up at the time limit


def test_wait_for_port_polls_until_something_listens_or_time_runs_out():
    host = Host(**{"GET /v1/vms/vm1/ports": [{"ports": []}, {"ports": []}, {"ports": [3000]}]})
    client, slept = make(host)
    from talnex_ai.sandbox.client import SandboxVM, VmInfo
    vm = SandboxVM(client, VmInfo("vm1", "i", "e"))
    assert vm.wait_for_port(timeout_seconds=30) == 3000 and slept == [1.0, 1.0]

    never = Host(**{"GET /v1/vms/vm1/ports": [{"ports": []}]})
    client, _ = make(never)
    assert SandboxVM(client, VmInfo("vm1", "i", "e")).wait_for_port(timeout_seconds=3) is None


def test_a_folder_is_packed_without_libraries_or_git_history(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.js").write_text("x")
    (tmp_path / "node_modules" / "lib").mkdir(parents=True)
    (tmp_path / "node_modules" / "lib" / "big.js").write_text("y")
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "HEAD").write_text("z")
    (tmp_path / "package.json").write_text("{}")
    names = sorted(tarfile.open(fileobj=io.BytesIO(tar_folder(str(tmp_path)))).getnames())
    assert names == ["package.json", "src/app.js"]


@pytest.mark.skipif(os.environ.get("TALNEX_TEST_SANDBOXD") != "1", reason="TALNEX_TEST_SANDBOXD is not 1")
def test_the_real_host_runs_an_app_we_upload(tmp_path):
    """Needs a running sandboxd and the node image. SANDBOXD_URL and SANDBOXD_TOKEN come from the environment."""
    cfg = SandboxSettings(os.environ["SANDBOXD_URL"], os.environ["SANDBOXD_TOKEN"], 300, 120, 60)
    client = SandboxClient(cfg)
    assert client.health()["status"] == "ok"
    (tmp_path / "server.js").write_text(
        "require('http').createServer((q,r)=>{r.setHeader('Content-Type','application/json');r.end(JSON.stringify({url:q.url}))}).listen(3000)")
    with client.vm("talnex-sandbox-full") as vm:
        vm.upload_dir(str(tmp_path), "/work/app")
        assert vm.exec("ls /work/app").stdout.strip() == "server.js"
        vm.exec("node server.js > /tmp/app.log 2>&1", workdir="/work/app", detach=True)
        assert vm.wait_for_port(timeout_seconds=30) == 3000
        res = vm.request("GET", 3000, "/hello")
        assert res.status == 200 and res.json() == {"url": "/hello"}
