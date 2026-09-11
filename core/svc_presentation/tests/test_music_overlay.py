"""Music Station player page + its `/music/queue` JSON read and `/music/advance` proxy."""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import replace
from typing import Any

import httpx
import pytest
import pytest_asyncio
from quart.typing import TestClientProtocol

from app import create_app
from config import Config
from services.queue_reader import MusicQueueReader


class _FakeResponse:
    def __init__(self, status_code: int, json_body: Any) -> None:
        self.status_code = status_code
        self._json_body = json_body

    def json(self) -> Any:
        return self._json_body


class _FakeClient:
    def __init__(self) -> None:
        self.get_calls: list[dict[str, Any]] = []
        self.post_calls: list[dict[str, Any]] = []
        self._get_response: _FakeResponse | Exception = _FakeResponse(200, {})
        self._post_response: _FakeResponse | Exception = _FakeResponse(200, {})

    def queue_get(self, response: _FakeResponse | Exception) -> None:
        self._get_response = response

    def queue_post(self, response: _FakeResponse | Exception) -> None:
        self._post_response = response

    async def get(self, path: str, **kwargs: Any) -> _FakeResponse:
        self.get_calls.append({"path": path, **kwargs})
        if isinstance(self._get_response, Exception):
            raise self._get_response
        return self._get_response

    async def post(self, path: str, **kwargs: Any) -> _FakeResponse:
        self.post_calls.append({"path": path, **kwargs})
        if isinstance(self._post_response, Exception):
            raise self._post_response
        return self._post_response

    async def aclose(self) -> None:
        return None


def _dto_item(
    *,
    item_id: int,
    status: str,
    title: str,
    artist: str,
    provider: str,
    external_id: str,
    requested_by: dict[str, str] | None,
) -> dict[str, Any]:
    return {
        "id": item_id,
        "position": 0,
        "status": status,
        "title": title,
        "artist": artist,
        "duration_ms": 180000,
        "artwork_url": "https://example.com/art.jpg",
        "provider": provider,
        "external_id": external_id,
        "url": f"https://example.com/{provider}/{external_id}",
        "eta_seconds": 0,
        "started_at": "2026-09-11T00:00:00Z",
        "requested_by": requested_by,
    }


@pytest.mark.asyncio
async def test_music_page_renders_html_with_playback_hooks(client: TestClientProtocol) -> None:
    """The Music Station page wires the YouTube ENDED handler, Spotify controller, and advance."""
    response = await client.get("/overlay/testcommunity/music")
    assert response.status_code == 200
    assert response.headers["Content-Type"].startswith("text/html")
    body = await response.get_data(as_text=True)
    assert "<!DOCTYPE html>" in body
    assert "youtube.com/iframe_api" in body
    assert "open.spotify.com/embed/iframe-api/v1" in body
    assert "/overlay/${community}/music/queue" in body
    assert "/overlay/${community}/music/advance" in body
    assert "YT.PlayerState.ENDED" in body
    assert "onStateChange" in body
    assert "playback_update" in body
    assert "testcommunity" in body
    # Playback pause/resume/seek wiring (issue #315): embed pause/resume
    # calls, the resume-time seek, the paused badge markup, and the
    # paused-guard on both ended handlers (never advance while paused).
    assert "pauseVideo" in body
    assert "playVideo" in body
    assert "seekTo" in body
    assert "np-paused-badge" in body
    assert "⏸ paused" in body
    assert "event.data === YT.PlayerState.ENDED && !isPaused" in body
    assert "!isPaused &&" in body


@pytest.mark.asyncio
async def test_music_page_invalid_community_rejected(client: TestClientProtocol) -> None:
    response = await client.get("/overlay/%3Cscript%3E/music")
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_music_page_disabled_surface_returns_404(client: TestClientProtocol) -> None:
    """A `music` row with `enabled=False` blocks the player page for that community."""
    app = client.app
    async_dal, dal = app.config["async_dal"], app.config["dal"]
    await async_dal.insert_async(
        dal.overlay_surfaces, community_id=77, surface="music", enabled=False
    )
    response = await client.get("/overlay/77/music")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_queue_endpoint_unavailable_when_service_key_not_configured(
    client: TestClientProtocol,
) -> None:
    """No `SERVICE_API_KEY` (the default test posture) -- honest unavailability, never a 500."""
    response = await client.get("/overlay/99/music/queue")
    assert response.status_code == 200
    payload = await response.get_json()
    assert payload["available"] is False
    assert payload["unavailable_reason"] == "service_key_not_configured"
    assert payload["now_playing"] is None
    assert payload["upcoming"] == []
    assert payload["playback"] == {"paused": False, "paused_since": None, "position_ms": None}


@pytest.mark.asyncio
async def test_queue_endpoint_invalid_community_rejected(client: TestClientProtocol) -> None:
    response = await client.get("/overlay/%3Cscript%3E/music/queue")
    assert response.status_code == 400


@pytest_asyncio.fixture
async def keyed_client(
    test_config: Config,
) -> AsyncIterator[tuple[TestClientProtocol, _FakeClient]]:
    """A running app with `service_api_key` configured, its `MusicQueueReader` HTTP-mocked."""
    keyed_config = replace(test_config, service_api_key="test-service-key")
    app = create_app(keyed_config)
    async with app.test_app() as running:
        reader: MusicQueueReader = app.config["MUSIC_QUEUE_READER"]
        fake = _FakeClient()
        reader._client = fake  # type: ignore[attr-defined]
        yield running.test_client(), fake


@pytest.mark.asyncio
async def test_queue_endpoint_unresolvable_slug_reports_unavailable(
    keyed_client: tuple[TestClientProtocol, _FakeClient],
) -> None:
    """A service key IS configured, but the community slug isn't numeric -- can't resolve."""
    test_client, _fake = keyed_client
    response = await test_client.get("/overlay/testcommunity/music/queue")
    assert response.status_code == 200
    payload = await response.get_json()
    assert payload["available"] is False
    assert payload["unavailable_reason"] == "community_not_resolvable"


@pytest.mark.asyncio
async def test_queue_endpoint_proxies_hub_api_and_maps_dto(
    keyed_client: tuple[TestClientProtocol, _FakeClient],
) -> None:
    test_client, fake = keyed_client
    fake.queue_get(
        _FakeResponse(
            200,
            {
                "status": "success",
                "data": {
                    "community_id": 42,
                    "now_playing": _dto_item(
                        item_id=1,
                        status="playing",
                        title="Song A",
                        artist="Artist A",
                        provider="spotify",
                        external_id="spotify123",
                        requested_by={"display_name": "viewer1", "platform": "twitch"},
                    ),
                    "queue": [
                        _dto_item(
                            item_id=2,
                            status="queued",
                            title="Song B",
                            artist="Artist B",
                            provider="youtube",
                            external_id="ytABC",
                            requested_by=None,
                        )
                    ],
                    "updated_at": "2026-09-11T00:00:05Z",
                    "playback": {
                        "paused": True,
                        "paused_since": "2026-09-11T00:00:10Z",
                        "position_ms": 12000,
                    },
                },
            },
        )
    )

    response = await test_client.get("/overlay/42/music/queue")
    assert response.status_code == 200
    payload = await response.get_json()

    assert payload["available"] is True
    assert payload["now_playing"]["queue_id"] == 1
    assert payload["now_playing"]["provider"] == "spotify"
    assert payload["now_playing"]["external_id"] == "spotify123"
    assert payload["now_playing"]["requested_by"] == {
        "display_name": "viewer1",
        "platform": "twitch",
    }
    assert len(payload["upcoming"]) == 1
    assert payload["upcoming"][0]["provider"] == "youtube"
    assert payload["upcoming"][0]["external_id"] == "ytABC"
    assert payload["upcoming"][0]["requested_by"] is None
    assert payload["playback"] == {
        "paused": True,
        "paused_since": "2026-09-11T00:00:10Z",
        "position_ms": 12000,
    }

    call = fake.get_calls[0]
    assert call["params"] == {"community_id": 42}
    assert call["headers"] == {"X-Service-Key": "test-service-key"}


@pytest.mark.asyncio
async def test_queue_endpoint_hub_api_unreachable_returns_empty_not_500(
    keyed_client: tuple[TestClientProtocol, _FakeClient],
) -> None:
    test_client, fake = keyed_client
    fake.queue_get(httpx.ConnectError("connection refused"))

    response = await test_client.get("/overlay/42/music/queue")
    assert response.status_code == 200
    payload = await response.get_json()
    assert payload["available"] is True
    assert payload["now_playing"] is None
    assert payload["stale"] is False


@pytest.mark.asyncio
async def test_advance_requires_item_id(
    keyed_client: tuple[TestClientProtocol, _FakeClient],
) -> None:
    test_client, _fake = keyed_client
    response = await test_client.post("/overlay/42/music/advance", json={})
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_advance_rejects_invalid_community(client: TestClientProtocol) -> None:
    response = await client.post("/overlay/%3Cscript%3E/music/advance", json={"item_id": 1})
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_advance_without_service_key_returns_503(client: TestClientProtocol) -> None:
    response = await client.post("/overlay/42/music/advance", json={"item_id": 1})
    assert response.status_code == 503


@pytest.mark.asyncio
async def test_advance_disabled_surface_returns_404(
    keyed_client: tuple[TestClientProtocol, _FakeClient],
) -> None:
    test_client, _fake = keyed_client
    app = test_client.app
    async_dal, dal = app.config["async_dal"], app.config["dal"]
    await async_dal.insert_async(
        dal.overlay_surfaces, community_id=88, surface="music", enabled=False
    )
    response = await test_client.post("/overlay/88/music/advance", json={"item_id": 1})
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_advance_unresolvable_slug_returns_400(
    keyed_client: tuple[TestClientProtocol, _FakeClient],
) -> None:
    test_client, _fake = keyed_client
    response = await test_client.post("/overlay/testcommunity/music/advance", json={"item_id": 1})
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_advance_proxies_to_hub_api_and_returns_advanced_flag(
    keyed_client: tuple[TestClientProtocol, _FakeClient],
) -> None:
    test_client, fake = keyed_client
    fake.queue_post(
        _FakeResponse(
            200,
            {
                "status": "success",
                "data": {
                    "now_playing": _dto_item(
                        item_id=2,
                        status="playing",
                        title="Song B",
                        artist="Artist B",
                        provider="youtube",
                        external_id="ytABC",
                        requested_by=None,
                    ),
                    "queue": [],
                    "updated_at": "2026-09-11T00:01:00Z",
                },
                "advanced": True,
            },
        )
    )

    response = await test_client.post("/overlay/42/music/advance", json={"item_id": 1})
    assert response.status_code == 200
    payload = await response.get_json()
    assert payload["advanced"] is True
    assert payload["now_playing"]["queue_id"] == 2

    call = fake.post_calls[0]
    assert call["json"] == {"community_id": 42, "item_id": 1}
    assert call["headers"] == {"X-Service-Key": "test-service-key"}


@pytest.mark.asyncio
async def test_advance_hub_api_unreachable_returns_502(
    keyed_client: tuple[TestClientProtocol, _FakeClient],
) -> None:
    test_client, fake = keyed_client
    fake.queue_post(httpx.ConnectError("connection refused"))

    response = await test_client.post("/overlay/42/music/advance", json={"item_id": 1})
    assert response.status_code == 502
