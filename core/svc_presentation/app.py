"""svc-presentation -- Quart application factory + hypercorn entry point.

The 8th container / 4th stage-runner (`docs/plans/2026-08-31-music-station-
design.md` §8): serves per-community OBS browser-source overlay surfaces
(`full_screen`/`media`/`crawler`), the Music Station player, and the
push+SSE live-update channel every surface shares. Follows the same
create_app()/blueprint-auto-discovery shape `hub_api/app.py` established
for this monorepo's Quart services.

Real Quart serving, real live push (SSE + Valkey pub/sub relay,
`services/presentation_hub.py`), real HTML/JS that renders -- what remains
genuinely open (not stubbed, explicitly documented): hub-api poll+reconcile
for activated bundles' own `presentation` components, per-community
overlay-key auth on the render routes, and read-replica routing for the
`overlay_surfaces`/`presentation_config` reads (this service's own primary
DB connection is used for both -- see `config.py`; it is the sole writer of
these two tables today, so a replica split has no correctness benefit yet).
"""

from __future__ import annotations

import asyncio

from flask_core import (
    create_health_blueprint,
    init_database,
    install_rate_limiting,
    install_security_headers,
    setup_aaa_logging,
)
from flask_core.security_headers import OVERLAY_CSP
from quart import Quart

from blueprints import register_blueprints
from config import Config
from services.presentation_hub import PresentationHub
from services.queue_reader import MusicQueueReader
from services.schema import bind_presentation_tables


def create_app(config: Config | None = None) -> Quart:
    """Build the svc-presentation Quart application."""
    cfg = config or Config.from_env()
    app = Quart(__name__)
    app.config["APP_CONFIG"] = cfg

    logger = setup_aaa_logging(cfg.module_name, cfg.module_version, log_level=cfg.log_level)
    app.config["logger"] = logger

    # security.md A05 hardening -- this service's whole purpose is serving
    # OBS browser-source overlay HTML (`services/render.py`: inline
    # <script>/<style>, YouTube iframe API, Spotify track embeds), so it
    # gets the relaxed OVERLAY_CSP rather than the JSON-only DEFAULT_CSP.
    install_security_headers(app, csp=OVERLAY_CSP)

    app.register_blueprint(create_health_blueprint(cfg.module_name, cfg.module_version))
    register_blueprints(app)

    # SECURITY (A04): every overlay/music-station/SSE route had zero rate
    # limiting -- shared global before_request hook, see
    # flask_core.http_rate_limit module docstring.
    install_rate_limiting(app, namespace=cfg.module_name, redis_url=cfg.valkey_url)

    @app.before_serving
    async def startup() -> None:
        """Initialize the DAL, bind this service's own tables, connect Valkey."""
        logger.system(
            "Starting svc-presentation", action="startup", extra={"port": cfg.module_port}
        )

        async_dal = init_database(
            cfg.database_url,
            pool_size=cfg.db_pool_size,
            read_replica_uri=cfg.database_read_replica_url,
        )
        dal = async_dal.dal
        bind_presentation_tables(dal, migrate=cfg.db_migrate)
        # `lazy_tables=True` (AsyncDAL's own default) defers each table's
        # actual `CREATE TABLE` until first ORM access -- left lazy, the
        # first access could happen on an `async_dal.*_async()` worker
        # thread mid-request, racing its own `CREATE TABLE` against this
        # thread's still-open sqlite file handle ("database is locked" --
        # the exact gotcha `hub_api/tests/conftest.py`'s `auth_db` fixture
        # documents). Touching every table once here, still on this
        # thread, forces that DDL to run before any worker thread exists.
        for table_name in dal.tables:
            dal(dal[table_name]).count()
        app.config["async_dal"] = async_dal
        app.config["dal"] = dal

        hub = PresentationHub(valkey_url=cfg.valkey_url)
        await hub.start()
        app.config["PRESENTATION_HUB"] = hub

        queue_reader = MusicQueueReader(
            hub_api_url=cfg.hub_api_url, service_api_key=cfg.service_api_key
        )
        await queue_reader.start()
        app.config["MUSIC_QUEUE_READER"] = queue_reader

        logger.system("svc-presentation started", action="startup", result="SUCCESS")

    @app.after_serving
    async def shutdown() -> None:
        """Close the PresentationHub, queue reader, and DAL connection pool."""
        hub = app.config.get("PRESENTATION_HUB")
        if hub is not None:
            await hub.stop()
        queue_reader = app.config.get("MUSIC_QUEUE_READER")
        if queue_reader is not None:
            await queue_reader.stop()
        async_dal = app.config.get("async_dal")
        if async_dal is not None:
            try:
                await async_dal.close_async()
            except Exception as exc:  # noqa: BLE001 - shutdown must not raise
                logger.warning(f"Error closing DAL on shutdown: {exc}")
        logger.system("svc-presentation shutdown complete", action="shutdown", result="SUCCESS")

    return app


app = create_app()


if __name__ == "__main__":  # pragma: no cover - process entrypoint, not exercised by unit tests
    import hypercorn.asyncio
    from hypercorn.config import Config as HyperConfig

    hyper_config = HyperConfig()
    hyper_config.bind = [f"0.0.0.0:{app.config['APP_CONFIG'].module_port}"]
    asyncio.run(hypercorn.asyncio.serve(app, hyper_config))
