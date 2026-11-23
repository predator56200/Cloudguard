"""API routers — one module per resource.

A router is a THIN HTTP adapter (docs/02):
    parse → authorise → call a core service → serialise.

If a router contains a `for` loop over business objects, an `if` about severity, or a
SQLAlchemy `select()`, it is doing a job that belongs one layer down. The test: could this
logic be needed by the WORKER? If yes, it belongs in a service.

M0 ships only `health`. There is nothing to authenticate yet, so there is nothing else that
could honestly exist.

Arriving:
    M2  cloud_accounts.py
    M4  scans.py, findings.py, score.py, rules.py
    M8  billing.py, public_scan.py, webhooks/
"""

from cloudguard_api.routers import health

__all__ = ["health"]
