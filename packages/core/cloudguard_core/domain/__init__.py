"""The domain — PURE PYTHON. No I/O. No SQLAlchemy. No network. No clock.

This is the bottom of the dependency graph (docs/02): it imports NOTHING of ours.

Everything here is a pure function or an immutable value object, which is why docs/10 demands
**100% test coverage** of this package and gets it cheaply: there is nothing to mock, so
there is no excuse.

Arriving here:
    M3  severity.py    Severity enum + effective-severity adjustment
    M4  fingerprint.py sha256(cloud_account_id|rule_id|resource_arn) — finding identity
    M4  lifecycle.py   the observation → finding reconciliation state machine
    M4  scoring.py     the 0–100 security score

`lifecycle.py` is the single highest-stakes file in the product: get reconciliation wrong and
a scan with broken credentials auto-resolves every finding and reports a perfect score to a
customer whose cloud is on fire (docs/12 § R3). It is pure precisely so that we can test
every one of its seven state transitions exhaustively, in milliseconds, with no database.

That is the entire argument for this package existing.
"""
