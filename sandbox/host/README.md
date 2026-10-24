# Sandbox host setup

The sandbox host runs `sandboxd` (architecture section 28). For now the host is the founder's laptop with Docker Desktop
(Linux containers). Each VM is a container made from one of our own images; nothing else can be started.

## One-time

1. Start Docker Desktop.
2. Build the base image: `bash sandbox/host/build_images.sh` (builds `talnex-sandbox-full`: Python 3.12 and Node 20 together, so any Node or Python repo runs in one VM).
3. Put these in `.env` (see `.env.example`): `SANDBOXD_LISTEN_ADDR`, `SANDBOXD_TOKEN` (a long random string),
   `SANDBOX_DRIVER=docker`, and `SANDBOXD_URL` for the callers (from a container: `http://host.docker.internal:7070`).

## Run

```
cd backend && go build -o sandboxd.exe ./cmd/sandboxd     # build outside the repo folder if Windows blocks it
SANDBOXD_LISTEN_ADDR=0.0.0.0:7070 SANDBOXD_TOKEN=... SANDBOX_DRIVER=docker ./sandboxd.exe
```

`GET /healthz` needs no token and shows the driver, how many VMs run and the maximum.

## Rules that always hold

- Every VM has a time limit, a CPU and memory limit, and is destroyed by the reaper at its limit.
- A VM is fresh for every run and never reused. At start-up, sandboxd destroys any VM left by an earlier run.
- No TalNex key, database address or token is ever passed into a VM.
- Strong isolation (Firecracker, restricted network) is deferred; until then only repos we chose are run here (28.13).
