"""Tests for `bundles.social_alias_process.transform` -- alias set/list/remove/invoke."""

from __future__ import annotations

import re
from typing import Any

import pytest
from flask_core import PlatformEvent, bundle_context, reset_bundle_dal_for_tests, set_bundle_dal

import bundles.social_alias_process as social_alias_process
import services.command_alias_store as command_alias_store_module
from bundles.social_alias_process import (
    _ALIAS_USAGE,
    _COMMUNITY_REQUIRED_MSG,
    _NO_ALIASES_MSG,
    _PERMISSION_DENIED_MSG,
    transform,
)

TENANT = "acme"
COMMUNITY = "1"
COMMUNITY_2 = "2"
APP_ID = "waddles.social.alias.default"

#: Default test actor -- seeded as `moderator` in `_FakeDal` so ordinary
#: set/list/remove tests don't have to opt into permission separately;
#: dedicated `TestPermissions` tests use a non-privileged actor instead.
MOD_ACTOR = "penguin"
NON_MOD_ACTOR = "rando"


def _event(
    text: str, *, actor: str | None = MOD_ACTOR, **payload_overrides: object
) -> PlatformEvent:
    payload: dict[str, object] = {
        "text": text,
        "channel_id": "chan-123",
        **payload_overrides,
    }
    return PlatformEvent(
        platform="discord",
        event_type="message",
        actor=actor,
        payload=payload,
        occurred_at="2026-01-01T00:00:00+00:00",
    )


class _FakeRow:
    """Mock row object that supports both dict and attribute access."""

    def __init__(self, data: dict[str, Any]) -> None:
        self._data = data

    def __getitem__(self, key: str) -> Any:
        return self._data[key]

    def __getattr__(self, name: str) -> Any:
        if name.startswith("_"):
            return object.__getattribute__(self, name)
        if name in self._data:
            return self._data[name]
        raise AttributeError(f"Row has no attribute {name}")

    def __repr__(self) -> str:
        return f"_FakeRow({self._data})"


class _FakeDal:
    """In-memory stand-in for `AsyncDAL` -- pydal-style `command_aliases` + raw `execute()`.

    `command_aliases` mirrors the original mock (`.select()`/`.update()`/
    `.insert_async()`, generic over `community_id` so cross-community
    isolation can be exercised). `execute()` is new: it answers the
    `community_members.role` lookup `_caller_is_moderator_or_admin` issues,
    same shape as `community_reputation_process`'s own `_FakeDal.execute()`.
    """

    def __init__(self) -> None:
        self.command_aliases = _FakeTable()
        self.should_error = False
        self.error_message = "Test error"
        self.should_error_on_role_lookup = False
        self._aliases: dict[int, dict[str, Any]] = {
            1: {
                "id": 1,
                "community_id": 1,
                "alias": "greet",
                "target_command": "hello {user} {args}",
                "usage_count": 5,
                "deleted_at": None,
                "created_by": "penguin",
            },
        }
        self._next_id = 2
        self.roles_by_display_name: dict[str, str] = {MOD_ACTOR: "moderator"}
        self.roles_by_platform_user_id: dict[str, str] = {}
        self._last_query: Any = None
        self._select_count = 0
        self._execute_count = 0

    def select(self, query: Any) -> _FakeRows:
        if self.should_error:
            raise Exception(self.error_message)

        self._last_query = query
        self._select_count += 1
        query_str = str(query) if not isinstance(query, str) else query

        community_match = re.search(r"community_id=(\d+)", query_str)
        query_community_id = int(community_match.group(1)) if community_match else None

        alias_match = re.search(r"alias=([\w-]+)", query_str)
        query_alias_name = alias_match.group(1) if alias_match else None

        require_undeleted = "IS NULL" in query_str

        results = []
        for alias in self._aliases.values():
            if query_community_id is not None and alias.get("community_id") != query_community_id:
                continue
            if query_alias_name is not None and alias.get("alias") != query_alias_name:
                continue
            if require_undeleted and alias.get("deleted_at") is not None:
                continue
            results.append(_FakeRow(alias))
        return _FakeRows(results)

    def update(self, query: Any, **kwargs: object) -> None:
        if self.should_error:
            raise Exception(self.error_message)

        query_str = str(query) if not isinstance(query, str) else query
        id_match = re.search(r"\bid=(\d+)", query_str)
        if id_match:
            alias_id = int(id_match.group(1))
            if alias_id in self._aliases:
                self._aliases[alias_id].update(kwargs)

    def insert_async(self, table: Any, **kwargs: object) -> None:
        if self.should_error:
            raise Exception(self.error_message)

        new_id = self._next_id
        self._next_id += 1
        self._aliases[new_id] = {"id": new_id, "deleted_at": None, "usage_count": 0, **kwargs}

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


class _FakeTable:
    """Mock table object."""

    def __init__(self) -> None:
        self.community_id = _FakeColumn("community_id")
        self.alias = _FakeColumn("alias")
        self.deleted_at = _FakeColumn("deleted_at")
        self.id = _FakeColumn("id")
        self.usage_count = _FakeColumn("usage_count")

    def __and__(self, other: Any) -> Any:
        if isinstance(other, _FakeQuery):
            return other
        return other


class _FakeColumn:
    """Mock column object for queries."""

    def __init__(self, name: str) -> None:
        self.name = name

    def __eq__(self, other: Any) -> Any:
        return _FakeQuery(f"{self.name}={other}")

    def __and__(self, other: Any) -> Any:
        return _FakeQuery(f"{self.name} AND {other}")

    def is_null(self) -> Any:
        return _FakeQuery(f"{self.name} IS NULL")


class _FakeQuery:
    """Mock query object that can be combined with & operator."""

    def __init__(self, expr: str) -> None:
        self.expr = expr

    def __and__(self, other: Any) -> _FakeQuery:
        if isinstance(other, _FakeQuery):
            return _FakeQuery(f"({self.expr}) AND ({other.expr})")
        return _FakeQuery(f"({self.expr}) AND {other}")

    def __str__(self) -> str:
        return self.expr


class _FakeRows:
    """Mock rows collection."""

    def __init__(self, rows: list[Any]) -> None:
        self.rows = [r for r in rows if r is not None]

    def __bool__(self) -> bool:
        return len(self.rows) > 0

    def __iter__(self) -> Any:
        return iter(self.rows)

    def first(self) -> Any:
        return self.rows[0] if self.rows else None


async def _flag_on(*_args: Any, **_kwargs: Any) -> bool:
    return True


@pytest.fixture(autouse=True)
def _flag_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    """Default every test to flag ON -- `TestFeatureFlag` overrides this explicitly.

    Mocked (not exercising the real entitlement client) so the suite never
    depends on PostHog/license-server reachability, matching
    `community_context_process`'s own test convention.
    """
    monkeypatch.setattr(social_alias_process, "feature_enabled", _flag_on)


@pytest.fixture(autouse=True)
def _dal() -> Any:
    """Set up fake DAL for all tests."""
    fake = _FakeDal()
    set_bundle_dal(fake)
    yield fake
    reset_bundle_dal_for_tests()


@pytest.fixture(autouse=True)
def _invalidate_calls(monkeypatch: pytest.MonkeyPatch) -> list[tuple[int, str]]:
    """Stub `services.command_alias_store.invalidate_alias` -- writes must never hit real Redis."""
    calls: list[tuple[int, str]] = []

    async def _fake_invalidate(*, community_id: int, alias: str, redis_client: Any = None) -> None:
        calls.append((community_id, alias))

    monkeypatch.setattr(command_alias_store_module, "invalidate_alias", _fake_invalidate)
    return calls


async def _run(
    text: str,
    *,
    community: str | None = COMMUNITY,
    actor: str | None = MOD_ACTOR,
    **overrides: object,
) -> PlatformEvent | None:
    with bundle_context(tenant=TENANT, community=community, app_id=APP_ID):
        return await transform(_event(text, actor=actor, **overrides))


class TestFeatureFlag:
    async def test_flag_off_returns_none_no_reply(
        self, monkeypatch: pytest.MonkeyPatch, _dal: _FakeDal
    ) -> None:
        async def _flag_off(*_a: Any, **_kw: Any) -> bool:
            return False

        monkeypatch.setattr(social_alias_process, "feature_enabled", _flag_off)
        result = await _run("!alias list")
        assert result is None
        assert _dal._select_count == 0


class TestRoutingAndMalformedEvents:
    async def test_non_command_chatter_returns_none(self) -> None:
        assert await _run("just chatting") is None

    async def test_command_without_bang_returns_none(self) -> None:
        assert await _run("greet penguin") is None

    async def test_missing_text_raises(self) -> None:
        event = PlatformEvent(
            platform="discord", event_type="message", actor=None, payload={}, occurred_at="x"
        )
        with bundle_context(tenant=TENANT, community=COMMUNITY, app_id=APP_ID):
            with pytest.raises(ValueError, match="text"):
                await transform(event)

    async def test_empty_text_raises(self) -> None:
        event = PlatformEvent(
            platform="discord",
            event_type="message",
            actor=None,
            payload={"text": ""},
            occurred_at="x",
        )
        with bundle_context(tenant=TENANT, community=COMMUNITY, app_id=APP_ID):
            with pytest.raises(ValueError, match="text"):
                await transform(event)

    async def test_text_is_not_string_raises(self) -> None:
        event = PlatformEvent(
            platform="discord",
            event_type="message",
            actor=None,
            payload={"text": 123},
            occurred_at="x",
        )
        with bundle_context(tenant=TENANT, community=COMMUNITY, app_id=APP_ID):
            with pytest.raises(ValueError, match="text"):
                await transform(event)

    async def test_whitespace_only_text_raises(self) -> None:
        event = PlatformEvent(
            platform="discord",
            event_type="message",
            actor=None,
            payload={"text": "   "},
            occurred_at="x",
        )
        with bundle_context(tenant=TENANT, community=COMMUNITY, app_id=APP_ID):
            with pytest.raises(ValueError, match="text"):
                await transform(event)


class TestList:
    async def test_bare_alias_lists(self) -> None:
        result = await _run("!alias")
        assert result is not None
        assert result.payload["text"] == "aliases: !greet → !hello {user} {args}"

    async def test_alias_list_word_lists(self) -> None:
        result = await _run("!alias list")
        assert result is not None
        assert result.payload["text"] == "aliases: !greet → !hello {user} {args}"

    async def test_list_case_insensitive(self) -> None:
        result = await _run("!ALIAS LIST")
        assert result is not None
        assert result.payload["text"] == "aliases: !greet → !hello {user} {args}"

    async def test_list_empty_returns_no_aliases_message(self, _dal: _FakeDal) -> None:
        _dal._aliases = {}
        result = await _run("!alias list")
        assert result is not None
        assert result.payload["text"] == _NO_ALIASES_MSG

    async def test_list_sorted_and_truncated_past_15(self, _dal: _FakeDal) -> None:
        _dal._aliases = {
            i: {
                "id": i,
                "community_id": 1,
                "alias": f"a{i:02d}",
                "target_command": "ping",
                "deleted_at": None,
                "usage_count": 0,
            }
            for i in range(20)
        }
        result = await _run("!alias list")
        assert result is not None
        text = result.payload["text"]
        assert text.startswith("aliases: !a00 → !ping, !a01 → !ping")
        assert text.endswith("…and 5 more")

    async def test_list_without_community_returns_guard(self, _dal: _FakeDal) -> None:
        result = await _run("!alias list", community=None)
        assert result is not None
        assert result.payload["text"] == _COMMUNITY_REQUIRED_MSG
        assert _dal._select_count == 0

    async def test_list_handles_db_error(self, _dal: _FakeDal) -> None:
        _dal.should_error = True
        result = await _run("!alias list")
        assert result is not None
        assert "Failed to list aliases" in result.payload["text"]


class TestSetAlias:
    async def test_positional_set_success(
        self, _dal: _FakeDal, _invalidate_calls: list[Any]
    ) -> None:
        result = await _run("!alias newcmd echo hi there")
        assert result is not None
        assert result.payload["text"] == "alias set: !newcmd → !echo hi there"
        assert _invalidate_calls == [(1, "newcmd")]

    async def test_add_synonym_success(self, _dal: _FakeDal) -> None:
        result = await _run("!alias add newcmd echo hi there")
        assert result is not None
        assert result.payload["text"] == "alias set: !newcmd → !echo hi there"

    async def test_set_lowercases_name(self, _dal: _FakeDal) -> None:
        result = await _run("!alias NewCmd echo hi")
        assert result is not None
        assert result.payload["text"] == "alias set: !newcmd → !echo hi"

    async def test_set_overwrites_existing_active_alias(self, _dal: _FakeDal) -> None:
        result = await _run("!alias greet echo hi")
        assert result is not None
        assert result.payload["text"] == "alias set: !greet → !echo hi"
        assert _dal._aliases[1]["target_command"] == "echo hi"

    async def test_set_revives_soft_deleted_alias(self, _dal: _FakeDal) -> None:
        _dal._aliases[1]["deleted_at"] = "2026-01-01T00:00:00+00:00"
        result = await _run("!alias greet echo hi")
        assert result is not None
        assert result.payload["text"] == "alias set: !greet → !echo hi"
        assert _dal._aliases[1]["deleted_at"] is None

    async def test_missing_args_add_only_returns_usage(self) -> None:
        result = await _run("!alias add")
        assert result is not None
        assert result.payload["text"] == _ALIAS_USAGE

    async def test_missing_expansion_positional_returns_usage(self) -> None:
        result = await _run("!alias newcmd")
        assert result is not None
        assert result.payload["text"] == _ALIAS_USAGE

    async def test_missing_expansion_add_returns_usage(self) -> None:
        result = await _run("!alias add newcmd")
        assert result is not None
        assert result.payload["text"] == _ALIAS_USAGE

    async def test_invalid_name_rejected(self) -> None:
        result = await _run("!alias greet@me echo hi")
        assert result is not None
        assert "alias names are letters, numbers, - and _ (max 32)" in result.payload["text"]

    async def test_name_allows_hyphen_and_underscore(self, _dal: _FakeDal) -> None:
        result = await _run("!alias my-new_cmd echo hi")
        assert result is not None
        assert result.payload["text"] == "alias set: !my-new_cmd → !echo hi"

    async def test_name_too_long_rejected(self) -> None:
        long_name = "a" * 33
        result = await _run(f"!alias {long_name} echo hi")
        assert result is not None
        assert "alias names are letters, numbers, - and _ (max 32)" in result.payload["text"]

    async def test_name_at_max_length_accepted(self, _dal: _FakeDal) -> None:
        max_name = "a" * 32
        result = await _run(f"!alias {max_name} echo hi")
        assert result is not None
        assert result.payload["text"] == f"alias set: !{max_name} → !echo hi"

    async def test_name_equal_to_bot_command_rejected(self) -> None:
        result = await _run("!alias ping echo hi")
        assert result is not None
        assert result.payload["text"] == "!ping is a built-in command and can't be aliased"

    async def test_name_equal_to_feature_command_rejected(self) -> None:
        result = await _run("!alias poll echo hi")
        assert result is not None
        assert result.payload["text"] == "!poll is a built-in command and can't be aliased"

    async def test_expansion_starting_with_alias_rejected(self) -> None:
        result = await _run("!alias newcmd alias list")
        assert result is not None
        assert result.payload["text"] == "an alias can't run !alias"

    async def test_expansion_starting_with_unalias_rejected(self) -> None:
        result = await _run("!alias newcmd unalias greet")
        assert result is not None
        assert result.payload["text"] == "an alias can't run !alias"

    async def test_expansion_unknown_command_rejected(self) -> None:
        result = await _run("!alias newcmd totallymadeupword foo")
        assert result is not None
        assert result.payload["text"] == "unknown command: totallymadeupword"

    async def test_expansion_flattens_existing_alias(self, _dal: _FakeDal) -> None:
        result = await _run("!alias b greet extra")
        assert result is not None
        assert result.payload["text"] == "alias set: !b → !hello {user} {args} extra"

    async def test_expansion_flattens_existing_alias_no_trailing_args(self, _dal: _FakeDal) -> None:
        """`!alias b greet` (no trailing args) flattens to `greet`'s own target verbatim."""
        result = await _run("!alias b greet")
        assert result is not None
        assert result.payload["text"] == "alias set: !b → !hello {user} {args}"

    async def test_expansion_too_long_rejected(self) -> None:
        long_expansion = "echo " + ("a" * 250)
        result = await _run(f"!alias newcmd {long_expansion}")
        assert result is not None
        assert "too long" in result.payload["text"]

    async def test_set_without_community_returns_guard(self, _dal: _FakeDal) -> None:
        result = await _run("!alias newcmd echo hi", community=None)
        assert result is not None
        assert result.payload["text"] == _COMMUNITY_REQUIRED_MSG
        assert 2 not in _dal._aliases

    async def test_set_handles_db_error(self, _dal: _FakeDal) -> None:
        _dal.should_error = True
        result = await _run("!alias newcmd echo hi")
        assert result is not None
        assert "Failed to set alias" in result.payload["text"]


class TestRemoveAlias:
    async def test_unalias_success(self, _dal: _FakeDal, _invalidate_calls: list[Any]) -> None:
        result = await _run("!unalias greet")
        assert result is not None
        assert result.payload["text"] == "alias removed: !greet"
        assert _dal._aliases[1]["deleted_at"] is not None
        assert _invalidate_calls == [(1, "greet")]

    async def test_alias_delete_success(self, _dal: _FakeDal) -> None:
        result = await _run("!alias delete greet")
        assert result is not None
        assert result.payload["text"] == "alias removed: !greet"
        assert _dal._aliases[1]["deleted_at"] is not None

    async def test_alias_remove_success(self, _dal: _FakeDal) -> None:
        result = await _run("!alias remove greet")
        assert result is not None
        assert result.payload["text"] == "alias removed: !greet"
        assert _dal._aliases[1]["deleted_at"] is not None

    async def test_unalias_not_found(self, _dal: _FakeDal) -> None:
        result = await _run("!unalias nosuchalias")
        assert result is not None
        assert result.payload["text"] == "no alias named !nosuchalias"

    async def test_unalias_missing_name_returns_usage(self) -> None:
        result = await _run("!unalias")
        assert result is not None
        assert result.payload["text"] == _ALIAS_USAGE

    async def test_alias_delete_missing_name_returns_usage(self) -> None:
        result = await _run("!alias delete")
        assert result is not None
        assert result.payload["text"] == _ALIAS_USAGE

    async def test_unalias_without_community_returns_guard(self, _dal: _FakeDal) -> None:
        result = await _run("!unalias greet", community=None)
        assert result is not None
        assert result.payload["text"] == _COMMUNITY_REQUIRED_MSG
        assert _dal._aliases[1]["deleted_at"] is None

    async def test_unalias_handles_db_error(self, _dal: _FakeDal) -> None:
        _dal.should_error = True
        result = await _run("!unalias greet")
        assert result is not None
        assert "Failed to remove alias" in result.payload["text"]


class TestPermissions:
    async def test_set_denied_for_non_moderator(self, _dal: _FakeDal) -> None:
        result = await _run("!alias newcmd echo hi", actor=NON_MOD_ACTOR)
        assert result is not None
        assert result.payload["text"] == _PERMISSION_DENIED_MSG
        assert 2 not in _dal._aliases

    async def test_unalias_denied_for_non_moderator(self, _dal: _FakeDal) -> None:
        result = await _run("!unalias greet", actor=NON_MOD_ACTOR)
        assert result is not None
        assert result.payload["text"] == _PERMISSION_DENIED_MSG
        assert _dal._aliases[1]["deleted_at"] is None

    async def test_set_denied_when_role_lookup_errors_fail_closed(self, _dal: _FakeDal) -> None:
        _dal.should_error_on_role_lookup = True
        result = await _run("!alias newcmd echo hi")
        assert result is not None
        assert result.payload["text"] == _PERMISSION_DENIED_MSG

    async def test_set_allowed_by_platform_user_id_match(self, _dal: _FakeDal) -> None:
        _dal.roles_by_platform_user_id["plat-42"] = "admin"
        result = await _run("!alias newcmd echo hi", actor=NON_MOD_ACTOR, author_id="plat-42")
        assert result is not None
        assert result.payload["text"] == "alias set: !newcmd → !echo hi"

    async def test_list_does_not_require_permission(self, _dal: _FakeDal) -> None:
        result = await _run("!alias list", actor=NON_MOD_ACTOR)
        assert result is not None
        assert result.payload["text"] != _PERMISSION_DENIED_MSG


class TestInvocation:
    async def test_bare_alias_invocation_returns_none_no_expansion(self, _dal: _FakeDal) -> None:
        """Bare `!greet alice` returns None -- expansion is handled by bot_process, not here."""
        result = await _run("!greet alice")
        assert result is None
        # Verify no database lookup occurred
        assert _dal._select_count == 0
        # Verify usage count didn't increment (no DB access)
        assert _dal._aliases[1]["usage_count"] == 5

    async def test_unknown_bang_word_returns_none_no_lookup(self, _dal: _FakeDal) -> None:
        """Unknown bang-words like `!sr foo` return None with no DB lookup."""
        result = await _run("!sr foo")
        assert result is None
        assert _dal._select_count == 0

    async def test_unknown_alias_returns_none(self) -> None:
        """Unknown alias `!notarealalias` returns None."""
        assert await _run("!notarealalias test") is None

    async def test_invocation_without_community_returns_none_no_query(self, _dal: _FakeDal) -> None:
        """Bare invocation without community context returns None without query."""
        result = await _run("!greet alice", community=None)
        assert result is None
        assert _dal._select_count == 0

    async def test_bare_invocation_no_db_access_on_error(self, _dal: _FakeDal) -> None:
        """Bare invocation doesn't access DB even if it errors, so DB error is never hit."""
        _dal.should_error = True
        result = await _run("!greet alice")
        # No DB access means no error can occur
        assert result is None
        assert _dal._select_count == 0

    async def test_preserves_channel_id_on_response(self) -> None:
        result = await _run("!alias list", channel_id="chan-42")
        assert result is not None
        assert result.payload["channel_id"] == "chan-42"

    async def test_preserves_other_payload_fields(self) -> None:
        result = await _run("!alias list", extra="keep-me")
        assert result is not None
        assert result.payload["extra"] == "keep-me"

    async def test_original_event_not_mutated(self) -> None:
        event = _event("!alias list")
        with bundle_context(tenant=TENANT, community=COMMUNITY, app_id=APP_ID):
            result = await transform(event)
        assert result is not event
        assert event.payload["text"] == "!alias list"

    async def test_strips_leading_trailing_whitespace(self) -> None:
        result = await _run("  !alias list  ")
        assert result is not None
        assert result.payload["text"] != "  !alias list  "

    async def test_actor_none_defaults_gracefully(self) -> None:
        result = await _run("!alias list", actor=None)
        assert result is not None
        assert isinstance(result.payload["text"], str)


class TestCrossCommunityIsolation:
    """Regression: cross-community alias IDOR -- unchanged from prior behavior."""

    async def test_alias_not_listed_from_other_community(self, _dal: _FakeDal) -> None:
        # regression: cross-community alias IDOR
        result = await _run("!alias list", community=COMMUNITY_2)
        assert result is not None
        assert "greet" not in result.payload["text"]
        assert result.payload["text"] == _NO_ALIASES_MSG

    async def test_alias_still_listed_from_its_own_community(self, _dal: _FakeDal) -> None:
        # regression: cross-community alias IDOR
        result = await _run("!alias list", community=COMMUNITY)
        assert result is not None
        assert "greet" in result.payload["text"]

    async def test_alias_not_expanded_from_other_community(self, _dal: _FakeDal) -> None:
        # regression: cross-community alias IDOR
        result = await _run("!greet penguin", community=COMMUNITY_2)
        assert result is None

    async def test_alias_not_deletable_from_other_community(self, _dal: _FakeDal) -> None:
        # regression: cross-community alias IDOR
        result = await _run("!unalias greet", community=COMMUNITY_2)
        assert result is not None
        assert result.payload["text"] == "no alias named !greet"
        assert _dal._aliases[1]["deleted_at"] is None


class TestInvalidateAliasCacheGuard:
    async def test_missing_module_logs_debug_and_write_still_succeeds(
        self, _dal: _FakeDal, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """`import services.command_alias_store` failing must never block a write."""

        def _raise_import_error(name: str) -> Any:
            raise ImportError(f"No module named {name!r}")

        monkeypatch.setattr(social_alias_process.importlib, "import_module", _raise_import_error)
        result = await _run("!alias newcmd echo hi")
        assert result is not None
        assert result.payload["text"] == "alias set: !newcmd → !echo hi"

    async def test_invalidate_failure_logs_debug_and_write_still_succeeds(
        self, _dal: _FakeDal, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def _boom(*, community_id: int, alias: str, redis_client: Any = None) -> None:
            raise RuntimeError("redis unreachable")

        monkeypatch.setattr(command_alias_store_module, "invalidate_alias", _boom)
        result = await _run("!alias newcmd echo hi")
        assert result is not None
        assert result.payload["text"] == "alias set: !newcmd → !echo hi"
