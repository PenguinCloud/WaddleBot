"""Tests for `bundles.social_music_process.transform`."""

from __future__ import annotations

from typing import Any

import pytest
from flask_core import PROCESS_TARGET_APP_ID_KEY, PlatformEvent, bundle_context

from bundles.social_music_process import (
    _MUSIC_APP_ID,
    _SET_UNAVAILABLE_REPLY,
    _SR_USAGE,
    _STATUS_CHECK_KEY,
    _STATUS_DISABLED_REPLY,
    transform,
)

TENANT = "global"
COMMUNITY = "42"
APP_ID = "waddles.bot.discord.default"


def _event(text: str, **payload_overrides: object) -> PlatformEvent:
    """Create a test event with the given text; a channel_id + tokenized author_id by default."""
    payload: dict[str, object] = {
        "text": text,
        "channel_id": "123",
        "author_id": "platform-user-1",
        **payload_overrides,
    }
    return PlatformEvent(
        platform="discord",
        event_type="message",
        actor="test_user",
        payload=payload,
        occurred_at="2026-01-01T00:00:00+00:00",
    )


async def _flag_on(*_args: Any, **_kwargs: Any) -> bool:
    return True


async def _flag_off(*_args: Any, **_kwargs: Any) -> bool:
    return False


@pytest.fixture(autouse=True)
def _flag_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    """Default every test to flag ON -- the OFF-specific tests override this explicitly."""
    monkeypatch.setattr("bundles.social_music_process.feature_enabled", _flag_on)


class TestTransformSongRequest:
    """Valid `!sr`/`!songrequest` parsing."""

    async def test_parses_sr_with_url(self) -> None:
        with bundle_context(tenant=TENANT, community=COMMUNITY, app_id=APP_ID):
            result = await transform(_event("!sr https://youtu.be/dQw4w9WgXcQ"))
        assert isinstance(result, PlatformEvent)
        assert result.payload["music_query"] == "https://youtu.be/dQw4w9WgXcQ"
        assert result.payload["text"] == "https://youtu.be/dQw4w9WgXcQ"

    async def test_parses_songrequest_alias_with_free_text_query(self) -> None:
        with bundle_context(tenant=TENANT, community=COMMUNITY, app_id=APP_ID):
            result = await transform(_event("!songrequest never gonna give you up"))
        assert isinstance(result, PlatformEvent)
        assert result.payload["music_query"] == "never gonna give you up"

    async def test_sets_target_app_id_for_cross_app_routing(self) -> None:
        """Mirrors the forum bundle's gh #298 routing mechanism -- see that bundle's test."""
        with bundle_context(tenant=TENANT, community=COMMUNITY, app_id=APP_ID):
            result = await transform(_event("!sr some song"))
        assert isinstance(result, PlatformEvent)
        assert result.payload[PROCESS_TARGET_APP_ID_KEY] == _MUSIC_APP_ID
        assert _MUSIC_APP_ID == "waddles.social.music.default"

    async def test_preserves_tokenized_requester_identity_and_channel(self) -> None:
        """`author_id` (tokenized platform id) and `channel_id` must survive untouched."""
        with bundle_context(tenant=TENANT, community=COMMUNITY, app_id=APP_ID):
            result = await transform(_event("!sr some song"))
        assert isinstance(result, PlatformEvent)
        assert result.payload["channel_id"] == "123"
        assert result.payload["author_id"] == "platform-user-1"
        assert result.actor == "test_user"

    async def test_case_insensitive(self) -> None:
        with bundle_context(tenant=TENANT, community=COMMUNITY, app_id=APP_ID):
            result = await transform(_event("!SR Some Song"))
        assert isinstance(result, PlatformEvent)
        assert result.payload["music_query"] == "Some Song"

    async def test_whitespace_around_query_is_stripped(self) -> None:
        with bundle_context(tenant=TENANT, community=COMMUNITY, app_id=APP_ID):
            result = await transform(_event("!sr   some song   "))
        assert isinstance(result, PlatformEvent)
        assert result.payload["music_query"] == "some song"


class TestTransformUsageHint:
    """Bad/empty arg -> usage-hint reply, never a crash."""

    async def test_bare_sr_returns_usage(self) -> None:
        with bundle_context(tenant=TENANT, community=COMMUNITY, app_id=APP_ID):
            result = await transform(_event("!sr"))
        assert isinstance(result, PlatformEvent)
        assert result.payload["text"] == _SR_USAGE
        assert PROCESS_TARGET_APP_ID_KEY not in result.payload

    async def test_bare_songrequest_returns_usage(self) -> None:
        with bundle_context(tenant=TENANT, community=COMMUNITY, app_id=APP_ID):
            result = await transform(_event("!songrequest"))
        assert isinstance(result, PlatformEvent)
        assert result.payload["text"] == _SR_USAGE

    async def test_whitespace_only_arg_returns_usage(self) -> None:
        with bundle_context(tenant=TENANT, community=COMMUNITY, app_id=APP_ID):
            result = await transform(_event("!sr      "))
        assert isinstance(result, PlatformEvent)
        assert result.payload["text"] == _SR_USAGE


class TestTransformNonMatchingMessages:
    """Anything not `!sr`/`!songrequest` returns `None` -- no echo."""

    async def test_ordinary_chatter_returns_none(self) -> None:
        with bundle_context(tenant=TENANT, community=COMMUNITY, app_id=APP_ID):
            assert await transform(_event("hello everyone")) is None

    async def test_other_commands_return_none(self) -> None:
        with bundle_context(tenant=TENANT, community=COMMUNITY, app_id=APP_ID):
            assert await transform(_event("!forum create x | y")) is None
            assert await transform(_event("!ping")) is None

    async def test_word_boundary_prevents_partial_match(self) -> None:
        """`!srx` must not be treated as `!sr` with a mangled arg."""
        with bundle_context(tenant=TENANT, community=COMMUNITY, app_id=APP_ID):
            assert await transform(_event("!srx something")) is None

    async def test_empty_text_returns_none(self) -> None:
        with bundle_context(tenant=TENANT, community=COMMUNITY, app_id=APP_ID):
            assert await transform(_event("")) is None
            assert await transform(_event("   ")) is None


class TestTransformFeatureFlag:
    """Flag OFF (or a flag/license outage, which `feature_enabled` itself degrades) -> `None`."""

    async def test_flag_off_returns_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("bundles.social_music_process.feature_enabled", _flag_off)
        with bundle_context(tenant=TENANT, community=COMMUNITY, app_id=APP_ID):
            assert await transform(_event("!sr some song")) is None

    async def test_flag_off_still_ignores_non_matching_messages(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Flag OFF must not change behavior for messages that were never `!sr` to begin with."""
        monkeypatch.setattr("bundles.social_music_process.feature_enabled", _flag_off)
        with bundle_context(tenant=TENANT, community=COMMUNITY, app_id=APP_ID):
            assert await transform(_event("hello")) is None

    async def test_flag_check_receives_tenant_and_community(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        captured: dict[str, Any] = {}

        async def _capture(
            flag_key: str, *, tenant: str, community: int | None = None, default: bool = False
        ) -> bool:
            captured["flag_key"] = flag_key
            captured["tenant"] = tenant
            captured["community"] = community
            captured["default"] = default
            return True

        monkeypatch.setattr("bundles.social_music_process.feature_enabled", _capture)
        with bundle_context(tenant=TENANT, community=COMMUNITY, app_id=APP_ID):
            await transform(_event("!sr some song"))

        assert captured["flag_key"] == "waddles.social.music"
        assert captured["tenant"] == TENANT
        assert captured["community"] == 42
        assert captured["default"] is True


class TestTransformStatus:
    """`!sr status` -- always answers, flag on or off."""

    async def test_status_enabled_routes_to_action_with_status_check_flag(self) -> None:
        with bundle_context(tenant=TENANT, community=COMMUNITY, app_id=APP_ID):
            result = await transform(_event("!sr status"))
        assert isinstance(result, PlatformEvent)
        assert result.payload[_STATUS_CHECK_KEY] is True
        assert result.payload[PROCESS_TARGET_APP_ID_KEY] == _MUSIC_APP_ID

    async def test_status_alias_songrequest_also_routes(self) -> None:
        with bundle_context(tenant=TENANT, community=COMMUNITY, app_id=APP_ID):
            result = await transform(_event("!songrequest status"))
        assert isinstance(result, PlatformEvent)
        assert result.payload[_STATUS_CHECK_KEY] is True

    async def test_status_case_insensitive(self) -> None:
        with bundle_context(tenant=TENANT, community=COMMUNITY, app_id=APP_ID):
            result = await transform(_event("!sr STATUS"))
        assert isinstance(result, PlatformEvent)
        assert result.payload[_STATUS_CHECK_KEY] is True

    async def test_status_disabled_replies_directly_without_target_app_id(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The one subcommand that must still answer when the flag is off."""
        monkeypatch.setattr("bundles.social_music_process.feature_enabled", _flag_off)
        with bundle_context(tenant=TENANT, community=COMMUNITY, app_id=APP_ID):
            result = await transform(_event("!sr status"))
        assert isinstance(result, PlatformEvent)
        assert result.payload["text"] == _STATUS_DISABLED_REPLY
        assert PROCESS_TARGET_APP_ID_KEY not in result.payload
        assert _STATUS_CHECK_KEY not in result.payload

    async def test_status_preserves_channel_and_requester(self) -> None:
        with bundle_context(tenant=TENANT, community=COMMUNITY, app_id=APP_ID):
            result = await transform(_event("!sr status"))
        assert isinstance(result, PlatformEvent)
        assert result.payload["channel_id"] == "123"
        assert result.payload["author_id"] == "platform-user-1"


class TestTransformSet:
    """`!sr set ...` -- out of scope this pass, never treated as a song title."""

    async def test_set_returns_unavailable_reply(self) -> None:
        with bundle_context(tenant=TENANT, community=COMMUNITY, app_id=APP_ID):
            result = await transform(_event("!sr set discord #music"))
        assert isinstance(result, PlatformEvent)
        assert result.payload["text"] == _SET_UNAVAILABLE_REPLY
        assert PROCESS_TARGET_APP_ID_KEY not in result.payload
        assert "music_query" not in result.payload

    async def test_bare_set_returns_unavailable_reply(self) -> None:
        with bundle_context(tenant=TENANT, community=COMMUNITY, app_id=APP_ID):
            result = await transform(_event("!sr set"))
        assert isinstance(result, PlatformEvent)
        assert result.payload["text"] == _SET_UNAVAILABLE_REPLY

    async def test_set_returns_none_when_flag_disabled(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """`set` follows the general flag gate (unlike `status`) -- silent when disabled."""
        monkeypatch.setattr("bundles.social_music_process.feature_enabled", _flag_off)
        with bundle_context(tenant=TENANT, community=COMMUNITY, app_id=APP_ID):
            assert await transform(_event("!sr set discord #music")) is None

    async def test_a_song_literally_titled_settle_is_not_mistaken_for_set(self) -> None:
        """Word-boundary check: `settle down` must not match the `set` subcommand."""
        with bundle_context(tenant=TENANT, community=COMMUNITY, app_id=APP_ID):
            result = await transform(_event("!sr settle down"))
        assert isinstance(result, PlatformEvent)
        assert result.payload["music_query"] == "settle down"


class TestTransformErrorHandling:
    """Missing/non-string `text` raises -- caught per-event by the process runner."""

    async def test_missing_text_field_raises(self) -> None:
        event = PlatformEvent(
            platform="discord",
            event_type="message",
            actor="test_user",
            payload={"channel_id": "123"},
            occurred_at="2026-01-01T00:00:00+00:00",
        )
        with bundle_context(tenant=TENANT, community=COMMUNITY, app_id=APP_ID):
            with pytest.raises(ValueError, match="text"):
                await transform(event)

    async def test_non_string_text_raises(self) -> None:
        event = PlatformEvent(
            platform="discord",
            event_type="message",
            actor="test_user",
            payload={"text": 123},
            occurred_at="2026-01-01T00:00:00+00:00",
        )
        with bundle_context(tenant=TENANT, community=COMMUNITY, app_id=APP_ID):
            with pytest.raises(ValueError, match="text"):
                await transform(event)
