"""The only code that talks to sandboxd, the VM host (architecture section 28).

Everything else in TalNex asks this client. It never blames a project for the host's trouble: a host that is not set up,
cannot be reached or is full raises a SandboxError that stages turn into "could not run: <reason>".

    with client.vm("talnex-sandbox-full") as vm:
        vm.exec("git clone --depth 1 https://github.com/a/b app", timeout_seconds=120)
        vm.exec("npm start > /tmp/app.log 2>&1", workdir="/work/app", detach=True)
        port = vm.wait_for_port(timeout_seconds=60)
        print(vm.request("GET", port, "/health").status)
"""
from __future__ import annotations

import io
import json
import os
import tarfile
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Callable, Iterator, Mapping, Optional

import httpx

from talnex_ai.settings import SandboxSettings

# Folders that are never copied into a VM: they are huge and the VM installs its own.
SKIPPED_FOLDERS = {".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build", ".next", "target"}


class SandboxError(RuntimeError):
    """The sandbox host could not do what was asked. Never a mark against the project."""


class SandboxUnavailable(SandboxError):
    """The sandbox host is not set up or cannot be reached."""


class SandboxBusy(SandboxError):
    """The host stayed full for the whole time we were willing to wait."""


@dataclass(frozen=True)
class ExecResult:
    exit_code: int
    stdout: str = ""
    stderr: str = ""
    duration_ms: int = 0
    timed_out: bool = False
    truncated: bool = False

    @property
    def ok(self) -> bool:
        return self.exit_code == 0 and not self.timed_out

    @property
    def output(self) -> str:
        """Both streams together, which is what a person reads when a command fails."""
        return (self.stdout + ("\n" if self.stdout and self.stderr else "") + self.stderr).strip()


@dataclass(frozen=True)
class HttpResult:
    """What the app answered. `error` is set (and status is 0) when no answer came back at all."""

    status: int
    headers: Mapping[str, list[str]] = field(default_factory=dict)
    body: bytes = b""
    duration_ms: int = 0
    truncated: bool = False
    error: Optional[str] = None

    @property
    def answered(self) -> bool:
        return self.status > 0

    @property
    def text(self) -> str:
        return self.body.decode("utf-8", errors="replace")

    def json(self) -> Any:
        return json.loads(self.body.decode("utf-8"))

    def header(self, name: str) -> Optional[str]:
        values = self.headers.get(name.title()) or self.headers.get(name)
        return values[0] if values else None


@dataclass(frozen=True)
class VmInfo:
    id: str
    image: str
    expires_at: str


class SandboxClient:
    def __init__(
        self,
        cfg: SandboxSettings,
        http: Optional[httpx.Client] = None,
        *,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ):
        self.cfg = cfg
        self._http = http
        self._sleep = sleep
        self._clock = clock

    # ------------------------------------------------------------------ plumbing

    def _client(self) -> httpx.Client:
        if not self.cfg.enabled:
            raise SandboxUnavailable("the sandbox host is not set up (SANDBOXD_URL and SANDBOXD_TOKEN are empty)")
        if self._http is None:
            self._http = httpx.Client(timeout=self.cfg.build_timeout_seconds + 60)
        return self._http

    def _call(self, method: str, path: str, *, json_body: Any = None, content: Optional[bytes] = None,
              params: Optional[dict] = None, timeout: Optional[float] = None, ok: tuple[int, ...] = (200,)) -> httpx.Response:
        headers = {"Authorization": f"Bearer {self.cfg.token}"}
        if content is not None:
            headers["Content-Type"] = "application/x-tar"
        try:
            resp = self._client().request(method, self.cfg.url + path, headers=headers, json=json_body, content=content,
                                          params=params, timeout=timeout)
        except httpx.TransportError as exc:
            raise SandboxUnavailable(f"the sandbox host did not answer ({type(exc).__name__})") from exc
        if resp.status_code in ok:
            return resp
        message = _error_text(resp)
        if resp.status_code == 401:
            raise SandboxError("the sandbox host refused the token")
        if resp.status_code == 429:
            raise SandboxBusy(message)
        if resp.status_code == 404:
            raise SandboxError("that VM no longer exists (it ended or ran past its time limit)")
        raise SandboxError(f"the sandbox host answered {resp.status_code}: {message}")

    # ------------------------------------------------------------------ calls

    def health(self) -> dict:
        """Needs no token. Raises SandboxUnavailable when the host is down or not set up."""
        if not self.cfg.url:
            raise SandboxUnavailable("the sandbox host is not set up (SANDBOXD_URL is empty)")
        try:
            resp = (self._http or httpx.Client(timeout=15)).get(self.cfg.url + "/healthz", timeout=15)
        except httpx.TransportError as exc:
            raise SandboxUnavailable(f"the sandbox host did not answer ({type(exc).__name__})") from exc
        data = resp.json()
        if resp.status_code != 200:
            raise SandboxUnavailable(f"the sandbox host is not healthy: {data.get('status')}")
        return data

    def create_vm(self, image: str, *, cpus: int = 0, memory_mb: int = 0, time_limit_seconds: int = 0,
                  services=()) -> VmInfo:
        """Make a fresh VM. When the host is full this waits, up to the configured time, for a place to open.
        `services` are backing stores (postgres, redis...) to start beside it; the host refuses any it does not know."""
        deadline = self._clock() + self.cfg.busy_wait_seconds
        body = {"image": image, "cpus": cpus, "memory_mb": memory_mb,
                "time_limit_seconds": time_limit_seconds or self.cfg.vm_time_limit_seconds,
                "services": list(services)}
        while True:
            try:
                data = self._call("POST", "/v1/vms", json_body=body, ok=(201,)).json()
                return VmInfo(data["id"], data["image"], data["expires_at"])
            except SandboxBusy as busy:
                if self._clock() >= deadline:
                    raise SandboxBusy(f"the sandbox host stayed full for {self.cfg.busy_wait_seconds} s") from busy
                self._sleep(5)

    def upload(self, vm_id: str, archive: bytes, directory: str = "/work") -> None:
        self._call("POST", f"/v1/vms/{vm_id}/files", content=archive, params={"dir": directory}, ok=(204,))

    def upload_dir(self, vm_id: str, local_dir: str, directory: str = "/work") -> None:
        """Copy a local folder into the VM (without .git, node_modules and the like)."""
        self.upload(vm_id, tar_folder(local_dir), directory)

    def exec(self, vm_id: str, command: str, *, timeout_seconds: Optional[int] = None, env: Optional[Mapping[str, str]] = None,
             workdir: str = "", detach: bool = False) -> ExecResult:
        limit = timeout_seconds or self.cfg.build_timeout_seconds
        data = self._call(
            "POST", f"/v1/vms/{vm_id}/exec",
            json_body={"command": command, "timeout_seconds": limit, "env": dict(env or {}), "workdir": workdir, "detach": detach},
            timeout=limit + 60,
        ).json()
        return ExecResult(data["exit_code"], data.get("stdout", ""), data.get("stderr", ""), data.get("duration_ms", 0),
                          data.get("timed_out", False), data.get("truncated", False))

    def ports(self, vm_id: str) -> list[int]:
        return list(self._call("GET", f"/v1/vms/{vm_id}/ports", timeout=60).json().get("ports") or [])

    def request(self, vm_id: str, method: str, port: int, path: str, *, headers: Optional[Mapping[str, str]] = None,
                body: Optional[bytes] = None, timeout_seconds: int = 30) -> HttpResult:
        import base64

        data = self._call(
            "POST", f"/v1/vms/{vm_id}/request",
            json_body={"method": method, "port": port, "path": path, "headers": dict(headers or {}),
                       "body": base64.b64encode(body).decode() if body else None, "timeout_seconds": timeout_seconds},
            timeout=timeout_seconds + 60,
        ).json()
        raw = data.get("body")
        return HttpResult(
            status=data.get("status", 0), headers=data.get("headers") or {}, body=base64.b64decode(raw) if raw else b"",
            duration_ms=data.get("duration_ms", 0), truncated=data.get("truncated", False), error=data.get("error") or None,
        )

    def destroy(self, vm_id: str) -> None:
        self._call("DELETE", f"/v1/vms/{vm_id}", ok=(204,), timeout=60)

    def open_vm(self, image: str, **kwargs: Any) -> "SandboxVM":
        """A VM that is NOT destroyed automatically, for work that spans several stages. The caller must destroy it
        (SandboxVM.destroy); if that never happens, the host's reaper removes it at its time limit."""
        return SandboxVM(self, self.create_vm(image, **kwargs))

    def attach(self, vm_id: str) -> "SandboxVM":
        """A handle on a VM an earlier stage left running. Nothing is checked here: the first call tells if it is still alive."""
        return SandboxVM(self, VmInfo(vm_id, "", ""))

    @contextmanager
    def vm(self, image: str, **kwargs: Any) -> Iterator["SandboxVM"]:
        """A VM that is always destroyed when the block ends, even after an error."""
        info = self.create_vm(image, **kwargs)
        handle = SandboxVM(self, info)
        try:
            yield handle
        finally:
            try:
                self.destroy(info.id)
            except SandboxError:
                pass  # the reaper removes it at its time limit


class SandboxVM:
    """One VM, with its id filled in."""

    def __init__(self, client: SandboxClient, info: VmInfo):
        self._c = client
        self.info = info

    @property
    def id(self) -> str:
        return self.info.id

    def exec(self, command: str, **kwargs: Any) -> ExecResult:
        return self._c.exec(self.id, command, **kwargs)

    def upload(self, archive: bytes, directory: str = "/work") -> None:
        self._c.upload(self.id, archive, directory)

    def upload_dir(self, local_dir: str, directory: str = "/work") -> None:
        self._c.upload_dir(self.id, local_dir, directory)

    def ports(self) -> list[int]:
        return self._c.ports(self.id)

    def destroy(self) -> None:
        """Destroy this VM. Never raises: a VM that is already gone, or a host that cannot be reached, is left to the reaper."""
        try:
            self._c.destroy(self.id)
        except SandboxError:
            pass

    def request(self, method: str, port: int, path: str, **kwargs: Any) -> HttpResult:
        return self._c.request(self.id, method, port, path, **kwargs)

    def wait_for_port(self, *, timeout_seconds: int = 60, port: Optional[int] = None, poll_seconds: float = 1.0) -> Optional[int]:
        """Wait until something listens (on `port`, or on any port) and return the port, or None if nothing does in time."""
        deadline = self._c._clock() + timeout_seconds
        while True:
            open_ports = self.ports()
            if port is not None and port in open_ports:
                return port
            if port is None and open_ports:
                return open_ports[0]
            if self._c._clock() >= deadline:
                return None
            self._c._sleep(poll_seconds)


def tar_folder(local_dir: str) -> bytes:
    """A tar archive of a folder's contents, without the folders in SKIPPED_FOLDERS."""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tar:
        for root, dirs, files in os.walk(local_dir):
            dirs[:] = [d for d in dirs if d not in SKIPPED_FOLDERS]
            for name in files:
                full = os.path.join(root, name)
                tar.add(full, arcname=os.path.relpath(full, local_dir).replace(os.sep, "/"), recursive=False)
    return buf.getvalue()


def _error_text(resp: httpx.Response) -> str:
    try:
        return str(resp.json().get("error") or resp.text)[:300]
    except ValueError:
        return resp.text[:300]
