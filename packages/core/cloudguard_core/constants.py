"""Shared constants.

WHY THIS FILE EXISTS
--------------------
A magic number that appears in three files will eventually be changed in two of them. Naming
it once makes the inconsistency impossible.

WHAT BELONGS HERE
-----------------
Values that are TRUE ACROSS THE WHOLE SYSTEM and are not configurable per-environment.

WHAT DOES NOT
-------------
- Anything an operator might want to tune per environment → `config.py` (env var).
- Anything a customer's plan changes (scan frequency, account limits) → the billing service
  (M8). A plan limit hard-coded here is a plan limit you must redeploy to change.
- Domain enums (Severity, ResourceType) → they live with their domain module (M3/M4), not in
  a constants junk-drawer. A file called `constants.py` attracts clutter; keep it disciplined.
"""

from __future__ import annotations

from typing import Final

# --- Identity ---------------------------------------------------------------
SERVICE_NAME: Final = "cloudguard"
API_VERSION: Final = "v1"
API_PREFIX: Final = f"/{API_VERSION}"

# --- HTTP -------------------------------------------------------------------
# Echoed on every response and bound to every log line in the request (docs/02 § step 2).
# The single most useful field in an incident: it joins a customer's screenshot to our logs.
REQUEST_ID_HEADER: Final = "X-Request-ID"

# Required on POSTs with side effects (docs/05). Prevents a double-clicked "Scan now" from
# enqueueing two scans.
IDEMPOTENCY_KEY_HEADER: Final = "Idempotency-Key"

# --- Pagination (docs/05 § Conventions) -------------------------------------
# Cursor-based, never offset: on a live-updating findings table, offset pagination shows
# duplicates and skips rows as data shifts under the reader.
DEFAULT_PAGE_SIZE: Final = 25
MAX_PAGE_SIZE: Final = 100  # a cap is a DoS control, not a nicety

# --- Timeouts ---------------------------------------------------------------
# Deliberately generous for scans: a large customer AWS account is genuinely slow, and a
# scan that times out at 60s would silently fail for exactly the customers we most want.
SCAN_TIMEOUT_SECONDS: Final = 900  # 15 min
DEFAULT_JOB_TIMEOUT_SECONDS: Final = 120
HTTP_CLIENT_TIMEOUT_SECONDS: Final = 30

# --- Graceful shutdown ------------------------------------------------------
# On SIGTERM (every Railway deploy sends one), finish in-flight work before exiting.
# Without this, every deploy kills every running scan. See docs/07 § Failure recovery.
GRACEFUL_SHUTDOWN_SECONDS: Final = 60
