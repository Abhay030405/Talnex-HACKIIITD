# Sandbox host setup

The sandbox host runs `sandboxd` (architecture section 28). For now the host is the founder's laptop with Docker Desktop
(Linux containers). Each VM is a container made from one of our own images; nothing else can be started.

## One-time

1. Start Docker Desktop.
2. Build the base image: `bash sandbox/host/build_images.sh` (builds `talnex-sandbox-full`: Python 3.12 and Node 20 together, so any Node or Python repo runs in one VM).
3. Put these in `.env` (see `.env.example`): `SANDBOXD_LISTEN_ADDR`, `SANDBOXD_TOKEN` (a long random string),
   `SANDBOX_DRIVER=docker`, and `SANDBOXD_URL` for the callers (from a container: `http://host.docker.internal:7070`).

## Run

`sandboxd` is part of the main Docker Compose stack: `docker compose up -d --build` builds the VM base image
(`talnex-sandbox-full`, the `sandbox-image` service, which exits once built) and starts `sandboxd` with the host's Docker
socket mounted, so each VM is a sibling container. Callers use `SANDBOXD_URL=http://sandboxd:7070`.

- Health: `docker compose exec sandboxd wget -qO- http://127.0.0.1:7070/healthz` (driver, running VMs, maximum).
- Logs: `docker compose logs -f sandboxd`. VMs: `docker ps --filter label=talnex.sandbox=1`.

Running it by hand outside Compose still works: `cd backend && go build -o sandboxd.exe ./cmd/sandboxd`, then
`SANDBOXD_LISTEN_ADDR=0.0.0.0:7070 SANDBOXD_TOKEN=... SANDBOX_DRIVER=docker ./sandboxd.exe` (and point `SANDBOXD_URL`
at `http://host.docker.internal:7070`).

## Rules that always hold

- Every VM has a time limit, a CPU and memory limit, and is destroyed by the reaper at its limit.
- A VM is fresh for every run and never reused. At start-up, sandboxd destroys any VM left by an earlier run.
- No TalNex key, database address or token is ever passed into a VM.
- Strong isolation (Firecracker, restricted network) is deferred; until then only repos we chose are run here (28.13).
