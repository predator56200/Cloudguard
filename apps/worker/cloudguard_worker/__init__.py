"""CloudGuard worker — the ARQ adapter over `cloudguard_core.services`.

Responsibility: execute long, retryable, scheduled work. Owns ALL egress to customer AWS.

Note the symmetry with `apps/api`: both are thin adapters over the SAME services. A scan can
be triggered by an HTTP request, a cron job, or a test, with zero duplicated logic. That is
the entire payoff of the layering rule in docs/02 — and it is why `core` may never import
`arq` or `fastapi`.

SECURITY (docs/08 § T3): the worker has NO inbound network surface. No ports are published.
It holds short-lived customer AWS credentials in memory and must not be reachable from
anywhere. Compare the API, which is public by necessity.
"""

__version__ = "0.1.0"
