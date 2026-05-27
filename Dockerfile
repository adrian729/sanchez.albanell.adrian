# ─── Stage 1: builder ──────────────────────────────────────────────────────
# Builds the Python venv and runs the Tailwind + post-process pipeline so the
# final image ships with the compiled static/cv.css (no Tailwind tooling needed
# at runtime).
FROM python:3.13-slim-bookworm AS builder

# uv (Python package manager)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

# curl + CA certs so install-tailwind.sh can fetch the Tailwind binary
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
WORKDIR /app

# Python deps (cached on uv.lock / pyproject.toml changes)
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --frozen --no-install-project --no-dev

# Tailwind v4 standalone binary (changes rarely)
COPY scripts/install-tailwind.sh scripts/install-tailwind.sh
RUN ./scripts/install-tailwind.sh

# Sources that drive the CSS build
COPY scripts/build-css.py scripts/build-css.py
COPY static/src ./static/src
COPY templates ./templates

# Build static/cv.css. Invoke the script via the venv's Python so the
# uv-based shebang isn't required at build time.
RUN /app/.venv/bin/python scripts/build-css.py


# ─── Stage 2: runtime ──────────────────────────────────────────────────────
FROM python:3.13-slim-bookworm

# WeasyPrint native dependencies + curl for the healthcheck
RUN apt-get update && apt-get install -y --no-install-recommends \
        libpango-1.0-0 \
        libpangoft2-1.0-0 \
        libharfbuzz-subset0 \
        libgdk-pixbuf2.0-0 \
        shared-mime-info \
        libcairo2 \
        curl \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd -r appuser && useradd -r -g appuser appuser
WORKDIR /app

# Copy only what's needed at runtime: venv + app + templates + static assets.
# Runtime needs photo + built CSS, but NOT Tailwind sources (static/src/) —
# .dockerignore can't strip src/ globally because the builder stage needs it,
# so we copy each runtime asset explicitly here.
COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/static/cv.css /app/static/cv.css
COPY static/photo.jpg /app/static/photo.jpg
COPY static/fonts /app/static/fonts
COPY app /app/app
COPY templates /app/templates

RUN chown -R appuser:appuser /app
USER appuser

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1

HEALTHCHECK --interval=1h --timeout=5s --start-period=10s --start-interval=10s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

EXPOSE 8000

CMD ["fastapi", "run", "app/main.py", "--port", "8000"]
