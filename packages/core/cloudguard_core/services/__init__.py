"""Services — the USE CASES. The layer that knows the product.

A service orchestrates repositories, the scanner, the domain, and integrations to accomplish
one business goal. It is the layer BOTH `apps/api` and `apps/worker` call into, which is what
lets a scan be triggered by an HTTP request, a cron job, or a test with zero duplication.

RULES
-----
1. Services raise DOMAIN errors (`cloudguard_core.errors`), never `HTTPException`. The moment
   a service raises an HTTP exception it is coupled to HTTP and the worker cannot use it.
2. Every collaborator is CONSTRUCTOR-INJECTED and typed as a `Protocol`. No module-level
   globals, no `boto3.client()` called inside a method. The dependency you didn't inject is
   the dependency you can't fake — and the one you can't fake makes your tests slow and flaky.
3. A service does not know whether it is inside a web request. It has no `Request`, no
   `Response`, no cookies.

Arriving here:
    M2  cloud_account_service.py   onboarding, AssumeRole verification
    M4  scan_service.py            the full scan pipeline
    M4  finding_service.py         list, suppress, resolve
    M6  enrichment_service.py      cached Claude context
    M7  report_service.py          weekly report → PDF → S3 → email
    M8  billing_service.py         Stripe, plans, entitlements
"""
