"""Tests for `receivers.kick_pusher.KickPusherReceiver`.

The WebSocket half uses a REAL local `websockets.serve()` test server (no
mocked client) -- matching `libs/waddle_transports/tests/
test_transport_socket.py`'s own "real local server" testing convention for
this same underlying `websockets` library, rather than
`test_receivers_slack_socket.py`'s "mock the SDK client" approach (Kick
Pusher chat has no equivalent SDK here -- this receiver speaks the wire
protocol directly, so there is a real client to exercise against a real
server). The chatroom-lookup HTTP half uses `httpx.MockTransport`, matching
every other receiver/action bundle's own convention.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest
import websockets
from waddle_transports import (
    Direction,
    NonRetryableTransportError,
    RetryableTransportError,
    Transport,
)

import receivers.kick_pusher as kick_pusher_module
from receivers.kick_pusher import (
    CONSUMES_TAG,
    DEFAULT_CLUSTER,
    DEFAULT_PUSHER_KEY,
    KickPusherReceiver,
)

_CHAT_EVENT = "App\\Events\\ChatMessageEvent"


def _client(handler: Any) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler), follow_redirects=False)


@pytest.fixture
def _bypass_ssrf_guard_for_local_server(monkeypatch: pytest.MonkeyPatch) -> None:
    """Bypass the SSRF guard's loopback rejection for the real local WS test server below.

    Mirrors `test_transport_socket.py`'s identical fixture -- these tests
    exercise real wire behavior against 127.0.0.1 (a loopback address the
    guard correctly rejects in production); the guard itself is exercised
    separately in `TestSsrfGuard`, against non-loopback hosts, unpatched.
    """
    monkeypatch.setattr(kick_pusher_module, "is_private_host", lambda host: False)  # noqa: ARG005


def _chat_message_frame(
    channel: str,
    *,
    content: str = "hello chat",
    sender_id: int = 42,
    username: str = "alice",
    badges: list[dict[str, str]] | None = None,
    is_moderator: bool = False,
    is_subscriber: bool = False,
    is_channel_owner: bool = False,
    message_id: str = "msg-1",
    created_at: str = "2026-09-11T12:00:00.000000Z",
) -> str:
    return json.dumps(
        {
            "event": _CHAT_EVENT,
            "channel": channel,
            "data": json.dumps(
                {
                    "id": message_id,
                    "chatroom_id": 999,
                    "content": content,
                    "created_at": created_at,
                    "sender": {
                        "id": sender_id,
                        "username": username,
                        "slug": username,
                        "is_moderator": is_moderator,
                        "is_subscriber": is_subscriber,
                        "is_channel_owner": is_channel_owner,
                        "identity": {"badges": badges or []},
                    },
                }
            ),
        }
    )


@pytest.fixture
async def pusher_server() -> AsyncIterator[tuple[str, list[dict[str, Any]]]]:
    """Real Pusher-protocol-shaped WebSocket test server.

    On `pusher:subscribe`, replies with `pusher_internal:subscription_
    succeeded`, then a `pusher:ping`, one real chat message frame, and one
    frame of an event type this receiver must skip (`Subscription`) --
    then closes. Every frame the CLIENT sends is recorded into `received`
    for the test to assert against (subscribe request, pong reply).
    """
    received: list[dict[str, Any]] = []

    async def _handler(ws: Any) -> None:
        await ws.send(
            json.dumps(
                {
                    "event": "pusher:connection_established",
                    "data": json.dumps({"socket_id": "123.456", "activity_timeout": 30}),
                }
            )
        )
        channel: str | None = None
        async for raw in ws:
            frame = json.loads(raw)
            received.append(frame)
            event = frame.get("event")
            if event == "pusher:subscribe":
                channel = frame["data"]["channel"]
                await ws.send(
                    json.dumps(
                        {
                            "event": "pusher_internal:subscription_succeeded",
                            "data": "{}",
                            "channel": channel,
                        }
                    )
                )
                await ws.send(json.dumps({"event": "pusher:ping", "data": "{}"}))
            elif event == "pusher:pong" and channel is not None:
                # Wait for the client's pong reply before sending the rest
                # of the scripted sequence -- sending (and closing) right
                # after the ping, without waiting, races the client's own
                # `ws.send(pong)` against the server's close handshake and
                # can drop already-in-flight frames (real-world behavior
                # of the underlying `websockets` library, not specific to
                # this receiver -- a genuine Pusher server's own ping
                # cadence never closes immediately after a ping either).
                await ws.send(
                    json.dumps({"event": "Subscription", "channel": channel, "data": "{}"})
                )
                await ws.send(_chat_message_frame(channel))
                return  # closes the connection after the scripted sequence

    server = await websockets.serve(_handler, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    try:
        yield f"ws://127.0.0.1:{port}", received
    finally:
        server.close()
        await server.wait_closed()


class TestTransportClassification:
    """`KickPusherReceiver` maps to `waddle_transports.Transport`.

    `name="kick_pusher"`, `directions={Direction.INBOUND}`.
    """

    def test_is_a_transport_subclass(self) -> None:
        assert isinstance(KickPusherReceiver(), Transport)

    def test_name_is_kick_pusher(self) -> None:
        assert KickPusherReceiver().name == "kick_pusher"

    def test_directions_is_inbound_only(self) -> None:
        assert KickPusherReceiver().directions == frozenset({Direction.INBOUND})

    def test_consumes_tag_matches_expected(self) -> None:
        assert CONSUMES_TAG == "kick.message"

    def test_defaults_are_kicks_own_public_pusher_app(self) -> None:
        assert DEFAULT_PUSHER_KEY == "eb1d5f283081a78b932c"
        assert DEFAULT_CLUSTER == "us2"


class TestMissingChannelSlug:
    async def test_missing_channel_slug_is_non_retryable(self) -> None:
        receiver = KickPusherReceiver()
        with pytest.raises(NonRetryableTransportError, match="channel_slug"):
            async for _item in receiver.receive({}):
                pass


class TestChatroomLookup:
    async def test_resolves_chatroom_id_from_channel_api(self) -> None:
        captured = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["url"] = str(request.url)
            return httpx.Response(200, json={"chatroom": {"id": 555}})

        async with _client(handler) as http_client:
            receiver = KickPusherReceiver(http_client=http_client)
            with pytest.raises(NonRetryableTransportError, match="SSRF"):
                # Real (unpatched) SSRF guard rejects the ws:// connect to
                # a made-up unreachable host below -- proves the chatroom
                # lookup itself completed first (its own real call, with
                # a non-loopback api_base) before the WS stage is reached.
                async for _item in receiver.receive(
                    {
                        "channel_slug": "acme",
                        "api_base": "https://8.8.8.8",
                        "ws_url": "ws://169.254.169.254/x",
                    }
                ):
                    pass

        assert captured["url"] == "https://8.8.8.8/channels/acme"

    async def test_pre_resolved_chatroom_id_skips_the_lookup(self) -> None:
        called = False

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal called
            called = True
            return httpx.Response(200, json={"chatroom": {"id": 555}})

        async with _client(handler) as http_client:
            receiver = KickPusherReceiver(http_client=http_client)
            with pytest.raises(NonRetryableTransportError, match="SSRF"):
                async for _item in receiver.receive(
                    {
                        "channel_slug": "acme",
                        "chatroom_id": 999,
                        "ws_url": "ws://169.254.169.254/x",
                    }
                ):
                    pass
        assert called is False

    async def test_channel_not_found_is_non_retryable(self) -> None:
        async with _client(lambda r: httpx.Response(404)) as http_client:
            receiver = KickPusherReceiver(http_client=http_client)
            with pytest.raises(NonRetryableTransportError, match="not found"):
                async for _item in receiver.receive(
                    {"channel_slug": "nope", "api_base": "https://8.8.8.8"}
                ):
                    pass

    async def test_server_error_is_retryable(self) -> None:
        async with _client(lambda r: httpx.Response(503)) as http_client:
            receiver = KickPusherReceiver(http_client=http_client)
            with pytest.raises(RetryableTransportError):
                async for _item in receiver.receive(
                    {"channel_slug": "acme", "api_base": "https://8.8.8.8"}
                ):
                    pass

    async def test_missing_chatroom_in_response_is_non_retryable(self) -> None:
        async with _client(lambda r: httpx.Response(200, json={})) as http_client:
            receiver = KickPusherReceiver(http_client=http_client)
            with pytest.raises(NonRetryableTransportError, match="no chatroom id"):
                async for _item in receiver.receive(
                    {"channel_slug": "acme", "api_base": "https://8.8.8.8"}
                ):
                    pass

    async def test_network_error_is_retryable(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("connection refused", request=request)

        async with _client(handler) as http_client:
            receiver = KickPusherReceiver(http_client=http_client)
            with pytest.raises(RetryableTransportError):
                async for _item in receiver.receive(
                    {"channel_slug": "acme", "api_base": "https://8.8.8.8"}
                ):
                    pass


async def _drain(gen: AsyncIterator[dict[str, Any]]) -> list[dict[str, Any]]:
    """Collect every item `gen` yields until it stops.

    A CLEAN close (code 1000, e.g. `pusher_server`'s own scripted
    sequence below) ends `receive()`'s `async for raw in ws:` loop
    normally -- no exception, matching `TwitchIrcReceiver`/
    `SlackSocketReceiver`'s own "the generator just ends" contract for a
    graceful disconnect. `supervisor.ReceiverSupervisor` treats that
    plain return exactly like a raised exception (restart-on-exit either
    way, see `supervisor.py`'s own `_supervise` docstring) -- so either
    path is a legitimate "go reconnect" signal; `TestConnectionDropped`
    below covers the exception path (an abnormal close/network failure)
    separately.
    """
    return [item async for item in gen]


@pytest.mark.usefixtures("_bypass_ssrf_guard_for_local_server")
class TestReceivePusherProtocol:
    async def test_subscribes_replies_to_ping_and_yields_the_chat_message(
        self, pusher_server: tuple[str, list[dict[str, Any]]]
    ) -> None:
        ws_url, received = pusher_server
        receiver = KickPusherReceiver()
        gen = receiver.receive({"channel_slug": "acme", "chatroom_id": 999, "ws_url": ws_url})
        items = await _drain(gen)

        assert items == [
            {
                "platform": "kick",
                "text": "hello chat",
                "chatroom_id": 999,
                "channel_slug": "acme",
                "author_id": "42",
                "display_name": "alice",
                "badges": [],
                "is_mod": False,
                "is_subscriber": False,
                "is_owner": False,
                "message_id": "msg-1",
                "created_at": "2026-09-11T12:00:00.000000Z",
            }
        ]

        subscribe_frames = [f for f in received if f.get("event") == "pusher:subscribe"]
        assert subscribe_frames == [
            {"event": "pusher:subscribe", "data": {"channel": "chatrooms.999.v2"}}
        ]
        pong_frames = [f for f in received if f.get("event") == "pusher:pong"]
        assert len(pong_frames) == 1

    async def test_ready_log_uses_channel_and_chatroom(
        self,
        pusher_server: tuple[str, list[dict[str, Any]]],
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        ws_url, _received = pusher_server
        receiver = KickPusherReceiver()
        gen = receiver.receive({"channel_slug": "acme", "chatroom_id": 999, "ws_url": ws_url})
        with caplog.at_level("INFO", logger="receivers.kick_pusher"):
            await _drain(gen)
        assert any("gateway.kick_ready" in r.message for r in caplog.records)


@pytest.mark.usefixtures("_bypass_ssrf_guard_for_local_server")
class TestConnectionDropped:
    """Reconnect precedent: an ABNORMAL close raises `RetryableTransportError`, never hangs.

    `supervisor.ReceiverSupervisor`'s own restart-on-exit + backoff (not
    this receiver) is what actually reconnects -- see module docstring.
    Proving the generator terminates via a caught, typed exception
    (rather than blocking forever or raising something unclassified) is
    what makes that restart possible.
    """

    async def test_abnormal_close_raises_retryable(self, monkeypatch: pytest.MonkeyPatch) -> None:
        async def _handler(ws: Any) -> None:
            await ws.send(json.dumps({"event": "pusher:connection_established", "data": "{}"}))
            # 1011 ("internal error") is an ABNORMAL close code, distinct
            # from `pusher_server`'s own clean (1000) scripted disconnect
            # above -- proves `receive()` maps an unclean close to a
            # `RetryableTransportError`, not just to a silent generator end.
            await ws.close(code=1011, reason="simulated failure")

        server = await websockets.serve(_handler, "127.0.0.1", 0)
        port = server.sockets[0].getsockname()[1]
        try:
            receiver = KickPusherReceiver()
            gen = receiver.receive(
                {
                    "channel_slug": "acme",
                    "chatroom_id": 999,
                    "ws_url": f"ws://127.0.0.1:{port}",
                }
            )
            with pytest.raises(RetryableTransportError, match="kick pusher connection failed"):
                await _drain(gen)
        finally:
            server.close()
            await server.wait_closed()


class TestSsrfGuard:
    """Fail-first regression: the Pusher WS URL must go through the shared SSRF guard."""

    def _spy_connect(self, monkeypatch: pytest.MonkeyPatch) -> dict[str, int]:
        calls = {"n": 0}

        def _fail_if_called(*args: object, **kwargs: object) -> None:
            calls["n"] += 1
            raise AssertionError("websockets.connect must not be called -- SSRF guard failed")

        monkeypatch.setattr(websockets, "connect", _fail_if_called)
        return calls

    async def test_metadata_ip_ws_url_is_rejected(self, monkeypatch: pytest.MonkeyPatch) -> None:
        calls = self._spy_connect(monkeypatch)
        receiver = KickPusherReceiver()
        with pytest.raises(NonRetryableTransportError, match="SSRF"):
            async for _item in receiver.receive(
                {
                    "channel_slug": "acme",
                    "chatroom_id": 999,
                    "ws_url": "ws://169.254.169.254/x",
                }
            ):
                pass
        assert calls["n"] == 0

    async def test_loopback_ws_url_is_rejected(self, monkeypatch: pytest.MonkeyPatch) -> None:
        calls = self._spy_connect(monkeypatch)
        receiver = KickPusherReceiver()
        with pytest.raises(NonRetryableTransportError, match="SSRF"):
            async for _item in receiver.receive(
                {"channel_slug": "acme", "chatroom_id": 999, "ws_url": "ws://127.0.0.1:1/x"}
            ):
                pass
        assert calls["n"] == 0


class TestNormalizeChatMessage:
    """Direct unit coverage of `_normalize_chat_message`'s field derivation, off the wire."""

    def test_badges_derive_mod_subscriber_owner_flags(self) -> None:
        badges = [{"type": "moderator"}, {"type": "subscriber"}, {"type": "broadcaster"}]
        data = {
            "content": "hi",
            "id": "m1",
            "created_at": "2026-01-01T00:00:00Z",
            "sender": {"id": 1, "username": "bob", "identity": {"badges": badges}},
        }
        item = KickPusherReceiver._normalize_chat_message(data, "acme", 999)
        assert item is not None
        assert item["badges"] == ["moderator", "subscriber", "broadcaster"]
        assert item["is_mod"] is True
        assert item["is_subscriber"] is True
        assert item["is_owner"] is True

    def test_explicit_sender_flags_also_set_booleans_without_badges(self) -> None:
        data = {
            "content": "hi",
            "sender": {
                "id": 1,
                "username": "bob",
                "is_moderator": True,
                "is_subscriber": True,
                "is_channel_owner": True,
            },
        }
        item = KickPusherReceiver._normalize_chat_message(data, "acme", 999)
        assert item is not None
        assert item["badges"] == []
        assert item["is_mod"] is True
        assert item["is_subscriber"] is True
        assert item["is_owner"] is True

    def test_missing_content_returns_none(self) -> None:
        assert KickPusherReceiver._normalize_chat_message({"sender": {}}, "acme", 999) is None

    def test_empty_content_returns_none(self) -> None:
        assert KickPusherReceiver._normalize_chat_message({"content": ""}, "acme", 999) is None

    def test_missing_sender_defaults_author_fields_to_none(self) -> None:
        item = KickPusherReceiver._normalize_chat_message({"content": "hi"}, "acme", 999)
        assert item is not None
        assert item["author_id"] is None
        assert item["display_name"] is None
        assert item["badges"] == []
