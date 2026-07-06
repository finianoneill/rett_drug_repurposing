FROM python:3.12-slim AS base

WORKDIR /app

# uv version pin protects reproducibility.
RUN pip install --no-cache-dir uv==0.5.*

# Dependency layer — cached unless lockfile/pyproject changes.
# Copy lockfile if present so reproducible builds can use it; tolerate its
# absence on a fresh checkout (commit 1 ships before `make install`).
# LICENSE and README are required here because building the editable project
# validates the `license`/`readme` metadata declared in pyproject.toml.
COPY pyproject.toml ./
COPY uv.lock* ./
COPY LICENSE README.md ./
RUN if [ -f uv.lock ]; then uv sync --frozen --no-dev; else uv sync --no-dev; fi

# Source — invalidates only when code changes.
COPY src/ ./src/
COPY scripts/ ./scripts/

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

EXPOSE 8000

CMD ["uvicorn", "rett_repurposing.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
