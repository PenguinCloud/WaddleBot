"""Tests for `bundles.community_announcements_process.transform`."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest
from flask_core import (
    AsyncDAL,
    PlatformEvent,
    bundle_context,
    reset_bundle_dal_for_tests,
    set_bundle_dal,
)

from bundles.community_announcements_process import _ANNOUNCE_USAGE, transform


class _FakeDalQuery:
    """Fake query object supporting chaining."""

    def __init__(self, parent_dal: Any) -> None:
        self._parent_dal = parent_dal
        self._community_id_filter: int | None = None

    def __and__(self, other: Any) -> Any:
        """Support & operator for combining queries.

        When combining with another comparison (e.g., community_id == value),
        extract and store the community_id filter.
        """
        # The other operand should be another comparison; extract its value
        # For simplicity, just return self - the second comparison will have
        # set _query_community_id on the DAL
        return self

    def select(self) -> Any:
        """Return self to support chaining."""
        return self

    def first(self) -> Any:
        """Return the stored announcement or None."""
        if (
            self._parent_dal._query_id is not None
            and self._parent_dal._query_id in self._parent_dal._announcements
        ):
            ann = self._parent_dal._announcements[self._parent_dal._query_id]
            # Check community filter if set
            if self._parent_dal._query_community_id is not None:
                if (
                    not hasattr(ann, "community_id")
                    or ann.community_id != self._parent_dal._query_community_id
                ):
                    return None
            return ann
        return None


class _FakeDalAttr:
    """Represents an attribute access like dal.announcements.id or .community_id."""

    def __init__(self, parent_dal: Any, attr_name: str) -> None:
        self._parent_dal = parent_dal
        self._attr_name = attr_name

    def __eq__(self, other: int) -> Any:
        """Support == comparison for attributes."""
        if self._attr_name == "id":
            self._parent_dal._query_id = other
        elif self._attr_name == "community_id":
            self._parent_dal._query_community_id = other
        return _FakeDalQuery(self._parent_dal)


class _FakeDalTable:
    """Fake table object supporting attribute access."""

    def __init__(self, parent_dal: Any) -> None:
        self._parent_dal = parent_dal

    def __getattr__(self, name: str) -> Any:
        """Support dal.announcements.id == value syntax."""
        # Return an attribute object that can handle comparisons
        return _FakeDalAttr(self._parent_dal, name)

    def __and__(self, other: Any) -> Any:
        """Support & operator for combining conditions."""
        return self


class _FakeDal:
    """In-memory stand-in for AsyncDAL -- implements only the surface this bundle uses."""

    def __init__(self) -> None:
        self._announcements: dict[int, Any] = {}
        self._query_id: int | None = None
        self._query_community_id: int | None = None
        self._raise_on_query: Exception | None = None
        self.announcements = _FakeDalTable(self)
        # `dal.dal(query)` (the real `AsyncDAL.dal` raw-pydal-DAL
        # attribute) resolves to this same fake's own `__call__` --
        # and `.tables` pre-populated so `_ensure_announcements_table`'s
        # idempotent `"x" not in dal.tables` guard is a no-op.
        self.dal = self
        self.tables = ("announcements",)

    def __call__(self, query: Any) -> Any:
        """Support the query pattern dal(dal.announcements.id == id)."""
        if self._raise_on_query is not None:
            raise self._raise_on_query
        # Extract community_id from query if it's a comparison with community_id
        if hasattr(query, "_parent_dal"):
            # This is a query object, extract any community_id filter
            pass
        return query if hasattr(query, "first") else self

    async def select_async(self, query: Any, *args: object, **kwargs: object) -> Any:
        """Async version of select -- delegates to the fake query's own `.select()`."""
        return query.select() if hasattr(query, "select") else query

    def add_announcement(self, id: int, title: str, content: str, **kwargs: object) -> None:
        """Add a test announcement."""
        self._announcements[id] = type(
            "Row",
            (),
            {
                "id": id,
                "title": title,
                "content": content,
                "announcement_type": kwargs.get("announcement_type", "general"),
                "status": kwargs.get("status", "published"),
                "community_id": kwargs.get("community_id", 1),
                "broadcasted_platforms": kwargs.get("broadcasted_platforms", []),
            },
        )()


def _event(text: str, **payload_overrides: object) -> PlatformEvent:
    """Build a test PlatformEvent with the given text and payload overrides."""
    payload = {"text": text, "channel_id": "chan-1"}
    payload.update(payload_overrides)
    return PlatformEvent(
        platform="discord",
        event_type="message",
        actor="testuser",
        payload=payload,
        occurred_at="2026-09-04T00:00:00Z",
    )


@pytest.fixture(autouse=True)
def _dal() -> Any:
    """Inject fake DAL and reset after each test."""
    fake = _FakeDal()
    set_bundle_dal(fake)
    yield fake
    reset_bundle_dal_for_tests()


class TestTransform:
    """Tests for announcement command parsing and enrichment."""

    async def test_announce_publish_command_with_valid_id(self, _dal: _FakeDal) -> None:
        """Test parsing of `!announce publish <id>` with a valid announcement ID."""
        _dal.add_announcement(
            42,
            "Test Announcement",
            "This is a test announcement",
            announcement_type="general",
            status="published",
            community_id=42,  # Match the community in the context
            broadcasted_platforms=["discord", "twitch"],
        )

        with bundle_context(
            tenant="acme-corp", community="42", app_id="waddles.community.announcements.default"
        ):
            result = await transform(_event("!announce publish 42"))

        assert result is not None
        assert isinstance(result, PlatformEvent)
        assert result.payload["announcement_id"] == 42
        assert result.payload["announcement"]["title"] == "Test Announcement"
        assert "discord" in result.payload["target_platforms"]
        assert "twitch" in result.payload["target_platforms"]
        # Original fields preserved
        assert result.payload["channel_id"] == "chan-1"
        assert result.platform == "discord"

    async def test_announce_publish_command_case_insensitive(self, _dal: _FakeDal) -> None:
        """Test that the command parser is case-insensitive."""
        _dal.add_announcement(
            99,
            "Uppercase Test",
            "test",
            announcement_type="event",
            status="published",
            community_id=42,
            broadcasted_platforms=[],
        )

        with bundle_context(
            tenant="acme-corp", community="42", app_id="waddles.community.announcements.default"
        ):
            result = await transform(_event("!ANNOUNCE PUBLISH 99"))

        assert result is not None
        assert result.payload["announcement_id"] == 99

    async def test_ordinary_chatter_returns_none(self) -> None:
        """Test that non-announcement messages return None (no reply)."""
        with bundle_context(
            tenant="acme-corp", community="42", app_id="waddles.community.announcements.default"
        ):
            result = await transform(_event("just chatting"))
        assert result is None

    async def test_partial_command_returns_usage_hint(self) -> None:
        """Test that an incomplete `!announce` command gets a usage-hint reply, not None."""
        with bundle_context(
            tenant="acme-corp", community="42", app_id="waddles.community.announcements.default"
        ):
            result = await transform(_event("!announce"))
        assert isinstance(result, PlatformEvent)
        assert result.payload["text"] == _ANNOUNCE_USAGE

    async def test_other_bot_commands_return_none(self) -> None:
        """Test that other bot commands (not announce) return None."""
        with bundle_context(
            tenant="acme-corp", community="42", app_id="waddles.community.announcements.default"
        ):
            result = await transform(_event("!ping"))
        assert result is None

    async def test_announcement_not_found_returns_none(self) -> None:
        """Test that non-existent announcements return None."""
        with bundle_context(
            tenant="acme-corp", community="42", app_id="waddles.community.announcements.default"
        ):
            result = await transform(_event("!announce publish 999"))
        assert result is None

    async def test_invalid_announcement_id_returns_usage_hint(self) -> None:
        """Test that a non-numeric announcement id gets a usage-hint reply, not None."""
        with bundle_context(
            tenant="acme-corp", community="42", app_id="waddles.community.announcements.default"
        ):
            result = await transform(_event("!announce publish abc"))
        assert isinstance(result, PlatformEvent)
        assert result.payload["text"] == _ANNOUNCE_USAGE

    async def test_missing_text_field_raises(self) -> None:
        """Test that missing text field in payload raises ValueError."""
        event = PlatformEvent(
            platform="discord",
            event_type="message",
            actor="testuser",
            payload={"channel_id": "chan-1"},  # Missing 'text'
            occurred_at="2026-09-04T00:00:00Z",
        )
        with bundle_context(
            tenant="acme-corp", community="42", app_id="waddles.community.announcements.default"
        ):
            with pytest.raises(ValueError, match="text"):
                await transform(event)

    async def test_enriched_event_preserves_top_level_fields(self, _dal: _FakeDal) -> None:
        """Test that enrichment preserves all top-level PlatformEvent fields."""
        _dal.add_announcement(
            55,
            "Title",
            "content",
            announcement_type="update",
            status="published",
            community_id=42,
            broadcasted_platforms=["discord"],
        )

        with bundle_context(
            tenant="acme-corp", community="42", app_id="waddles.community.announcements.default"
        ):
            result = await transform(_event("!announce publish 55"))

        assert result is not None
        assert result.platform == "discord"
        assert result.event_type == "message"
        assert result.actor == "testuser"
        assert result.occurred_at == "2026-09-04T00:00:00Z"

    async def test_defaults_to_all_platforms_if_not_specified(self, _dal: _FakeDal) -> None:
        """Test that bundles default to all platforms if none specified."""
        _dal.add_announcement(
            77,
            "Title",
            "content",
            announcement_type="general",
            status="published",
            community_id=42,
            broadcasted_platforms=[],  # Empty list
        )

        with bundle_context(
            tenant="acme-corp", community="42", app_id="waddles.community.announcements.default"
        ):
            result = await transform(_event("!announce publish 77"))

        assert result is not None
        # Should default to discord + twitch
        assert "discord" in result.payload["target_platforms"]
        assert "twitch" in result.payload["target_platforms"]

    async def test_handles_missing_broadcasted_platforms_attr(self, _dal: _FakeDal) -> None:
        """Test handling when broadcasted_platforms attribute is missing."""
        # Add announcement without broadcasted_platforms attribute
        announcement = type(
            "Row",
            (),
            {
                "id": 88,
                "title": "Title",
                "content": "content",
                "announcement_type": "general",
                "status": "published",
                "community_id": 42,
            },
        )()
        _dal._announcements[88] = announcement
        _dal._query_id = 88

        with bundle_context(
            tenant="acme-corp", community="42", app_id="waddles.community.announcements.default"
        ):
            result = await transform(_event("!announce publish 88"))

        assert result is not None
        # Should default to discord + twitch
        assert "discord" in result.payload["target_platforms"]
        assert "twitch" in result.payload["target_platforms"]

    async def test_handles_invalid_broadcasted_platforms_type(self, _dal: _FakeDal) -> None:
        """Test handling when broadcasted_platforms is not a list."""
        # Add announcement with non-list broadcasted_platforms
        announcement = type(
            "Row",
            (),
            {
                "id": 89,
                "title": "Title",
                "content": "content",
                "announcement_type": "general",
                "status": "published",
                "community_id": 42,
                "broadcasted_platforms": "discord",  # Not a list
            },
        )()
        _dal._announcements[89] = announcement
        _dal._query_id = 89

        with bundle_context(
            tenant="acme-corp", community="42", app_id="waddles.community.announcements.default"
        ):
            result = await transform(_event("!announce publish 89"))

        assert result is not None
        # Should default to discord + twitch when invalid type
        assert "discord" in result.payload["target_platforms"]
        assert "twitch" in result.payload["target_platforms"]

    async def test_db_error_during_query_raises(self, _dal: _FakeDal) -> None:
        """Test that DB query errors are caught and re-raised as ValueError."""
        # Configure DAL to raise an error on query
        _dal._raise_on_query = RuntimeError("Connection failed")

        with bundle_context(
            tenant="acme-corp", community="42", app_id="waddles.community.announcements.default"
        ):
            with pytest.raises(ValueError, match="failed to lookup or enrich"):
                await transform(_event("!announce publish 100"))

    async def test_cross_community_announcement_not_found(self, _dal: _FakeDal) -> None:
        """Regression: announcement from another community should not be found (IDOR prevention)."""
        # Add an announcement belonging to community 99
        _dal.add_announcement(
            123,
            "Other Community Announcement",
            "This belongs to community 99",
            announcement_type="general",
            status="published",
            community_id=99,  # Different community
            broadcasted_platforms=["discord"],
        )

        # Try to access it from community 42
        with bundle_context(
            tenant="acme-corp", community="42", app_id="waddles.community.announcements.default"
        ):
            result = await transform(_event("!announce publish 123"))

        # Should return None (as if announcement not found) to prevent IDOR
        assert result is None

    async def test_tenant_wide_activation_cannot_broadcast(self) -> None:
        """Tenant-wide activations (community=None) cannot broadcast announcements."""
        # Even if an announcement exists, tenant-wide activations should return None
        with bundle_context(
            tenant="acme-corp", community=None, app_id="waddles.community.announcements.default"
        ):
            result = await transform(_event("!announce publish 1"))

        assert result is None


@pytest.fixture
async def real_dal(tmp_path: Path) -> AsyncIterator[AsyncDAL]:
    """Real sqlite `AsyncDAL` -- `tenants`/`communities`/`announcements` physically created.

    Same two-tier convention as `svc_action/tests/test_bundles_twitch_
    shoutout_action.py`'s own `dal` fixture: `_ensure_announcements_table`
    always binds with `migrate=False`, so this fixture defines the
    identical column set with `migrate=True` first; the bundle's own
    guard then finds the table already registered and is a no-op.
    """
    async_dal = AsyncDAL(f"sqlite://{tmp_path}/announce_process_test.db", pool_size=1, migrate=True)
    d = async_dal.dal
    d.define_table("tenants", migrate=True)
    d.define_table("communities", d.Field("tenant_id", "reference tenants"), migrate=True)
    d.define_table(
        "announcements",
        d.Field("community_id", "reference communities", notnull=True),
        d.Field("title", "string", notnull=True),
        d.Field("content", "text", notnull=True),
        d.Field("announcement_type", "string", default="general"),
        d.Field("status", "string", default="published"),
        d.Field("broadcasted_platforms", "json", default=[]),
        migrate=True,
    )
    d.tenants.insert()
    d.communities.insert(tenant_id=1)
    d.commit()
    set_bundle_dal(async_dal)
    try:
        yield async_dal
    finally:
        reset_bundle_dal_for_tests()
        try:
            await async_dal.close_async()
        except Exception:  # noqa: BLE001, S110 -- known pydal cross-thread close gotcha
            pass  # nosec B110


class TestRealPydal:
    """Real-DB smoke (gh-298): exercises the actual pydal query path, not a fake."""

    async def test_announce_publish_against_real_sqlite(self, real_dal: AsyncDAL) -> None:
        # regression: gh-298 real-pydal
        """`dal.dal(query)` fix: insert one announcement, enrich via `transform`, read back."""
        d = real_dal.dal
        community_id = d.communities.insert(tenant_id=1)
        announcement_id = d.announcements.insert(
            community_id=community_id,
            title="Real Announcement",
            content="Real content",
            announcement_type="general",
            status="published",
            broadcasted_platforms=["discord"],
        )
        d.commit()

        with bundle_context(
            tenant="acme-corp",
            community=str(community_id),
            app_id="waddles.community.announcements.default",
        ):
            result = await transform(_event(f"!announce publish {announcement_id}"))

        assert result is not None
        assert result.payload["announcement_id"] == announcement_id
        assert result.payload["announcement"]["title"] == "Real Announcement"
        assert result.payload["target_platforms"] == ["discord"]
