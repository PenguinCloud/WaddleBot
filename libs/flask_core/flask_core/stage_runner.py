"""Stage-runner engine shared by `core/svc_ingest`/`core/svc_process`.

Two pieces every pipeline-stage container needs, factored out here rather
than duplicated per-service (backend.md Shared Libraries): (1)
:class:`BundlePoller`, which polls hub-api's `GET /api/v1/distribution/
bundles?stage=...` endpoint on an interval, with exponential backoff and
graceful degrade to the last-known-good bundle set on failure -- never
raises out of a poll cycle, never crashes the runner because hub-api is
briefly unreachable; and (2) :func:`load_entrypoint`, which resolves a
bundle's `module:function` dotted-path entrypoint (`app_catalog.stages[
stage].entrypoint`, migration 071) via `importlib` -- never `exec()` of
DB-stored text, so there is no code-injection surface: the module must
already be an installed, vetted package inside the stage-runner's own
container image (see migration 071's own docstring).
"""

from __future__ import annotations

import importlib
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, cast

import httpx

logger = logging.getLogger(__name__)

#: Default poll cadence and backoff bounds -- overridable per `BundlePoller`
#: instance, these are just sane defaults for a control-plane poll loop
#: (frequent enough to pick up a new activation quickly, bounded so a
#: prolonged hub-api outage doesn't hammer it with retries).
DEFAULT_POLL_INTERVAL_S = 5.0
DEFAULT_BASE_BACKOFF_S = 1.0
DEFAULT_MAX_BACKOFF_S = 60.0


class EntrypointLoadError(Exception):
    """Raised by :func:`load_entrypoint` for a malformed or unresolvable entrypoint string."""


@dataclass(slots=True, frozen=True)
class BundleDistribution:
    """One bundle's `{entrypoint, config, spec}` for a stage, as served by the distribution API.

    Field names mirror `hub_api/blueprints/v1/distribution.py`'s
    `DistributionBundleDTO` wire shape (camelCase on the wire, snake_case
    here) -- `app_id`/`community_id` are used to build the bundle's Valkey
    isolation key (`bundle_stream_key`, `stream_pipeline.py`).
    """

    app_id: str
    community_id: int | None
    entrypoint: str | None
    spec: dict[str, Any] = field(default_factory=dict)
    config: dict[str, Any] = field(default_factory=dict)


def _parse_bundle(raw: dict[str, Any]) -> BundleDistribution:
    """Parse one item of the distribution response's `data.bundles` list."""
    return BundleDistribution(
        app_id=raw["appId"],
        community_id=raw.get("communityId"),
        entrypoint=raw.get("entrypoint"),
        spec=dict(raw.get("spec") or {}),
        config=dict(raw.get("config") or {}),
    )


async def fetch_active_bundles(
    client: httpx.AsyncClient,
    distribution_url: str,
    *,
    stage: str,
    jwt: str,
    community_id: int | None = None,
    timeout_s: float = 10.0,
) -> tuple[BundleDistribution, ...]:
    """Call hub-api's distribution endpoint once; raises on any non-2xx or network failure.

    Raising (rather than swallowing) is deliberate -- :class:`BundlePoller`
    is the layer that decides what "failed" means for the poll loop
    (backoff + keep the last-known set); this function is a thin, honest
    HTTP call so it stays independently testable and reusable outside a
    poller (e.g. a one-shot CLI/debug script).
    """
    params: dict[str, str] = {"stage": stage}
    if community_id is not None:
        params["community_id"] = str(community_id)

    response = await client.get(
        distribution_url,
        params=params,
        headers={"Authorization": f"Bearer {jwt}"},
        timeout=timeout_s,
    )
    response.raise_for_status()
    body = response.json()
    # Matches `hub_api/blueprints/v1/distribution.py`'s `DistributionBundlesResponse`
    # wire shape exactly: {"success", "stage", "bundles", "meta"} -- flat, no
    # "data" envelope wrapper (this repo's established DTO convention, see
    # flask_core.api_utils.success_response -- not backend.md's generic
    # {"status", "data", "meta"} shape, a deliberate repo-level divergence).
    raw_bundles = body["bundles"]
    return tuple(_parse_bundle(raw) for raw in raw_bundles)


def load_entrypoint(entrypoint: str) -> Callable[..., Awaitable[Any]]:
    """Resolve a `module.submodule:function` dotted-path entrypoint via `importlib`.

    Raises :class:`EntrypointLoadError` for a malformed path (no `:`), an
    unimportable module, or a missing/non-callable attribute -- every
    failure mode is a typed, catchable error, never a bare `ImportError`/
    `AttributeError` leaking into the runner's poll loop uncaught.
    """
    if ":" not in entrypoint:
        raise EntrypointLoadError(
            f"entrypoint {entrypoint!r} must be 'module.submodule:function'"
        )
    module_path, _, func_name = entrypoint.rpartition(":")
    try:
        module = importlib.import_module(module_path)
    except ImportError as exc:
        raise EntrypointLoadError(
            f"cannot import module {module_path!r}: {exc}"
        ) from exc

    func = getattr(module, func_name, None)
    if func is None or not callable(func):
        raise EntrypointLoadError(
            f"module {module_path!r} has no callable attribute {func_name!r}"
        )
    return cast(Callable[..., Awaitable[Any]], func)


class BundlePoller:
    """Polls the distribution endpoint for one stage; exponential backoff, graceful degrade.

    `poll_once()` is the unit-testable core (mockable `client`); the
    production loop (`core/svc_ingest`/`core/svc_process`'s own
    `run_forever()`) calls it in a loop with `asyncio.sleep(poller.
    next_delay_s)` between iterations. On failure, the previous successful
    result (`last_known`) is returned unchanged and the next delay doubles
    (capped at `max_backoff_s`) -- the runner keeps executing whatever
    bundle set it already knew about rather than going idle the moment
    hub-api is briefly unreachable. On success, the delay resets to
    `poll_interval_s`.
    """

    def __init__(
        self,
        client: httpx.AsyncClient,
        distribution_url: str,
        *,
        stage: str,
        jwt_provider: Callable[[], str],
        community_id: int | None = None,
        poll_interval_s: float = DEFAULT_POLL_INTERVAL_S,
        base_backoff_s: float = DEFAULT_BASE_BACKOFF_S,
        max_backoff_s: float = DEFAULT_MAX_BACKOFF_S,
    ) -> None:
        self._client = client
        self._distribution_url = distribution_url
        self._stage = stage
        self._jwt_provider = jwt_provider
        self._community_id = community_id
        self._poll_interval_s = poll_interval_s
        self._base_backoff_s = base_backoff_s
        self._max_backoff_s = max_backoff_s

        self._last_known: tuple[BundleDistribution, ...] = ()
        self._current_backoff_s = base_backoff_s
        self._next_delay_s = poll_interval_s

    @property
    def last_known(self) -> tuple[BundleDistribution, ...]:
        """The most recently successfully-fetched bundle set (possibly stale)."""
        return self._last_known

    @property
    def next_delay_s(self) -> float:
        """How long the runner should sleep before the next `poll_once()` call."""
        return self._next_delay_s

    async def poll_once(self) -> tuple[BundleDistribution, ...]:
        """Fetch the active bundle set once; never raises -- degrades to `last_known` on failure."""
        try:
            bundles = await fetch_active_bundles(
                self._client,
                self._distribution_url,
                stage=self._stage,
                jwt=self._jwt_provider(),
                community_id=self._community_id,
            )
        except Exception as exc:  # noqa: BLE001 - poll loop must never crash the runner
            error_str = str(exc) if str(exc) else repr(exc)
            logger.warning(
                "stage_runner.poll_failed stage=%s error_type=%s error=%s backoff_s=%s",
                self._stage,
                type(exc).__name__,
                error_str,
                self._current_backoff_s,
            )
            self._next_delay_s = self._current_backoff_s
            self._current_backoff_s = min(
                self._current_backoff_s * 2, self._max_backoff_s
            )
            return self._last_known

        self._current_backoff_s = self._base_backoff_s
        self._next_delay_s = self._poll_interval_s
        self._last_known = bundles
        return bundles
