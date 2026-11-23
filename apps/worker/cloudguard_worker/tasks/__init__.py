"""Background tasks — thin adapters over `core.services`.

M0 ships only `ping`, to prove the queue is wired.

Arriving (docs/07):
    M4  scan.py         run_scan(org_id, cloud_account_id, scan_id)   queue: scans
    M4  reaper.py       reap_stuck_scans()  ← the safety net for the WHOLE async system
    M6  enrich.py       enrich_finding(finding_id)                    queue: default
    M7  report.py       send_weekly_report(org_id)                    queue: reports
    M7  snapshot.py     capture_daily_scores()
    M9  remediation.py  open_fix_pr(finding_id)

THE RULE FOR EVERY TASK IN THIS FOLDER:

  * IDEMPOTENT. A worker can crash mid-job and ARQ will re-run it. `run_scan` uses a
    deterministic `job_id` (`scan:{scan_id}`) so a double-enqueue is a no-op, and
    reconciliation is a pure convergent function — so re-running a half-finished scan is
    SAFE. That is the payoff for making reconciliation pure (docs/03).

  * RETRY CLASSIFICATION IS IN THE TYPE, not in a caller's judgement.
    `RetryableError` → back off and retry.
    `PermanentError` → dead-letter immediately.
    Retrying an AccessDenied five times wastes our time and lights up the customer's
    CloudTrail like an attack (docs/07 § Retries).

  * NO BARE `except: pass`. In a security scanner, a swallowed exception becomes
    "0 findings, score 100" reported to a customer whose cloud is on fire.
"""

from cloudguard_worker.tasks.ping import ping

__all__ = ["ping"]
