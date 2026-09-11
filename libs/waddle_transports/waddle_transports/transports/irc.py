"""`irc` transport -- send/receive a chat message over a real IRC connection.

Generic IRC-protocol primitive (raw `asyncio` TCP/TLS socket, real
`PASS`/`NICK`/`USER`/`JOIN`/`PRIVMSG` wire protocol -- no third-party IRC
library) for any IRC-based chat connector. Twitch chat is the first
intended caller (Twitch's own chat protocol runs over IRC,
`irc.chat.twitch.tv:6697` TLS), though this transport makes no
Twitch-specific assumptions. **Not** a port of existing repo logic --
`action/pushing/twitch_action_module` already migrated off raw IRC onto
Twitch's Helix REST API (`services/twitch_service.py::send_chat_message`)
-- there is no IRC send code left in this repo to reuse; this is a new,
from-scratch, real IRC client.

`send()`: one connection per call (connect, auth, join, PRIVMSG, quit,
close) -- simpler and safer than a pooled/persistent connection for a
single outbound message.

`receive()`: one **persistent** connection for the duration of iteration
(connect, auth, join once, then read lines until the caller stops
iterating or the connection drops) -- yields one dict per `PRIVMSG` seen:
`{"channel": ..., "sender": ..., "text": ..., "tags": ...}`. Real IRC line
parsing (`:nick!user@host PRIVMSG #channel :message text`, optionally
prefixed with a raw IRCv3 `@tag1=val1;tag2=val2 ` message-tags segment
per the generic IRCv3.2 message-tags spec), not a stub. `tags` is the
**raw, unparsed** tag string (or `None` when the line carries none) --
this transport makes no Twitch-or-any-other-network-specific assumptions
about which tags exist or what they mean; per-network tag interpretation
(e.g. Twitch's `user-id`/`badges`/`mod` semantics) is the caller's job
(see `core/svc_ingest/receivers/twitch_irc.py`).

Callers wanting IRCv3 capabilities negotiated at connect (e.g. Twitch's
own `twitch.tv/tags`/`twitch.tv/commands`) pass `config["cap_requests"]`
-- an iterable of capability strings sent as one `CAP REQ :<space-joined>`
right after `NICK`/`USER`, before registration completes. Omitted/empty
means no `CAP REQ` is sent at all (unchanged prior behavior) -- this
transport itself has no opinion on which capabilities exist; it is purely
a generic IRCv3 CAP REQ mechanism, matching this module's own
Twitch-agnostic design.
"""

from __future__ import annotations

import asyncio
import re
import ssl as ssl_module
from collections.abc import AsyncIterator, Mapping
from typing import Any

from waddle_transports.base import (
    NonRetryableTransportError,
    RetryableTransportError,
    Transport,
    TransportResult,
)
from waddle_transports.signing import SecretResolutionError, resolve_secret
from waddle_transports.templating import render_template
from waddle_transports.types import Direction

_RPL_WELCOME = " 001 "
_REGISTRATION_REJECTED = (" 464 ", " 465 ")
#: Optional leading `@tag1=val1;tag2=val2 ` IRCv3 message-tags segment
#: (generic IRCv3.2 spec, RFC-agnostic to any specific network) captured
#: as the raw, unsplit `tags` group -- `None` when a line carries none.
_PRIVMSG_RE = re.compile(
    r"^(?:@(?P<tags>\S+) )?:(?P<prefix>\S+) PRIVMSG (?P<channel>\S+) :(?P<text>.*)$"
)

_DEFAULT_TIMEOUT_SECONDS = 10.0

#: CR, LF, and every other C0 control character (`\x00`-`\x1F`).
_CONTROL_CHARS_RE = re.compile(r"[\x00-\x1f]")


def sanitize_irc_component(value: str) -> str:
    r"""Strip CR/LF and other control chars (`\x00`-`\x1F`) before an IRC wire write.

    Applied to both the outgoing message text and the channel/target name
    -- either one written unsanitized lets a payload smuggle a second wire
    command (CRLF/command injection) or otherwise corrupt the line the
    server itself parses. Exported (not `_`-prefixed) so `irc_relay.py`'s
    queue-based send path -- which never writes to the wire directly, but
    whose queued value a drain loop elsewhere eventually does write as a
    real `PRIVMSG` -- can apply the identical sanitization as defense in
    depth.
    """
    return _CONTROL_CHARS_RE.sub("", value)


class IrcTransport(Transport):
    """`irc` transport -- no sub_type, both directions implemented."""

    name = "irc"
    directions = frozenset({Direction.OUTBOUND, Direction.INBOUND})

    async def send(self, config: Mapping[str, Any], payload: Mapping[str, Any]) -> TransportResult:
        """Connect, authenticate, join, PRIVMSG one message, quit, close."""
        timeout_seconds = float(config.get("timeout_seconds", _DEFAULT_TIMEOUT_SECONDS))
        body_template = config.get("body_template")
        message = (
            render_template(body_template, payload)
            if isinstance(body_template, str) and body_template
            else str(payload.get("text", ""))
        )
        message = sanitize_irc_component(message)
        if not message:
            raise NonRetryableTransportError(
                "irc target has no message to send (empty body_template/payload.text)"
            )

        reader, writer, channel = await self._connect_and_register(
            config, timeout_seconds=timeout_seconds
        )
        try:
            writer.write(f"PRIVMSG {channel} :{message}\r\n".encode())
            await writer.drain()
            writer.write(b"QUIT\r\n")
            await writer.drain()
        except (OSError, TimeoutError) as exc:
            raise RetryableTransportError(f"irc send failed: {exc}") from exc
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:  # noqa: BLE001, S110 -- best-effort clean close, never fatal
                pass

        host = config.get("host", "")
        port = config.get("port", 6697)
        return TransportResult(transport="irc", detail=f"sent to {channel} on {host}:{port}")

    async def receive(self, config: Mapping[str, Any]) -> AsyncIterator[Mapping[str, Any]]:
        """Connect once, join, then yield one dict per `PRIVMSG` seen until the connection drops."""
        timeout_seconds = float(config.get("timeout_seconds", _DEFAULT_TIMEOUT_SECONDS))
        max_messages = config.get("_max_messages")  # test-only escape hatch, see tests

        reader, writer, _channel = await self._connect_and_register(
            config, timeout_seconds=timeout_seconds
        )
        received = 0
        try:
            while True:
                line = await reader.readline()
                if not line:
                    return  # connection closed -- iteration simply ends
                text = line.decode("utf-8", errors="replace").strip()
                if text.startswith("PING"):
                    writer.write(f"PONG{text[4:]}\r\n".encode())
                    await writer.drain()
                    continue
                match = _PRIVMSG_RE.match(text)
                if match is None:
                    continue
                sender = match.group("prefix").split("!", 1)[0]
                yield {
                    "channel": match.group("channel"),
                    "sender": sender,
                    "text": match.group("text"),
                    "tags": match.group("tags"),
                }
                received += 1
                if max_messages is not None and received >= max_messages:
                    return
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:  # noqa: BLE001, S110 -- best-effort clean close, never fatal
                pass

    # --- shared connect+register -------------------------------------------

    async def _connect_and_register(
        self, config: Mapping[str, Any], *, timeout_seconds: float
    ) -> tuple[asyncio.StreamReader, asyncio.StreamWriter, str]:
        host = config.get("host")
        nick = config.get("nick")
        channel_raw = config.get("channel")
        if not isinstance(host, str) or not host:
            raise NonRetryableTransportError("irc config missing required 'host'")
        if not isinstance(nick, str) or not nick:
            raise NonRetryableTransportError("irc config missing required 'nick'")
        if not isinstance(channel_raw, str) or not channel_raw:
            raise NonRetryableTransportError("irc config missing required 'channel'")

        port = int(config.get("port", 6697))
        use_tls = bool(config.get("use_tls", True))
        password_ref = config.get("password_ref")

        password: str | None = None
        if password_ref:
            try:
                password = resolve_secret(str(password_ref))
            except SecretResolutionError as exc:
                raise NonRetryableTransportError(f"irc password resolution failed: {exc}") from exc

        ssl_context = ssl_module.create_default_context() if use_tls else None
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(host, port, ssl=ssl_context), timeout=timeout_seconds
            )
        except (OSError, TimeoutError) as exc:
            raise RetryableTransportError(f"irc connection to {host}:{port} failed: {exc}") from exc

        sanitized_channel = sanitize_irc_component(channel_raw)
        channel = (
            sanitized_channel
            if sanitized_channel.startswith("#")
            else f"#{sanitized_channel}"
        )
        cap_requests = config.get("cap_requests")

        try:
            if password:
                writer.write(f"PASS {password}\r\n".encode())
            writer.write(f"NICK {nick}\r\n".encode())
            writer.write(f"USER {nick} 0 * :{nick}\r\n".encode())
            if isinstance(cap_requests, (list, tuple, set, frozenset)) and cap_requests:
                caps = " ".join(str(cap) for cap in cap_requests)
                writer.write(f"CAP REQ :{caps}\r\n".encode())
            await writer.drain()
            await self._wait_for_registration(reader, timeout_seconds=timeout_seconds)
            writer.write(f"JOIN {channel}\r\n".encode())
            await writer.drain()
        except (OSError, TimeoutError) as exc:
            writer.close()
            raise RetryableTransportError(
                f"irc registration to {host}:{port} failed: {exc}"
            ) from exc

        return reader, writer, channel

    async def _wait_for_registration(
        self, reader: asyncio.StreamReader, *, timeout_seconds: float
    ) -> None:
        """Read lines until numeric 001 (RPL_WELCOME) or a registration-rejection reply."""

        async def _read_lines() -> None:
            while True:
                line = await reader.readline()
                if not line:
                    raise RetryableTransportError(
                        "irc connection closed before registration completed"
                    )
                text = line.decode("utf-8", errors="replace").strip()
                if _RPL_WELCOME in text:
                    return
                if text.startswith("ERROR") or any(code in text for code in _REGISTRATION_REJECTED):
                    raise NonRetryableTransportError(f"irc registration rejected: {text}")

        try:
            await asyncio.wait_for(_read_lines(), timeout=timeout_seconds)
        except TimeoutError as exc:
            raise RetryableTransportError(
                "irc registration timed out waiting for numeric 001"
            ) from exc
