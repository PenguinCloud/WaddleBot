"""Tests for `bundles.community_loyalty_process.transform`."""

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

from bundles.community_loyalty_process import (
    _LOYALTY_APP_ID,
    _PERMISSION_DENIED_REPLY,
    _POINTS_USAGE_REPLY,
    _REDEEM_USAGE_REPLY,
    transform,
)

TENANT = "global"
COMMUNITY = "42"
APP_ID = "waddles.bot.discord.default"

MOD_ACTOR = "test_mod"
NON_MOD_ACTOR = "rando"


def _event(text: str, *, actor: str = MOD_ACTOR, **payload_overrides: object) -> PlatformEvent:
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
        actor=actor,
        payload=payload,
        occurred_at="2026-01-01T00:00:00+00:00",
    )


class _FakeDal:
    """Minimal `AsyncDAL` stand-in -- answers `_caller_is_moderator_or_admin`'s raw `execute()`.

    Same shape as `social_music_process`'s own test `_FakeDal.execute()`.
    """

    def __init__(self) -> None:
        self.should_error_on_role_lookup = False
        self.roles_by_display_name: dict[str, str] = {MOD_ACTOR: "moderator"}
        self.roles_by_platform_user_id: dict[str, str] = {}
        self._execute_count = 0

    async def execute(self, sql: str, params: list[Any]) -> list[dict[str, Any]]:
        self._execute_count += 1
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
    """Set up a fake DAL (seeded with `MOD_ACTOR` as moderator) for all tests."""
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
    monkeypatch.setattr("bundles.community_loyalty_process.feature_enabled", _flag_on)


async def _transform(text: str, *, actor: str = MOD_ACTOR) -> PlatformEvent | None:
    with bundle_context(tenant=TENANT, community=COMMUNITY, app_id=APP_ID):
        return await transform(_event(text, actor=actor))


class TestNotThisBundlesCommand:
    """Text that isn't `!points`/`!top`/`!shop`/`!redeem` -- always `None`."""

    async def test_non_command_text_returns_none(self) -> None:
        assert await _transform("just chatting") is None

    async def test_unrelated_command_returns_none(self) -> None:
        assert await _transform("!quote add something") is None

    async def test_bare_bang_returns_none(self) -> None:
        assert await _transform("!") is None

    async def test_missing_text_field_raises(self) -> None:
        with bundle_context(tenant=TENANT, community=COMMUNITY, app_id=APP_ID):
            with pytest.raises(ValueError, match="text"):
                await transform(
                    PlatformEvent(
                        platform="discord",
                        event_type="message",
                        actor=MOD_ACTOR,
                        payload={"channel_id": "123"},
                        occurred_at="2026-01-01T00:00:00+00:00",
                    )
                )


class TestFlagGating:
    """Flag OFF -- every one of this bundle's commands behaves like unrecognized (no reply)."""

    async def test_points_no_reply_when_flag_off(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("bundles.community_loyalty_process.feature_enabled", _flag_off)
        assert await _transform("!points") is None

    async def test_top_no_reply_when_flag_off(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("bundles.community_loyalty_process.feature_enabled", _flag_off)
        assert await _transform("!top") is None

    async def test_shop_no_reply_when_flag_off(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("bundles.community_loyalty_process.feature_enabled", _flag_off)
        assert await _transform("!shop") is None

    async def test_redeem_no_reply_when_flag_off(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("bundles.community_loyalty_process.feature_enabled", _flag_off)
        assert await _transform("!redeem sku1") is None


class TestPointsOwnBalance:
    """`!points` with no arguments -- own balance, no permission check needed."""

    async def test_routes_to_action_with_balance_subcommand(self) -> None:
        result = await _transform("!points", actor=NON_MOD_ACTOR)
        assert isinstance(result, PlatformEvent)
        assert result.payload["subcommand"] == "balance"
        assert "target" not in result.payload
        assert result.payload[PROCESS_TARGET_APP_ID_KEY] == _LOYALTY_APP_ID

    async def test_preserves_other_payload_fields(self) -> None:
        result = await _transform("!points")
        assert isinstance(result, PlatformEvent)
        assert result.payload["channel_id"] == "123"
        assert result.payload["author_id"] == "platform-user-1"


class TestPointsViewOther:
    """`!points <user>` / `!points @user` -- moderator/admin only."""

    async def test_mod_can_view_plain_username(self) -> None:
        result = await _transform("!points someone")
        assert isinstance(result, PlatformEvent)
        assert result.payload["subcommand"] == "balance"
        assert result.payload["target"] == "someone"

    async def test_mod_can_view_at_mention_strips_at(self) -> None:
        result = await _transform("!points @someone")
        assert isinstance(result, PlatformEvent)
        assert result.payload["target"] == "someone"

    async def test_trailing_tokens_ignored(self) -> None:
        result = await _transform("!points someone else")
        assert isinstance(result, PlatformEvent)
        assert result.payload["target"] == "someone"

    async def test_non_mod_denied(self) -> None:
        result = await _transform("!points someone", actor=NON_MOD_ACTOR)
        assert isinstance(result, PlatformEvent)
        assert result.payload["text"] == _PERMISSION_DENIED_REPLY
        assert PROCESS_TARGET_APP_ID_KEY not in result.payload


class TestPointsAdjust:
    """`!points add|remove <user> <n>` -- moderator/admin only, `n` in `[1, 1_000_000]`."""

    async def test_add_routes_to_action_with_positive_delta(self) -> None:
        result = await _transform("!points add someone 50")
        assert isinstance(result, PlatformEvent)
        assert result.payload["subcommand"] == "adjust"
        assert result.payload["target"] == "someone"
        assert result.payload["delta"] == 50

    async def test_remove_routes_to_action_with_negative_delta(self) -> None:
        result = await _transform("!points remove someone 50")
        assert isinstance(result, PlatformEvent)
        assert result.payload["subcommand"] == "adjust"
        assert result.payload["delta"] == -50

    async def test_at_mention_target_strips_at(self) -> None:
        result = await _transform("!points add @someone 10")
        assert isinstance(result, PlatformEvent)
        assert result.payload["target"] == "someone"

    async def test_case_insensitive_action_word(self) -> None:
        result = await _transform("!points ADD someone 10")
        assert isinstance(result, PlatformEvent)
        assert result.payload["subcommand"] == "adjust"
        assert result.payload["delta"] == 10

    async def test_boundary_min_amount_accepted(self) -> None:
        result = await _transform("!points add someone 1")
        assert isinstance(result, PlatformEvent)
        assert result.payload["delta"] == 1

    async def test_boundary_max_amount_accepted(self) -> None:
        result = await _transform("!points add someone 1000000")
        assert isinstance(result, PlatformEvent)
        assert result.payload["delta"] == 1000000

    async def test_non_mod_denied(self) -> None:
        result = await _transform("!points add someone 50", actor=NON_MOD_ACTOR)
        assert isinstance(result, PlatformEvent)
        assert result.payload["text"] == _PERMISSION_DENIED_REPLY
        assert PROCESS_TARGET_APP_ID_KEY not in result.payload

    async def test_missing_amount_usage_reply(self) -> None:
        result = await _transform("!points add someone")
        assert isinstance(result, PlatformEvent)
        assert result.payload["text"] == _POINTS_USAGE_REPLY

    async def test_missing_user_and_amount_usage_reply(self) -> None:
        result = await _transform("!points add")
        assert isinstance(result, PlatformEvent)
        assert result.payload["text"] == _POINTS_USAGE_REPLY

    async def test_non_numeric_amount_usage_reply(self) -> None:
        result = await _transform("!points add someone abc")
        assert isinstance(result, PlatformEvent)
        assert result.payload["text"] == _POINTS_USAGE_REPLY

    async def test_zero_amount_out_of_range_usage_reply(self) -> None:
        result = await _transform("!points add someone 0")
        assert isinstance(result, PlatformEvent)
        assert result.payload["text"] == _POINTS_USAGE_REPLY

    async def test_over_max_amount_usage_reply(self) -> None:
        result = await _transform("!points add someone 1000001")
        assert isinstance(result, PlatformEvent)
        assert result.payload["text"] == _POINTS_USAGE_REPLY

    async def test_negative_amount_usage_reply(self) -> None:
        result = await _transform("!points add someone -5")
        assert isinstance(result, PlatformEvent)
        assert result.payload["text"] == _POINTS_USAGE_REPLY

    async def test_usage_reply_checked_before_permission_for_malformed_command(self) -> None:
        """A non-mod's malformed `add` (missing amount) still gets the usage reply.

        Order documented in `_handle_points_adjust`: shape check first,
        THEN permission -- an incomplete command never leaks whether the
        caller would have been denied.
        """
        result = await _transform("!points add someone", actor=NON_MOD_ACTOR)
        assert isinstance(result, PlatformEvent)
        assert result.payload["text"] == _POINTS_USAGE_REPLY


class TestTop:
    """`!top` -- no permission required."""

    async def test_routes_to_action_with_top_subcommand(self) -> None:
        result = await _transform("!top", actor=NON_MOD_ACTOR)
        assert isinstance(result, PlatformEvent)
        assert result.payload["subcommand"] == "top"
        assert result.payload[PROCESS_TARGET_APP_ID_KEY] == _LOYALTY_APP_ID

    async def test_trailing_text_ignored(self) -> None:
        result = await _transform("!top anything")
        assert isinstance(result, PlatformEvent)
        assert result.payload["subcommand"] == "top"


class TestShop:
    """`!shop` -- no permission required."""

    async def test_routes_to_action_with_shop_subcommand(self) -> None:
        result = await _transform("!shop", actor=NON_MOD_ACTOR)
        assert isinstance(result, PlatformEvent)
        assert result.payload["subcommand"] == "shop"
        assert result.payload[PROCESS_TARGET_APP_ID_KEY] == _LOYALTY_APP_ID


class TestRedeem:
    """`!redeem <sku>` -- own points, no permission gate."""

    async def test_routes_to_action_with_sku(self) -> None:
        result = await _transform("!redeem cool-hat", actor=NON_MOD_ACTOR)
        assert isinstance(result, PlatformEvent)
        assert result.payload["subcommand"] == "redeem"
        assert result.payload["sku"] == "cool-hat"
        assert result.payload[PROCESS_TARGET_APP_ID_KEY] == _LOYALTY_APP_ID

    async def test_trailing_tokens_ignored(self) -> None:
        result = await _transform("!redeem cool-hat now please")
        assert isinstance(result, PlatformEvent)
        assert result.payload["sku"] == "cool-hat"

    async def test_missing_sku_usage_reply(self) -> None:
        result = await _transform("!redeem")
        assert isinstance(result, PlatformEvent)
        assert result.payload["text"] == _REDEEM_USAGE_REPLY
        assert PROCESS_TARGET_APP_ID_KEY not in result.payload


class TestPermissionCheckFailsClosed:
    """A DB error during the moderator lookup must deny, never raise or crash the bundle."""

    async def test_role_lookup_error_denies_view(self, _dal: Any) -> None:
        _dal.should_error_on_role_lookup = True
        result = await _transform("!points someone")
        assert isinstance(result, PlatformEvent)
        assert result.payload["text"] == _PERMISSION_DENIED_REPLY

    async def test_role_lookup_error_denies_adjust(self, _dal: Any) -> None:
        _dal.should_error_on_role_lookup = True
        result = await _transform("!points add someone 10")
        assert isinstance(result, PlatformEvent)
        assert result.payload["text"] == _PERMISSION_DENIED_REPLY

    async def test_unresolvable_community_denies(self, _dal: Any) -> None:
        with bundle_context(tenant=TENANT, community=None, app_id=APP_ID):
            result = await transform(_event("!points someone"))
        assert isinstance(result, PlatformEvent)
        assert result.payload["text"] == _PERMISSION_DENIED_REPLY

    async def test_platform_user_id_match_takes_priority(self, _dal: Any) -> None:
        """A `platform_user_id` role match wins even if `display_name` isn't seeded."""
        _dal.roles_by_platform_user_id["platform-user-1"] = "moderator"
        _dal.roles_by_display_name.clear()
        result = await _transform("!points someone", actor="totally-unseeded-actor")
        assert isinstance(result, PlatformEvent)
        assert result.payload["target"] == "someone"
