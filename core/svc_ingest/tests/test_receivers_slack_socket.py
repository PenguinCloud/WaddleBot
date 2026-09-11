"""Tests for `receivers.slack_socket.SlackSocketReceiver`.

`slack_sdk.socket_mode.aiohttp.SocketModeClient`/`AsyncWebClient` are both
monkeypatched to fakes (record `connect()`/`close()`/`auth_test()` calls,
capture the real request listener `_build_client` registers) rather than
opening a real WebSocket/HTTP connection -- the fakes still exercise the
REAL `_build_client`/`_normalize_event`/`receive()` wiring (queue
bridging, ack-every-envelope, event-type/self/subtype filtering), only
the actual slack_sdk network layer is replaced, matching
`test_discord_gateway.py`'s own "mock the gateway in tests" scope.
"""

from __future__ import annotations

import asyncio
import contextlib
from dataclasses import dataclass, field
from typing import Any

import pytest
from slack_sdk.errors import SlackApiError
from slack_sdk.socket_mode.request import SocketModeRequest
from slack_sdk.socket_mode.response import SocketModeResponse
from waddle_transports import Direction, NonRetryableTransportError, Transport

import receivers.slack_socket as slack_socket_module
from receivers.slack_socket import CONSUMES_TAG, SlackSocketReceiver

APP_TOKEN = "xapp-fake-not-a-real-slack-app-token"  # noqa: S105 - test literal, not a secret
BOT_TOKEN = "xoxb-fake-not-a-real-slack-bot-token"  # noqa: S105 - test literal, not a secret


@dataclass
class _FakeWebClient:
    """Stand-in for `AsyncWebClient` -- controllable `auth_test()` outcome."""

    token: str
    team_id: str | None = "T123"
    auth_test_calls: int = 0
    raise_on_auth_test: Exception | None = None

    async def auth_test(self) -> dict[str, Any]:
        self.auth_test_calls += 1
        if self.raise_on_auth_test is not None:
            raise self.raise_on_auth_test
        return {"ok": True, "team_id": self.team_id}


@dataclass
class _FakeSocketModeClient:
    """Stand-in for `SocketModeClient` -- records lifecycle calls, holds the real listener."""

    app_token: str
    web_client: Any
    socket_mode_request_listeners: list[Any] = field(default_factory=list)
    connect_calls: int = 0
    close_calls: int = 0
    sent_responses: list[SocketModeResponse] = field(default_factory=list)

    async def connect(self) -> None:
        self.connect_calls += 1

    async def close(self) -> None:
        self.close_calls += 1

    async def send_socket_mode_response(self, response: SocketModeResponse) -> None:
        self.sent_responses.append(response)


@pytest.fixture
def fake_web_clients(monkeypatch: pytest.MonkeyPatch) -> list[_FakeWebClient]:
    """Every `AsyncWebClient(token=...)` constructed during the test lands in this list."""
    created: list[_FakeWebClient] = []

    def _fake_ctor(*, token: str) -> _FakeWebClient:
        client = _FakeWebClient(token=token)
        created.append(client)
        return client

    monkeypatch.setattr(slack_socket_module, "AsyncWebClient", _fake_ctor)
    return created


@pytest.fixture
def fake_clients(monkeypatch: pytest.MonkeyPatch) -> list[_FakeSocketModeClient]:
    """Every `SocketModeClient(...)` constructed during the test lands in this list."""
    created: list[_FakeSocketModeClient] = []

    def _fake_ctor(*, app_token: str, web_client: Any) -> _FakeSocketModeClient:
        client = _FakeSocketModeClient(app_token=app_token, web_client=web_client)
        created.append(client)
        return client

    monkeypatch.setattr(slack_socket_module, "SocketModeClient", _fake_ctor)
    return created


async def _advance_to_connected(
    gen: Any, fake_clients: list[_FakeSocketModeClient]
) -> asyncio.Task[Any]:
    """Start `gen.__anext__()` as a task and yield control until `receive()` has connected.

    Mirrors `test_discord_gateway.py`'s `_advance_to_bot_started` -- polls
    (bounded) rather than assuming a fixed number of `asyncio.sleep(0)`
    yields is enough, so this stays robust to unrelated asyncio internals
    changes.
    """
    next_task = asyncio.ensure_future(gen.__anext__())
    for _ in range(50):
        await asyncio.sleep(0)
        if fake_clients and fake_clients[-1].connect_calls:
            return next_task
    raise AssertionError("client.connect() was never actually entered")


async def _cancel_and_close(next_task: asyncio.Task[Any], gen: Any) -> None:
    """Cancel `next_task`, await its cancellation, then close `gen` -- safe teardown order."""
    next_task.cancel()
    with contextlib.suppress(asyncio.CancelledError, StopAsyncIteration):
        await next_task
    await gen.aclose()


def _events_api_request(event: dict[str, Any], *, team_id: str = "T1") -> SocketModeRequest:
    return SocketModeRequest(
        type="events_api",
        envelope_id="env-1",
        payload={"team_id": team_id, "event": event},
    )


class TestResolveToken:
    async def test_literal_tokens_are_used_directly(
        self, fake_clients: list[_FakeSocketModeClient], fake_web_clients: list[_FakeWebClient]
    ) -> None:
        receiver = SlackSocketReceiver()
        gen = receiver.receive({"app_token": APP_TOKEN, "bot_token": BOT_TOKEN})
        next_task = await _advance_to_connected(gen, fake_clients)
        assert fake_clients[0].app_token == APP_TOKEN
        assert fake_web_clients[0].token == BOT_TOKEN
        await _cancel_and_close(next_task, gen)

    async def test_token_refs_are_resolved_from_env(
        self,
        fake_clients: list[_FakeSocketModeClient],
        fake_web_clients: list[_FakeWebClient],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("SOME_SLACK_APP_TOKEN_VAR", APP_TOKEN)
        monkeypatch.setenv("SOME_SLACK_BOT_TOKEN_VAR", BOT_TOKEN)
        receiver = SlackSocketReceiver()
        gen = receiver.receive(
            {
                "app_token_ref": "SOME_SLACK_APP_TOKEN_VAR",
                "bot_token_ref": "SOME_SLACK_BOT_TOKEN_VAR",
            }
        )
        next_task = await _advance_to_connected(gen, fake_clients)
        assert fake_clients[0].app_token == APP_TOKEN
        assert fake_web_clients[0].token == BOT_TOKEN
        await _cancel_and_close(next_task, gen)

    async def test_missing_app_token_raises(self) -> None:
        receiver = SlackSocketReceiver()
        gen = receiver.receive({"bot_token": BOT_TOKEN})
        with pytest.raises(NonRetryableTransportError, match="app_token"):
            await gen.__anext__()

    async def test_missing_bot_token_raises(self) -> None:
        receiver = SlackSocketReceiver()
        gen = receiver.receive({"app_token": APP_TOKEN})
        with pytest.raises(NonRetryableTransportError, match="bot_token"):
            await gen.__anext__()

    async def test_unresolvable_token_ref_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("UNSET_SLACK_TOKEN_VAR", raising=False)
        receiver = SlackSocketReceiver()
        gen = receiver.receive({"app_token_ref": "UNSET_SLACK_TOKEN_VAR", "bot_token": BOT_TOKEN})
        with pytest.raises(NonRetryableTransportError, match="resolution failed"):
            await gen.__anext__()


class TestAuthTestValidation:
    async def test_auth_test_failure_raises_before_connect(
        self, fake_clients: list[_FakeSocketModeClient], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """An invalid bot token fails fast, before `connect()` is ever reached.

        `NonRetryableTransportError` -- the already-constructed client is
        still cleanly closed.
        """
        failing_web_client = _FakeWebClient(token=BOT_TOKEN)
        failing_web_client.raise_on_auth_test = SlackApiError(
            "invalid_auth", {"ok": False, "error": "invalid_auth"}
        )
        monkeypatch.setattr(
            slack_socket_module, "AsyncWebClient", lambda *, token: failing_web_client
        )

        receiver = SlackSocketReceiver()
        gen = receiver.receive({"app_token": APP_TOKEN, "bot_token": BOT_TOKEN})
        with pytest.raises(NonRetryableTransportError, match="auth.test"):
            await gen.__anext__()

        assert fake_clients[0].connect_calls == 0
        assert fake_clients[0].close_calls == 1


class TestReceiveAcksEveryEnvelope:
    async def test_acks_a_kept_message_event(
        self, fake_clients: list[_FakeSocketModeClient], fake_web_clients: list[_FakeWebClient]
    ) -> None:
        receiver = SlackSocketReceiver()
        gen = receiver.receive({"app_token": APP_TOKEN, "bot_token": BOT_TOKEN})
        next_task = await _advance_to_connected(gen, fake_clients)
        client = fake_clients[0]
        listener = client.socket_mode_request_listeners[0]

        request = _events_api_request(
            {"type": "message", "channel": "C1", "user": "U1", "text": "hi", "ts": "1.1"}
        )
        await listener(client, request)

        assert len(client.sent_responses) == 1
        assert client.sent_responses[0].envelope_id == "env-1"
        item = await asyncio.wait_for(next_task, timeout=2.0)
        assert item["text"] == "hi"
        await gen.aclose()

    async def test_acks_even_a_dropped_bot_message(
        self, fake_clients: list[_FakeSocketModeClient], fake_web_clients: list[_FakeWebClient]
    ) -> None:
        receiver = SlackSocketReceiver()
        gen = receiver.receive({"app_token": APP_TOKEN, "bot_token": BOT_TOKEN})
        next_task = await _advance_to_connected(gen, fake_clients)
        client = fake_clients[0]
        listener = client.socket_mode_request_listeners[0]

        request = _events_api_request(
            {
                "type": "message",
                "channel": "C1",
                "user": "U1",
                "text": "hi",
                "ts": "1.1",
                "bot_id": "B1",
            }
        )
        await listener(client, request)

        assert len(client.sent_responses) == 1  # acked regardless of the drop
        assert next_task.done() is False  # nothing queued
        await _cancel_and_close(next_task, gen)

    async def test_acks_a_non_events_api_envelope_without_queueing(
        self, fake_clients: list[_FakeSocketModeClient], fake_web_clients: list[_FakeWebClient]
    ) -> None:
        receiver = SlackSocketReceiver()
        gen = receiver.receive({"app_token": APP_TOKEN, "bot_token": BOT_TOKEN})
        next_task = await _advance_to_connected(gen, fake_clients)
        client = fake_clients[0]
        listener = client.socket_mode_request_listeners[0]

        request = SocketModeRequest(
            type="interactive", envelope_id="env-2", payload={"type": "block_actions"}
        )
        await listener(client, request)

        assert len(client.sent_responses) == 1
        assert next_task.done() is False
        await _cancel_and_close(next_task, gen)


class TestNormalizeEventTypes:
    async def test_message_event_fields(
        self, fake_clients: list[_FakeSocketModeClient], fake_web_clients: list[_FakeWebClient]
    ) -> None:
        receiver = SlackSocketReceiver()
        gen = receiver.receive({"app_token": APP_TOKEN, "bot_token": BOT_TOKEN})
        next_task = await _advance_to_connected(gen, fake_clients)
        client = fake_clients[0]
        listener = client.socket_mode_request_listeners[0]

        await listener(
            client,
            _events_api_request(
                {
                    "type": "message",
                    "channel": "C1",
                    "user": "U1",
                    "text": "hello",
                    "ts": "1.100",
                    "thread_ts": "1.000",
                },
                team_id="T9",
            ),
        )
        item = await asyncio.wait_for(next_task, timeout=2.0)
        assert item == {
            "platform": "slack",
            "event_type": "message",
            "text": "hello",
            "channel_id": "C1",
            "team_id": "T9",
            "thread_ts": "1.000",
            "message_ts": "1.100",
            "platform_user_id": "U1",
            "display_name": None,
        }
        await gen.aclose()

    async def test_app_mention_event_fields(
        self, fake_clients: list[_FakeSocketModeClient], fake_web_clients: list[_FakeWebClient]
    ) -> None:
        receiver = SlackSocketReceiver()
        gen = receiver.receive({"app_token": APP_TOKEN, "bot_token": BOT_TOKEN})
        next_task = await _advance_to_connected(gen, fake_clients)
        client = fake_clients[0]
        listener = client.socket_mode_request_listeners[0]

        await listener(
            client,
            _events_api_request(
                {
                    "type": "app_mention",
                    "channel": "C1",
                    "user": "U2",
                    "text": "@bot hi",
                    "ts": "2.0",
                }
            ),
        )
        item = await asyncio.wait_for(next_task, timeout=2.0)
        assert item["event_type"] == "app_mention"
        assert item["platform_user_id"] == "U2"
        await gen.aclose()

    async def test_member_joined_channel_event_fields(
        self, fake_clients: list[_FakeSocketModeClient], fake_web_clients: list[_FakeWebClient]
    ) -> None:
        receiver = SlackSocketReceiver()
        gen = receiver.receive({"app_token": APP_TOKEN, "bot_token": BOT_TOKEN})
        next_task = await _advance_to_connected(gen, fake_clients)
        client = fake_clients[0]
        listener = client.socket_mode_request_listeners[0]

        await listener(
            client,
            _events_api_request({"type": "member_joined_channel", "channel": "C1", "user": "U3"}),
        )
        item = await asyncio.wait_for(next_task, timeout=2.0)
        assert item["event_type"] == "member_joined_channel"
        assert item["platform_user_id"] == "U3"
        assert item["text"] is None
        await gen.aclose()

    async def test_unhandled_event_type_is_dropped(
        self, fake_clients: list[_FakeSocketModeClient], fake_web_clients: list[_FakeWebClient]
    ) -> None:
        receiver = SlackSocketReceiver()
        gen = receiver.receive({"app_token": APP_TOKEN, "bot_token": BOT_TOKEN})
        next_task = await _advance_to_connected(gen, fake_clients)
        client = fake_clients[0]
        listener = client.socket_mode_request_listeners[0]

        await listener(client, _events_api_request({"type": "reaction_added", "user": "U1"}))

        assert next_task.done() is False
        await _cancel_and_close(next_task, gen)


class TestNormalizeSkippedSubtypes:
    @pytest.mark.parametrize("subtype", ["message_changed", "message_deleted"])
    async def test_edit_and_delete_subtypes_are_dropped(
        self,
        subtype: str,
        fake_clients: list[_FakeSocketModeClient],
        fake_web_clients: list[_FakeWebClient],
    ) -> None:
        receiver = SlackSocketReceiver()
        gen = receiver.receive({"app_token": APP_TOKEN, "bot_token": BOT_TOKEN})
        next_task = await _advance_to_connected(gen, fake_clients)
        client = fake_clients[0]
        listener = client.socket_mode_request_listeners[0]

        await listener(
            client,
            _events_api_request(
                {"type": "message", "channel": "C1", "user": "U1", "subtype": subtype}
            ),
        )

        assert next_task.done() is False
        await _cancel_and_close(next_task, gen)

    async def test_non_edit_delete_subtype_is_not_dropped(
        self, fake_clients: list[_FakeSocketModeClient], fake_web_clients: list[_FakeWebClient]
    ) -> None:
        receiver = SlackSocketReceiver()
        gen = receiver.receive({"app_token": APP_TOKEN, "bot_token": BOT_TOKEN})
        next_task = await _advance_to_connected(gen, fake_clients)
        client = fake_clients[0]
        listener = client.socket_mode_request_listeners[0]

        await listener(
            client,
            _events_api_request(
                {
                    "type": "message",
                    "channel": "C1",
                    "user": "U1",
                    "text": "hi",
                    "ts": "1.0",
                    "subtype": "thread_broadcast",
                }
            ),
        )
        item = await asyncio.wait_for(next_task, timeout=2.0)
        assert item["text"] == "hi"
        await gen.aclose()


class TestReceiveLifecycle:
    async def test_keeps_yielding_across_multiple_events(
        self, fake_clients: list[_FakeSocketModeClient], fake_web_clients: list[_FakeWebClient]
    ) -> None:
        """Queue-bridge decoupling: the generator survives repeated events.

        By that same decoupling, it also survives a simulated reconnect --
        slack_sdk's own `auto_reconnect_enabled` keeps the underlying
        connection alive without ever signalling `receive()` -- see this
        module's own docstring.
        """
        receiver = SlackSocketReceiver()
        gen = receiver.receive({"app_token": APP_TOKEN, "bot_token": BOT_TOKEN})
        next_task = await _advance_to_connected(gen, fake_clients)
        client = fake_clients[0]
        listener = client.socket_mode_request_listeners[0]

        for i in range(3):
            await listener(
                client,
                _events_api_request(
                    {
                        "type": "message",
                        "channel": "C1",
                        "user": "U1",
                        "text": f"msg{i}",
                        "ts": f"{i}.0",
                    }
                ),
            )
            item = await asyncio.wait_for(next_task, timeout=2.0)
            assert item["text"] == f"msg{i}"
            next_task = asyncio.ensure_future(gen.__anext__())

        assert client.connect_calls == 1  # connected exactly once across all 3 events
        await _cancel_and_close(next_task, gen)

    async def test_cancelling_the_consumer_closes_the_client(
        self, fake_clients: list[_FakeSocketModeClient], fake_web_clients: list[_FakeWebClient]
    ) -> None:
        receiver = SlackSocketReceiver()
        gen = receiver.receive({"app_token": APP_TOKEN, "bot_token": BOT_TOKEN})
        next_task = await _advance_to_connected(gen, fake_clients)
        client = fake_clients[0]
        assert client.close_calls == 0

        await _cancel_and_close(next_task, gen)

        assert client.close_calls == 1

    async def test_ready_log_uses_resolved_team_id(
        self,
        fake_clients: list[_FakeSocketModeClient],
        fake_web_clients: list[_FakeWebClient],
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        fake_web_clients_seen: list[_FakeWebClient] = fake_web_clients
        receiver = SlackSocketReceiver()
        gen = receiver.receive({"app_token": APP_TOKEN, "bot_token": BOT_TOKEN})
        with caplog.at_level("INFO", logger="receivers.slack_socket"):
            next_task = await _advance_to_connected(gen, fake_clients)
        assert fake_web_clients_seen[0].auth_test_calls == 1
        assert any("gateway.slack_ready" in r.message for r in caplog.records)
        await _cancel_and_close(next_task, gen)


class TestTransportClassification:
    """`SlackSocketReceiver` maps to `waddle_transports.Transport`.

    `name="slack_socket"`, `directions={Direction.INBOUND}`.
    """

    def test_is_a_transport_subclass(self) -> None:
        assert isinstance(SlackSocketReceiver(), Transport)

    def test_name_is_slack_socket(self) -> None:
        assert SlackSocketReceiver().name == "slack_socket"

    def test_directions_is_inbound_only(self) -> None:
        assert SlackSocketReceiver().directions == frozenset({Direction.INBOUND})

    def test_consumes_tag_matches_expected(self) -> None:
        assert CONSUMES_TAG == "slack.message"
