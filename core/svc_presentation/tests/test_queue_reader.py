"""`MusicQueueReader` -- HTTP client, DTO mapping, caching, and stale-on-failure tests."""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from services.queue_reader import MusicQueueReader, PlaybackState, QueueSnapshot


class _FakeResponse:
    def __init__(self, status_code: int, json_body: Any) -> None:
        self.status_code = status_code
        self._json_body = json_body

    def json(self) -> Any:
        if isinstance(self._json_body, Exception):
            raise self._json_body
        return self._json_body


class _FakeClient:
    """Stand-in for `httpx.AsyncClient` -- records calls, returns a queued response."""

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


def _queue_item(
    *,
    item_id: int,
    status: str,
    title: str,
    artist: str,
    provider: str,
    external_id: str,
    position: int = 0,
    requested_by: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Build one hub-api `QueueItem` DTO entry."""
    return {
        "id": item_id,
        "position": position,
        "status": status,
        "title": title,
        "artist": artist,
        "duration_ms": 210000,
        "artwork_url": "https://example.com/art.jpg",
        "provider": provider,
        "external_id": external_id,
        "url": f"https://example.com/{provider}/{external_id}",
        "eta_seconds": 30,
        "started_at": "2026-09-11T00:00:00Z",
        "requested_by": requested_by,
    }


async def _connected_reader() -> tuple[MusicQueueReader, _FakeClient]:
    """A `MusicQueueReader` with a fake HTTP client swapped in post-`start()`."""
    reader = MusicQueueReader(hub_api_url="http://hub-api-test.invalid:8204", service_api_key="k")
    await reader.start()
    fake = _FakeClient()
    reader._client = fake  # type: ignore[assignment]
    return reader, fake


@pytest.mark.asyncio
async def test_start_without_service_key_stays_disconnected() -> None:
    """No `SERVICE_API_KEY` -- `connected` stays False, `get_queue` returns an empty snapshot."""
    reader = MusicQueueReader(hub_api_url="http://hub-api-test.invalid:8204", service_api_key="")
    await reader.start()
    assert reader.connected is False
    snapshot = await reader.get_queue(1)
    assert snapshot == QueueSnapshot(
        community_id=1, now_playing=None, upcoming=[], updated_at=None, stale=False
    )
    await reader.stop()


@pytest.mark.asyncio
async def test_start_with_service_key_connects() -> None:
    reader = MusicQueueReader(hub_api_url="http://hub-api-test.invalid:8204", service_api_key="k")
    await reader.start()
    assert reader.connected is True
    await reader.stop()


@pytest.mark.asyncio
async def test_get_queue_maps_dto_and_calls_correct_url_and_headers() -> None:
    reader, fake = await _connected_reader()
    fake.queue_get(
        _FakeResponse(
            200,
            {
                "status": "success",
                "data": {
                    "community_id": 42,
                    "now_playing": _queue_item(
                        item_id=1,
                        status="playing",
                        title="Song A",
                        artist="Artist A",
                        provider="spotify",
                        external_id="spotify123",
                        requested_by={"display_name": "viewer1", "platform": "twitch"},
                    ),
                    "queue": [
                        _queue_item(
                            item_id=2,
                            status="queued",
                            title="Song B",
                            artist="Artist B",
                            provider="youtube",
                            external_id="ytABC",
                            position=1,
                        )
                    ],
                    "updated_at": "2026-09-11T00:00:05Z",
                },
                "meta": {"version": 1},
            },
        )
    )

    snapshot = await reader.get_queue(42)

    assert len(fake.get_calls) == 1
    call = fake.get_calls[0]
    assert call["path"] == "/api/v1/internal/music/queue"
    assert call["params"] == {"community_id": 42}
    assert call["headers"] == {"X-Service-Key": "k"}

    assert snapshot.stale is False
    assert snapshot.now_playing is not None
    assert snapshot.now_playing.queue_id == 1
    assert snapshot.now_playing.provider == "spotify"
    assert snapshot.now_playing.external_id == "spotify123"
    assert snapshot.now_playing.name == "Song A"
    assert snapshot.now_playing.requested_by is not None
    assert snapshot.now_playing.requested_by.display_name == "viewer1"
    assert snapshot.now_playing.requested_by.platform == "twitch"
    assert len(snapshot.upcoming) == 1
    assert snapshot.upcoming[0].queue_id == 2
    assert snapshot.upcoming[0].provider == "youtube"


@pytest.mark.asyncio
async def test_get_queue_handles_null_now_playing_and_empty_queue() -> None:
    reader, fake = await _connected_reader()
    fake.queue_get(
        _FakeResponse(
            200,
            {
                "status": "success",
                "data": {
                    "community_id": 5,
                    "now_playing": None,
                    "queue": [],
                    "updated_at": None,
                },
            },
        )
    )
    snapshot = await reader.get_queue(5)
    assert snapshot.now_playing is None
    assert snapshot.upcoming == []
    assert snapshot.stale is False


@pytest.mark.asyncio
async def test_get_queue_maps_playback_state() -> None:
    """hub-api's `data.playback` -- `{paused, paused_since, position_ms}` -- passes through."""
    reader, fake = await _connected_reader()
    fake.queue_get(
        _FakeResponse(
            200,
            {
                "status": "success",
                "data": {
                    "now_playing": None,
                    "queue": [],
                    "updated_at": None,
                    "playback": {
                        "paused": True,
                        "paused_since": "2026-09-11T00:00:10Z",
                        "position_ms": 45000,
                    },
                },
            },
        )
    )

    snapshot = await reader.get_queue(20)

    assert snapshot.playback == PlaybackState(
        paused=True, paused_since="2026-09-11T00:00:10Z", position_ms=45000
    )


@pytest.mark.asyncio
async def test_get_queue_defaults_playback_when_missing_or_malformed() -> None:
    """No `playback` key (or a non-dict value) on the wire -- defaults to "playing"."""
    reader, fake = await _connected_reader()
    fake.queue_get(
        _FakeResponse(
            200,
            {"status": "success", "data": {"now_playing": None, "queue": [], "updated_at": None}},
        )
    )
    snapshot = await reader.get_queue(21)
    assert snapshot.playback == PlaybackState(paused=False, paused_since=None, position_ms=None)

    reader2, fake2 = await _connected_reader()
    fake2.queue_get(
        _FakeResponse(
            200,
            {
                "status": "success",
                "data": {
                    "now_playing": None,
                    "queue": [],
                    "updated_at": None,
                    "playback": "not-a-dict",
                },
            },
        )
    )
    snapshot2 = await reader2.get_queue(22)
    assert snapshot2.playback == PlaybackState(paused=False, paused_since=None, position_ms=None)


@pytest.mark.asyncio
async def test_get_queue_caches_within_ttl() -> None:
    """A second call inside `cache_ttl_seconds` doesn't hit the network again."""
    reader, fake = await _connected_reader()
    reader.cache_ttl_seconds = 60.0
    fake.queue_get(
        _FakeResponse(
            200,
            {"status": "success", "data": {"now_playing": None, "queue": [], "updated_at": None}},
        )
    )

    await reader.get_queue(7)
    await reader.get_queue(7)

    assert len(fake.get_calls) == 1


@pytest.mark.asyncio
async def test_get_queue_unreachable_returns_stale_cached_value() -> None:
    """A cached snapshot exists; the next fetch fails -- stale=True, cached data preserved."""
    reader, fake = await _connected_reader()
    reader.cache_ttl_seconds = 0.0  # force a real fetch every call
    fake.queue_get(
        _FakeResponse(
            200,
            {
                "status": "success",
                "data": {
                    "now_playing": _queue_item(
                        item_id=9,
                        status="playing",
                        title="Cached Song",
                        artist="X",
                        provider="youtube",
                        external_id="yt9",
                    ),
                    "queue": [],
                    "updated_at": "2026-09-11T00:00:00Z",
                },
            },
        )
    )
    first = await reader.get_queue(3)
    assert first.stale is False
    assert first.now_playing is not None

    fake.queue_get(httpx.ConnectError("connection refused"))
    second = await reader.get_queue(3)
    assert second.stale is True
    assert second.now_playing is not None
    assert second.now_playing.queue_id == 9


@pytest.mark.asyncio
async def test_get_queue_unreachable_with_no_cache_returns_empty() -> None:
    reader, fake = await _connected_reader()
    fake.queue_get(httpx.ReadTimeout("timed out"))

    snapshot = await reader.get_queue(11)

    assert snapshot.stale is False
    assert snapshot.now_playing is None
    assert snapshot.upcoming == []


@pytest.mark.asyncio
async def test_get_queue_non_2xx_treated_as_failure() -> None:
    reader, fake = await _connected_reader()
    fake.queue_get(_FakeResponse(401, {"error": "unauthorized"}))

    snapshot = await reader.get_queue(13)

    assert snapshot.now_playing is None
    assert snapshot.stale is False


@pytest.mark.asyncio
async def test_get_queue_malformed_json_treated_as_failure() -> None:
    reader, fake = await _connected_reader()
    fake.queue_get(_FakeResponse(200, ValueError("bad json")))

    snapshot = await reader.get_queue(14)

    assert snapshot.now_playing is None
    assert snapshot.stale is False


@pytest.mark.asyncio
async def test_get_queue_skips_malformed_upcoming_entries() -> None:
    """An entry with a missing/non-numeric `id` is skipped, not a crash or a bogus track."""
    reader, fake = await _connected_reader()
    fake.queue_get(
        _FakeResponse(
            200,
            {
                "status": "success",
                "data": {
                    "now_playing": None,
                    "queue": [
                        {"title": "no id field"},
                        {"id": "not-an-int"},
                        _queue_item(
                            item_id=3,
                            status="queued",
                            title="Valid",
                            artist="X",
                            provider="youtube",
                            external_id="yt3",
                        ),
                    ],
                    "updated_at": None,
                },
            },
        )
    )

    snapshot = await reader.get_queue(16)

    assert len(snapshot.upcoming) == 1
    assert snapshot.upcoming[0].queue_id == 3


@pytest.mark.asyncio
async def test_get_queue_missing_data_key_treated_as_failure() -> None:
    reader, fake = await _connected_reader()
    fake.queue_get(_FakeResponse(200, {"status": "success"}))

    snapshot = await reader.get_queue(15)

    assert snapshot.now_playing is None


@pytest.mark.asyncio
async def test_get_queue_not_connected_returns_empty_without_calling() -> None:
    reader = MusicQueueReader(hub_api_url="http://hub-api-test.invalid:8204", service_api_key="")
    await reader.start()
    fake = _FakeClient()
    reader._client = fake  # type: ignore[assignment]

    snapshot = await reader.get_queue(1)

    assert snapshot.now_playing is None
    assert fake.get_calls == []


@pytest.mark.asyncio
async def test_advance_posts_community_and_item_id_and_returns_advanced_flag() -> None:
    reader, fake = await _connected_reader()
    fake.queue_post(
        _FakeResponse(
            200,
            {
                "status": "success",
                "data": {
                    "now_playing": _queue_item(
                        item_id=2,
                        status="playing",
                        title="Next Song",
                        artist="Y",
                        provider="youtube",
                        external_id="yt2",
                    ),
                    "queue": [],
                    "updated_at": "2026-09-11T00:01:00Z",
                },
                "advanced": True,
            },
        )
    )

    advanced, snapshot = await reader.advance(42, 1)

    assert advanced is True
    assert snapshot is not None
    assert snapshot.now_playing is not None
    assert snapshot.now_playing.queue_id == 2
    call = fake.post_calls[0]
    assert call["path"] == "/api/v1/internal/music/queue/advance"
    assert call["json"] == {"community_id": 42, "item_id": 1}
    assert call["headers"] == {"X-Service-Key": "k"}


@pytest.mark.asyncio
async def test_advance_not_current_item_returns_advanced_false_with_snapshot() -> None:
    reader, fake = await _connected_reader()
    fake.queue_post(
        _FakeResponse(
            200,
            {
                "status": "success",
                "data": {"now_playing": None, "queue": [], "updated_at": None},
                "advanced": False,
            },
        )
    )

    advanced, snapshot = await reader.advance(42, 999)

    assert advanced is False
    assert snapshot is not None


@pytest.mark.asyncio
async def test_advance_unreachable_returns_false_none() -> None:
    reader, fake = await _connected_reader()
    fake.queue_post(httpx.ConnectError("connection refused"))

    advanced, snapshot = await reader.advance(42, 1)

    assert advanced is False
    assert snapshot is None


@pytest.mark.asyncio
async def test_advance_non_2xx_returns_false_none() -> None:
    reader, fake = await _connected_reader()
    fake.queue_post(_FakeResponse(404, {"error": "not found"}))

    advanced, snapshot = await reader.advance(42, 1)

    assert advanced is False
    assert snapshot is None


@pytest.mark.asyncio
async def test_advance_malformed_json_returns_false_none() -> None:
    reader, fake = await _connected_reader()
    fake.queue_post(_FakeResponse(200, ValueError("bad json")))

    advanced, snapshot = await reader.advance(42, 1)

    assert advanced is False
    assert snapshot is None


@pytest.mark.asyncio
async def test_advance_missing_data_key_returns_false_none() -> None:
    reader, fake = await _connected_reader()
    fake.queue_post(_FakeResponse(200, {"status": "success", "advanced": False}))

    advanced, snapshot = await reader.advance(42, 1)

    assert advanced is False
    assert snapshot is None


@pytest.mark.asyncio
async def test_advance_not_connected_returns_false_none_without_calling() -> None:
    reader = MusicQueueReader(hub_api_url="http://hub-api-test.invalid:8204", service_api_key="")
    await reader.start()
    fake = _FakeClient()
    reader._client = fake  # type: ignore[assignment]

    advanced, snapshot = await reader.advance(42, 1)

    assert advanced is False
    assert snapshot is None
    assert fake.post_calls == []
