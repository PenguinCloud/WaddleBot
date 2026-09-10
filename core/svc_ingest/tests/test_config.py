"""Regression: `Config.VALKEY_URL` must resolve to the AUTHENTICATED in-cluster URL.

2026-09-10 fix (paired with `socket_lease`'s shared-client wiring in
`app.py` -- see `TestLeaseClientSharesAuthenticatedRedisClient` in
`test_app.py`): Helm's `-secrets` Secret only ever defines `REDIS_URL`
(host + AUTH password, `k8s/helm/waddlebot/templates/secrets.yaml`).
Before this fix, `Config.VALKEY_URL = os.getenv("VALKEY_URL",
"redis://localhost:6379/0")` checked ONLY `VALKEY_URL` -- an env var name
the chart never actually injects -- so in a real cluster it silently fell
through to the bare, unauthenticated, wrong-host dev default. That one bad
default was the root cause of BOTH symptoms an earlier debugging pass
treated as separate ("wrong host" and "AuthenticationError: HELLO must be
called with the client already authenticated"): every Redis/Valkey client
in this service (`app.py`'s shared `redis_client`, `outbound_drain.py`'s
dedicated BRPOP connection, and -- transitively, since `socket_lease.
SocketLease` never constructs its own client, only ever receiving one
already built by a caller -- every `SocketLease`/`LeasedReceiver` lease
call) is built from this one `Config.VALKEY_URL` value via `redis.
from_url()`. Fixing the fallback chain here fixes every one of those
call sites at once; there is no separate per-client auth gap to patch.
"""

from __future__ import annotations

import importlib
from typing import Any

import pytest


@pytest.fixture
def reloaded_config(monkeypatch: pytest.MonkeyPatch) -> Any:
    """Reload `config` after mutating env vars, restoring the original module state after."""
    import config as config_module

    yield config_module

    # Restore the real env-derived state for every subsequent test/module
    # that does `from config import Config` -- monkeypatch itself only
    # restores env VARS on teardown, not this already-reloaded module
    # object other imports may still be holding a reference to.
    importlib.reload(config_module)


class TestValkeyUrlAuthFallback:
    """`VALKEY_URL` falls back to the AUTHENTICATED `REDIS_URL`, never a bare dev default."""

    def test_prefers_explicit_valkey_url_when_set(
        self, monkeypatch: pytest.MonkeyPatch, reloaded_config: Any
    ) -> None:
        monkeypatch.setenv("VALKEY_URL", "redis://:explicit-pw@valkey-override:6379/0")
        monkeypatch.setenv("REDIS_URL", "redis://:secret-pw@infra-redis:6379/0")
        importlib.reload(reloaded_config)

        assert reloaded_config.Config.VALKEY_URL == "redis://:explicit-pw@valkey-override:6379/0"

    def test_falls_back_to_authenticated_redis_url_when_valkey_url_unset(
        self, monkeypatch: pytest.MonkeyPatch, reloaded_config: Any
    ) -> None:
        """The real Helm shape: only `REDIS_URL` (with embedded AUTH creds) is ever injected."""
        monkeypatch.delenv("VALKEY_URL", raising=False)
        monkeypatch.setenv("REDIS_URL", "redis://:secret-pw@infra-redis:6379/0")
        importlib.reload(reloaded_config)

        resolved = reloaded_config.Config.VALKEY_URL
        assert resolved == "redis://:secret-pw@infra-redis:6379/0"
        # The regression this guards: falling through to the bare,
        # credential-free dev default despite a real, authenticated
        # REDIS_URL being available.
        assert "@" in resolved
        assert resolved != "redis://localhost:6379/0"

    def test_bare_dev_default_only_when_neither_is_set(
        self, monkeypatch: pytest.MonkeyPatch, reloaded_config: Any
    ) -> None:
        monkeypatch.delenv("VALKEY_URL", raising=False)
        monkeypatch.delenv("REDIS_URL", raising=False)
        importlib.reload(reloaded_config)

        assert reloaded_config.Config.VALKEY_URL == "redis://localhost:6379/0"
