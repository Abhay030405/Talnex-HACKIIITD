# The one base image for repo runs: Python 3.12 and Node 20 together, so a repo needs exactly one VM whatever it is
# built with (a Python API with a Node build step, a Node API with a Python tool, or either alone). Go, Java and
# compose images are added beside it when those stacks are supported; a repo that needs one of them gets that VM.
FROM python:3.12-slim-bookworm
RUN apt-get update \
 && apt-get install -y --no-install-recommends git curl ca-certificates gnupg build-essential libpq-dev make g++ \
 && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
 && apt-get install -y --no-install-recommends nodejs \
 && rm -rf /var/lib/apt/lists/* \
 && corepack enable \
 && pip install --no-cache-dir uv
WORKDIR /work
