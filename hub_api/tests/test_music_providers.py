"""Tests for `services/music_providers/*` -- real request/response shape, mocked transport only.

The HTTP *transport* is mocked (`httpx.MockTransport`, swapped in via
`monkeypatch.setattr(httpx, "AsyncClient", ...)`) so no test ever reaches a
real socket -- but request building, URL/param encoding, and JSON response
parsing all run for real through `httpx`. Fixtures below are shaped like
actual YouTube Data API v3 / Spotify Web API responses.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

import httpx
import pytest

from services.music_providers import ProviderUnavailable, TrackNotFound, resolve, search
from services.music_providers import spotify as spotify_mod
from services.music_providers import youtube as youtube_mod
from services.music_providers.track import Track

_RealAsyncClient = httpx.AsyncClient


def _client_factory(transport: httpx.MockTransport) -> Callable[..., httpx.AsyncClient]:
    """Build a replacement for `httpx.AsyncClient` that always uses `transport`."""

    def factory(*_args: Any, **_kwargs: Any) -> httpx.AsyncClient:
        return _RealAsyncClient(transport=transport)

    return factory


@pytest.fixture(autouse=True)
def _reset_spotify_token_cache() -> Any:
    """Spotify's bearer-token cache is module-level state -- isolate every test."""
    spotify_mod._token_cache = None
    yield
    spotify_mod._token_cache = None


@pytest.fixture(autouse=True)
def _reset_youtube_oauth_token_cache() -> Any:
    """YouTube's OAuth access-token cache is module-level state -- isolate every test."""
    youtube_mod._oauth_token_cache = None
    yield
    youtube_mod._oauth_token_cache = None


@pytest.fixture(autouse=True)
def _reset_youtube_labels_cache() -> Any:
    """YouTube's `Track.labels` cache (gh-313) is module-level state -- isolate every test."""
    youtube_mod._labels_cache.clear()
    yield
    youtube_mod._labels_cache.clear()


@pytest.fixture(autouse=True)
def _no_real_creds(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every test controls its own credential source explicitly."""
    monkeypatch.delenv("YOUTUBE_API_KEY", raising=False)
    monkeypatch.delenv("YOUTUBE_CLIENT_ID", raising=False)
    monkeypatch.delenv("YOUTUBE_CLIENT_SECRET", raising=False)
    monkeypatch.delenv("YOUTUBE_REFRESH_TOKEN", raising=False)
    monkeypatch.delenv("SPOTIFY_CLIENT_ID", raising=False)
    monkeypatch.delenv("SPOTIFY_CLIENT_SECRET", raising=False)
    monkeypatch.setattr(
        youtube_mod, "_TOKEN_FILE", youtube_mod._TOKEN_FILE.parent / "__nope__.token"
    )
    monkeypatch.setattr(
        spotify_mod, "_TOKEN_FILE", spotify_mod._TOKEN_FILE.parent / "__nope__.token"
    )


# --------------------------------------------------------------------------
# Track shape
# --------------------------------------------------------------------------


class TestTrackShape:
    """The normalized `Track` itself -- field set and `slots=True`."""

    def test_track_fields_and_slots(self) -> None:
        track = Track(
            provider="youtube",
            external_id="abc123",
            title="Song",
            artist="Artist",
            duration_ms=1000,
            artwork_url="https://example.com/art.jpg",
            url="https://example.com/watch",
        )
        assert track.provider == "youtube"
        assert track.external_id == "abc123"
        assert track.duration_ms == 1000
        assert not hasattr(track, "__dict__")  # slots=True -- no instance dict

    def test_track_artwork_url_optional(self) -> None:
        track = Track(
            provider="spotify",
            external_id="x",
            title="t",
            artist="a",
            duration_ms=1,
            artwork_url=None,
            url="https://example.com",
        )
        assert track.artwork_url is None


# --------------------------------------------------------------------------
# YouTube fixtures
# --------------------------------------------------------------------------

_YT_VIDEO_ITEM = {
    "id": "dQw4w9WgXcQ",
    "snippet": {
        "title": "Rick Astley - Never Gonna Give You Up",
        "channelTitle": "Rick Astley",
        "thumbnails": {
            "default": {"url": "https://i.ytimg.com/vi/dQw4w9WgXcQ/default.jpg"},
            "medium": {"url": "https://i.ytimg.com/vi/dQw4w9WgXcQ/mqdefault.jpg"},
            "high": {"url": "https://i.ytimg.com/vi/dQw4w9WgXcQ/hqdefault.jpg"},
        },
    },
    "contentDetails": {"duration": "PT3M33S"},
}

_YT_SEARCH_RESPONSE = {
    "items": [
        {"id": {"kind": "youtube#video", "videoId": "dQw4w9WgXcQ"}},
        {"id": {"kind": "youtube#video", "videoId": "otherId123"}},
    ]
}

_YT_SECOND_VIDEO_ITEM = {
    "id": "otherId123",
    "snippet": {
        "title": "Another Song",
        "channelTitle": "Another Channel",
        "thumbnails": {"default": {"url": "https://i.ytimg.com/vi/otherId123/default.jpg"}},
    },
    "contentDetails": {"duration": "PT1H2M3S"},
}


def _youtube_transport(
    videos_payload: dict[str, Any],
    search_payload: dict[str, Any] | None = None,
    *,
    labels_payload: dict[str, Any] | None = None,
) -> httpx.MockTransport:
    """Build a `videos.list` mock transport, optionally distinguishing the labels call.

    `labels_payload` (gh-313), when given, answers the SECOND `videos.list`
    call (`part=snippet,topicDetails`) distinctly from the primary one
    (`part=snippet,contentDetails`) -- omit it and both calls get `videos_payload`,
    which is fine for every pre-gh-313 test since none of them assert `.labels`.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/search"):
            assert search_payload is not None
            return httpx.Response(200, json=search_payload)
        if request.url.path.endswith("/videos"):
            part = request.url.params.get("part", "")
            if "topicDetails" in part and labels_payload is not None:
                return httpx.Response(200, json=labels_payload)
            return httpx.Response(200, json=videos_payload)
        raise AssertionError(f"unexpected path: {request.url.path}")

    return httpx.MockTransport(handler)


#: A video with a mapped category, mixed-case/duplicate tags, and topic categories --
#: exercises `_extract_labels()`'s full union + dedupe/lowercase behavior end-to-end.
_YT_VIDEO_ITEM_WITH_LABELS = {
    "id": "labelVid1",
    "snippet": {
        "title": "Song With Labels",
        "channelTitle": "Channel",
        "categoryId": "10",
        "tags": ["Pop", "Live Performance", "POP"],
        "thumbnails": {"default": {"url": "https://i.ytimg.com/vi/labelVid1/default.jpg"}},
    },
    "contentDetails": {"duration": "PT3M0S"},
    "topicDetails": {
        "topicCategories": [
            "https://en.wikipedia.org/wiki/Pop_music",
            "https://en.wikipedia.org/wiki/Music",
        ]
    },
}


class TestYoutubeResolve:
    """`youtube.resolve()` -- URL -> `videos.list` -> `Track`."""

    async def test_resolve_watch_url_success(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("YOUTUBE_API_KEY", "test-key")
        transport = _youtube_transport({"items": [_YT_VIDEO_ITEM]})
        monkeypatch.setattr(httpx, "AsyncClient", _client_factory(transport))

        track = await youtube_mod.resolve("https://www.youtube.com/watch?v=dQw4w9WgXcQ")

        assert track.provider == "youtube"
        assert track.external_id == "dQw4w9WgXcQ"
        assert track.title == "Rick Astley - Never Gonna Give You Up"
        assert track.artist == "Rick Astley"
        assert track.duration_ms == (3 * 60 + 33) * 1000
        assert track.artwork_url == "https://i.ytimg.com/vi/dQw4w9WgXcQ/hqdefault.jpg"
        assert track.url == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"

    async def test_resolve_short_url(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("YOUTUBE_API_KEY", "test-key")
        transport = _youtube_transport({"items": [_YT_VIDEO_ITEM]})
        monkeypatch.setattr(httpx, "AsyncClient", _client_factory(transport))

        track = await youtube_mod.resolve("https://youtu.be/dQw4w9WgXcQ")
        assert track.external_id == "dQw4w9WgXcQ"

    async def test_resolve_no_items_raises_track_not_found(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("YOUTUBE_API_KEY", "test-key")
        transport = _youtube_transport({"items": []})
        monkeypatch.setattr(httpx, "AsyncClient", _client_factory(transport))

        with pytest.raises(TrackNotFound):
            await youtube_mod.resolve("https://www.youtube.com/watch?v=missing")

    async def test_resolve_unparseable_url_raises_track_not_found_without_network(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("YOUTUBE_API_KEY", "test-key")

        def boom(_request: httpx.Request) -> httpx.Response:
            raise AssertionError("no network call should happen")

        monkeypatch.setattr(httpx, "AsyncClient", _client_factory(httpx.MockTransport(boom)))

        with pytest.raises(TrackNotFound):
            await youtube_mod.resolve("https://example.com/not-a-video")

    async def test_resolve_no_credentials_raises_provider_unavailable(self) -> None:
        with pytest.raises(ProviderUnavailable) as exc_info:
            await youtube_mod.resolve("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
        assert exc_info.value.provider == (
            "youtube credentials not configured: set YOUTUBE_API_KEY or "
            "YOUTUBE_CLIENT_ID+YOUTUBE_CLIENT_SECRET+YOUTUBE_REFRESH_TOKEN"
        )

    async def test_resolve_api_key_from_token_file(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Any
    ) -> None:
        token_file = tmp_path / ".youtube.token"
        token_file.write_text("AIzaSyRealLookingKey\nunused-secret-line\n")
        monkeypatch.setattr(youtube_mod, "_TOKEN_FILE", token_file)
        transport = _youtube_transport({"items": [_YT_VIDEO_ITEM]})
        monkeypatch.setattr(httpx, "AsyncClient", _client_factory(transport))

        track = await youtube_mod.resolve("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
        assert track.external_id == "dQw4w9WgXcQ"

    async def test_oauth_client_id_in_token_file_is_unusable(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Any
    ) -> None:
        token_file = tmp_path / ".youtube.token"
        token_file.write_text("123456-abc.apps.googleusercontent.com\nsome-secret\n")
        monkeypatch.setattr(youtube_mod, "_TOKEN_FILE", token_file)

        with pytest.raises(ProviderUnavailable):
            await youtube_mod.resolve("https://www.youtube.com/watch?v=dQw4w9WgXcQ")

    async def test_upstream_403_maps_to_provider_unavailable(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("YOUTUBE_API_KEY", "bad-key")

        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(403, json={"error": {"message": "quota exceeded"}})

        monkeypatch.setattr(httpx, "AsyncClient", _client_factory(httpx.MockTransport(handler)))

        with pytest.raises(ProviderUnavailable):
            await youtube_mod.resolve("https://www.youtube.com/watch?v=dQw4w9WgXcQ")

    async def test_network_error_maps_to_provider_unavailable(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("YOUTUBE_API_KEY", "test-key")

        def handler(_request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("refused")

        monkeypatch.setattr(httpx, "AsyncClient", _client_factory(httpx.MockTransport(handler)))

        with pytest.raises(ProviderUnavailable):
            await youtube_mod.resolve("https://www.youtube.com/watch?v=dQw4w9WgXcQ")


class TestYoutubeSearch:
    """`youtube.search()` -- `search.list` then `videos.list` hydration."""

    async def test_search_success_hydrates_durations(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("YOUTUBE_API_KEY", "test-key")
        videos_payload = {"items": [_YT_VIDEO_ITEM, _YT_SECOND_VIDEO_ITEM]}
        transport = _youtube_transport(videos_payload, search_payload=_YT_SEARCH_RESPONSE)
        monkeypatch.setattr(httpx, "AsyncClient", _client_factory(transport))

        tracks = await youtube_mod.search("never gonna give you up")

        assert len(tracks) == 2
        assert tracks[0].external_id == "dQw4w9WgXcQ"
        assert tracks[0].duration_ms == (3 * 60 + 33) * 1000
        assert tracks[1].external_id == "otherId123"
        assert tracks[1].duration_ms == (3600 + 2 * 60 + 3) * 1000

    async def test_search_empty_results_raises_track_not_found(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("YOUTUBE_API_KEY", "test-key")
        transport = _youtube_transport({"items": []}, search_payload={"items": []})
        monkeypatch.setattr(httpx, "AsyncClient", _client_factory(transport))

        with pytest.raises(TrackNotFound):
            await youtube_mod.search("no such song anywhere")

    async def test_search_no_credentials_raises_provider_unavailable(self) -> None:
        with pytest.raises(ProviderUnavailable) as exc_info:
            await youtube_mod.search("anything")
        assert exc_info.value.provider == (
            "youtube credentials not configured: set YOUTUBE_API_KEY or "
            "YOUTUBE_CLIENT_ID+YOUTUBE_CLIENT_SECRET+YOUTUBE_REFRESH_TOKEN"
        )

    async def test_search_hydrate_returns_no_items_raises_track_not_found(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """`search.list` finds ids but the follow-up `videos.list` hydrate comes back empty."""
        monkeypatch.setenv("YOUTUBE_API_KEY", "test-key")
        transport = _youtube_transport({"items": []}, search_payload=_YT_SEARCH_RESPONSE)
        monkeypatch.setattr(httpx, "AsyncClient", _client_factory(transport))

        with pytest.raises(TrackNotFound):
            await youtube_mod.search("never gonna give you up")


class TestYoutubeCredentialLoading:
    """`_load_api_key()` -- token-file edge cases not exercised via resolve()/search()."""

    def test_unreadable_token_file_returns_none(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Any
    ) -> None:
        token_dir = tmp_path / ".youtube.token"
        token_dir.mkdir()  # reading a directory as text raises OSError
        monkeypatch.setattr(youtube_mod, "_TOKEN_FILE", token_dir)
        assert youtube_mod._load_api_key() is None

    def test_empty_token_file_returns_none(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Any
    ) -> None:
        token_file = tmp_path / ".youtube.token"
        token_file.write_text("")
        monkeypatch.setattr(youtube_mod, "_TOKEN_FILE", token_file)
        assert youtube_mod._load_api_key() is None


class TestYoutubeHelpers:
    """Pure helper functions -- URL/duration parsing edge cases."""

    @pytest.mark.parametrize(
        ("url", "expected"),
        [
            ("https://www.youtube.com/watch?v=abc123", "abc123"),
            ("https://youtube.com/watch?v=abc123", "abc123"),
            ("https://youtu.be/abc123", "abc123"),
            ("https://youtu.be/abc123?t=30", "abc123"),
            ("https://www.youtube.com/embed/abc123", "abc123"),
            ("https://www.youtube.com/shorts/abc123", "abc123"),
            ("https://example.com/watch?v=abc123", None),
            ("not a url at all", None),
        ],
    )
    def test_extract_video_id(self, url: str, expected: str | None) -> None:
        assert youtube_mod._extract_video_id(url) == expected

    @pytest.mark.parametrize(
        ("duration", "expected_ms"),
        [
            ("PT3M33S", (3 * 60 + 33) * 1000),
            ("PT1H2M3S", (3600 + 2 * 60 + 3) * 1000),
            ("PT45S", 45 * 1000),
            ("PT2H", 2 * 3600 * 1000),
            ("P0D", 0),
            ("garbage", 0),
        ],
    )
    def test_parse_iso8601_duration_ms(self, duration: str, expected_ms: int) -> None:
        assert youtube_mod._parse_iso8601_duration_ms(duration) == expected_ms

    def test_best_thumbnail_prefers_highest_quality(self) -> None:
        thumbs = {
            "default": {"url": "d"},
            "high": {"url": "h"},
            "medium": {"url": "m"},
        }
        assert youtube_mod._best_thumbnail(thumbs) == "h"

    def test_best_thumbnail_empty(self) -> None:
        assert youtube_mod._best_thumbnail({}) is None


# --------------------------------------------------------------------------
# Label extraction (gh-313) -- pure helpers
# --------------------------------------------------------------------------


class TestYoutubeLabelExtraction:
    """`_category_label()` / `_topic_leaf_name()` / `_extract_labels()` -- pure, no network."""

    @pytest.mark.parametrize(
        ("category_id", "expected"),
        [
            ("10", "music"),
            ("20", "gaming"),
            ("24", "entertainment"),
            ("22", "people & blogs"),
            ("9999", "category:9999"),
            (None, None),
            ("", None),
        ],
    )
    def test_category_label(self, category_id: str | None, expected: str | None) -> None:
        assert youtube_mod._category_label(category_id) == expected

    @pytest.mark.parametrize(
        ("topic_url", "expected"),
        [
            ("https://en.wikipedia.org/wiki/Pop_music", "Pop music"),
            ("https://en.wikipedia.org/wiki/Music", "Music"),
            ("https://en.wikipedia.org/wiki/", None),
            ("not-a-url", "not-a-url"),
        ],
    )
    def test_topic_leaf_name(self, topic_url: str, expected: str | None) -> None:
        assert youtube_mod._topic_leaf_name(topic_url) == expected

    def test_extract_labels_dedupes_lowercases_preserves_first_seen_order(self) -> None:
        labels = youtube_mod._extract_labels(_YT_VIDEO_ITEM_WITH_LABELS)
        assert labels == ("music", "pop", "live performance", "pop music")

    def test_extract_labels_empty_item_returns_empty_tuple(self) -> None:
        assert youtube_mod._extract_labels({}) == ()

    def test_extract_labels_ignores_non_string_tags_and_topics(self) -> None:
        item = {
            "snippet": {"tags": [123, None, "valid"]},
            "topicDetails": {"topicCategories": [456, None, "https://en.wikipedia.org/wiki/Jazz"]},
        }
        assert youtube_mod._extract_labels(item) == ("valid", "jazz")

    def test_extract_labels_unmapped_category_falls_back(self) -> None:
        item = {"snippet": {"categoryId": "777"}}
        assert youtube_mod._extract_labels(item) == ("category:777",)


# --------------------------------------------------------------------------
# Label resolution + caching (gh-313) -- resolve()/search() integration
# --------------------------------------------------------------------------


class TestYoutubeLabels:
    """`Track.labels` populated via the second `videos.list` call -- cache, failure modes."""

    async def test_resolve_populates_labels(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("YOUTUBE_API_KEY", "test-key")
        transport = _youtube_transport(
            {"items": [_YT_VIDEO_ITEM]},
            labels_payload={"items": [_YT_VIDEO_ITEM_WITH_LABELS]},
        )
        monkeypatch.setattr(httpx, "AsyncClient", _client_factory(transport))

        track = await youtube_mod.resolve("https://www.youtube.com/watch?v=dQw4w9WgXcQ")

        assert track.labels == ("music", "pop", "live performance", "pop music")
        # Primary resolution is unaffected by the second call's payload.
        assert track.external_id == "dQw4w9WgXcQ"

    async def test_spotify_tracks_never_get_labels(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SPOTIFY_CLIENT_ID", "id")
        monkeypatch.setenv("SPOTIFY_CLIENT_SECRET", "secret")
        transport = _spotify_transport(_SPOTIFY_TRACK_ITEM)
        monkeypatch.setattr(httpx, "AsyncClient", _client_factory(transport))

        track = await spotify_mod.resolve("https://open.spotify.com/track/3n3Ppam7vgaVa1iaRUc9Lp")
        assert track.labels == ()

    async def test_search_populates_labels_per_track(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("YOUTUBE_API_KEY", "test-key")

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("/search"):
                return httpx.Response(200, json=_YT_SEARCH_RESPONSE)
            part = request.url.params.get("part", "")
            if "topicDetails" in part:
                video_id = request.url.params.get("id", "")
                if video_id == "dQw4w9WgXcQ":
                    return httpx.Response(200, json={"items": [_YT_VIDEO_ITEM_WITH_LABELS]})
                return httpx.Response(
                    200, json={"items": [{"id": video_id, "snippet": {"categoryId": "20"}}]}
                )
            return httpx.Response(200, json={"items": [_YT_VIDEO_ITEM, _YT_SECOND_VIDEO_ITEM]})

        monkeypatch.setattr(httpx, "AsyncClient", _client_factory(httpx.MockTransport(handler)))

        tracks = await youtube_mod.search("never gonna give you up")

        assert len(tracks) == 2
        assert tracks[0].labels == ("music", "pop", "live performance", "pop music")
        assert tracks[1].labels == ("gaming",)

    async def test_second_call_failure_returns_empty_labels_and_warns(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        monkeypatch.setenv("YOUTUBE_API_KEY", "test-key")
        label_calls = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal label_calls
            part = request.url.params.get("part", "")
            if "topicDetails" in part:
                label_calls += 1
                return httpx.Response(500, json={"error": "boom"})
            return httpx.Response(200, json={"items": [_YT_VIDEO_ITEM]})

        monkeypatch.setattr(httpx, "AsyncClient", _client_factory(httpx.MockTransport(handler)))

        with caplog.at_level("WARNING"):
            track = await youtube_mod.resolve("https://www.youtube.com/watch?v=dQw4w9WgXcQ")

        assert track.labels == ()
        assert track.external_id == "dQw4w9WgXcQ"  # primary resolution unaffected
        assert label_calls == 1
        assert any("youtube.labels fetch_failed" in record.message for record in caplog.records)

    async def test_second_call_network_error_returns_empty_labels(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("YOUTUBE_API_KEY", "test-key")

        def handler(request: httpx.Request) -> httpx.Response:
            part = request.url.params.get("part", "")
            if "topicDetails" in part:
                raise httpx.ConnectError("refused")
            return httpx.Response(200, json={"items": [_YT_VIDEO_ITEM]})

        monkeypatch.setattr(httpx, "AsyncClient", _client_factory(httpx.MockTransport(handler)))

        track = await youtube_mod.resolve("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
        assert track.labels == ()

    async def test_second_call_empty_items_returns_empty_labels(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("YOUTUBE_API_KEY", "test-key")
        transport = _youtube_transport({"items": [_YT_VIDEO_ITEM]}, labels_payload={"items": []})
        monkeypatch.setattr(httpx, "AsyncClient", _client_factory(transport))

        track = await youtube_mod.resolve("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
        assert track.labels == ()

    async def test_labels_cached_across_resolve_calls(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("YOUTUBE_API_KEY", "test-key")
        label_calls = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal label_calls
            part = request.url.params.get("part", "")
            if "topicDetails" in part:
                label_calls += 1
                return httpx.Response(200, json={"items": [_YT_VIDEO_ITEM_WITH_LABELS]})
            return httpx.Response(200, json={"items": [_YT_VIDEO_ITEM]})

        monkeypatch.setattr(httpx, "AsyncClient", _client_factory(httpx.MockTransport(handler)))

        track1 = await youtube_mod.resolve("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
        track2 = await youtube_mod.resolve("https://www.youtube.com/watch?v=dQw4w9WgXcQ")

        assert (
            track1.labels
            == track2.labels
            == (
                "music",
                "pop",
                "live performance",
                "pop music",
            )
        )
        assert label_calls == 1  # second resolve() hit the cache

    def test_labels_cache_expiry_forces_refetch(self) -> None:
        youtube_mod._labels_cache_set("vid1", ("music",))
        assert youtube_mod._labels_cache_get("vid1") == ("music",)

        youtube_mod._labels_cache["vid1"].expires_at = time.monotonic() - 1

        assert youtube_mod._labels_cache_get("vid1") is None
        assert "vid1" not in youtube_mod._labels_cache

    def test_labels_cache_bounded_size_evicts_oldest(self) -> None:
        for i in range(youtube_mod._LABELS_CACHE_MAX_SIZE):
            youtube_mod._labels_cache_set(f"vid{i}", (f"label{i}",))
        assert len(youtube_mod._labels_cache) == youtube_mod._LABELS_CACHE_MAX_SIZE
        assert "vid0" in youtube_mod._labels_cache

        youtube_mod._labels_cache_set("vid_overflow", ("overflow",))

        assert len(youtube_mod._labels_cache) == youtube_mod._LABELS_CACHE_MAX_SIZE
        assert "vid0" not in youtube_mod._labels_cache
        assert "vid_overflow" in youtube_mod._labels_cache


# --------------------------------------------------------------------------
# Spotify fixtures
# --------------------------------------------------------------------------

_SPOTIFY_TOKEN_RESPONSE = {
    "access_token": "test-bearer-token",
    "token_type": "Bearer",
    "expires_in": 3600,
}

_SPOTIFY_TRACK_ITEM = {
    "id": "3n3Ppam7vgaVa1iaRUc9Lp",
    "name": "Mr. Brightside",
    "duration_ms": 222075,
    "artists": [{"name": "The Killers"}],
    "album": {
        "images": [
            {"url": "https://i.scdn.co/image/large.jpg", "width": 640, "height": 640},
            {"url": "https://i.scdn.co/image/small.jpg", "width": 64, "height": 64},
        ]
    },
    "external_urls": {"spotify": "https://open.spotify.com/track/3n3Ppam7vgaVa1iaRUc9Lp"},
}

_SPOTIFY_SEARCH_RESPONSE = {"tracks": {"items": [_SPOTIFY_TRACK_ITEM]}}


def _spotify_transport(
    api_payload: dict[str, Any], *, api_status: int = 200, token_status: int = 200
) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "accounts.spotify.com":
            if token_status != 200:
                return httpx.Response(token_status, json={"error": "invalid_client"})
            return httpx.Response(200, json=_SPOTIFY_TOKEN_RESPONSE)
        return httpx.Response(api_status, json=api_payload)

    return httpx.MockTransport(handler)


class TestSpotifyResolve:
    """`spotify.resolve()` -- URL -> `GET /v1/tracks/{id}` -> `Track`."""

    async def test_resolve_success(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SPOTIFY_CLIENT_ID", "id")
        monkeypatch.setenv("SPOTIFY_CLIENT_SECRET", "secret")
        transport = _spotify_transport(_SPOTIFY_TRACK_ITEM)
        monkeypatch.setattr(httpx, "AsyncClient", _client_factory(transport))

        track = await spotify_mod.resolve(
            "https://open.spotify.com/track/3n3Ppam7vgaVa1iaRUc9Lp?si=abc"
        )

        assert track.provider == "spotify"
        assert track.external_id == "3n3Ppam7vgaVa1iaRUc9Lp"
        assert track.title == "Mr. Brightside"
        assert track.artist == "The Killers"
        assert track.duration_ms == 222075
        assert track.artwork_url == "https://i.scdn.co/image/large.jpg"
        assert track.url == "https://open.spotify.com/track/3n3Ppam7vgaVa1iaRUc9Lp"

    async def test_resolve_bad_url_raises_track_not_found_without_network(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("SPOTIFY_CLIENT_ID", "id")
        monkeypatch.setenv("SPOTIFY_CLIENT_SECRET", "secret")

        def boom(_request: httpx.Request) -> httpx.Response:
            raise AssertionError("no network call should happen")

        monkeypatch.setattr(httpx, "AsyncClient", _client_factory(httpx.MockTransport(boom)))

        with pytest.raises(TrackNotFound):
            await spotify_mod.resolve("https://open.spotify.com/playlist/xyz")

    async def test_resolve_404_raises_track_not_found(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("SPOTIFY_CLIENT_ID", "id")
        monkeypatch.setenv("SPOTIFY_CLIENT_SECRET", "secret")
        transport = _spotify_transport({}, api_status=404)
        monkeypatch.setattr(httpx, "AsyncClient", _client_factory(transport))

        with pytest.raises(TrackNotFound):
            await spotify_mod.resolve("https://open.spotify.com/track/doesnotexist")

    async def test_resolve_rate_limited_raises_provider_unavailable(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("SPOTIFY_CLIENT_ID", "id")
        monkeypatch.setenv("SPOTIFY_CLIENT_SECRET", "secret")
        transport = _spotify_transport({}, api_status=429)
        monkeypatch.setattr(httpx, "AsyncClient", _client_factory(transport))

        with pytest.raises(ProviderUnavailable):
            await spotify_mod.resolve("https://open.spotify.com/track/3n3Ppam7vgaVa1iaRUc9Lp")

    async def test_resolve_no_credentials_raises_provider_unavailable(self) -> None:
        with pytest.raises(ProviderUnavailable) as exc_info:
            await spotify_mod.resolve("https://open.spotify.com/track/3n3Ppam7vgaVa1iaRUc9Lp")
        assert exc_info.value.provider == "spotify"

    async def test_resolve_credentials_from_token_file(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Any
    ) -> None:
        token_file = tmp_path / ".spotify.token"
        token_file.write_text("client-id-from-file\nclient-secret-from-file\n")
        monkeypatch.setattr(spotify_mod, "_TOKEN_FILE", token_file)
        transport = _spotify_transport(_SPOTIFY_TRACK_ITEM)
        monkeypatch.setattr(httpx, "AsyncClient", _client_factory(transport))

        track = await spotify_mod.resolve("https://open.spotify.com/track/3n3Ppam7vgaVa1iaRUc9Lp")
        assert track.external_id == "3n3Ppam7vgaVa1iaRUc9Lp"

    async def test_invalid_client_credentials_raises_provider_unavailable(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("SPOTIFY_CLIENT_ID", "id")
        monkeypatch.setenv("SPOTIFY_CLIENT_SECRET", "wrong")
        transport = _spotify_transport({}, token_status=400)
        monkeypatch.setattr(httpx, "AsyncClient", _client_factory(transport))

        with pytest.raises(ProviderUnavailable):
            await spotify_mod.resolve("https://open.spotify.com/track/3n3Ppam7vgaVa1iaRUc9Lp")

    async def test_network_error_raises_provider_unavailable(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("SPOTIFY_CLIENT_ID", "id")
        monkeypatch.setenv("SPOTIFY_CLIENT_SECRET", "secret")

        def handler(_request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("refused")

        monkeypatch.setattr(httpx, "AsyncClient", _client_factory(httpx.MockTransport(handler)))

        with pytest.raises(ProviderUnavailable):
            await spotify_mod.resolve("https://open.spotify.com/track/3n3Ppam7vgaVa1iaRUc9Lp")

    async def test_bearer_token_cached_across_calls(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SPOTIFY_CLIENT_ID", "id")
        monkeypatch.setenv("SPOTIFY_CLIENT_SECRET", "secret")
        token_calls = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal token_calls
            if request.url.host == "accounts.spotify.com":
                token_calls += 1
                return httpx.Response(200, json=_SPOTIFY_TOKEN_RESPONSE)
            return httpx.Response(200, json=_SPOTIFY_TRACK_ITEM)

        monkeypatch.setattr(httpx, "AsyncClient", _client_factory(httpx.MockTransport(handler)))

        await spotify_mod.resolve("https://open.spotify.com/track/3n3Ppam7vgaVa1iaRUc9Lp")
        await spotify_mod.resolve("https://open.spotify.com/track/3n3Ppam7vgaVa1iaRUc9Lp")

        assert token_calls == 1

    async def test_bearer_token_refreshed_after_expiry(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("SPOTIFY_CLIENT_ID", "id")
        monkeypatch.setenv("SPOTIFY_CLIENT_SECRET", "secret")
        token_calls = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal token_calls
            if request.url.host == "accounts.spotify.com":
                token_calls += 1
                return httpx.Response(200, json=_SPOTIFY_TOKEN_RESPONSE)
            return httpx.Response(200, json=_SPOTIFY_TRACK_ITEM)

        monkeypatch.setattr(httpx, "AsyncClient", _client_factory(httpx.MockTransport(handler)))

        await spotify_mod.resolve("https://open.spotify.com/track/3n3Ppam7vgaVa1iaRUc9Lp")
        assert token_calls == 1

        # Force the cached token to look expired.
        assert spotify_mod._token_cache is not None
        spotify_mod._token_cache.expires_at = time.monotonic() - 1

        await spotify_mod.resolve("https://open.spotify.com/track/3n3Ppam7vgaVa1iaRUc9Lp")
        assert token_calls == 2

    async def test_track_fetch_network_error_after_token_obtained(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Token endpoint succeeds; the follow-up `/tracks/{id}` GET fails -- distinct branch."""
        monkeypatch.setenv("SPOTIFY_CLIENT_ID", "id")
        monkeypatch.setenv("SPOTIFY_CLIENT_SECRET", "secret")

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.host == "accounts.spotify.com":
                return httpx.Response(200, json=_SPOTIFY_TOKEN_RESPONSE)
            raise httpx.ConnectError("refused")

        monkeypatch.setattr(httpx, "AsyncClient", _client_factory(httpx.MockTransport(handler)))

        with pytest.raises(ProviderUnavailable):
            await spotify_mod.resolve("https://open.spotify.com/track/3n3Ppam7vgaVa1iaRUc9Lp")

    async def test_non_dict_response_raises_track_not_found(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("SPOTIFY_CLIENT_ID", "id")
        monkeypatch.setenv("SPOTIFY_CLIENT_SECRET", "secret")

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.host == "accounts.spotify.com":
                return httpx.Response(200, json=_SPOTIFY_TOKEN_RESPONSE)
            return httpx.Response(200, json=[])

        monkeypatch.setattr(httpx, "AsyncClient", _client_factory(httpx.MockTransport(handler)))

        with pytest.raises(TrackNotFound):
            await spotify_mod.resolve("https://open.spotify.com/track/3n3Ppam7vgaVa1iaRUc9Lp")

    async def test_token_response_missing_access_token_raises_provider_unavailable(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("SPOTIFY_CLIENT_ID", "id")
        monkeypatch.setenv("SPOTIFY_CLIENT_SECRET", "secret")

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.host == "accounts.spotify.com":
                return httpx.Response(200, json={"token_type": "Bearer", "expires_in": 3600})
            return httpx.Response(200, json=_SPOTIFY_TRACK_ITEM)

        monkeypatch.setattr(httpx, "AsyncClient", _client_factory(httpx.MockTransport(handler)))

        with pytest.raises(ProviderUnavailable):
            await spotify_mod.resolve("https://open.spotify.com/track/3n3Ppam7vgaVa1iaRUc9Lp")


class TestSpotifyCredentialLoading:
    """`_load_credentials()` -- token-file edge cases not exercised via resolve()/search()."""

    def test_unreadable_token_file_returns_none(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Any
    ) -> None:
        token_dir = tmp_path / ".spotify.token"
        token_dir.mkdir()  # reading a directory as text raises OSError
        monkeypatch.setattr(spotify_mod, "_TOKEN_FILE", token_dir)
        assert spotify_mod._load_credentials() is None

    def test_single_line_token_file_returns_none(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Any
    ) -> None:
        token_file = tmp_path / ".spotify.token"
        token_file.write_text("only-one-line\n")
        monkeypatch.setattr(spotify_mod, "_TOKEN_FILE", token_file)
        assert spotify_mod._load_credentials() is None

    def test_blank_secret_line_returns_none(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Any
    ) -> None:
        token_file = tmp_path / ".spotify.token"
        token_file.write_text("client-id\n   \n")
        monkeypatch.setattr(spotify_mod, "_TOKEN_FILE", token_file)
        assert spotify_mod._load_credentials() is None


class TestSpotifySearch:
    """`spotify.search()` -- `GET /v1/search?type=track`."""

    async def test_search_success(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SPOTIFY_CLIENT_ID", "id")
        monkeypatch.setenv("SPOTIFY_CLIENT_SECRET", "secret")
        transport = _spotify_transport(_SPOTIFY_SEARCH_RESPONSE)
        monkeypatch.setattr(httpx, "AsyncClient", _client_factory(transport))

        tracks = await spotify_mod.search("mr brightside")

        assert len(tracks) == 1
        assert tracks[0].title == "Mr. Brightside"
        assert tracks[0].artist == "The Killers"

    async def test_search_empty_results_raises_track_not_found(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("SPOTIFY_CLIENT_ID", "id")
        monkeypatch.setenv("SPOTIFY_CLIENT_SECRET", "secret")
        transport = _spotify_transport({"tracks": {"items": []}})
        monkeypatch.setattr(httpx, "AsyncClient", _client_factory(transport))

        with pytest.raises(TrackNotFound):
            await spotify_mod.search("no such track anywhere")

    async def test_search_rate_limited_raises_provider_unavailable(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("SPOTIFY_CLIENT_ID", "id")
        monkeypatch.setenv("SPOTIFY_CLIENT_SECRET", "secret")
        transport = _spotify_transport({}, api_status=429)
        monkeypatch.setattr(httpx, "AsyncClient", _client_factory(transport))

        with pytest.raises(ProviderUnavailable):
            await spotify_mod.search("anything")

    async def test_search_no_credentials_raises_provider_unavailable(self) -> None:
        with pytest.raises(ProviderUnavailable):
            await spotify_mod.search("anything")

    async def test_search_network_error_after_token_obtained(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("SPOTIFY_CLIENT_ID", "id")
        monkeypatch.setenv("SPOTIFY_CLIENT_SECRET", "secret")

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.host == "accounts.spotify.com":
                return httpx.Response(200, json=_SPOTIFY_TOKEN_RESPONSE)
            raise httpx.ConnectError("refused")

        monkeypatch.setattr(httpx, "AsyncClient", _client_factory(httpx.MockTransport(handler)))

        with pytest.raises(ProviderUnavailable):
            await spotify_mod.search("anything")


class TestSpotifyHelpers:
    """Pure helper functions -- URL parsing and image-selection edge cases."""

    @pytest.mark.parametrize(
        ("url", "expected"),
        [
            ("https://open.spotify.com/track/abc123", "abc123"),
            ("https://open.spotify.com/track/abc123?si=xyz", "abc123"),
            ("https://open.spotify.com/playlist/abc123", None),
            ("not a url", None),
        ],
    )
    def test_extract_track_id(self, url: str, expected: str | None) -> None:
        assert spotify_mod._extract_track_id(url) == expected

    def test_best_image_picks_widest(self) -> None:
        images = [{"url": "small", "width": 64}, {"url": "large", "width": 640}]
        assert spotify_mod._best_image(images) == "large"

    def test_best_image_empty(self) -> None:
        assert spotify_mod._best_image([]) is None


# --------------------------------------------------------------------------
# Contract: services/music_providers/__init__.py
# --------------------------------------------------------------------------


class TestResolveContract:
    """`resolve()`/`search()` -- provider auto-detection and dispatch."""

    async def test_resolve_autodetects_youtube_from_url(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        called_with = {}

        async def fake_youtube_resolve(url: str) -> Track:
            called_with["url"] = url
            return Track(
                provider="youtube",
                external_id="x",
                title="t",
                artist="a",
                duration_ms=1,
                artwork_url=None,
                url=url,
            )

        monkeypatch.setattr(youtube_mod, "resolve", fake_youtube_resolve)

        track = await resolve("https://www.youtube.com/watch?v=abc123")
        assert track.provider == "youtube"
        assert called_with["url"] == "https://www.youtube.com/watch?v=abc123"

    async def test_resolve_autodetects_spotify_from_url(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def fake_spotify_resolve(url: str) -> Track:
            return Track(
                provider="spotify",
                external_id="x",
                title="t",
                artist="a",
                duration_ms=1,
                artwork_url=None,
                url=url,
            )

        monkeypatch.setattr(spotify_mod, "resolve", fake_spotify_resolve)

        track = await resolve("https://open.spotify.com/track/abc123")
        assert track.provider == "spotify"

    async def test_resolve_bare_query_uses_explicit_provider(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def fake_youtube_resolve(url: str) -> Track:
            return Track(
                provider="youtube",
                external_id="x",
                title="t",
                artist="a",
                duration_ms=1,
                artwork_url=None,
                url=url,
            )

        monkeypatch.setattr(youtube_mod, "resolve", fake_youtube_resolve)

        track = await resolve("some search text", provider="youtube")
        assert track.provider == "youtube"

    async def test_resolve_bare_query_no_provider_raises_track_not_found(self) -> None:
        """No explicit `provider`, no `YOUTUBE_API_KEY` -- default falls straight to Spotify.

        Real, unmocked `resolve()` path -- see `TestBareTextProviderDefault` for mocked-dispatch
        coverage of the default-provider policy itself. `spotify.resolve()` extracts a track id
        from the URL BEFORE touching credentials, so bare search text (not a Spotify track URL)
        raises `TrackNotFound` here, same outward result as before this default policy existed,
        just via a different code path.
        """
        with pytest.raises(TrackNotFound):
            await resolve("some bare search text with no provider")

    async def test_search_dispatches_to_youtube(self, monkeypatch: pytest.MonkeyPatch) -> None:
        async def fake_search(query: str) -> list[Track]:
            return [
                Track(
                    provider="youtube",
                    external_id="x",
                    title=query,
                    artist="a",
                    duration_ms=1,
                    artwork_url=None,
                    url="https://youtube.com/x",
                )
            ]

        monkeypatch.setattr(youtube_mod, "search", fake_search)

        results = await search("some query", "youtube")
        assert len(results) == 1
        assert results[0].provider == "youtube"

    async def test_search_dispatches_to_spotify(self, monkeypatch: pytest.MonkeyPatch) -> None:
        async def fake_search(query: str) -> list[Track]:
            return [
                Track(
                    provider="spotify",
                    external_id="x",
                    title=query,
                    artist="a",
                    duration_ms=1,
                    artwork_url=None,
                    url="https://open.spotify.com/track/x",
                )
            ]

        monkeypatch.setattr(spotify_mod, "search", fake_search)

        results = await search("some query", "spotify")
        assert results[0].provider == "spotify"

    async def test_search_unknown_provider_raises_track_not_found(self) -> None:
        with pytest.raises(TrackNotFound):
            await search("query", "unknown-provider")


class TestBareTextProviderDefault:
    """`resolve()`'s bare-text (no URL, no explicit `provider`) default-provider policy.

    `_no_real_creds` (autouse) clears `YOUTUBE_API_KEY` before every test, so each test here
    sets it explicitly only where the case requires it configured.
    """

    async def test_youtube_tried_first_when_key_configured(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("YOUTUBE_API_KEY", "test-key")
        spotify_called = False

        async def fake_youtube_resolve(url: str) -> Track:
            return Track(
                provider="youtube",
                external_id="yt",
                title="t",
                artist="a",
                duration_ms=1,
                artwork_url=None,
                url=url,
            )

        async def fake_spotify_resolve(url: str) -> Track:
            nonlocal spotify_called
            spotify_called = True
            raise AssertionError("spotify must not be called when youtube succeeds")

        monkeypatch.setattr(youtube_mod, "resolve", fake_youtube_resolve)
        monkeypatch.setattr(spotify_mod, "resolve", fake_spotify_resolve)

        track = await resolve("some bare search text")

        assert track.provider == "youtube"
        assert spotify_called is False

    async def test_falls_back_to_spotify_when_youtube_finds_nothing(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("YOUTUBE_API_KEY", "test-key")

        async def fake_youtube_resolve(url: str) -> Track:
            raise TrackNotFound(url)

        async def fake_spotify_resolve(url: str) -> Track:
            return Track(
                provider="spotify",
                external_id="sp",
                title="t",
                artist="a",
                duration_ms=1,
                artwork_url=None,
                url=url,
            )

        monkeypatch.setattr(youtube_mod, "resolve", fake_youtube_resolve)
        monkeypatch.setattr(spotify_mod, "resolve", fake_spotify_resolve)

        track = await resolve("some bare search text")
        assert track.provider == "spotify"

    async def test_falls_back_to_spotify_when_youtube_unavailable(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("YOUTUBE_API_KEY", "test-key")

        async def fake_youtube_resolve(url: str) -> Track:
            raise ProviderUnavailable("youtube")

        async def fake_spotify_resolve(url: str) -> Track:
            return Track(
                provider="spotify",
                external_id="sp",
                title="t",
                artist="a",
                duration_ms=1,
                artwork_url=None,
                url=url,
            )

        monkeypatch.setattr(youtube_mod, "resolve", fake_youtube_resolve)
        monkeypatch.setattr(spotify_mod, "resolve", fake_spotify_resolve)

        track = await resolve("some bare search text")
        assert track.provider == "spotify"

    async def test_spotify_only_when_no_youtube_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """`_no_real_creds` already cleared `YOUTUBE_API_KEY` -- today's (pre-change) behavior."""
        youtube_called = False

        async def fake_youtube_resolve(url: str) -> Track:
            nonlocal youtube_called
            youtube_called = True
            raise AssertionError("youtube must not be called with no key configured")

        async def fake_spotify_resolve(url: str) -> Track:
            return Track(
                provider="spotify",
                external_id="sp",
                title="t",
                artist="a",
                duration_ms=1,
                artwork_url=None,
                url=url,
            )

        monkeypatch.setattr(youtube_mod, "resolve", fake_youtube_resolve)
        monkeypatch.setattr(spotify_mod, "resolve", fake_spotify_resolve)

        track = await resolve("some bare search text")

        assert track.provider == "spotify"
        assert youtube_called is False

    async def test_explicit_provider_still_wins_over_default(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """`YOUTUBE_API_KEY` set, but an explicit `provider="spotify"` overrides the default."""
        monkeypatch.setenv("YOUTUBE_API_KEY", "test-key")
        youtube_called = False

        async def fake_youtube_resolve(url: str) -> Track:
            nonlocal youtube_called
            youtube_called = True
            raise AssertionError("youtube must not be called -- explicit provider was spotify")

        async def fake_spotify_resolve(url: str) -> Track:
            return Track(
                provider="spotify",
                external_id="sp",
                title="t",
                artist="a",
                duration_ms=1,
                artwork_url=None,
                url=url,
            )

        monkeypatch.setattr(youtube_mod, "resolve", fake_youtube_resolve)
        monkeypatch.setattr(spotify_mod, "resolve", fake_spotify_resolve)

        track = await resolve("some bare search text", provider="spotify")

        assert track.provider == "spotify"
        assert youtube_called is False

    async def test_url_detection_unaffected_by_default_policy(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A URL always wins host detection, regardless of `YOUTUBE_API_KEY`."""
        monkeypatch.setenv("YOUTUBE_API_KEY", "test-key")

        async def fake_spotify_resolve(url: str) -> Track:
            return Track(
                provider="spotify",
                external_id="sp",
                title="t",
                artist="a",
                duration_ms=1,
                artwork_url=None,
                url=url,
            )

        monkeypatch.setattr(spotify_mod, "resolve", fake_spotify_resolve)

        track = await resolve("https://open.spotify.com/track/abc123")
        assert track.provider == "spotify"


class TestDetectProvider:
    """`_detect_provider()` -- host sniffing, including scheme-less input."""

    @pytest.mark.parametrize(
        ("url_or_query", "expected"),
        [
            ("https://www.youtube.com/watch?v=abc", "youtube"),
            ("https://youtube.com/watch?v=abc", "youtube"),
            ("https://youtu.be/abc", "youtube"),
            ("https://music.youtube.com/watch?v=abc", "youtube"),
            ("https://open.spotify.com/track/abc", "spotify"),
            ("youtu.be/abc", "youtube"),
            ("https://notyoutube.com/watch?v=abc", None),
            ("just a plain search query", None),
        ],
    )
    def test_detect_provider(self, url_or_query: str, expected: str | None) -> None:
        from services.music_providers import _detect_provider

        assert _detect_provider(url_or_query) == expected
