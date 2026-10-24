FROM python:3.10-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app
COPY pyproject.toml ./
COPY talnex_ai ./talnex_ai
RUN pip install . && useradd --create-home --uid 10001 talnex

USER talnex
CMD ["python", "-m", "talnex_ai.worker"]
