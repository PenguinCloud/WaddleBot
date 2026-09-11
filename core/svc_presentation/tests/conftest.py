"""Shared fixtures for svc-presentation's tests.

svc_presentation isn't installed as a package (a standalone stage-runner
directory run via `hypercorn app:app`, same shape as
`core/browser_source_core_module`) -- its own directory has to be put on
`sys.path` explicitly for `from app import create_app` / `import config` to
resolve.

`test_config`/`built_app` build a real `Quart` app against a file-backed
sqlite DB (`tmp_path`-scoped -- `AsyncDAL`'s `ThreadPoolExecutor` opens a
connection per worker thread; `sqlite:memory` is connection-scoped and a
worker thread would see a blank DB, the exact gotcha
`hub_api/tests/conftest.py`'s `auth_db` fixture documents) with
`db_migrate=True` so `bind_presentation_tables()` issues real DDL, no
Valkey URL configured (`PresentationHub` runs in fallback, pure in-process
mode unless a test explicitly injects a fake Valkey client), and no
`SERVICE_API_KEY` configured (`MusicQueueReader.connected` stays `False`)
unless a test explicitly injects a fake HTTP client.
"""

from __future__ import annotations

import os
import sys
from collections.abc import AsyncIterator
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
import pytest_asyncio
from quart.typing import TestClientProtocol

from app import create_app
from config import Config


@pytest.fixture
def test_config(tmp_path: Path) -> Config:
    """A `Config` pointed at an ephemeral, migrated sqlite file DB, no Valkey."""
    db_path = tmp_path / "presentation_test.db"
    return Config(
        module_name="svc-presentation",
        module_version="test",
        module_port=8207,
        pipeline_stage="presentation",
        log_level="INFO",
        database_url=f"sqlite://{db_path}",
        database_read_replica_url=None,
        db_pool_size=1,
        db_migrate=True,
        valkey_url=None,
        hub_api_url="http://hub-api:8204",
        hub_api_poll_interval_seconds=30,
        push_token="",
        service_api_key="",
    )


@pytest_asyncio.fixture
async def client(test_config: Config) -> AsyncIterator[TestClientProtocol]:
    """A running svc-presentation app (startup/shutdown hooks fired) + its test client."""
    app = create_app(test_config)
    async with app.test_app() as running:
        yield running.test_client()
