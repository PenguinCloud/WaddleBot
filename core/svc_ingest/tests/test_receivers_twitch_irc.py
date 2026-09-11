"""Tests for `receivers.twitch_irc.TwitchIrcReceiver`.

`IrcTransport.receive()` (the real wire protocol -- a genuine asyncio TCP/
TLS socket) is monkeypatched to a fake async generator on the receiver's
own `self._irc` instance -- opening a real connection is out of scope for
this container's unit tests, same precedent `test_discord_gateway.py`
sets for py-cord's own network layer. Unlike Discord's callback-driven
`discord.Bot`, `IrcTransport.receive()` is already a native async
generator, so no queue-bridging harness is needed here -- `receive()`
just needs to prove it normalizes each yielded item correctly.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Mapping

import pytest
from waddle_transports import Direction, Transport

from receivers.twitch_irc import CONSUMES_TAG, TwitchIrcReceiver

_IRC_CONFIG = {
    "host": "irc.chat.twitch.tv",
    "port": 6697,
    "nick": "waddlebot",
    "channel": "waddlebot",
    "password_ref": "TEST_TWITCH_TOKEN_REF",
}


async def _fake_privmsgs(*items: Mapping[str, str]) -> AsyncIterator[Mapping[str, str]]:
    for item in items:
        yield item


class TestTransportClassification:
    """`TwitchIrcReceiver` maps to `waddle_transports.Transport`.

    `name="twitch_irc"`, `directions={Direction.INBOUND}`.
    """

    def test_is_a_transport_subclass(self) -> None:
        assert isinstance(TwitchIrcReceiver(), Transport)

    def test_name_is_twitch_irc(self) -> None:
        assert TwitchIrcReceiver().name == "twitch_irc"

    def test_directions_is_inbound_only(self) -> None:
        assert TwitchIrcReceiver().directions == frozenset({Direction.INBOUND})

    def test_consumes_tag_matches_manifest(self) -> None:
        assert CONSUMES_TAG == "twitch.message"


class TestReceive:
    async def test_normalizes_raw_irc_transport_output(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        receiver = TwitchIrcReceiver()
        raw_privmsg = {"channel": "#waddlebot", "sender": "alice", "text": "hello chat"}
        monkeypatch.setattr(
            receiver._irc,  # noqa: SLF001 - test override of the real IrcTransport instance
            "receive",
            lambda config: _fake_privmsgs(raw_privmsg),
        )

        items = [item async for item in receiver.receive(_IRC_CONFIG)]

        assert items == [
            {
                "platform": "twitch",
                "channel_name": "waddlebot",
                "author_username": "alice",
                "content": "hello chat",
                "author_id": None,
                "user_id": None,
                "display_name": None,
                "message_id": None,
                "room_id": None,
                "badges": [],
                "is_mod": False,
                "is_subscriber": False,
                "is_vip": False,
                "is_broadcaster": False,
            }
        ]

    async def test_strips_leading_hash_from_channel(self, monkeypatch: pytest.MonkeyPatch) -> None:
        receiver = TwitchIrcReceiver()
        raw_privmsg = {"channel": "#somechannel", "sender": "bob", "text": "hi"}
        monkeypatch.setattr(
            receiver._irc,  # noqa: SLF001
            "receive",
            lambda config: _fake_privmsgs(raw_privmsg),
        )

        items = [item async for item in receiver.receive(_IRC_CONFIG)]
        assert items[0]["channel_name"] == "somechannel"

    async def test_yields_multiple_messages_in_order(self, monkeypatch: pytest.MonkeyPatch) -> None:
        receiver = TwitchIrcReceiver()
        monkeypatch.setattr(
            receiver._irc,  # noqa: SLF001
            "receive",
            lambda config: _fake_privmsgs(
                {"channel": "#waddlebot", "sender": "alice", "text": "one"},
                {"channel": "#waddlebot", "sender": "bob", "text": "two"},
            ),
        )

        items = [item async for item in receiver.receive(_IRC_CONFIG)]
        assert [i["author_username"] for i in items] == ["alice", "bob"]

    async def test_no_messages_ends_cleanly(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A connection that yields nothing before ending just ends iteration -- no error."""
        receiver = TwitchIrcReceiver()
        monkeypatch.setattr(receiver._irc, "receive", lambda config: _fake_privmsgs())  # noqa: SLF001

        items = [item async for item in receiver.receive(_IRC_CONFIG)]
        assert items == []

    async def test_self_authored_message_is_dropped(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A PRIVMSG whose sender matches `config["nick"]` (case-insensitive) is not fanned out."""
        receiver = TwitchIrcReceiver()
        monkeypatch.setattr(
            receiver._irc,  # noqa: SLF001
            "receive",
            lambda config: _fake_privmsgs(
                {"channel": "#waddlebot", "sender": "WaddleBot", "text": "Hey alice! 👋"},
                {"channel": "#waddlebot", "sender": "alice", "text": "hi"},
            ),
        )

        items = [item async for item in receiver.receive(_IRC_CONFIG)]

        assert [i["author_username"] for i in items] == ["alice"]

    async def test_other_bot_authored_message_is_not_dropped(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Scope is self-only -- a DIFFERENT sender's message must still be fanned out."""
        receiver = TwitchIrcReceiver()
        monkeypatch.setattr(
            receiver._irc,  # noqa: SLF001
            "receive",
            lambda config: _fake_privmsgs(
                {"channel": "#waddlebot", "sender": "othergreetbot", "text": "hi there"},
            ),
        )

        items = [item async for item in receiver.receive(_IRC_CONFIG)]

        assert [i["author_username"] for i in items] == ["othergreetbot"]

    async def test_missing_nick_in_config_does_not_drop_anything(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Unknown self-identity (no `nick` in config) errs toward NOT dropping."""
        receiver = TwitchIrcReceiver()
        monkeypatch.setattr(
            receiver._irc,  # noqa: SLF001
            "receive",
            lambda config: _fake_privmsgs(
                {"channel": "#waddlebot", "sender": "waddlebot", "text": "hi"},
            ),
        )
        config_without_nick = {k: v for k, v in _IRC_CONFIG.items() if k != "nick"}

        items = [item async for item in receiver.receive(config_without_nick)]

        assert [i["author_username"] for i in items] == ["waddlebot"]

    async def test_passes_config_through_to_irc_transport(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Every original config key survives untouched, alongside the added `cap_requests`."""
        receiver = TwitchIrcReceiver()
        captured: dict[str, Mapping[str, object]] = {}

        def _fake_receive(config: Mapping[str, object]) -> AsyncIterator[Mapping[str, str]]:
            captured["config"] = config
            return _fake_privmsgs()

        monkeypatch.setattr(receiver._irc, "receive", _fake_receive)  # noqa: SLF001

        async for _item in receiver.receive(_IRC_CONFIG):
            pass  # pragma: no cover -- no items yielded

        passed_config = captured["config"]
        for key, value in _IRC_CONFIG.items():
            assert passed_config[key] == value
        assert passed_config["cap_requests"] == ("twitch.tv/tags", "twitch.tv/commands")

    async def test_original_config_mapping_is_not_mutated(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """`config` may be a caller-owned/shared mapping -- must never be mutated in place."""
        receiver = TwitchIrcReceiver()
        monkeypatch.setattr(receiver._irc, "receive", lambda config: _fake_privmsgs())  # noqa: SLF001
        original = dict(_IRC_CONFIG)

        async for _item in receiver.receive(original):
            pass  # pragma: no cover -- no items yielded

        assert original == _IRC_CONFIG
        assert "cap_requests" not in original

    async def test_caller_supplied_cap_requests_is_not_overridden(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        receiver = TwitchIrcReceiver()
        captured: dict[str, Mapping[str, object]] = {}

        def _fake_receive(config: Mapping[str, object]) -> AsyncIterator[Mapping[str, str]]:
            captured["config"] = config
            return _fake_privmsgs()

        monkeypatch.setattr(receiver._irc, "receive", _fake_receive)  # noqa: SLF001
        config_with_override = {**_IRC_CONFIG, "cap_requests": ["custom.cap"]}

        async for _item in receiver.receive(config_with_override):
            pass  # pragma: no cover -- no items yielded

        assert captured["config"]["cap_requests"] == ["custom.cap"]


class TestIrcv3TagParsing:
    """Real IRCv3 `@tag=val;...` parsing into Twitch's per-message metadata."""

    async def test_full_tag_set_is_parsed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        receiver = TwitchIrcReceiver()
        raw_tags = (
            "badge-info=subscriber/12;badges=moderator/1,subscriber/12,vip/1;"
            "color=#0000FF;display-name=PenguinFan;id=msg-abc-123;mod=1;"
            "room-id=555444;subscriber=1;user-id=87654321"
        )
        monkeypatch.setattr(
            receiver._irc,  # noqa: SLF001
            "receive",
            lambda config: _fake_privmsgs(
                {
                    "channel": "#waddlebot",
                    "sender": "penguinfan",
                    "text": "hello",
                    "tags": raw_tags,
                }
            ),
        )

        items = [item async for item in receiver.receive(_IRC_CONFIG)]
        item = items[0]

        assert item["author_id"] == "87654321"
        assert item["user_id"] == "87654321"
        assert item["display_name"] == "PenguinFan"
        assert item["message_id"] == "msg-abc-123"
        assert item["room_id"] == "555444"
        assert item["badges"] == ["moderator", "subscriber", "vip"]
        assert item["is_mod"] is True
        assert item["is_subscriber"] is True
        assert item["is_vip"] is True
        assert item["is_broadcaster"] is False

    async def test_missing_tags_key_yields_absent_fields_never_crashes(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """No `tags` key at all (e.g. an older/mocked raw source) -- treated same as `None`."""
        receiver = TwitchIrcReceiver()
        monkeypatch.setattr(
            receiver._irc,  # noqa: SLF001
            "receive",
            lambda config: _fake_privmsgs(
                {"channel": "#waddlebot", "sender": "alice", "text": "hi"}
            ),
        )

        items = [item async for item in receiver.receive(_IRC_CONFIG)]
        item = items[0]

        assert item["author_id"] is None
        assert item["user_id"] is None
        assert item["display_name"] is None
        assert item["message_id"] is None
        assert item["room_id"] is None
        assert item["badges"] == []
        assert item["is_mod"] is False
        assert item["is_subscriber"] is False
        assert item["is_vip"] is False
        assert item["is_broadcaster"] is False

    async def test_none_tags_value_yields_absent_fields(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """CAP not granted -- `IrcTransport` yields `tags=None` explicitly."""
        receiver = TwitchIrcReceiver()
        monkeypatch.setattr(
            receiver._irc,  # noqa: SLF001
            "receive",
            lambda config: _fake_privmsgs(
                {"channel": "#waddlebot", "sender": "alice", "text": "hi", "tags": None}
            ),
        )

        items = [item async for item in receiver.receive(_IRC_CONFIG)]
        assert items[0]["author_id"] is None
        assert items[0]["badges"] == []

    async def test_broadcaster_badge_sets_is_broadcaster(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        receiver = TwitchIrcReceiver()
        monkeypatch.setattr(
            receiver._irc,  # noqa: SLF001
            "receive",
            lambda config: _fake_privmsgs(
                {
                    "channel": "#waddlebot",
                    "sender": "streamer",
                    "text": "hi chat",
                    "tags": "badges=broadcaster/1;mod=0;subscriber=0;user-id=1",
                }
            ),
        )

        items = [item async for item in receiver.receive(_IRC_CONFIG)]
        assert items[0]["is_broadcaster"] is True
        assert items[0]["is_mod"] is False

    async def test_badge_versions_are_stripped_to_names_only(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        receiver = TwitchIrcReceiver()
        monkeypatch.setattr(
            receiver._irc,  # noqa: SLF001
            "receive",
            lambda config: _fake_privmsgs(
                {
                    "channel": "#waddlebot",
                    "sender": "alice",
                    "text": "hi",
                    "tags": "badges=subscriber/24,premium/1;user-id=1",
                }
            ),
        )

        items = [item async for item in receiver.receive(_IRC_CONFIG)]
        assert items[0]["badges"] == ["subscriber", "premium"]

    async def test_no_badges_tag_yields_empty_badges_list(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        receiver = TwitchIrcReceiver()
        monkeypatch.setattr(
            receiver._irc,  # noqa: SLF001
            "receive",
            lambda config: _fake_privmsgs(
                {"channel": "#waddlebot", "sender": "alice", "text": "hi", "tags": "user-id=1"}
            ),
        )

        items = [item async for item in receiver.receive(_IRC_CONFIG)]
        assert items[0]["badges"] == []
        assert items[0]["is_vip"] is False
        assert items[0]["is_broadcaster"] is False

    async def test_escaped_space_in_display_name_is_unescaped(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        r"""IRCv3 tag escaping: `\s` on the wire decodes to a literal space."""
        receiver = TwitchIrcReceiver()
        monkeypatch.setattr(
            receiver._irc,  # noqa: SLF001
            "receive",
            lambda config: _fake_privmsgs(
                {
                    "channel": "#waddlebot",
                    "sender": "penguin_fan",
                    "text": "hi",
                    "tags": r"display-name=Penguin\sFan;user-id=1",
                }
            ),
        )

        items = [item async for item in receiver.receive(_IRC_CONFIG)]
        assert items[0]["display_name"] == "Penguin Fan"

    async def test_valueless_tag_and_empty_user_id_do_not_crash(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A boolean-style valueless tag (`;flags;`) and an empty `user-id=` -- never raises."""
        receiver = TwitchIrcReceiver()
        monkeypatch.setattr(
            receiver._irc,  # noqa: SLF001
            "receive",
            lambda config: _fake_privmsgs(
                {
                    "channel": "#waddlebot",
                    "sender": "alice",
                    "text": "hi",
                    "tags": "flags;user-id=;mod=0",
                }
            ),
        )

        items = [item async for item in receiver.receive(_IRC_CONFIG)]
        assert items[0]["author_id"] is None
        assert items[0]["user_id"] is None

    async def test_tags_are_parsed_even_for_self_authored_message_before_drop(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        """The tag-presence DEBUG log fires on the first PRIVMSG regardless of self-drop."""
        import logging

        receiver = TwitchIrcReceiver()
        monkeypatch.setattr(
            receiver._irc,  # noqa: SLF001
            "receive",
            lambda config: _fake_privmsgs(
                {
                    "channel": "#waddlebot",
                    "sender": "WaddleBot",
                    "text": "self msg",
                    "tags": "user-id=1",
                },
                {"channel": "#waddlebot", "sender": "alice", "text": "hi", "tags": "user-id=2"},
            ),
        )

        with caplog.at_level(logging.DEBUG, logger="receivers.twitch_irc"):
            items = [item async for item in receiver.receive(_IRC_CONFIG)]

        assert [i["author_username"] for i in items] == ["alice"]
        tags_present_logs = [r for r in caplog.records if "receiver.tags_present" in r.message]
        assert len(tags_present_logs) == 1
        assert "present=True" in tags_present_logs[0].message

    async def test_tags_absent_logged_once_per_connection(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        import logging

        receiver = TwitchIrcReceiver()
        monkeypatch.setattr(
            receiver._irc,  # noqa: SLF001
            "receive",
            lambda config: _fake_privmsgs(
                {"channel": "#waddlebot", "sender": "alice", "text": "one"},
                {"channel": "#waddlebot", "sender": "bob", "text": "two"},
            ),
        )

        with caplog.at_level(logging.DEBUG, logger="receivers.twitch_irc"):
            items = [item async for item in receiver.receive(_IRC_CONFIG)]

        assert len(items) == 2
        tags_present_logs = [r for r in caplog.records if "receiver.tags_present" in r.message]
        assert len(tags_present_logs) == 1
        assert "present=False" in tags_present_logs[0].message
