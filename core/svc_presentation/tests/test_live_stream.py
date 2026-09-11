"""Live-stream (HLS) player page + its `/live/status` JSON proxy."""

from __future__ import annotations

from typing import Any

import httpx
import pytest
from quart.typing import TestClientProtocol

import blueprints.live_stream as live_stream


class _FakeResponse:
    def __init__(self, status_code: int, json_body: Any) -> None:
        self.status_code = status_code
        self._json_body = json_body

    def json(self) -> Any:
        return self._json_body


class _FakeAsyncClient:
    """Stand-in for `httpx.AsyncClient` as an async context manager."""

    def __init__(self, response: _FakeResponse | None = None, exc: Exception | None = None) -> None:
        self._response = response
        self._exc = exc
        self.get_calls: list[str] = []

    async def __aenter__(self) -> _FakeAsyncClient:
        return self

    async def __aexit__(self, *exc_info: Any) -> None:
        return None

    async def get(self, url: str, **kwargs: Any) -> _FakeResponse:
        self.get_calls.append(url)
        if self._exc is not None:
            raise self._exc
        assert self._response is not None
        return self._response


def _patch_client(monkeypatch: pytest.MonkeyPatch, client: _FakeAsyncClient) -> None:
    monkeypatch.setattr(live_stream.httpx, "AsyncClient", lambda **kwargs: client)


@pytest.mark.asyncio
async def test_live_route_invalid_community_is_400(client: TestClientProtocol) -> None:
    """A malformed `community` segment is rejected before any renderer/fetch."""
    response = await client.get("/overlay/%3Cscript%3E/live")
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_live_route_renders_html_with_pinned_hlsjs_and_offline_badge(
    client: TestClientProtocol,
) -> None:
    """Non-numeric community can't resolve to a `community_id` -- renders offline, no crash."""
    response = await client.get("/overlay/testcommunity/live")
    assert response.status_code == 200
    assert response.headers["Content-Type"].startswith("text/html")
    body = await response.get_data(as_text=True)
    assert "<!DOCTYPE html>" in body
    assert "https://cdnjs.cloudflare.com/ajax/libs/hls.js/1.5.13/hls.min.js" in body
    assert 'id="badge"' in body
    assert "offline" in body
    assert "/overlay/${community}/live/status" in body
    assert "testcommunity" in body


@pytest.mark.asyncio
async def test_live_route_embeds_master_url_when_pipeline_running(
    client: TestClientProtocol, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A resolvable community with a running pipeline renders `live=true` and the master URL."""
    fake = _FakeAsyncClient(
        response=_FakeResponse(
            200,
            {
                "pipelines": [
                    {
                        "id": "11111111-1111-1111-1111-111111111111",
                        "profile": "1080p60",
                        "url": "/live/42/11111111-1111-1111-1111-111111111111/1080p60/master.m3u8",
                        "started_at": "2026-09-11T00:00:00Z",
                    }
                ]
            },
        )
    )
    _patch_client(monkeypatch, fake)
    monkeypatch.setenv("PUBLIC_STREAMING_URL", "https://streaming.example.com")

    response = await client.get("/overlay/42/live")
    assert response.status_code == 200
    body = await response.get_data(as_text=True)
    assert (
        "https://streaming.example.com/live/42/11111111-1111-1111-1111-111111111111"
        "/1080p60/master.m3u8" in body
    )
    assert "setLive(true)" in body
    assert fake.get_calls == ["http://svc-streaming:8208/live/42"]


@pytest.mark.asyncio
async def test_status_endpoint_returns_offline_when_svc_streaming_unreachable(
    client: TestClientProtocol, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An unreachable svc-streaming degrades to `{live: false, pipelines: []}`, never a 500."""
    _patch_client(monkeypatch, _FakeAsyncClient(exc=httpx.ConnectError("boom")))
    response = await client.get("/overlay/42/live/status")
    assert response.status_code == 200
    payload = await response.get_json()
    assert payload == {"live": False, "pipelines": []}


@pytest.mark.asyncio
async def test_status_endpoint_returns_offline_for_non_200(
    client: TestClientProtocol, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A non-2xx svc-streaming response degrades to offline, not an error passthrough."""
    _patch_client(monkeypatch, _FakeAsyncClient(response=_FakeResponse(503, {"pipelines": []})))
    response = await client.get("/overlay/42/live/status")
    assert response.status_code == 200
    payload = await response.get_json()
    assert payload == {"live": False, "pipelines": []}


@pytest.mark.asyncio
async def test_status_endpoint_returns_offline_for_malformed_payload(
    client: TestClientProtocol, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A `pipelines` field that isn't a list is treated as malformed, not trusted."""
    _patch_client(monkeypatch, _FakeAsyncClient(response=_FakeResponse(200, {"pipelines": "nope"})))
    response = await client.get("/overlay/42/live/status")
    assert response.status_code == 200
    payload = await response.get_json()
    assert payload == {"live": False, "pipelines": []}


@pytest.mark.asyncio
async def test_status_endpoint_live_true_with_normalized_public_url(
    client: TestClientProtocol, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A running pipeline is reported live, with its `url` rewritten onto `PUBLIC_STREAMING_URL`."""
    fake = _FakeAsyncClient(
        response=_FakeResponse(
            200,
            {
                "pipelines": [
                    {
                        "id": "pipeline-1",
                        "profile": "1080p60",
                        "url": "/live/42/pipeline-1/1080p60/master.m3u8",
                        "started_at": "2026-09-11T00:00:00Z",
                    },
                    {"id": "malformed-entry-missing-url"},
                ]
            },
        )
    )
    _patch_client(monkeypatch, fake)
    monkeypatch.setenv("PUBLIC_STREAMING_URL", "https://streaming.example.com")

    response = await client.get("/overlay/42/live/status")
    assert response.status_code == 200
    payload = await response.get_json()
    assert payload["live"] is True
    assert len(payload["pipelines"]) == 1
    assert (
        payload["pipelines"][0]["url"]
        == "https://streaming.example.com/live/42/pipeline-1/1080p60/master.m3u8"
    )


@pytest.mark.asyncio
async def test_status_endpoint_without_public_streaming_url_falls_back_to_relative(
    client: TestClientProtocol, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No `PUBLIC_STREAMING_URL` configured -- pass the relative URL through unchanged."""
    monkeypatch.delenv("PUBLIC_STREAMING_URL", raising=False)
    fake = _FakeAsyncClient(
        response=_FakeResponse(
            200,
            {
                "pipelines": [
                    {
                        "id": "pipeline-1",
                        "profile": "1080p60",
                        "url": "/live/42/pipeline-1/1080p60/master.m3u8",
                        "started_at": "2026-09-11T00:00:00Z",
                    }
                ]
            },
        )
    )
    _patch_client(monkeypatch, fake)

    response = await client.get("/overlay/42/live/status")
    payload = await response.get_json()
    assert payload["pipelines"][0]["url"] == "/live/42/pipeline-1/1080p60/master.m3u8"


@pytest.mark.asyncio
async def test_status_endpoint_invalid_community_is_400(client: TestClientProtocol) -> None:
    """A malformed `community` segment 400s before any svc-streaming call."""
    response = await client.get("/overlay/%3Cscript%3E/live/status")
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_status_endpoint_non_numeric_community_is_offline_without_calling_streaming(
    client: TestClientProtocol, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A syntactically valid but non-numeric community can't resolve -- offline, zero HTTP calls."""
    fake = _FakeAsyncClient(response=_FakeResponse(200, {"pipelines": []}))
    _patch_client(monkeypatch, fake)
    response = await client.get("/overlay/testcommunity/live/status")
    assert response.status_code == 200
    payload = await response.get_json()
    assert payload == {"live": False, "pipelines": []}
    assert fake.get_calls == []
