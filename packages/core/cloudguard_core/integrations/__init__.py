"""Integrations — thin wrappers over the outside world.

EVERY integration is defined as a `Protocol` first, with at least two implementations:
the real one, and a fake for tests.

    class EmailClient(Protocol):
        async def send(self, to: str, subject: str, html: str) -> None: ...

    class ResendClient:   ...  # production
    class FakeEmailClient: ... # tests: records calls in a list, asserts on them

WHY THE PROTOCOL COMES FIRST
----------------------------
Not ceremony. Three concrete payoffs:

1. TESTS DON'T MONKEYPATCH. `monkeypatch.setattr("stripe.Customer.create", ...)` couples your
   test to a third-party library's internal structure. It breaks when they refactor, and the
   error message tells you nothing. Injecting a fake couples the test to OUR interface, which
   we control.

2. TESTS DON'T HIT THE NETWORK. A test suite that calls Anthropic is slow, flaky, costs money,
   and fails on a plane. Our unit suite must run in under 5 seconds (docs/10) — that budget is
   only achievable if nothing in it opens a socket.

3. SWAPPING A VENDOR IS A ONE-FILE CHANGE. Resend → SES is a new class, not a grep.

Also: the choice of implementation is made ONCE, at the composition root — never via
`if settings.environment == "test"` scattered through the code (docs/11 § Configuration).

Arriving here:
    M2  aws/       STS AssumeRole, boto3 session broker
    M6  llm/       LLMClient protocol, AnthropicClient, FakeLLMClient
    M7  email/     EmailClient protocol, ResendClient, FakeEmailClient
    M7  storage/   ObjectStore protocol, S3Store, InMemoryStore
    M8  billing/   Stripe
    M9  github/    GitHub App, PR creation
"""
