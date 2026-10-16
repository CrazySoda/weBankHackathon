# ClearTrade backend — build with pinned base (digest-pin in prod builds).
FROM python:3.12-slim

# uv for fast, hash-locked installs
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# Install deps first (layer-cached); the lockfile pins hashes (rule 0.11)
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY app ./app
# Loaded at runtime relative to the package (prompts, skills, rule pack); without
# these the graph fails at the first node.
COPY prompts ./prompts
COPY skills ./skills
COPY seed/rules ./seed/rules
# read by the one-click demo loader, POST /deals/seed/{id}
COPY seed/deals/pdfs ./seed/deals/pdfs
RUN uv sync --frozen --no-dev

ENV PATH="/app/.venv/bin:$PATH"
EXPOSE 8000

# Health-checked by compose; uvicorn with a single worker for the demo
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
