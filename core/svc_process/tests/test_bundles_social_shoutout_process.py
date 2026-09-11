"""Tests for `bundles.social_shoutout_process.transform` -- gh #316 process half.

Mirrors `test_bundles_social_music_process.py`'s shape: one `_event()`
factory, a substring-routed `_FakeDal` standing in for both
`shoutout_config` and `community_members` reads, one class per behavioral
group. `TestBotProcessFeatureModuleRegistration` at the bottom covers
`bot_process._FEATURE_MODULES` registration + real dispatch, following
that same sibling file's precedent for a bundle whose own
`test_bundles_bot_process.py` is scoped to another agent this round (see
task scope) -- only the joke-reply assertions were touched there.
"""

from __future__ import annotations

from typing import Any

import pytest
from flask_core import (
    PROCESS_TARGET_APP_ID_KEY,
    PlatformEvent,
    bundle_context,
    reset_bundle_dal_for_tests,
    set_bundle_dal,
)

from bundles.social_shoutout_process import (
    _INVALID_LOGIN_REPLY,
    _PERMISSION_DENIED_REPLY,
    _SELF_SHOUTOUT_REPLY,
    _SHOUTOUT_APP_ID,
    _SO_USAGE,
    _VSO_USAGE,
    transform,
)

TENANT = "global"
COMMUNITY = "42"
APP_ID = "waddles.bot.twitch.default"

#: Default test actor -- seeded as `moderator` in `_FakeDal` so `mod`-gated
#: tests don't have to opt into permission separately.
MOD_ACTOR = "test_user"
NON_MOD_ACTOR = "rando"
ADMIN_ACTOR = "the_owner"


def _event(
    text: str, *, actor: str | None = MOD_ACTOR, **payload_overrides: object
) -> PlatformEvent:
    """Create a test event with the given text; a channel_id + tokenized author_id by default."""
    payload: dict[str, object] = {
        "text": text,
        "channel_id": "123",
        "author_id": "platform-user-1",
        **payload_overrides,
    }
    return PlatformEvent(
        platform="twitch",
        event_type="message",
        actor=actor,
        payload=payload,
        occurred_at="2026-01-01T00:00:00+00:00",
    )


class _FakeDal:
    """Minimal `AsyncDAL` stand-in for `shoutout_config` + `community_members` reads.

    Routes by SQL substring: a `shoutout_config` query returns the seeded
    `so_permission`/`vso_permission` row (or no row at all, when
    `has_config_row=False`); everything else is the same `community_members`
    role lookup convention `test_bundles_social_music_process.py`'s own
    `_FakeDal.execute()` uses (matched by whether `platform_user_id`
    appears in the SQL text).
    """

    def __init__(
        self,
        *,
        so_permission: str = "mod",
        vso_permission: str = "mod",
        has_config_row: bool = True,
    ) -> None:
        self.so_permission = so_permission
        self.vso_permission = vso_permission
        self.has_config_row = has_config_row
        self.should_error_on_config = False
        self.should_error_on_role_lookup = False
        self.roles_by_display_name: dict[str, str] = {
            MOD_ACTOR: "moderator",
            ADMIN_ACTOR: "admin",
        }
        self.roles_by_platform_user_id: dict[str, str] = {}
        self.config_query_count = 0

    async def execute(self, sql: str, params: list[Any]) -> list[dict[str, Any]]:
        if "shoutout_config" in sql:
            self.config_query_count += 1
            if self.should_error_on_config:
                raise RuntimeError("simulated shoutout_config outage")
            if not self.has_config_row:
                return []
            return [{"so_permission": self.so_permission, "vso_permission": self.vso_permission}]

        if self.should_error_on_role_lookup:
            raise RuntimeError("simulated permission lookup outage")

        if "platform_user_id" in sql:
            _community_id, _platform, platform_user_id = params
            role = self.roles_by_platform_user_id.get(platform_user_id)
        else:
            _community_id, display_name = params
            role = self.roles_by_display_name.get(display_name)
        return [{"role": role}] if role is not None else []


@pytest.fixture(autouse=True)
def _dal() -> Any:
    """Set up a fake DAL (seeded with `MOD_ACTOR`/`ADMIN_ACTOR` roles) for all tests."""
    fake = _FakeDal()
    set_bundle_dal(fake)
    yield fake
    reset_bundle_dal_for_tests()


async def _flag_on(*_args: Any, **_kwargs: Any) -> bool:
    return True


async def _flag_off(*_args: Any, **_kwargs: Any) -> bool:
    return False


@pytest.fixture(autouse=True)
def _flag_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    """Default every test to flag ON -- the OFF-specific tests override this explicitly."""
    monkeypatch.setattr("bundles.social_shoutout_process.feature_enabled", _flag_on)


class TestTransformShoutout:
    """Valid `!so`/`!shoutout`/`!vso` parsing -- both commands, aliases, payload shape."""

    @pytest.mark.parametrize("cmd", ["!so", "!shoutout"])
    async def test_text_shoutout_aliases_produce_kind_text(self, cmd: str) -> None:
        with bundle_context(tenant=TENANT, community=COMMUNITY, app_id=APP_ID):
            result = await transform(_event(f"{cmd} clubpenguinfan"))
        assert isinstance(result, PlatformEvent)
        assert result.payload["subcommand"] == "shoutout"
        assert result.payload["kind"] == "text"
        assert result.payload["target"] == "clubpenguinfan"

    async def test_vso_produces_kind_video(self) -> None:
        with bundle_context(tenant=TENANT, community=COMMUNITY, app_id=APP_ID):
            result = await transform(_event("!vso clubpenguinfan"))
        assert isinstance(result, PlatformEvent)
        assert result.payload["kind"] == "video"
        assert result.payload["target"] == "clubpenguinfan"

    async def test_strips_leading_at_and_lowercases(self) -> None:
        with bundle_context(tenant=TENANT, community=COMMUNITY, app_id=APP_ID):
            result = await transform(_event("!so @ClubPenguinFan"))
        assert isinstance(result, PlatformEvent)
        assert result.payload["target"] == "clubpenguinfan"

    async def test_command_prefix_is_case_insensitive(self) -> None:
        with bundle_context(tenant=TENANT, community=COMMUNITY, app_id=APP_ID):
            result = await transform(_event("!SO clubpenguinfan"))
        assert isinstance(result, PlatformEvent)
        assert result.payload["target"] == "clubpenguinfan"

    async def test_sets_target_app_id_for_cross_app_routing(self) -> None:
        """Mirrors the forum/music bundles' gh #298 routing mechanism (see those bundles' tests)."""
        with bundle_context(tenant=TENANT, community=COMMUNITY, app_id=APP_ID):
            result = await transform(_event("!so clubpenguinfan"))
        assert isinstance(result, PlatformEvent)
        assert result.payload[PROCESS_TARGET_APP_ID_KEY] == _SHOUTOUT_APP_ID
        assert _SHOUTOUT_APP_ID == "waddles.bot.shoutout.default"

    async def test_preserves_tokenized_requester_identity_and_channel(self) -> None:
        with bundle_context(tenant=TENANT, community=COMMUNITY, app_id=APP_ID):
            result = await transform(_event("!so clubpenguinfan"))
        assert isinstance(result, PlatformEvent)
        assert result.payload["channel_id"] == "123"
        assert result.payload["author_id"] == "platform-user-1"
        assert result.actor == MOD_ACTOR


class TestTransformUsageHint:
    """Missing/blank target -> usage-hint reply, never a crash; no cross-app routing."""

    async def test_bare_so_returns_usage(self) -> None:
        with bundle_context(tenant=TENANT, community=COMMUNITY, app_id=APP_ID):
            result = await transform(_event("!so"))
        assert isinstance(result, PlatformEvent)
        assert result.payload["text"] == _SO_USAGE
        assert PROCESS_TARGET_APP_ID_KEY not in result.payload

    async def test_bare_shoutout_alias_also_uses_so_usage(self) -> None:
        with bundle_context(tenant=TENANT, community=COMMUNITY, app_id=APP_ID):
            result = await transform(_event("!shoutout"))
        assert isinstance(result, PlatformEvent)
        assert result.payload["text"] == _SO_USAGE

    async def test_bare_vso_returns_vso_usage(self) -> None:
        with bundle_context(tenant=TENANT, community=COMMUNITY, app_id=APP_ID):
            result = await transform(_event("!vso"))
        assert isinstance(result, PlatformEvent)
        assert result.payload["text"] == _VSO_USAGE

    async def test_whitespace_only_target_returns_usage(self) -> None:
        with bundle_context(tenant=TENANT, community=COMMUNITY, app_id=APP_ID):
            result = await transform(_event("!so      "))
        assert isinstance(result, PlatformEvent)
        assert result.payload["text"] == _SO_USAGE


class TestTransformInvalidLogin:
    """Target failing `^[a-z0-9_]{3,25}$` (post-normalization) -> invalid-login reply."""

    async def test_too_short_is_invalid(self) -> None:
        with bundle_context(tenant=TENANT, community=COMMUNITY, app_id=APP_ID):
            result = await transform(_event("!so ab"))
        assert isinstance(result, PlatformEvent)
        assert result.payload["text"] == _INVALID_LOGIN_REPLY
        assert PROCESS_TARGET_APP_ID_KEY not in result.payload

    async def test_too_long_is_invalid(self) -> None:
        with bundle_context(tenant=TENANT, community=COMMUNITY, app_id=APP_ID):
            result = await transform(_event(f"!so {'a' * 26}"))
        assert isinstance(result, PlatformEvent)
        assert result.payload["text"] == _INVALID_LOGIN_REPLY

    async def test_invalid_character_is_invalid(self) -> None:
        with bundle_context(tenant=TENANT, community=COMMUNITY, app_id=APP_ID):
            result = await transform(_event("!so club-penguin-fan"))
        assert isinstance(result, PlatformEvent)
        assert result.payload["text"] == _INVALID_LOGIN_REPLY

    async def test_minimum_length_is_valid(self) -> None:
        with bundle_context(tenant=TENANT, community=COMMUNITY, app_id=APP_ID):
            result = await transform(_event("!so abc"))
        assert isinstance(result, PlatformEvent)
        assert result.payload.get("target") == "abc"

    async def test_maximum_length_is_valid(self) -> None:
        target = "a" * 25
        with bundle_context(tenant=TENANT, community=COMMUNITY, app_id=APP_ID):
            result = await transform(_event(f"!so {target}"))
        assert isinstance(result, PlatformEvent)
        assert result.payload.get("target") == target


class TestTransformSelfShoutout:
    """`target == caller` (both normalized) -> denied regardless of permission level."""

    async def test_self_shoutout_denied(self) -> None:
        with bundle_context(tenant=TENANT, community=COMMUNITY, app_id=APP_ID):
            result = await transform(_event(f"!so {MOD_ACTOR}", actor=MOD_ACTOR))
        assert isinstance(result, PlatformEvent)
        assert result.payload["text"] == _SELF_SHOUTOUT_REPLY
        assert PROCESS_TARGET_APP_ID_KEY not in result.payload

    async def test_self_shoutout_denied_case_and_at_insensitive(self) -> None:
        with bundle_context(tenant=TENANT, community=COMMUNITY, app_id=APP_ID):
            result = await transform(_event("!so @Test_User", actor="test_user"))
        assert isinstance(result, PlatformEvent)
        assert result.payload["text"] == _SELF_SHOUTOUT_REPLY

    async def test_self_shoutout_denied_even_for_admin(self, _dal: Any) -> None:
        """Self-shoutout is a flat rule -- not overridden by an elevated role."""
        with bundle_context(tenant=TENANT, community=COMMUNITY, app_id=APP_ID):
            result = await transform(_event(f"!so {ADMIN_ACTOR}", actor=ADMIN_ACTOR))
        assert isinstance(result, PlatformEvent)
        assert result.payload["text"] == _SELF_SHOUTOUT_REPLY

    async def test_different_target_is_not_self_shoutout(self) -> None:
        with bundle_context(tenant=TENANT, community=COMMUNITY, app_id=APP_ID):
            result = await transform(_event("!so someone_else", actor=MOD_ACTOR))
        assert isinstance(result, PlatformEvent)
        assert result.payload["text"] != _SELF_SHOUTOUT_REPLY


class TestTransformPermission:
    """`shoutout_config.so_permission`/`vso_permission` gates who may shout out."""

    async def test_everyone_permission_allows_non_mod(self, _dal: Any) -> None:
        _dal.so_permission = "everyone"
        with bundle_context(tenant=TENANT, community=COMMUNITY, app_id=APP_ID):
            result = await transform(_event("!so target_user", actor=NON_MOD_ACTOR))
        assert isinstance(result, PlatformEvent)
        assert result.payload[PROCESS_TARGET_APP_ID_KEY] == _SHOUTOUT_APP_ID

    async def test_vip_permission_degrades_to_everyone(self, _dal: Any) -> None:
        """No badge data on `PlatformEvent` -- `vip` is unenforceable, degrades to always-allow."""
        _dal.so_permission = "vip"
        with bundle_context(tenant=TENANT, community=COMMUNITY, app_id=APP_ID):
            result = await transform(_event("!so target_user", actor=NON_MOD_ACTOR))
        assert isinstance(result, PlatformEvent)
        assert result.payload[PROCESS_TARGET_APP_ID_KEY] == _SHOUTOUT_APP_ID

    async def test_subscriber_permission_degrades_to_everyone(self, _dal: Any) -> None:
        _dal.vso_permission = "subscriber"
        with bundle_context(tenant=TENANT, community=COMMUNITY, app_id=APP_ID):
            result = await transform(_event("!vso target_user", actor=NON_MOD_ACTOR))
        assert isinstance(result, PlatformEvent)
        assert result.payload[PROCESS_TARGET_APP_ID_KEY] == _SHOUTOUT_APP_ID

    async def test_mod_permission_denies_non_mod(self, _dal: Any) -> None:
        _dal.so_permission = "mod"
        with bundle_context(tenant=TENANT, community=COMMUNITY, app_id=APP_ID):
            result = await transform(_event("!so target_user", actor=NON_MOD_ACTOR))
        assert isinstance(result, PlatformEvent)
        assert result.payload["text"] == _PERMISSION_DENIED_REPLY
        assert PROCESS_TARGET_APP_ID_KEY not in result.payload

    async def test_mod_permission_allows_moderator(self, _dal: Any) -> None:
        _dal.so_permission = "mod"
        with bundle_context(tenant=TENANT, community=COMMUNITY, app_id=APP_ID):
            result = await transform(_event("!so target_user", actor=MOD_ACTOR))
        assert isinstance(result, PlatformEvent)
        assert result.payload[PROCESS_TARGET_APP_ID_KEY] == _SHOUTOUT_APP_ID

    async def test_admin_only_permission_denies_moderator(self, _dal: Any) -> None:
        """`admin_only` is a stricter tier than `mod` -- a plain moderator is still denied."""
        _dal.so_permission = "admin_only"
        with bundle_context(tenant=TENANT, community=COMMUNITY, app_id=APP_ID):
            result = await transform(_event("!so target_user", actor=MOD_ACTOR))
        assert isinstance(result, PlatformEvent)
        assert result.payload["text"] == _PERMISSION_DENIED_REPLY

    async def test_admin_only_permission_allows_admin(self, _dal: Any) -> None:
        _dal.so_permission = "admin_only"
        with bundle_context(tenant=TENANT, community=COMMUNITY, app_id=APP_ID):
            result = await transform(_event("!so target_user", actor=ADMIN_ACTOR))
        assert isinstance(result, PlatformEvent)
        assert result.payload[PROCESS_TARGET_APP_ID_KEY] == _SHOUTOUT_APP_ID

    async def test_unknown_permission_value_falls_back_to_mod_threshold(self, _dal: Any) -> None:
        _dal.so_permission = "some_future_tier"
        with bundle_context(tenant=TENANT, community=COMMUNITY, app_id=APP_ID):
            denied = await transform(_event("!so target_user", actor=NON_MOD_ACTOR))
            allowed = await transform(_event("!so target_user", actor=MOD_ACTOR))
        assert isinstance(denied, PlatformEvent)
        assert denied.payload["text"] == _PERMISSION_DENIED_REPLY
        assert isinstance(allowed, PlatformEvent)
        assert allowed.payload[PROCESS_TARGET_APP_ID_KEY] == _SHOUTOUT_APP_ID

    async def test_missing_config_row_defaults_to_mod(self, _dal: Any) -> None:
        _dal.has_config_row = False
        with bundle_context(tenant=TENANT, community=COMMUNITY, app_id=APP_ID):
            denied = await transform(_event("!so target_user", actor=NON_MOD_ACTOR))
            allowed = await transform(_event("!so target_user", actor=MOD_ACTOR))
        assert isinstance(denied, PlatformEvent)
        assert denied.payload["text"] == _PERMISSION_DENIED_REPLY
        assert isinstance(allowed, PlatformEvent)
        assert allowed.payload[PROCESS_TARGET_APP_ID_KEY] == _SHOUTOUT_APP_ID

    async def test_config_lookup_error_defaults_to_mod(self, _dal: Any) -> None:
        _dal.should_error_on_config = True
        with bundle_context(tenant=TENANT, community=COMMUNITY, app_id=APP_ID):
            result = await transform(_event("!so target_user", actor=NON_MOD_ACTOR))
        assert isinstance(result, PlatformEvent)
        assert result.payload["text"] == _PERMISSION_DENIED_REPLY

    async def test_role_lookup_error_fails_closed(self, _dal: Any) -> None:
        _dal.should_error_on_role_lookup = True
        with bundle_context(tenant=TENANT, community=COMMUNITY, app_id=APP_ID):
            result = await transform(_event("!so target_user", actor=MOD_ACTOR))
        assert isinstance(result, PlatformEvent)
        assert result.payload["text"] == _PERMISSION_DENIED_REPLY

    async def test_allowed_by_platform_user_id_match(self, _dal: Any) -> None:
        _dal.roles_by_platform_user_id["platform-user-1"] = "admin"
        with bundle_context(tenant=TENANT, community=COMMUNITY, app_id=APP_ID):
            result = await transform(_event("!so target_user", actor=NON_MOD_ACTOR))
        assert isinstance(result, PlatformEvent)
        assert result.payload[PROCESS_TARGET_APP_ID_KEY] == _SHOUTOUT_APP_ID

    async def test_no_community_defaults_to_mod_and_denies_by_default(self) -> None:
        """A tenant-wide envelope (`community=None`) has no config/role to read -- fails closed."""
        with bundle_context(tenant=TENANT, community=None, app_id=APP_ID):
            result = await transform(_event("!so target_user", actor=NON_MOD_ACTOR))
        assert isinstance(result, PlatformEvent)
        assert result.payload["text"] == _PERMISSION_DENIED_REPLY


class TestTransformFeatureFlag:
    """Flag OFF (or a flag/license outage, which `feature_enabled` itself degrades) -> `None`."""

    @pytest.mark.parametrize("cmd", ["!so", "!shoutout", "!vso"])
    async def test_flag_off_returns_none(self, cmd: str, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("bundles.social_shoutout_process.feature_enabled", _flag_off)
        with bundle_context(tenant=TENANT, community=COMMUNITY, app_id=APP_ID):
            assert await transform(_event(f"{cmd} clubpenguinfan")) is None

    async def test_flag_off_still_ignores_non_matching_messages(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr("bundles.social_shoutout_process.feature_enabled", _flag_off)
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

        monkeypatch.setattr("bundles.social_shoutout_process.feature_enabled", _capture)
        with bundle_context(tenant=TENANT, community=COMMUNITY, app_id=APP_ID):
            await transform(_event("!so clubpenguinfan"))

        assert captured["flag_key"] == "waddles.bot.shoutout"
        assert captured["tenant"] == TENANT
        assert captured["community"] == 42
        assert captured["default"] is True


class TestTransformNonMatchingMessages:
    """Anything not `!so`/`!shoutout`/`!vso` returns `None` -- no echo."""

    async def test_ordinary_chatter_returns_none(self) -> None:
        with bundle_context(tenant=TENANT, community=COMMUNITY, app_id=APP_ID):
            assert await transform(_event("hello everyone")) is None

    async def test_other_commands_return_none(self) -> None:
        with bundle_context(tenant=TENANT, community=COMMUNITY, app_id=APP_ID):
            assert await transform(_event("!forum create x | y")) is None
            assert await transform(_event("!sr some song")) is None
            assert await transform(_event("!ping")) is None

    async def test_word_boundary_prevents_partial_match(self) -> None:
        """`!sox`/`!vsox` must not be treated as `!so`/`!vso` with a mangled arg."""
        with bundle_context(tenant=TENANT, community=COMMUNITY, app_id=APP_ID):
            assert await transform(_event("!sox something")) is None
            assert await transform(_event("!vsox something")) is None

    async def test_empty_text_returns_none(self) -> None:
        with bundle_context(tenant=TENANT, community=COMMUNITY, app_id=APP_ID):
            assert await transform(_event("")) is None
            assert await transform(_event("   ")) is None


class TestTransformErrorHandling:
    """Missing/non-string `text` raises -- caught per-event by the process runner."""

    async def test_missing_text_field_raises(self) -> None:
        event = PlatformEvent(
            platform="twitch",
            event_type="message",
            actor=MOD_ACTOR,
            payload={},
            occurred_at="2026-01-01T00:00:00+00:00",
        )
        with bundle_context(tenant=TENANT, community=COMMUNITY, app_id=APP_ID):
            with pytest.raises(ValueError, match="text"):
                await transform(event)

    async def test_non_string_text_raises(self) -> None:
        event = PlatformEvent(
            platform="twitch",
            event_type="message",
            actor=MOD_ACTOR,
            payload={"text": 123},
            occurred_at="2026-01-01T00:00:00+00:00",
        )
        with bundle_context(tenant=TENANT, community=COMMUNITY, app_id=APP_ID):
            with pytest.raises(ValueError, match="text"):
                await transform(event)


class TestBotProcessFeatureModuleRegistration:
    """`so`/`shoutout`/`vso` register onto this module in `bot_process._FEATURE_MODULES`.

    `test_bundles_bot_process.py` is scoped to another agent this round
    (see task scope) -- only its joke-reply assertions were removed there;
    the registration/dispatch assertion lives here instead, mirroring
    `test_bundles_social_music_process.py::TestBotProcessFeatureModuleRegistration`'s
    identical precedent for `sq`/`songqueue`.
    """

    def test_so_shoutout_vso_registered_to_this_module(self) -> None:
        import bundles.bot_process as bot_process

        assert bot_process._FEATURE_MODULES["so"] == "bundles.social_shoutout_process"
        assert bot_process._FEATURE_MODULES["shoutout"] == "bundles.social_shoutout_process"
        assert bot_process._FEATURE_MODULES["vso"] == "bundles.social_shoutout_process"

    def test_so_and_shoutout_are_no_longer_bot_builtins(self) -> None:
        """The old hardcoded joke branch is gone -- feature dispatch owns these words now."""
        import bundles.bot_process as bot_process

        assert "so" not in bot_process._BOT_COMMANDS
        assert "shoutout" not in bot_process._BOT_COMMANDS

    async def test_so_dispatches_through_bot_process_router(self) -> None:
        """`!so` routes through `bot_process.transform` to this bundle, not the removed joke."""
        import bundles.bot_process as bot_process

        with bundle_context(tenant=TENANT, community=COMMUNITY, app_id=APP_ID):
            result = await bot_process.transform(_event("!so clubpenguinfan"))
        assert isinstance(result, PlatformEvent)
        assert result.payload["target"] == "clubpenguinfan"
        assert result.payload[PROCESS_TARGET_APP_ID_KEY] == _SHOUTOUT_APP_ID
