"""Health endpoint tests.

The single most important assertion in this file is
`test_healthz_does_not_check_dependencies`.

It encodes the liveness-vs-readiness distinction (see routers/health.py) as an EXECUTABLE
RULE. Someone, in eighteen months, under deadline pressure, will "improve" /healthz by adding
a database check — it feels obviously correct. That change reintroduces the crash-loop outage
where a 30-second database blip becomes a 20-minute self-inflicted total outage.

That test is how the architecture defends itself once we have all forgotten why.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from cloudguard_core.constants import REQUEST_ID_HEADER


class TestLiveness:
    def test_healthz_returns_ok(self, client: TestClient) -> None:
        response = client.get("/healthz")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"

    def test_healthz_does_not_check_dependencies(self, unhealthy_client: TestClient) -> None:
        """⚠️ THE LOAD-BEARING TEST. Read routers/health.py before changing it.

        With BOTH Postgres and Redis down, liveness must STILL return 200. Liveness answers
        "is this process alive?" — and it is. If this ever returns 503, the orchestrator will
        kill a perfectly healthy container during a transient DB blip, the replacement will
        also fail to reach the DB, and a 30-second database hiccup becomes a self-inflicted
        outage that outlives its cause.
        """
        response = unhealthy_client.get("/healthz")
        assert response.status_code == 200


class TestReadiness:
    def test_readyz_ok_when_dependencies_are_up(self, client: TestClient) -> None:
        response = client.get("/readyz")
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "ready"
        assert body["checks"] == {"database": "ok", "redis": "ok"}

    def test_readyz_503_when_dependencies_are_down(self, unhealthy_client: TestClient) -> None:
        """503 removes this container from the load balancer WITHOUT restarting it — it will
        recover on its own the moment the database comes back."""
        response = unhealthy_client.get("/readyz")
        assert response.status_code == 503
        assert response.json()["status"] == "not_ready"

    def test_readyz_reports_which_dependency_failed(
        self, unhealthy_client: TestClient
    ) -> None:
        """Skips the first ten minutes of an incident: not 'something is broken' but 'Redis
        is broken'."""
        body = unhealthy_client.get("/readyz").json()
        assert body["checks"]["database"] == "unavailable"
        assert body["checks"]["redis"] == "unavailable"

    def test_readyz_sets_retry_after(self, unhealthy_client: TestClient) -> None:
        assert unhealthy_client.get("/readyz").headers["Retry-After"] == "5"


class TestRequestId:
    def test_request_id_is_echoed(self, client: TestClient) -> None:
        """A caller can correlate their request with our logs. This is what a customer quotes
        in a support ticket."""
        assert REQUEST_ID_HEADER in client.get("/healthz").headers

    def test_inbound_request_id_is_preserved(self, client: TestClient) -> None:
        """Never break someone else's trace. If a CDN or the browser already started one,
        we join it rather than starting a competing one."""
        response = client.get("/healthz", headers={REQUEST_ID_HEADER: "trace-from-caller"})
        assert response.headers[REQUEST_ID_HEADER] == "trace-from-caller"

    def test_request_id_is_generated_when_absent(self, client: TestClient) -> None:
        first = client.get("/healthz").headers[REQUEST_ID_HEADER]
        second = client.get("/healthz").headers[REQUEST_ID_HEADER]
        assert first != second  # every request gets its own


class TestErrorContract:
    def test_404_is_rfc7807_problem_json(self, client: TestClient) -> None:
        """Every error in the system — including framework 404s — must speak one dialect, so
        the frontend has exactly one error path (docs/05)."""
        response = client.get("/this-route-does-not-exist")
        assert response.status_code == 404

    def test_500_never_leaks_internals(self, app: FastAPI) -> None:
        """⚠️ SECURITY. A stack trace in an HTTP response is a free architecture diagram for
        an attacker: framework versions, file paths, ORM internals, table names. We are a
        SECURITY company. The client gets a generic message and a request_id; the traceback
        goes to our logs (docs/05 § Error handling).
        """

        @app.get("/_boom")
        async def boom() -> None:
            raise RuntimeError("SECRET_INTERNAL_DETAIL: db password is hunter2")

        with TestClient(app, raise_server_exceptions=False) as c:
            response = c.get("/_boom")

        assert response.status_code == 500
        body = response.text
        assert "SECRET_INTERNAL_DETAIL" not in body
        assert "hunter2" not in body
        assert "Traceback" not in body
        assert response.json()["detail"] == "An unexpected error occurred."
        assert response.json()["request_id"] is not None  # ...but we CAN still debug it
