# =============================================================================
# apps/api — multi-stage Dockerfile
# =============================================================================
# Build context is the REPO ROOT (see docker-compose.yml), because this image needs BOTH
# `packages/core` and `apps/api`. A Dockerfile can only COPY from inside its context, so the
# context must be the common ancestor.
#
# Three stages:
#   base  shared foundation (python, system deps, non-root user)
#   dev   + dev dependencies + hot reload      → used by docker-compose
#   prod  slim, hardened, no dev deps          → used by Railway/CI
#
# WHY MULTI-STAGE: the dev image carries pytest, mypy, ruff and a bind-mounted source tree.
# Shipping that to production means shipping tools an attacker can use, and an image three
# times larger than necessary. Same Dockerfile, different `target`.
# =============================================================================

# --- base --------------------------------------------------------------------
# `-slim` not `-alpine`: Alpine uses musl libc, and Python wheels are built against glibc.
# On Alpine, pip falls back to compiling from source — asyncpg and friends turn a 30-second
# build into a 6-minute one, and occasionally just fail. Slim is the right default for Python.
FROM python:3.12-slim AS base

# PYTHONDONTWRITEBYTECODE: no .pyc files — the container is ephemeral, they're just noise.
# PYTHONUNBUFFERED:        CRITICAL. Without it, Python buffers stdout, and when the container
#                          is killed the last (usually most interesting) log lines are LOST.
#                          Debugging a crash whose final logs vanished is a special misery.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# `curl` for container-level healthchecks/debugging. Nothing else — every package is
# attack surface (docs/08 § T3: we hold read access to N production clouds).
# `apt-get upgrade` pulls in Debian security fixes released AFTER the python:3.12-slim image
# was last rebuilt. Without it, Trivy flags OS packages (zlib, openssl, util-linux...) that
# already have a patched version available, and we would ship the vulnerable one.
RUN apt-get update \
    && apt-get upgrade -y \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

# --- NON-ROOT USER: a genuine security control, not a checkbox ---
# By default a container runs as root (uid 0). If an attacker achieves RCE in our API, root
# inside the container plus any container-escape primitive (a kernel bug, a careless volume
# mount, a privileged flag) becomes root on the HOST — which runs every other customer's
# workload. Running as an unprivileged user removes that entire escalation chain for one line.
RUN groupadd --system --gid 1001 cloudguard \
    && useradd --system --uid 1001 --gid cloudguard --create-home cloudguard

# Dependency manifests FIRST, source LAST. This is the single biggest build-speed lever:
# Docker caches each layer, and a layer is invalidated only when its inputs change. Source
# changes on every commit; dependencies change monthly. Copying source first would reinstall
# every dependency on every commit — turning a 5-second rebuild into a 3-minute one.
COPY packages/core/pyproject.toml /app/packages/core/
COPY apps/api/pyproject.toml      /app/apps/api/

# --- dev ---------------------------------------------------------------------
FROM base AS dev

# `-e` (editable): the package points AT the source tree rather than copying it. Combined with
# the compose bind-mount, this means an edit on your host is live in the container instantly.
COPY packages/core /app/packages/core
COPY apps/api      /app/apps/api
RUN pip install -e "/app/packages/core[dev]" -e "/app/apps/api[dev]"

# Alembic config + migration scripts (repo root — see alembic.ini for why).
COPY alembic.ini  /app/alembic.ini
COPY migrations   /app/migrations

# Root tooling config: ruff, black, mypy and pytest all read /app/pyproject.toml, and
# import-linter reads /app/.importlinter. Without these, `make lint` and `make test` inside
# the container silently fall back to DEFAULT settings — which means CI and local would be
# enforcing two different rulesets, and the whole point of `make lint` is that they don't.
COPY pyproject.toml  /app/pyproject.toml
COPY .importlinter   /app/.importlinter

USER cloudguard
EXPOSE 8000

# --reload watches the bind-mounted source. NEVER use it in production: it spawns a file
# watcher, disables multi-worker mode, and is not hardened for untrusted input.
CMD ["uvicorn", "cloudguard_api.main:app", \
     "--host", "0.0.0.0", "--port", "8000", \
     "--reload", "--reload-dir", "/app/apps/api", "--reload-dir", "/app/packages/core"]

# --- prod --------------------------------------------------------------------
FROM base AS prod

# No [dev] extras: pytest, mypy and ruff have no business in a production image.
COPY packages/core /app/packages/core
COPY apps/api      /app/apps/api
# Install, then remove pip itself. Nothing installs packages at runtime, and pip's own
# vendored libraries are attack surface that Trivy reports against this image.
RUN pip install "/app/packages/core" "/app/apps/api" \
    && pip uninstall -y pip

COPY alembic.ini /app/alembic.ini
COPY migrations  /app/migrations

USER cloudguard
EXPOSE 8000

# Liveness only — NEVER /readyz here (routers/health.py explains at length why a readiness
# failure must not trigger a container restart).
HEALTHCHECK --interval=30s --timeout=3s --start-period=15s --retries=3 \
    CMD curl -fsS http://localhost:8000/healthz || exit 1

# Uvicorn handles SIGTERM correctly: it stops accepting connections, drains in-flight
# requests, then runs the lifespan teardown (main.py) which closes the DB pool cleanly.
# Every deploy sends SIGTERM; without that drain, in-flight customer requests die mid-response.
#
# Workers: kept at 1. Railway scales by adding CONTAINERS, not by adding processes inside one
# container — that keeps CPU/memory limits meaningful per replica and avoids two layers of
# concurrency management fighting each other.
CMD ["uvicorn", "cloudguard_api.main:app", \
     "--host", "0.0.0.0", "--port", "8000", \
     "--workers", "1", "--timeout-graceful-shutdown", "60"]
