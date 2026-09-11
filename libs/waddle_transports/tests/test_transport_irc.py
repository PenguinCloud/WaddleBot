"""transports/irc.py -- real IRC protocol over a real local asyncio TCP server.

No mocking of the transport itself -- only the "server" side is a
lightweight in-test stub speaking the minimal real IRC wire protocol this
transport depends on (numeric 001 on successful registration, PRIVMSG
lines), over a genuine loopback TCP socket.
"""

from __future__ import annotations

import asyncio

import pytest

from waddle_transports.base import NonRetryableTransportError, RetryableTransportError
from waddle_transports.transports.irc import IrcTransport


class _FakeIrcServer:
    """A minimal, real asyncio TCP server speaking just enough IRC to test against.

    `push_privmsg_after_join`, when set, writes one real `PRIVMSG` line
    back down the same connection immediately after seeing the client's
    `JOIN` -- mirrors how a real IRC server relays a channel message to an
    already-joined client, letting `TestReceive` exercise a genuine
    end-to-end read without any mocking of the transport's own parsing.
    """

    def __init__(self, *, reject: bool = False, push_privmsg_after_join: str | None = None) -> None:
        self.reject = reject
        self.push_privmsg_after_join = push_privmsg_after_join
        self.received_lines: list[str] = []
        self._server: asyncio.AbstractServer | None = None
        self.port: int = 0
        # `send()`'s client-side `writer.close()`/`wait_closed()` only
        # guarantees the *local* socket finished closing -- it says
        # nothing about whether this server's own `_handle` task has been
        # scheduled to actually read+record the already-flushed JOIN/
        # PRIVMSG/QUIT bytes yet (cooperative asyncio scheduling, no
        # synchronous cross-task guarantee). Tests await this event
        # (set right before the server itself closes on QUIT) instead of
        # racing `received_lines` immediately after `send()` returns.
        self.quit_seen = asyncio.Event()

    async def start(self) -> None:
        self._server = await asyncio.start_server(self._handle, "127.0.0.1", 0)
        self.port = self._server.sockets[0].getsockname()[1]

    async def stop(self) -> None:
        assert self._server is not None
        self._server.close()
        await self._server.wait_closed()

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            while True:
                line = await reader.readline()
                if not line:
                    return
                text = line.decode("utf-8", errors="replace").strip()
                self.received_lines.append(text)
                if text.startswith("NICK"):
                    if self.reject:
                        writer.write(b":server 464 * :Password incorrect\r\n")
                    else:
                        writer.write(b":server 001 nick :Welcome to the network\r\n")
                    await writer.drain()
                if text.startswith("JOIN") and self.push_privmsg_after_join is not None:
                    writer.write(self.push_privmsg_after_join.encode() + b"\r\n")
                    await writer.drain()
                if text == "QUIT":
                    self.quit_seen.set()
                    writer.close()
                    return
        except (ConnectionResetError, asyncio.IncompleteReadError):
            return


@pytest.fixture
async def fake_irc_server():
    server = _FakeIrcServer()
    await server.start()
    yield server
    await server.stop()


@pytest.fixture
async def rejecting_irc_server():
    server = _FakeIrcServer(reject=True)
    await server.start()
    yield server
    await server.stop()


def _config(server, **overrides: object) -> dict:  # noqa: ANN001
    base = {
        "host": "127.0.0.1",
        "port": server.port,
        "nick": "waddlebot",
        "channel": "testchannel",
        "use_tls": False,
        "timeout_seconds": 5.0,
    }
    base.update(overrides)
    return base


class TestSend:
    async def test_real_registration_join_and_privmsg(self, fake_irc_server) -> None:
        transport = IrcTransport()
        result = await transport.send(_config(fake_irc_server), {"text": "hello chat"})
        await asyncio.wait_for(fake_irc_server.quit_seen.wait(), timeout=3.0)

        assert result.transport == "irc"
        assert "NICK waddlebot" in fake_irc_server.received_lines
        assert "JOIN #testchannel" in fake_irc_server.received_lines
        assert "PRIVMSG #testchannel :hello chat" in fake_irc_server.received_lines
        assert "QUIT" in fake_irc_server.received_lines

    async def test_channel_hash_is_normalized(self, fake_irc_server) -> None:
        transport = IrcTransport()
        await transport.send(_config(fake_irc_server, channel="#already-hashed"), {"text": "hi"})
        await asyncio.wait_for(fake_irc_server.quit_seen.wait(), timeout=3.0)
        assert "JOIN #already-hashed" in fake_irc_server.received_lines

    async def test_body_template_rendered_against_payload(self, fake_irc_server) -> None:
        transport = IrcTransport()
        await transport.send(
            _config(fake_irc_server, body_template="raid from {{raider}}!"), {"raider": "bob"}
        )
        await asyncio.wait_for(fake_irc_server.quit_seen.wait(), timeout=3.0)
        assert "PRIVMSG #testchannel :raid from bob!" in fake_irc_server.received_lines

    async def test_empty_message_is_non_retryable(self, fake_irc_server) -> None:
        transport = IrcTransport()
        with pytest.raises(NonRetryableTransportError, match="no message to send"):
            await transport.send(_config(fake_irc_server), {})

    async def test_registration_rejected_is_non_retryable(self, rejecting_irc_server) -> None:
        transport = IrcTransport()
        with pytest.raises(NonRetryableTransportError, match="registration rejected"):
            await transport.send(_config(rejecting_irc_server), {"text": "hi"})

    async def test_connection_refused_is_retryable(self) -> None:
        transport = IrcTransport()
        with pytest.raises(RetryableTransportError, match="connection"):
            await transport.send(
                {
                    "host": "127.0.0.1",
                    "port": 1,
                    "nick": "b",
                    "channel": "c",
                    "use_tls": False,
                    "timeout_seconds": 2.0,
                },
                {"text": "hi"},
            )

    async def test_missing_host_is_non_retryable(self) -> None:
        transport = IrcTransport()
        with pytest.raises(NonRetryableTransportError, match="host"):
            await transport.send({"nick": "b", "channel": "c"}, {"text": "hi"})

    async def test_crlf_in_message_cannot_inject_a_second_command(
        self, fake_irc_server
    ) -> None:
        r"""Fail-first regression for IRC CRLF/command injection.

        A payload smuggling `\r\n` must yield exactly ONE PRIVMSG line and
        zero injected commands -- CRLF/control chars stripped before the
        wire write, never written verbatim.
        """
        transport = IrcTransport()
        result = await transport.send(_config(fake_irc_server), {"text": "hi\r\nQUIT\r\n"})
        await asyncio.wait_for(fake_irc_server.quit_seen.wait(), timeout=3.0)

        assert result.transport == "irc"
        privmsg_lines = [
            line for line in fake_irc_server.received_lines if line.startswith("PRIVMSG")
        ]
        assert len(privmsg_lines) == 1
        assert privmsg_lines[0] == "PRIVMSG #testchannel :hiQUIT"
        # Only the transport's own trailing QUIT -- no injected extra one.
        assert fake_irc_server.received_lines.count("QUIT") == 1

    async def test_crlf_in_channel_cannot_inject_a_second_line(self, fake_irc_server) -> None:
        r"""Fail-first regression for IRC CRLF/command injection via `channel`.

        A `channel` value smuggling `\r\n` must not create an extra JOIN/
        PRIVMSG line on the wire.
        """
        transport = IrcTransport()
        await transport.send(
            _config(fake_irc_server, channel="testchannel\r\nPRIVMSG #eviltarget :pwned"),
            {"text": "hi"},
        )
        await asyncio.wait_for(fake_irc_server.quit_seen.wait(), timeout=3.0)

        join_lines = [line for line in fake_irc_server.received_lines if line.startswith("JOIN")]
        privmsg_lines = [
            line for line in fake_irc_server.received_lines if line.startswith("PRIVMSG")
        ]
        assert len(join_lines) == 1
        assert len(privmsg_lines) == 1
        assert fake_irc_server.received_lines.count("QUIT") == 1


class TestReceive:
    async def test_yields_a_real_privmsg(self) -> None:
        server = _FakeIrcServer(
            push_privmsg_after_join=":alice!alice@host PRIVMSG #testchannel :hello there"
        )
        await server.start()
        try:
            transport = IrcTransport()
            items = [item async for item in transport.receive(_config(server, _max_messages=1))]
        finally:
            await server.stop()

        assert items == [
            {"channel": "#testchannel", "sender": "alice", "text": "hello there", "tags": None}
        ]

    async def test_yields_raw_tags_string_when_present(self) -> None:
        """A leading `@tag=val;...` segment is captured raw (unsplit) as `tags`."""
        raw_tags = "badges=moderator/1;display-name=Alice;id=abc-123;mod=1;user-id=12345"
        server = _FakeIrcServer(
            push_privmsg_after_join=f"@{raw_tags} :alice!alice@host PRIVMSG #testchannel :hi"
        )
        await server.start()
        try:
            transport = IrcTransport()
            items = [item async for item in transport.receive(_config(server, _max_messages=1))]
        finally:
            await server.stop()

        assert items == [
            {"channel": "#testchannel", "sender": "alice", "text": "hi", "tags": raw_tags}
        ]

    async def test_stops_iterating_after_max_messages(self) -> None:
        server = _FakeIrcServer(
            push_privmsg_after_join=":alice!alice@host PRIVMSG #testchannel :hello there"
        )
        await server.start()
        try:
            transport = IrcTransport()
            items = [item async for item in transport.receive(_config(server, _max_messages=1))]
        finally:
            await server.stop()
        assert len(items) == 1

    async def test_missing_channel_is_non_retryable(self, fake_irc_server) -> None:
        transport = IrcTransport()
        with pytest.raises(NonRetryableTransportError, match="channel"):
            async for _item in transport.receive(_config(fake_irc_server, channel=None)):
                pass


class TestCapRequests:
    """`config["cap_requests"]` -- generic IRCv3 CAP REQ negotiation, no Twitch knowledge."""

    async def test_cap_req_sent_when_configured(self, fake_irc_server) -> None:
        transport = IrcTransport()
        await transport.send(
            _config(fake_irc_server, cap_requests=["twitch.tv/tags", "twitch.tv/commands"]),
            {"text": "hi"},
        )
        await asyncio.wait_for(fake_irc_server.quit_seen.wait(), timeout=3.0)
        assert "CAP REQ :twitch.tv/tags twitch.tv/commands" in fake_irc_server.received_lines

    async def test_cap_req_sent_after_user_before_join(self, fake_irc_server) -> None:
        transport = IrcTransport()
        await transport.send(_config(fake_irc_server, cap_requests=["some.cap"]), {"text": "hi"})
        await asyncio.wait_for(fake_irc_server.quit_seen.wait(), timeout=3.0)
        lines = fake_irc_server.received_lines
        assert lines.index("USER waddlebot 0 * :waddlebot") < lines.index("CAP REQ :some.cap")
        assert lines.index("CAP REQ :some.cap") < lines.index("JOIN #testchannel")

    async def test_no_cap_req_when_absent(self, fake_irc_server) -> None:
        """Unchanged prior behavior -- omitted `cap_requests` sends no `CAP` line at all."""
        transport = IrcTransport()
        await transport.send(_config(fake_irc_server), {"text": "hi"})
        await asyncio.wait_for(fake_irc_server.quit_seen.wait(), timeout=3.0)
        assert not any(line.startswith("CAP") for line in fake_irc_server.received_lines)

    async def test_empty_cap_requests_sends_no_cap_line(self, fake_irc_server) -> None:
        transport = IrcTransport()
        await transport.send(_config(fake_irc_server, cap_requests=[]), {"text": "hi"})
        await asyncio.wait_for(fake_irc_server.quit_seen.wait(), timeout=3.0)
        assert not any(line.startswith("CAP") for line in fake_irc_server.received_lines)
