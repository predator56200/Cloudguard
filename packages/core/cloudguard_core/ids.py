"""Identifier generation — UUIDv7.

WHY NOT `bigserial` (auto-increment integers)
---------------------------------------------
1. It LEAKS BUSINESS DATA. If a customer signs up and gets `org_id=847`, then signs up again
   a month later and gets `org_id=901`, they now know we acquired 54 organisations that
   month. Competitors do this. It is called the German-tank problem and it is not theoretical.
2. It is GUESSABLE. `/v1/findings/1234` invites an attacker to try `1235`. Our defence
   against that is RLS + 404-not-403 (docs/08), but defence in depth means not handing them
   the enumeration on a plate in the first place.

WHY NOT UUIDv4 (fully random)
-----------------------------
Random keys destroy B-tree insert locality. Every INSERT lands at a random point in the
index, splitting pages all over the tree and thrashing the buffer cache. On a
write-heavy table — and `findings`/`resources` are written by every single scan — this is a
measurable, compounding slowdown that shows up right when you start to succeed.

WHY UUIDv7
----------
    ┌─────────────────────────────┬──────────────────────┐
    │ 48-bit Unix ms timestamp    │  74 bits randomness  │
    └─────────────────────────────┴──────────────────────┘

- TIME-SORTABLE: new rows append to the RIGHT of the B-tree, like a sequence. Insert locality
  is restored. We get bigserial's performance...
- ...with UUID's UNGUESSABILITY (74 bits of entropy) and no cross-shard coordination.
- Free bonus: `ORDER BY id` is chronological, so cursor pagination (docs/05) can use the PK
  as a stable tiebreaker without an extra column or an extra index.

Python 3.12's `uuid` module has no `uuid7()` yet, so we implement RFC 9562 directly. It is
~20 lines and avoids a dependency — and a dependency in a security product is an audit
liability, so we don't take them lightly.

Roadmap: M0 task 0.6.
"""

from __future__ import annotations

import os
import threading
import time
from uuid import UUID

# --- Monotonicity state (see the `uuid7` docstring) --------------------------
# A lock, not a lock-free trick: generating an ID is nanoseconds, so contention is nil, and a
# subtly-wrong lock-free counter would produce DUPLICATE PRIMARY KEYS under concurrency. That
# is not a trade worth making to save a mutex.
_lock = threading.Lock()
_last_ms: int = 0
_counter: int = 0

_COUNTER_BITS = 12  # rand_a
_COUNTER_MAX = (1 << _COUNTER_BITS) - 1  # 4095


def uuid7() -> UUID:
    """Generate a UUIDv7: time-ordered, unguessable, RFC 9562 compliant.

    Layout (128 bits):
        bits   0-47   unix_ts_ms   millisecond timestamp
        bits  48-51   version      = 7
        bits  52-63   rand_a       ← MONOTONIC COUNTER (see below), not pure randomness
        bits  64-65   variant      = 0b10 (RFC 4122)
        bits  66-127  rand_b       62 random bits

    WHY rand_a IS A COUNTER AND NOT RANDOM (RFC 9562 §6.2, "Method 2")
    ------------------------------------------------------------------
    The timestamp only has MILLISECOND resolution. A tight loop — a scan reconciling 500
    findings, say — generates hundreds of IDs inside the SAME millisecond. If rand_a were
    random, those IDs would sort in a random order relative to each other, and the ONE
    PROPERTY WE CHOSE v7 FOR would silently fail exactly when it matters most: under load.

    Two things depend on strict monotonicity:
      - B-tree insert locality (the whole reason we rejected UUIDv4);
      - cursor pagination using the PK as a stable tiebreaker (docs/05). A non-monotonic
        tiebreaker means a paginating client can SKIP rows — and on a security dashboard, a
        silently skipped row is a customer missing a critical finding.

    So within a millisecond we INCREMENT. The counter is seeded randomly (11 bits) at each new
    millisecond rather than starting at zero, which preserves unguessability while leaving
    2048 increments of headroom. On the (astronomically unlikely) overflow, we borrow a
    millisecond from the future rather than emit a non-monotonic ID — correctness over
    precision.
    """
    global _last_ms, _counter

    now_ms = int(time.time() * 1000) & 0xFFFFFFFFFFFF  # 48 bits

    with _lock:
        if now_ms > _last_ms:
            _last_ms = now_ms
            # Seed randomly in the LOW half of the counter space: unguessable, with room to
            # increment. `os.urandom`, never `random` — the `random` module is a Mersenne
            # Twister and is fully predictable from ~624 observed outputs. That is a real
            # attack on a real system, and we are a security company.
            _counter = int.from_bytes(os.urandom(2), "big") & 0x7FF  # 11 bits: 0..2047
        else:
            # Same millisecond (or the clock went backwards — NTP does this). Increment.
            _counter += 1
            if _counter > _COUNTER_MAX:
                # Overflow: borrow a millisecond from the future. Never emit an out-of-order
                # ID; a slightly-fast timestamp is harmless, a broken sort order is not.
                _last_ms += 1
                _counter = 0
            now_ms = _last_ms

        ts, counter = _last_ms, _counter

    # 62 bits of randomness. This is what makes the ID unguessable and collision-proof — the
    # counter provides ordering, this provides entropy.
    rand_b = int.from_bytes(os.urandom(8), "big") & 0x3FFFFFFFFFFFFFFF

    value = (
        (ts << 80)
        | (0x7 << 76)  # version 7
        | (counter << 64)  # rand_a := monotonic counter
        | (0b10 << 62)  # RFC 4122 variant
        | rand_b
    )
    return UUID(int=value)


def timestamp_ms_from_uuid7(value: UUID) -> int:
    """Extract the embedded millisecond timestamp.

    Useful for debugging ("when was this finding row actually created?") without a JOIN, and
    a small demonstration of why v7 beats v4: the ID itself carries information.
    """
    return value.int >> 80
