# =============================================================================
# apps/worker — multi-stage Dockerfile
# =============================================================================
# Nearly identical to apps/api/Dockerfile, with three deliberate differences:
#
#   1. NO EXPOSE, NO PORTS. The worker has ZERO inbound network surface (docs/08 § T3).
#      It holds short-lived customer AWS credentials in memory. Nothing should be able to
#      reach it. The API is public because it must be; the worker is not, because it needn't.
#
#   2. NO HEALTHCHECK. With no HTTP server there is nothing to curl. ARQ writes a health key
#      into Redis every 30s instead (main.py § health_check_interval), which is how an
#      operator confirms it's alive.
#
#   3. NO `curl` PACKAGE. It was only installed in the API image FOR the healthcheck. Fewer
#      packages = smaller attack surface, and this is the container holding the credentials.
#
# The base stage is otherwise copy-pasted rather than shared via a common base image. That is
# a conscious trade: a shared base image would need its own build/push pipeline for a saving
# of ~15 lines. Two small, readable Dockerfiles beat one clever one.
# =============================================================================

FROM python:3.12-slim AS base

# PYTHONUNBUFFERED matters even more here than in the API: when a worker is OOM-killed
# mid-scan, the buffered logs explaining WHY are exactly the ones you lose.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Non-root. This container will hold customer AWS credentials in memory from M2 onward — it
# is the single most sensitive process we run. Root inside a container plus any escape
# primitive is root on a host shared with every other customer's workload.
RUN groupadd --system --gid 1001 cloudguard \
    && useradd --system --uid 1001 --gid cloudguard --create-home cloudguard

# Manifests first, source last — see apps/api/Dockerfile for the layer-caching rationale.
COPY packages/core/pyproject.toml   /app/packages/core/
COPY apps/worker/pyproject.toml     /app/apps/worker/

# --- dev ---------------------------------------------------------------------
FROM base AS dev

COPY packages/core /app/packages/core
COPY apps/worker   /app/apps/worker
RUN pip install -e "/app/packages/core[dev]" -e "/app/apps/worker[dev]"

# Root tooling config — see apps/api/Dockerfile for the rationale.
COPY pyproject.toml /app/pyproject.toml

USER cloudguard

# ARQ has no --reload. `--watch` re-execs the worker when source changes, which is the local
# development equivalent. In production we run without it.
CMD ["arq", "cloudguard_worker.main.WorkerSettings", "--watch", "/app"]

# --- prod --------------------------------------------------------------------
FROM base AS prod

COPY packages/core /app/packages/core
COPY apps/worker   /app/apps/worker
RUN pip install "/app/packages/core" "/app/apps/worker"

USER cloudguard

# ARQ handles SIGTERM: stop accepting new jobs, drain in-flight ones, then run `on_shutdown`
# (context.py) which disposes the DB pool. Every deploy sends SIGTERM — without this, every
# deploy would kill every running scan (docs/07 § Failure recovery).
CMD ["arq", "cloudguard_worker.main.WorkerSettings"]
