"""Tests for `bundles.kick_ingest` -- `normalize()` + the Kick webhook verify/handler helpers."""

from __future__ import annotations

import hashlib
import hmac

import pytest
from flask_core import PlatformEvent

from bundles.kick_ingest import (
    CONSUMES_TAG,
    KICK_WEBHOOK_EVENT_TYPE_MAP,
    handle_kick_webhook,
    normalize,
    verify_kick_webhook_signature,
)

WEBHOOK_SECRET = "test-kick-webhook-secret"  # noqa: S105 - test literal, not a secret


def _sign(body: bytes, secret: str = WEBHOOK_SECRET) -> str:
    return hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()


class TestConsumesTag:
    def test_re_exported_from_the_receiver(self) -> None:
        assert CONSUMES_TAG == "kick.message"


class TestNormalize:
    async def test_normalizes_a_real_chat_message(self) -> None:
        raw = {
            "platform": "kick",
            "text": "  hello chat  ",
            "chatroom_id": 12345,
            "channel_slug": "acme",
            "author_id": "999",
            "display_name": "PenguinFan",
            "badges": ["moderator", "subscriber"],
            "is_mod": True,
            "is_subscriber": True,
            "is_owner": False,
            "message_id": "msg-abc",
            "created_at": "2026-09-11T12:00:00.000000Z",
        }
        event = await normalize(raw)

        assert isinstance(event, PlatformEvent)
        assert event.platform == "kick"
        assert event.event_type == "message"
        assert event.actor == "999"
        assert event.payload["text"] == "hello chat"
        assert event.payload["chatroom_id"] == 12345
        assert event.payload["channel_slug"] == "acme"
        assert event.payload["author_id"] == "999"
        assert event.payload["display_name"] == "PenguinFan"
        assert event.payload["badges"] == ["moderator", "subscriber"]
        assert event.payload["is_mod"] is True
        assert event.payload["is_subscriber"] is True
        assert event.payload["is_owner"] is False
        assert event.payload["message_id"] == "msg-abc"
        assert event.occurred_at == "2026-09-11T12:00:00.000000Z"

    async def test_missing_text_raises(self) -> None:
        with pytest.raises(ValueError, match="text"):
            await normalize({"chatroom_id": 1, "channel_slug": "acme"})

    async def test_missing_chatroom_id_raises(self) -> None:
        with pytest.raises(ValueError, match="chatroom_id"):
            await normalize({"text": "hi", "channel_slug": "acme"})

    async def test_missing_channel_slug_raises(self) -> None:
        with pytest.raises(ValueError, match="channel_slug"):
            await normalize({"text": "hi", "chatroom_id": 1})

    async def test_missing_optional_fields_default_absent_never_raise(self) -> None:
        raw = {"text": "hi", "chatroom_id": 1, "channel_slug": "acme"}
        event = await normalize(raw)

        assert event.actor is None
        assert event.payload["author_id"] is None
        assert event.payload["display_name"] is None
        assert event.payload["badges"] == []
        assert event.payload["is_mod"] is False
        assert event.payload["is_subscriber"] is False
        assert event.payload["is_owner"] is False
        assert event.payload["message_id"] is None
        assert event.occurred_at  # stamped with a UTC default

    async def test_non_list_badges_defaults_to_empty_list(self) -> None:
        raw = {"text": "hi", "chatroom_id": 1, "channel_slug": "acme", "badges": "not-a-list"}
        event = await normalize(raw)
        assert event.payload["badges"] == []

    async def test_falls_back_to_created_at_when_occurred_at_absent(self) -> None:
        raw = {
            "text": "hi",
            "chatroom_id": 1,
            "channel_slug": "acme",
            "created_at": "2026-01-01T00:00:00.000000Z",
        }
        event = await normalize(raw)
        assert event.occurred_at == "2026-01-01T00:00:00.000000Z"

    async def test_occurred_at_takes_precedence_over_created_at(self) -> None:
        raw = {
            "text": "hi",
            "chatroom_id": 1,
            "channel_slug": "acme",
            "created_at": "2026-01-01T00:00:00.000000Z",
            "occurred_at": "2026-02-02T00:00:00+00:00",
        }
        event = await normalize(raw)
        assert event.occurred_at == "2026-02-02T00:00:00+00:00"

    async def test_string_chatroom_id_is_accepted(self) -> None:
        raw = {"text": "hi", "chatroom_id": "12345", "channel_slug": "acme"}
        event = await normalize(raw)
        assert event.payload["chatroom_id"] == "12345"

    async def test_zero_chatroom_id_is_accepted_not_treated_as_missing(self) -> None:
        """`0` is a falsy int but a structurally valid chatroom id -- must not raise."""
        raw = {"text": "hi", "chatroom_id": 0, "channel_slug": "acme"}
        event = await normalize(raw)
        assert event.payload["chatroom_id"] == 0


class TestVerifyKickWebhookSignature:
    def test_valid_signature_verifies(self) -> None:
        body = b'{"type":"StreamStart"}'
        assert verify_kick_webhook_signature(body, _sign(body), WEBHOOK_SECRET) is True

    def test_invalid_signature_fails(self) -> None:
        body = b'{"type":"StreamStart"}'
        result = verify_kick_webhook_signature(body, "not-the-real-signature", WEBHOOK_SECRET)
        assert result is False

    def test_missing_signature_fails_closed(self) -> None:
        body = b'{"type":"StreamStart"}'
        assert verify_kick_webhook_signature(body, "", WEBHOOK_SECRET) is False

    def test_signature_for_different_body_fails(self) -> None:
        signature = _sign(b'{"type":"StreamStart"}')
        result = verify_kick_webhook_signature(b'{"type":"StreamEnd"}', signature, WEBHOOK_SECRET)
        assert result is False


class TestHandleKickWebhook:
    async def test_unconfigured_secret_returns_503_without_verifying(self) -> None:
        body = b'{"type":"StreamStart"}'
        response, status = await handle_kick_webhook(
            {"X-Kick-Signature": _sign(body)}, body, {"type": "StreamStart"}, secret=""
        )
        assert status == 503
        assert "error" in response

    async def test_invalid_signature_returns_401(self) -> None:
        body = b'{"type":"StreamStart"}'
        response, status = await handle_kick_webhook(
            {"X-Kick-Signature": "bad"}, body, {"type": "StreamStart"}, secret=WEBHOOK_SECRET
        )
        assert status == 401
        assert "error" in response

    async def test_missing_signature_header_returns_401(self) -> None:
        body = b'{"type":"StreamStart"}'
        response, status = await handle_kick_webhook(
            {}, body, {"type": "StreamStart"}, secret=WEBHOOK_SECRET
        )
        assert status == 401
        assert "error" in response

    @pytest.mark.parametrize(
        ("kick_type", "mapped_type"), sorted(KICK_WEBHOOK_EVENT_TYPE_MAP.items())
    )
    async def test_every_known_event_type_maps_correctly(
        self, kick_type: str, mapped_type: str
    ) -> None:
        body = f'{{"type":"{kick_type}"}}'.encode()
        response, status = await handle_kick_webhook(
            {"X-Kick-Signature": _sign(body)},
            body,
            {"type": kick_type},
            secret=WEBHOOK_SECRET,
        )
        assert status == 200
        assert response == {"received": True, "event_type": mapped_type}

    async def test_unknown_event_type_maps_to_unknown_not_rejected(self) -> None:
        body = b'{"type":"SomeFutureEventType"}'
        response, status = await handle_kick_webhook(
            {"X-Kick-Signature": _sign(body)},
            body,
            {"type": "SomeFutureEventType"},
            secret=WEBHOOK_SECRET,
        )
        assert status == 200
        assert response == {"received": True, "event_type": "unknown"}

    async def test_missing_type_field_maps_to_unknown(self) -> None:
        body = b"{}"
        response, status = await handle_kick_webhook(
            {"X-Kick-Signature": _sign(body)}, body, {}, secret=WEBHOOK_SECRET
        )
        assert status == 200
        assert response == {"received": True, "event_type": "unknown"}
