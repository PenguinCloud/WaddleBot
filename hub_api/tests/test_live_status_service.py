"""Tests for `services.live_status_service` -- gh #287 S10's community-scoped live read.

Reuses `tests/conftest.py`'s existing `streaming_db` fixture (already
binds `coordination`/`community_servers` -- see `test_v1_stream_blueprint.
py`'s own `_seed_live_stream` for the seeding shape this file mirrors).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from services.live_status_service import get_live_status
from tests.conftest import TENANT_SLUG


def _tenant_id(db: Any) -> int:
    row = db.dal(db.dal.tenants.slug == TENANT_SLUG).select().first()
    return int(row.id)


def _seed_community(db: Any) -> int:
    community_id: int = db.dal.communities.insert(name="acme-community", tenant_id=_tenant_id(db))
    db.dal.commit()
    return community_id


def _seed_channel(
    db: Any,
    *,
    community_id: int,
    platform_server_id: str,
    entity_id: str,
    is_live: bool,
    viewer_count: int = 0,
    channel_name: str | None = "Cool Channel",
    live_since: datetime | None = None,
    status: str = "approved",
    platform: str = "twitch",
) -> None:
    db.dal.community_servers.insert(
        community_id=community_id,
        platform=platform,
        platform_server_id=platform_server_id,
        status=status,
    )
    db.dal.coordination.insert(
        entity_id=entity_id,
        platform=platform,
        server_id=platform_server_id,
        channel_id=platform_server_id,
        channel_name=channel_name,
        is_live=is_live,
        viewer_count=viewer_count,
        live_since=live_since,
    )
    db.dal.commit()


class TestNoConnectedChannels:
    async def test_returns_not_live_with_empty_streams(self, streaming_db: Any) -> None:
        community_id = _seed_community(streaming_db)

        status = await get_live_status(streaming_db, streaming_db.dal, community_id=community_id)

        assert status.live is False
        assert status.platform is None
        assert status.channel is None
        assert status.since is None
        assert status.viewer_count == 0
        assert status.streams == []


class TestAllChannelsOffline:
    async def test_returns_not_live_but_lists_the_offline_stream(self, streaming_db: Any) -> None:
        community_id = _seed_community(streaming_db)
        _seed_channel(
            streaming_db,
            community_id=community_id,
            platform_server_id="srv-1",
            entity_id="twitch:999",
            is_live=False,
        )

        status = await get_live_status(streaming_db, streaming_db.dal, community_id=community_id)

        assert status.live is False
        assert len(status.streams) == 1
        assert status.streams[0].live is False
        assert status.streams[0].since is None


class TestOneChannelLive:
    async def test_summary_reflects_the_live_channel(self, streaming_db: Any) -> None:
        community_id = _seed_community(streaming_db)
        since = datetime(2026, 1, 1, tzinfo=UTC)
        _seed_channel(
            streaming_db,
            community_id=community_id,
            platform_server_id="srv-1",
            entity_id="twitch:999",
            is_live=True,
            viewer_count=42,
            channel_name="Cool Channel",
            live_since=since,
        )

        status = await get_live_status(streaming_db, streaming_db.dal, community_id=community_id)

        assert status.live is True
        assert status.platform == "twitch"
        assert status.channel == "Cool Channel"
        assert status.viewer_count == 42
        # sqlite (this fixture's backing store) round-trips a `datetime` as
        # naive -- tzinfo is dropped, unlike production Postgres
        # (TIMESTAMPTZ). Compare the naive prefix only.
        assert status.since is not None
        assert status.since.startswith("2026-01-01T00:00:00")
        assert len(status.streams) == 1
        assert status.streams[0].live is True

    async def test_mixed_live_and_offline_orders_live_first(self, streaming_db: Any) -> None:
        community_id = _seed_community(streaming_db)
        _seed_channel(
            streaming_db,
            community_id=community_id,
            platform_server_id="srv-offline",
            entity_id="twitch:1",
            is_live=False,
        )
        _seed_channel(
            streaming_db,
            community_id=community_id,
            platform_server_id="srv-live",
            entity_id="twitch:2",
            is_live=True,
            viewer_count=10,
        )

        status = await get_live_status(streaming_db, streaming_db.dal, community_id=community_id)

        assert status.live is True
        assert len(status.streams) == 2
        assert status.streams[0].live is True  # live-first ordering


class TestUnapprovedOrOtherCommunityExcluded:
    async def test_pending_server_is_excluded(self, streaming_db: Any) -> None:
        community_id = _seed_community(streaming_db)
        _seed_channel(
            streaming_db,
            community_id=community_id,
            platform_server_id="srv-1",
            entity_id="twitch:999",
            is_live=True,
            status="pending",
        )

        status = await get_live_status(streaming_db, streaming_db.dal, community_id=community_id)

        assert status.live is False
        assert status.streams == []

    async def test_other_communitys_channel_is_excluded(self, streaming_db: Any) -> None:
        community_id = _seed_community(streaming_db)
        other_community_id = streaming_db.dal.communities.insert(
            name="other-community", tenant_id=_tenant_id(streaming_db)
        )
        streaming_db.dal.commit()
        _seed_channel(
            streaming_db,
            community_id=other_community_id,
            platform_server_id="srv-1",
            entity_id="twitch:999",
            is_live=True,
        )

        status = await get_live_status(streaming_db, streaming_db.dal, community_id=community_id)

        assert status.live is False
        assert status.streams == []
