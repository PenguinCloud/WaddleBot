"""Smoke tests for svc-ingest's Quart app -- health endpoints + real startup/shutdown lifecycle.

`app.test_client()`'s own `async with` does NOT run the ASGI lifespan
(confirmed via `QuartClient.__aenter__` source -- it only sets
`preserve_context`); `app.test_app()` is Quart's actual lifespan-triggering
context manager (`before_serving`/`after_serving` run on enter/exit) and is
what `TestLifespan` below uses. `VALKEY_URL` defaults to
`redis://localhost:6379/0` (config.py) -- `redis.from_url()` itself never
opens a socket until the first command, so startup succeeds without a live
Valkey; the background `run_forever()` task's first `poll_once()` fails
closed (httpx connection refused to the default `hub-api:8204`) and
degrades to an empty bundle set, exactly the graceful-degrade contract
`BundlePoller` guarantees -- proven separately, with a real fakeredis round
trip, by `test_runner.py`.
"""

from __future__ import annotations

import logging
import sys
from typing import Any

import pytest
from quart.testing.app import LifespanError

import app as app_module
from app import app as quart_app
from config import Config


@pytest.fixture
def client() -> Any:
    return quart_app.test_client()


class TestHealthEndpoints:
    async def test_health(self, client: Any) -> None:
        async with client as c:
            response = await c.get("/health")
            assert response.status_code == 200
            body = await response.get_json()
            assert body["module"] == "svc-ingest"

    async def test_healthz(self, client: Any) -> None:
        async with client as c:
            response = await c.get("/healthz")
            assert response.status_code == 200

    async def test_metrics(self, client: Any) -> None:
        async with client as c:
            response = await c.get("/metrics")
            assert response.status_code == 200


class TestLifespan:
    async def test_startup_wires_runner_and_shutdown_stops_it_cleanly(self) -> None:
        """The real `@app.before_serving`/`@app.after_serving` hooks run without raising.

        Proves the background task actually starts (config populated,
        `runner_task` present) and that `stop()` + task cancellation on
        shutdown terminates cleanly -- no hang, no unhandled exception.
        """
        async with quart_app.test_app() as test_app:
            client = test_app.test_client()
            response = await client.get("/health")
            assert response.status_code == 200
            assert quart_app.config["runner"] is not None
            assert not quart_app.config["runner_task"].done()
        # test_app's __aexit__ runs the ASGI lifespan shutdown, which calls
        # our after_serving hook -- by the time this block exits, the
        # runner task must be finished (stopped, not hung).
        assert quart_app.config["runner_task"].done()

    async def test_startup_wires_supervisor_with_no_receivers_when_no_token(self) -> None:
        """No `DISCORD_BOT_TOKEN` -- the supervisor still starts, with zero receivers.

        `discord_leased_receiver` is never populated (graceful skip,
        matching `trigger/receiver/discord_module/app.py`'s own
        precedent) -- test env has no token set by default.
        """
        async with quart_app.test_app():
            assert quart_app.config["supervisor"] is not None
            assert quart_app.config["registry"] is not None
            assert "discord_leased_receiver" not in quart_app.config

    async def test_startup_registers_both_discord_and_twitch_under_the_one_supervisor(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Both connectors' receivers register under the SAME `ReceiverSupervisor` instance.

        `Config` attributes are read fresh at `startup()` time (not
        cached at import), so monkeypatching the class directly (not env
        vars, which `Config` only reads once at import) takes effect for
        this one lifespan. `SocketLease.try_claim()`'s own real Valkey
        call is never reached by this assertion -- `supervisor.register()`
        happens before `supervisor.start()`, so a missing local Valkey
        (this test env has none) never prevents the registration itself
        from being observed.
        """
        monkeypatch.setattr(Config, "DISCORD_BOT_TOKEN", "fake-discord-token")  # noqa: S105
        monkeypatch.setattr(Config, "TWITCH_BOT_TOKEN_REF", "FAKE_TWITCH_TOKEN_REF")
        monkeypatch.setattr(Config, "TWITCH_CHANNELS", ["somechannel"])

        async with quart_app.test_app():
            supervisor = quart_app.config["supervisor"]
            registered = set(supervisor._receivers)  # noqa: SLF001 - test-only introspection

            assert "discord_gateway" in registered
            assert "twitch_irc:somechannel" in registered
            assert "twitch_outbound_drain" in registered
            assert quart_app.config["discord_leased_receiver"] is not None
            assert len(quart_app.config["twitch_leased_receivers"]) == 1


class TestLeaseClientSharesAuthenticatedRedisClient:
    """Regression: every socket-lease Redis client must be THE SAME object as the shared client.

    Must be `Config.VALKEY_URL`-authenticated -- never a separately constructed, unauthenticated
    one.

    2026-09-10 fix (paired with `test_config.py`'s `TestValkeyUrlAuthFallback`): an earlier
    debugging pass observed `AuthenticationError: HELLO must be called with the client already
    authenticated` on the Discord receiver's lease claim while the ordinary ingest->process
    fan-out (same process) kept working -- the apparent divergence was traced to
    `Config.VALKEY_URL` itself silently falling back to a bare, credential-free dev default in a
    real cluster (`test_config.py`), not to `socket_lease.py`/`outbound_drain.py` building a
    second, differently-authenticated client. `socket_lease.SocketLease` never constructs its own
    client -- it only ever receives one from a caller (`LeaseRedisLike`/`socket_lease.py`'s own
    docstring) -- so asserting object identity here is the strongest guarantee against that
    divergence ever silently reappearing: a future edit that builds ANY new `redis.from_url(...)`
    call for a lease client, instead of reusing `app.py`'s one shared `redis_client`, fails this
    test immediately.
    """

    async def test_discord_and_twitch_leases_reuse_the_one_shared_redis_client(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(Config, "DISCORD_BOT_TOKEN", "fake-discord-token")  # noqa: S105
        monkeypatch.setattr(Config, "TWITCH_BOT_TOKEN_REF", "FAKE_TWITCH_TOKEN_REF")
        monkeypatch.setattr(Config, "TWITCH_CHANNELS", ["somechannel"])

        async with quart_app.test_app():
            shared_redis_client = quart_app.config["redis_client"]

            discord_leased = quart_app.config["discord_leased_receiver"]
            assert discord_leased.redis_client is shared_redis_client

            twitch_leased = quart_app.config["twitch_leased_receivers"][0]
            assert twitch_leased.redis_client is shared_redis_client

            outbound_drain = quart_app.config["twitch_outbound_drain"]
            assert outbound_drain.lease_redis_client is shared_redis_client
            # The drain's BLOCKING-BRPOP connection is deliberately a
            # SEPARATE, dedicated client (outbound_drain.py's own "Two
            # separate Valkey clients" docstring) -- but still built from
            # the same authenticated `Config.VALKEY_URL`, never a bare one.
            assert outbound_drain.redis_client is not shared_redis_client


class TestConfigureRootLogging:
    """Regression for the 2026-09-10 diagnosis (`app._configure_root_logging`'s own docstring).

    A Discord receiver appeared to exit silently on startup; the real
    cause was that `socket_lease.py`/`supervisor.py`/`receivers/
    discord_gateway.py` (and siblings) log via a plain
    `logging.getLogger(__name__)` that was never attached to any handler
    -- reproduced directly: the untouched Python root logger defaults
    (level=WARNING, zero handlers) silently dropped every `.info()` call
    and routed every `.warning()`/`.error()` call to an unstructured
    STDERR fallback, a different stream/format than every other log line
    this service emits. `_configure_root_logging()` runs at `app.py`
    import time (module-level call), so this test observes its
    already-applied, process-wide effect.
    """

    def test_root_logger_has_a_stdout_handler_at_config_level(self) -> None:
        root_logger = logging.getLogger()
        assert any(
            isinstance(h, logging.StreamHandler) and h.stream is sys.stdout
            for h in root_logger.handlers
        )
        assert root_logger.getEffectiveLevel() <= logging.INFO

    def test_plain_child_logger_would_have_been_dropped_before_the_fix(self) -> None:
        """The exact shape `socket_lease.py`'s `logging.getLogger(__name__)` uses.

        Asserts at the logging-API level (not `capsys`, which can't see
        writes through a handler that captured `sys.stdout` at import
        time, before pytest's own capture substitution) -- before this
        fix, `isEnabledFor(INFO)` was False (root defaulted to WARNING),
        which is the exact condition that silently dropped
        `socket_lease.claimed`/`gateway.discord_ready` at the source,
        before any handler was even consulted.
        """
        child_logger = logging.getLogger("socket_lease")
        assert child_logger.isEnabledFor(logging.INFO)
        assert child_logger.handlers == []  # relies entirely on the root's handler
        assert len(logging.getLogger().handlers) >= 1


class TestStartupFailureLogging:
    """`startup()`'s receiver-registration guard -- see `app.py`'s own inline comment."""

    async def test_registration_failure_is_logged_with_exception_info_and_reraised(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A raised exception during receiver setup is never silent: logged, then re-raised.

        Proves `startup()` fails loud and fails closed rather than ever
        continuing to serve with a receiver that never actually
        registered.
        """
        logged: list[tuple[str, dict[str, Any]]] = []

        def _boom(*_args: Any, **_kwargs: Any) -> None:
            raise RuntimeError("boom")

        monkeypatch.setattr(app_module, "_register_discord_receiver", _boom)
        monkeypatch.setattr(
            app_module.logger,
            "error",
            lambda message, **kwargs: logged.append((message, kwargs)),
        )

        # Quart's own lifespan protocol converts a `before_serving` hook's
        # raised exception into a `lifespan.startup.failed` ASGI message
        # before it ever reaches test/production code -- `test_app()`'s
        # harness re-raises that as `LifespanError`, not the original
        # `RuntimeError` directly. What this test actually proves is that
        # `startup()` still fails (never silently continues) AND that our
        # own `logger.error()` ran with the exception's type + message
        # before Quart's own re-raise -- both asserted below.
        with pytest.raises(LifespanError, match="boom"):
            async with quart_app.test_app():
                pass

        assert len(logged) == 1
        message, kwargs = logged[0]
        assert "RuntimeError" in message
        assert "boom" in message
        assert kwargs["result"] == "FAILED"
