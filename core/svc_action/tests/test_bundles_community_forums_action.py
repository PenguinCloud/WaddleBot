"""Tests for `bundles.community_forums_action` bundle functions."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from flask_core import (
    AsyncDAL,
    PlatformEvent,
    StageEnvelope,
    reset_bundle_dal_for_tests,
    set_bundle_dal,
)
from waddle_transports import NonRetryableTransportError, TransportResult

from bundles.community_forums_action import create_forum_post, create_forum_reply


def _envelope(action: str, *, community: str = "42", **payload_overrides: object) -> StageEnvelope:
    """Create a test envelope with the given forum action.

    No `channel_id` in the default payload -- a `!forum` chat command never
    carries one; the target channel comes from `config`, not the payload.
    `community` defaults to the mock-DAL tests' fixed `"42"` -- the
    real-pydal test overrides it to match the row it actually inserted.
    """
    payload: dict[str, object] = {
        "author_id": 456,
        "author": "test_user",
        "forum_action": action,
    }
    payload.update(payload_overrides)
    return StageEnvelope(
        tenant="test_tenant",
        community=community,
        app_id="waddles.community.forums.default",
        stage="action",
        event=PlatformEvent(
            platform="hub",
            event_type="message",
            actor="test_user",
            payload=payload,
            occurred_at="2026-01-01T00:00:00Z",
        ),
        ts="2026-01-01T12:00:00Z",
    )


def _config(**overrides: object) -> dict:
    """Create a test bundle config -- `channel_id`, when present, is the per-activation target."""
    base: dict[str, object] = {}
    base.update(overrides)
    return base


async def _client() -> httpx.AsyncClient:
    """Create a test httpx client."""
    return httpx.AsyncClient()


class TestCreateForumPostValidation:
    """Test input validation for create_forum_post."""

    async def test_missing_title_raises_non_retryable(self) -> None:
        """Missing forum_title should raise NonRetryableTransportError."""
        with patch("bundles.community_forums_action.get_bundle_dal"):
            with pytest.raises(NonRetryableTransportError, match="forum_title"):
                await create_forum_post(
                    _envelope("create", forum_body="body"),
                    _config(),
                    http_client=await _client(),
                )

    async def test_missing_body_raises_non_retryable(self) -> None:
        """Missing forum_body should raise NonRetryableTransportError."""
        with patch("bundles.community_forums_action.get_bundle_dal"):
            with pytest.raises(NonRetryableTransportError, match="forum_body"):
                await create_forum_post(
                    _envelope("create", forum_title="title"),
                    _config(),
                    http_client=await _client(),
                )

    async def test_invalid_channel_id_config_type_raises_non_retryable(self) -> None:
        """Non-integer channel_id in config should raise NonRetryableTransportError."""
        with patch("bundles.community_forums_action.get_bundle_dal"):
            with pytest.raises(NonRetryableTransportError, match="channel_id"):
                await create_forum_post(
                    _envelope("create", forum_title="title", forum_body="body"),
                    _config(channel_id="not_a_number"),
                    http_client=await _client(),
                )


class TestCreateForumPostSuccess:
    """Test successful forum post creation."""

    async def test_creates_forum_post_successfully(self) -> None:
        """Valid post creation with a configured channel should return success TransportResult."""
        mock_channel = MagicMock()
        mock_channel.id = 123
        mock_channel.community_server_channel_id = None

        mock_dal = AsyncMock()
        mock_dal.tables = ("hub_channels", "hub_forum_posts", "hub_forum_replies")
        mock_dal.select_async = AsyncMock(return_value=[mock_channel])
        mock_dal.insert_async = AsyncMock(return_value=999)

        with patch("bundles.community_forums_action.get_bundle_dal", return_value=mock_dal):
            result = await create_forum_post(
                _envelope("create", forum_title="Test", forum_body="Content"),
                _config(channel_id=123),
                http_client=await _client(),
            )

        assert isinstance(result, TransportResult)
        assert result.transport == "bundle"
        assert result.http_status == 201
        assert "post_id=999" in result.detail
        mock_dal.insert_async.assert_called_once()
        assert mock_dal.insert_async.call_args.kwargs["hub_channel_id"] == 123

    async def test_includes_tags_in_creation(self) -> None:
        """Forum post creation should include tags from payload."""
        mock_channel = MagicMock()
        mock_channel.id = 123
        mock_channel.community_server_channel_id = None

        mock_dal = AsyncMock()
        mock_dal.tables = ("hub_channels", "hub_forum_posts", "hub_forum_replies")
        mock_dal.select_async = AsyncMock(return_value=[mock_channel])
        mock_dal.insert_async = AsyncMock(return_value=1)

        with patch("bundles.community_forums_action.get_bundle_dal", return_value=mock_dal):
            await create_forum_post(
                _envelope("create", forum_title="Test", forum_body="Body", tags=["tag1", "tag2"]),
                _config(channel_id=123),
                http_client=await _client(),
            )

        call_args = mock_dal.insert_async.call_args
        assert call_args.kwargs["tags"] == ["tag1", "tag2"]

    async def test_channel_not_found_raises_non_retryable(self) -> None:
        """Post to a configured but non-existent channel should raise NonRetryableTransportError."""
        mock_dal = AsyncMock()
        mock_dal.tables = ("hub_channels", "hub_forum_posts", "hub_forum_replies")
        mock_dal.select_async = AsyncMock(return_value=[])

        with patch("bundles.community_forums_action.get_bundle_dal", return_value=mock_dal):
            with pytest.raises(NonRetryableTransportError, match="channel.*not found"):
                await create_forum_post(
                    _envelope("create", forum_title="Test", forum_body="Body"),
                    _config(channel_id=123),
                    http_client=await _client(),
                )

    async def test_no_channel_configured_persists_with_null_channel(self) -> None:
        """No channel_id in config (unconfigured activation) still persists the post.

        `hub_channel_id` is nullable -- see alembic
        0006_forum_posts_channel_nullable -- and no channel lookup/relay is
        attempted when no channel was configured.
        """
        mock_dal = AsyncMock()
        mock_dal.tables = ("hub_channels", "hub_forum_posts", "hub_forum_replies")
        mock_dal.insert_async = AsyncMock(return_value=1)

        with patch("bundles.community_forums_action.get_bundle_dal", return_value=mock_dal):
            result = await create_forum_post(
                _envelope("create", forum_title="Test", forum_body="Body"),
                _config(),  # no channel_id configured
                http_client=await _client(),
            )

        assert result.http_status == 201
        mock_dal.select_async.assert_not_called()  # no channel lookup without a configured channel
        mock_dal.insert_async.assert_called_once()
        assert mock_dal.insert_async.call_args.kwargs["hub_channel_id"] is None


class TestCreateForumReplyValidation:
    """Test input validation for create_forum_reply."""

    async def test_missing_post_id_raises_non_retryable(self) -> None:
        """Missing forum_post_id should raise NonRetryableTransportError."""
        with patch("bundles.community_forums_action.get_bundle_dal"):
            with pytest.raises(NonRetryableTransportError, match="forum_post_id"):
                await create_forum_reply(
                    _envelope("reply", forum_content="content"),
                    _config(),
                    http_client=await _client(),
                )

    async def test_invalid_post_id_type_raises_non_retryable(self) -> None:
        """Non-integer forum_post_id should raise NonRetryableTransportError."""
        with patch("bundles.community_forums_action.get_bundle_dal"):
            with pytest.raises(NonRetryableTransportError, match="forum_post_id"):
                await create_forum_reply(
                    _envelope("reply", forum_post_id="not_int", forum_content="content"),
                    _config(),
                    http_client=await _client(),
                )

    async def test_missing_content_raises_non_retryable(self) -> None:
        """Missing forum_content should raise NonRetryableTransportError."""
        with patch("bundles.community_forums_action.get_bundle_dal"):
            with pytest.raises(NonRetryableTransportError, match="forum_content"):
                await create_forum_reply(
                    _envelope("reply", forum_post_id=1),
                    _config(),
                    http_client=await _client(),
                )

    async def test_empty_content_raises_non_retryable(self) -> None:
        """Empty forum_content should raise NonRetryableTransportError."""
        with patch("bundles.community_forums_action.get_bundle_dal"):
            with pytest.raises(NonRetryableTransportError, match="forum_content"):
                await create_forum_reply(
                    _envelope("reply", forum_post_id=1, forum_content=""),
                    _config(),
                    http_client=await _client(),
                )


class TestCreateForumReplySuccess:
    """Test successful forum reply creation."""

    async def test_creates_forum_reply_successfully(self) -> None:
        """Valid reply creation should return success TransportResult."""
        mock_channel = MagicMock()
        mock_channel.id = 123
        mock_channel.community_server_channel_id = None

        mock_post = MagicMock()
        mock_post.id = 42
        mock_post.hub_channel_id = 123
        mock_post.is_locked = False
        mock_post.reply_count = 0

        mock_dal = AsyncMock()
        mock_dal.tables = ("hub_channels", "hub_forum_posts", "hub_forum_replies")
        # Mock select_async to return post for post query, channel for channel query
        mock_dal.select_async = AsyncMock(side_effect=[
            [mock_post],  # First call: fetch post
            [mock_channel],  # Second call: fetch channel
        ])
        mock_dal.insert_async = AsyncMock(return_value=777)
        mock_dal.update_async = AsyncMock()

        with patch("bundles.community_forums_action.get_bundle_dal", return_value=mock_dal):
            result = await create_forum_reply(
                _envelope("reply", forum_post_id=42, forum_content="Great post!"),
                _config(),
                http_client=await _client(),
            )

        assert isinstance(result, TransportResult)
        assert result.transport == "bundle"
        assert result.http_status == 201
        assert "reply_id=777" in result.detail

    async def test_post_not_found_raises_non_retryable(self) -> None:
        """Reply to non-existent post should raise NonRetryableTransportError."""
        mock_dal = AsyncMock()
        mock_dal.tables = ("hub_channels", "hub_forum_posts", "hub_forum_replies")
        mock_dal.select_async = AsyncMock(return_value=[])

        with patch("bundles.community_forums_action.get_bundle_dal", return_value=mock_dal):
            with pytest.raises(NonRetryableTransportError, match="post.*not found"):
                await create_forum_reply(
                    _envelope("reply", forum_post_id=999, forum_content="content"),
                    _config(),
                    http_client=await _client(),
                )

    async def test_locked_post_raises_non_retryable(self) -> None:
        """Reply to locked post should raise NonRetryableTransportError."""
        mock_post = MagicMock()
        mock_post.id = 42
        mock_post.is_locked = True

        mock_dal = AsyncMock()
        mock_dal.tables = ("hub_channels", "hub_forum_posts", "hub_forum_replies")
        mock_dal.select_async = AsyncMock(return_value=[mock_post])

        with patch("bundles.community_forums_action.get_bundle_dal", return_value=mock_dal):
            with pytest.raises(NonRetryableTransportError, match="locked"):
                await create_forum_reply(
                    _envelope("reply", forum_post_id=42, forum_content="content"),
                    _config(),
                    http_client=await _client(),
                )


class TestErrorHandling:
    """Test error handling paths."""

    async def test_forum_post_generic_error_wrapping(self) -> None:
        """Test that generic exceptions are wrapped as NonRetryableTransportError."""
        mock_dal = AsyncMock()
        mock_dal.tables = ("hub_channels", "hub_forum_posts", "hub_forum_replies")
        # select_async returns empty list (channel not found), triggering an exception
        mock_dal.select_async = AsyncMock(return_value=[])

        with patch("bundles.community_forums_action.get_bundle_dal", return_value=mock_dal):
            with pytest.raises(NonRetryableTransportError, match="channel.*not found"):
                await create_forum_post(
                    _envelope("create", forum_title="Test", forum_body="Body"),
                    _config(channel_id=123),
                    http_client=await _client(),
                )

    async def test_forum_reply_generic_error_wrapping(self) -> None:
        """Test that generic exceptions in reply creation are wrapped."""
        mock_dal = AsyncMock()
        mock_dal.tables = ("hub_channels", "hub_forum_posts", "hub_forum_replies")
        mock_dal.select_async = AsyncMock(return_value=[])  # No post found

        with patch("bundles.community_forums_action.get_bundle_dal", return_value=mock_dal):
            with pytest.raises(NonRetryableTransportError, match="post.*not found"):
                await create_forum_reply(
                    _envelope("reply", forum_post_id=1, forum_content="Reply"),
                    _config(),
                    http_client=await _client(),
                )


class TestRegression:
    """Regression tests for known issues."""

    async def test_forum_post_creation_with_relay_gh108(self) -> None:
        # regression: gh-108
        """Forum post with relay should succeed without error."""
        mock_channel = MagicMock()
        mock_channel.id = 123
        mock_channel.community_server_channel_id = 456  # Has relay config

        mock_dal = AsyncMock()
        mock_dal.tables = ("hub_channels", "hub_forum_posts", "hub_forum_replies")
        mock_dal.select_async = AsyncMock(return_value=[mock_channel])
        mock_dal.insert_async = AsyncMock(return_value=1)

        with patch("bundles.community_forums_action.get_bundle_dal", return_value=mock_dal):
            result = await create_forum_post(
                _envelope("create", forum_title="Test", forum_body="Body"),
                _config(channel_id=123),
                http_client=await _client(),
            )

        assert result.http_status == 201

    async def test_forum_reply_updates_counter_gh108(self) -> None:
        # regression: gh-108
        """Forum reply creation should increment post's reply counter."""
        mock_channel = MagicMock()
        mock_channel.community_server_channel_id = None

        mock_post = MagicMock()
        mock_post.id = 1
        mock_post.hub_channel_id = 123
        mock_post.is_locked = False
        mock_post.reply_count = 5

        mock_dal = AsyncMock()
        mock_dal.tables = ("hub_channels", "hub_forum_posts", "hub_forum_replies")
        # Mock select_async to return post for post query, channel for channel query
        mock_dal.select_async = AsyncMock(side_effect=[
            [mock_post],  # First call: fetch post
            [mock_channel],  # Second call: fetch channel
        ])
        mock_dal.insert_async = AsyncMock(return_value=1)
        mock_dal.update_async = AsyncMock()

        with patch("bundles.community_forums_action.get_bundle_dal", return_value=mock_dal):
            await create_forum_reply(
                _envelope("reply", forum_post_id=1, forum_content="Reply"),
                _config(),
                http_client=await _client(),
            )

        # Verify that update was called with reply_count incremented
        mock_dal.update_async.assert_called_once()
        update_call_args = mock_dal.update_async.call_args
        # Check that reply_count was incremented by 1
        assert update_call_args.kwargs["reply_count"] == 6  # 5 + 1

    async def test_forum_create_from_chat_persists_one_committed_post(self) -> None:
        """`!forum create My Title | body` (process -> action) commits exactly one row.

        Root-cause regression: the action bundle previously (a) built its
        own AsyncDAL against a hardcoded URL with a non-existent DB role
        (`svc-action-rw`) instead of the shared `get_bundle_dal()`, and (b)
        required `channel_id` in the chat payload, which the process stage
        never sets -- every `!forum create` from chat was rejected before
        ever reaching the DB. `hub_forum_posts` stayed at 0 rows in
        production for both reasons.

        The transformed payload below is exactly what `bundles.
        community_forums_process.transform()` produces for this chat text
        (verified independently in `core/svc_process/tests/
        test_bundles_community_forums_process.py::
        TestTransformForumCreate.test_parses_valid_create_command`) --
        svc_process and svc_action each own a same-named top-level
        `bundles` package on their own `sys.path`
        (`core/svc_action/tests/conftest.py`), so the real `transform()`
        can't be imported cross-service into this test module.
        """
        transformed_payload = {
            "text": "body",
            "author": "alice",
            "author_id": 7,
            "forum_action": "create",
            "forum_title": "My Title",
            "forum_body": "body",
        }
        envelope = StageEnvelope(
            tenant="test_tenant",
            community="42",
            app_id="waddles.community.forums.default",
            stage="action",
            event=PlatformEvent(
                platform="hub",
                event_type="message",
                actor="alice",
                payload=transformed_payload,
                occurred_at="2026-09-04T00:00:00Z",
            ),
            ts="2026-09-04T00:00:00Z",
        )

        mock_dal = AsyncMock()
        mock_dal.tables = ("hub_channels", "hub_forum_posts", "hub_forum_replies")
        mock_dal.insert_async = AsyncMock(return_value=1)

        with patch("bundles.community_forums_action.get_bundle_dal", return_value=mock_dal):
            result = await create_forum_post(
                envelope,
                _config(),  # unconfigured activation -- no channel_id
                http_client=await _client(),
            )

        assert result.http_status == 201
        mock_dal.insert_async.assert_called_once()
        call_kwargs = mock_dal.insert_async.call_args.kwargs
        assert call_kwargs["community_id"] == envelope.community == "42"
        assert call_kwargs["title"] == "My Title"
        assert call_kwargs["body"] == "body"
        assert call_kwargs["hub_channel_id"] is None

    async def test_forum_reply_from_chat_persists_one_committed_reply(self) -> None:
        """`!forum reply <post_id> | content` (process -> action) commits exactly one row.

        Companion to the `!forum create` regression above -- same DAL
        root-cause; transformed payload verified independently in
        `core/svc_process/tests/test_bundles_community_forums_process.py::
        TestTransformForumReply.test_parses_valid_reply_command` (see that
        test's docstring for why `transform()` can't be imported here).
        """
        transformed_payload = {
            "text": "Great post!",
            "author": "bob",
            "author_id": 8,
            "forum_action": "reply",
            "forum_post_id": 42,
            "forum_content": "Great post!",
        }
        envelope = StageEnvelope(
            tenant="test_tenant",
            community="42",
            app_id="waddles.community.forums.default",
            stage="action",
            event=PlatformEvent(
                platform="hub",
                event_type="message",
                actor="bob",
                payload=transformed_payload,
                occurred_at="2026-09-04T00:00:00Z",
            ),
            ts="2026-09-04T00:00:00Z",
        )

        mock_post = MagicMock()
        mock_post.id = 42
        mock_post.hub_channel_id = None
        mock_post.is_locked = False
        mock_post.reply_count = 0

        mock_dal = AsyncMock()
        mock_dal.tables = ("hub_channels", "hub_forum_posts", "hub_forum_replies")
        mock_dal.select_async = AsyncMock(side_effect=[[mock_post], []])
        mock_dal.insert_async = AsyncMock(return_value=1)
        mock_dal.update_async = AsyncMock()

        with patch("bundles.community_forums_action.get_bundle_dal", return_value=mock_dal):
            result = await create_forum_reply(envelope, _config(), http_client=await _client())

        assert result.http_status == 201
        mock_dal.insert_async.assert_called_once()
        assert mock_dal.insert_async.call_args.kwargs["post_id"] == 42
        assert mock_dal.insert_async.call_args.kwargs["content"] == "Great post!"
        mock_dal.update_async.assert_called_once()
        assert mock_dal.update_async.call_args.kwargs["reply_count"] == 1


@pytest.fixture
async def real_dal(tmp_path: Path) -> AsyncIterator[AsyncDAL]:
    """Real sqlite `AsyncDAL` -- `tenants`/`communities`/forum tables physically created.

    Same two-tier convention as `test_bundles_twitch_shoutout_action.py`'s
    own `dal` fixture: `_ensure_forum_tables` always binds with
    `migrate=False` (schema owned by `057_community_interaction.sql`), so
    this fixture defines the identical column set with `migrate=True`
    first; `_ensure_forum_tables`'s own guard then finds the tables
    already registered and is a no-op when the bundle runs.
    """
    async_dal = AsyncDAL(f"sqlite://{tmp_path}/forums_test.db", pool_size=1, migrate=True)
    d = async_dal.dal
    d.define_table("tenants", migrate=True)
    d.define_table("communities", d.Field("tenant_id", "reference tenants"), migrate=True)
    d.define_table(
        "hub_channels",
        d.Field("community_id", "reference communities", notnull=True),
        d.Field("community_server_channel_id", "integer"),
        migrate=True,
    )
    d.define_table(
        "hub_forum_posts",
        d.Field("hub_channel_id", "integer"),
        d.Field("community_id", "reference communities", notnull=True),
        d.Field("title", "string", notnull=True),
        d.Field("body", "text"),
        d.Field("tags", "json", default=[]),
        d.Field("author_hub_user_id", "integer"),
        d.Field("author_platform", "string"),
        d.Field("author_username", "string"),
        d.Field("author_avatar_url", "string"),
        d.Field("is_locked", "boolean", default=False),
        d.Field("reply_count", "integer", default=0),
        d.Field("last_reply_at", "datetime"),
        d.Field("created_at", "datetime"),
        d.Field("updated_at", "datetime"),
        migrate=True,
    )
    d.define_table(
        "hub_forum_replies",
        d.Field("post_id", "reference hub_forum_posts", notnull=True),
        d.Field("author_hub_user_id", "integer"),
        d.Field("author_platform", "string"),
        d.Field("author_username", "string"),
        d.Field("author_avatar_url", "string"),
        d.Field("content", "text", notnull=True),
        d.Field("created_at", "datetime"),
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
    """Real-DB smoke (gh-298): exercises the actual pydal query path, not a mock."""

    async def test_create_post_and_reply_against_real_sqlite(self, real_dal: AsyncDAL) -> None:
        # regression: gh-298 real-pydal
        """`dal.dal(query)` fix: create a post, then a reply, reading each back from sqlite."""
        d = real_dal.dal
        community_id = d.communities.insert(tenant_id=1)
        channel_id = d.hub_channels.insert(community_id=community_id)
        d.commit()

        # `community_id` is a real FK -- envelope.community must match the
        # row actually inserted above, not the fixed "42" `_envelope()`
        # bakes in for the mock-based tests.
        post_result = await create_forum_post(
            _envelope(
                "create",
                forum_title="Real Title",
                forum_body="Real body",
                community=str(community_id),
            ),
            _config(channel_id=channel_id),
            http_client=await _client(),
        )
        assert post_result.http_status == 201
        posts = d(d.hub_forum_posts.hub_channel_id == channel_id).select()
        assert len(posts) == 1
        post_id = posts[0].id
        assert posts[0].title == "Real Title"

        reply_result = await create_forum_reply(
            _envelope(
                "reply",
                forum_post_id=post_id,
                forum_content="Real reply",
                community=str(community_id),
            ),
            _config(),
            http_client=await _client(),
        )
        assert reply_result.http_status == 201
        replies = d(d.hub_forum_replies.post_id == post_id).select()
        assert len(replies) == 1
        assert replies[0].content == "Real reply"

        refreshed_post = d(d.hub_forum_posts.id == post_id).select().first()
        assert refreshed_post.reply_count == 1
