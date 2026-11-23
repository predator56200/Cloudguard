"""CloudGuard API — the HTTP adapter over `cloudguard_core.services`.

Responsibility (docs/02): authenticate, authorise, validate, delegate, serialise. Nothing else.

HARD RULE: an API request NEVER does slow work.
Anything touching customer AWS, the LLM, S3, or email is enqueued on ARQ and returns
`202 Accepted`. A scan takes 30–180 seconds; running it inline would block a web worker, hit
gateway timeouts, and let one customer's slow AWS account degrade every other customer's
dashboard.
"""

__version__ = "0.1.0"
