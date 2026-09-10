"""Tests for `socket_lease` -- Valkey-lease-based socket ownership (claim/renew/failover).

`redis_client` is a real `fakeredis.FakeAsyncRedis` -- genuine `SET NX PX`
and Lua `EVAL` semantics (fakeredis's Lua support needs the `lupa`
extra, test-only -- real Valkey supports `EVAL` natively), not a mocked
call, matching this container's own `test_runner.py`/`test_fanout.py`
precedent. Fail-first: swapping `SocketLease.renew`'s compare-and-expire
script for an unconditional `PEXPIRE` turns `test_replica_b_cannot_renew_
replica_as_lease` green-for-the-wrong-reason into a false negative
(replica B would keep the lease alive forever) -- confirmed, reverted.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncIterator, Mapping
from typing import Any

from waddle_transports import Direction, Transport

from socket_lease import (
    PLATFORM_COMMUNITY,
    LeasedReceiver,
    SocketLease,
    lease_key,
)

PROVIDER = "discord"


async def _noop_on_item(item: Mapping[str, Any]) -> None:
    """`on_item` that does nothing.

    `LeasedReceiver.on_item` must be an async callable, not a bare sync
    `lambda`/`list.append` (`_consume` does `await self.on_item(item)`).
    """


class _FakeTransport(Transport):
    """Minimal `waddle_transports.Transport` double.

    `receive()` yields pushed items, blocking for more until closed
    (cancelled) -- mirrors a real persistent-socket transport's "connect
    once, yield forever until the connection ends" shape.
    """

    name = "fake"
    directions = frozenset({Direction.INBOUND})

    def __init__(self) -> None:
        self.receive_calls = 0
        self.closed = False
        self._queue: asyncio.Queue[Mapping[str, Any]] = asyncio.Queue()

    async def push(self, item: Mapping[str, Any]) -> None:
        await self._queue.put(item)

    async def receive(self, config: Mapping[str, Any]) -> AsyncIterator[Mapping[str, Any]]:
        self.receive_calls += 1
        try:
            while True:
                item = await self._queue.get()
                yield item
        finally:
            self.closed = True


class TestLeaseKey:
    def test_key_shape(self) -> None:
        assert lease_key("discord", "_platform") == "waddles:socket-owner:discord:_platform"


class TestClaimRenewRelease:
    async def test_claim_succeeds_when_unheld(self, redis_client: Any) -> None:
        lease = SocketLease(
            provider=PROVIDER,
            community=PLATFORM_COMMUNITY,
            owner_id="replica-a",
            redis_client=redis_client,
        )
        assert await lease.try_claim() is True

    async def test_second_replica_cannot_claim_a_held_lease(self, redis_client: Any) -> None:
        lease_a = SocketLease(
            provider=PROVIDER,
            community=PLATFORM_COMMUNITY,
            owner_id="replica-a",
            redis_client=redis_client,
        )
        lease_b = SocketLease(
            provider=PROVIDER,
            community=PLATFORM_COMMUNITY,
            owner_id="replica-b",
            redis_client=redis_client,
        )
        assert await lease_a.try_claim() is True
        assert await lease_b.try_claim() is False

    async def test_owner_can_renew_its_own_lease(self, redis_client: Any) -> None:
        lease = SocketLease(
            provider=PROVIDER,
            community=PLATFORM_COMMUNITY,
            owner_id="replica-a",
            redis_client=redis_client,
        )
        assert await lease.try_claim() is True
        assert await lease.renew() is True

    async def test_non_owner_cannot_renew_another_replicas_lease(self, redis_client: Any) -> None:
        lease_a = SocketLease(
            provider=PROVIDER,
            community=PLATFORM_COMMUNITY,
            owner_id="replica-a",
            redis_client=redis_client,
        )
        lease_b = SocketLease(
            provider=PROVIDER,
            community=PLATFORM_COMMUNITY,
            owner_id="replica-b",
            redis_client=redis_client,
        )
        assert await lease_a.try_claim() is True
        # replica-b never held the lease -- its renew must be a no-op, not
        # a forged extension of replica-a's claim.
        assert await lease_b.renew() is False

    async def test_release_frees_the_lease_for_another_claimant(self, redis_client: Any) -> None:
        lease_a = SocketLease(
            provider=PROVIDER,
            community=PLATFORM_COMMUNITY,
            owner_id="replica-a",
            redis_client=redis_client,
        )
        lease_b = SocketLease(
            provider=PROVIDER,
            community=PLATFORM_COMMUNITY,
            owner_id="replica-b",
            redis_client=redis_client,
        )
        assert await lease_a.try_claim() is True
        await lease_a.release()
        assert await lease_b.try_claim() is True

    async def test_non_owner_release_is_a_noop(self, redis_client: Any) -> None:
        """Compare-and-delete: releasing a lease you don't own must not free someone else's."""
        lease_a = SocketLease(
            provider=PROVIDER,
            community=PLATFORM_COMMUNITY,
            owner_id="replica-a",
            redis_client=redis_client,
        )
        lease_b = SocketLease(
            provider=PROVIDER,
            community=PLATFORM_COMMUNITY,
            owner_id="replica-b",
            redis_client=redis_client,
        )
        assert await lease_a.try_claim() is True
        await lease_b.release()  # replica-b never held it -- must be a no-op
        assert await lease_b.try_claim() is False  # still held by replica-a


class TestLeasedReceiver:
    async def test_run_starts_consuming_when_lease_claimed(self, redis_client: Any) -> None:
        transport = _FakeTransport()
        received: list[Mapping[str, Any]] = []

        async def _collect(item: Mapping[str, Any]) -> None:
            received.append(item)

        leased = LeasedReceiver(
            transport=transport,
            config={},
            on_item=_collect,
            redis_client=redis_client,
            provider=PROVIDER,
            community=PLATFORM_COMMUNITY,
            owner_id="replica-a",
        )
        task = asyncio.ensure_future(leased.run())
        await asyncio.sleep(0.05)
        assert transport.receive_calls == 1

        await transport.push({"content": "hi"})
        await asyncio.sleep(0.05)
        assert received == [{"content": "hi"}]

        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        assert transport.closed is True

    async def test_run_returns_immediately_when_lease_already_held(self, redis_client: Any) -> None:
        """A replica that loses the claim race never starts consuming.

        The raw `run()` coroutine just returns, letting
        `ReceiverSupervisor`'s own backoff retry later.
        """
        other = SocketLease(
            provider=PROVIDER,
            community=PLATFORM_COMMUNITY,
            owner_id="replica-a",
            redis_client=redis_client,
        )
        assert await other.try_claim() is True

        transport = _FakeTransport()
        leased = LeasedReceiver(
            transport=transport,
            config={},
            on_item=_noop_on_item,  # never called, lease unavailable
            redis_client=redis_client,
            provider=PROVIDER,
            community=PLATFORM_COMMUNITY,
            owner_id="replica-b",
        )
        await leased.run()  # returns without hanging -- lease unavailable
        assert transport.receive_calls == 0

    async def test_losing_the_lease_stops_consumption(self, redis_client: Any) -> None:
        """Fail-first proof of failover.

        Replica A's lease is stolen (simulated expiry via a direct
        compare-and-delete + replica B's claim); A's renew loop must
        notice and close the transport's `receive()` generator.
        """
        transport = _FakeTransport()
        leased_a = LeasedReceiver(
            transport=transport,
            config={},
            on_item=_noop_on_item,
            redis_client=redis_client,
            provider=PROVIDER,
            community=PLATFORM_COMMUNITY,
            owner_id="replica-a",
            renew_interval_s=0.01,
        )
        task = asyncio.ensure_future(leased_a.run())
        await asyncio.sleep(0.03)
        assert transport.receive_calls == 1

        # Simulate the lease expiring and replica-b claiming it (a real TTL
        # lapse in production; forced here via direct key deletion + a
        # fresh claim so the test doesn't wait out a real TTL).
        await redis_client.delete(lease_key(PROVIDER, PLATFORM_COMMUNITY))
        other = SocketLease(
            provider=PROVIDER,
            community=PLATFORM_COMMUNITY,
            owner_id="replica-b",
            redis_client=redis_client,
        )
        assert await other.try_claim() is True

        # replica-a's renew loop should notice on its next tick, close the
        # transport, and let run() return normally.
        await asyncio.wait_for(task, timeout=2.0)
        assert transport.closed is True

    async def test_cancellation_stops_consumption_and_releases_lease(
        self, redis_client: Any
    ) -> None:
        transport = _FakeTransport()
        leased = LeasedReceiver(
            transport=transport,
            config={},
            on_item=_noop_on_item,
            redis_client=redis_client,
            provider=PROVIDER,
            community=PLATFORM_COMMUNITY,
            owner_id="replica-a",
        )
        task = asyncio.ensure_future(leased.run())
        await asyncio.sleep(0.03)
        assert transport.receive_calls == 1

        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

        assert transport.closed is True
        # Lease released -- another replica can now claim it.
        other = SocketLease(
            provider=PROVIDER,
            community=PLATFORM_COMMUNITY,
            owner_id="replica-b",
            redis_client=redis_client,
        )
        assert await other.try_claim() is True


class _HangingRedis:
    """`LeaseRedisLike` double whose `set`/`eval` never resolve.

    Regression coverage for the silent-hang bug (2026-09-09): before
    `LeasedReceiver._guarded()` existed, a Redis call that never returns
    (a stalled/unresponsive connection -- confirmed via live trace as the
    real production symptom) blocked `run()` forever with no error, no
    log line, nothing for `ReceiverSupervisor` to restart on. Every test
    below bounds its own `asyncio.wait_for(...)` well above
    `claim_timeout_s` -- a regression back to the unguarded `await` would
    make these tests hang instead of fail, which is deliberate: a hang
    here is exactly the bug this suite exists to catch.
    """

    def __init__(self, *, hang_forever_s: float = 3600.0) -> None:
        self._hang_forever_s = hang_forever_s
        self.set_calls = 0
        self.eval_calls = 0

    async def set(  # noqa: D102 - matches LeaseRedisLike's own signature/docstring
        self, name: str, value: str, /, *, nx: bool = False, px: int | None = None
    ) -> Any:
        self.set_calls += 1
        await asyncio.sleep(self._hang_forever_s)

    async def eval(self, script: str, numkeys: int, /, *keys_and_args: str) -> Any:  # noqa: D102
        # Redis `EVAL` (server-side Lua) -- matches LeaseRedisLike.eval's
        # own signature, NOT Python's builtin eval(); no untrusted input
        # ever reaches this double, it never even inspects `script`.
        self.eval_calls += 1
        await asyncio.sleep(self._hang_forever_s)


class TestClaimTimeoutAndDegradation:
    """`claim_timeout_s`/`run_without_lease_on_unavailable` -- see `LeasedReceiver.run()`."""

    async def test_claim_timeout_degrades_and_runs_without_lease_by_default(self) -> None:
        """A backend that never answers SET NX must not block ingest on a single-replica deploy."""
        transport = _FakeTransport()
        received: list[Mapping[str, Any]] = []

        async def _collect(item: Mapping[str, Any]) -> None:
            received.append(item)

        leased = LeasedReceiver(
            transport=transport,
            config={},
            on_item=_collect,
            redis_client=_HangingRedis(),
            provider=PROVIDER,
            community=PLATFORM_COMMUNITY,
            owner_id="replica-a",
            claim_timeout_s=0.05,
            # run_without_lease_on_unavailable defaults to True.
        )
        task = asyncio.ensure_future(leased.run())
        # If claim_timeout_s regresses back to an unbounded await, this
        # wait_for is what turns a hang into a loud test failure instead
        # of a stuck test run.
        await asyncio.wait_for(asyncio.sleep(0.2), timeout=2.0)
        assert transport.receive_calls == 1  # degraded, but still consuming

        await transport.push({"content": "hi"})
        await asyncio.sleep(0.05)
        assert received == [{"content": "hi"}]

        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await asyncio.wait_for(task, timeout=2.0)
        assert transport.closed is True

    async def test_claim_timeout_does_not_run_when_degradation_disabled(self) -> None:
        """Multi-replica safety: an operator can disable the single-replica fallback."""
        transport = _FakeTransport()
        redis_double = _HangingRedis()
        leased = LeasedReceiver(
            transport=transport,
            config={},
            on_item=_noop_on_item,
            redis_client=redis_double,
            provider=PROVIDER,
            community=PLATFORM_COMMUNITY,
            owner_id="replica-a",
            claim_timeout_s=0.05,
            run_without_lease_on_unavailable=False,
        )
        await asyncio.wait_for(leased.run(), timeout=2.0)  # returns, never hangs
        assert transport.receive_calls == 0
        assert redis_double.set_calls == 1

    async def test_renew_timeout_is_treated_as_lease_lost(self, redis_client: Any) -> None:
        """A renew that never answers must be treated the same as a renew that returned False."""

        class _ClaimsThenHangsOnEval:
            """Real fakeredis SET NX (so the initial claim succeeds), hanging EVAL after."""

            def __init__(self, inner: Any) -> None:
                self._inner = inner

            async def set(
                self, name: str, value: str, /, *, nx: bool = False, px: int | None = None
            ) -> Any:
                return await self._inner.set(name, value, nx=nx, px=px)

            async def eval(self, script: str, numkeys: int, /, *keys_and_args: str) -> Any:
                # Redis `EVAL` (server-side Lua), not Python's builtin
                # eval() -- see _HangingRedis.eval's identical note above.
                await asyncio.sleep(3600.0)

        transport = _FakeTransport()
        leased = LeasedReceiver(
            transport=transport,
            config={},
            on_item=_noop_on_item,
            redis_client=_ClaimsThenHangsOnEval(redis_client),
            provider=PROVIDER,
            community=PLATFORM_COMMUNITY,
            owner_id="replica-a",
            claim_timeout_s=0.05,
            renew_interval_s=0.01,
        )
        task = asyncio.ensure_future(leased.run())
        await asyncio.sleep(0.03)
        assert transport.receive_calls == 1

        # Renew fires ~0.01s in, times out at ~0.05s -- well under the
        # generous outer bound below.
        await asyncio.wait_for(task, timeout=2.0)
        assert transport.closed is True

    async def test_happy_path_claim_is_unaffected_by_the_new_timeout_guard(
        self, redis_client: Any
    ) -> None:
        """A normal, fast fakeredis claim still succeeds -- the guard is a ceiling, not a floor."""
        transport = _FakeTransport()
        leased = LeasedReceiver(
            transport=transport,
            config={},
            on_item=_noop_on_item,
            redis_client=redis_client,
            provider=PROVIDER,
            community=PLATFORM_COMMUNITY,
            owner_id="replica-a",
            claim_timeout_s=5.0,
        )
        task = asyncio.ensure_future(leased.run())
        await asyncio.sleep(0.05)
        assert transport.receive_calls == 1

        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await asyncio.wait_for(task, timeout=2.0)
        assert transport.closed is True
