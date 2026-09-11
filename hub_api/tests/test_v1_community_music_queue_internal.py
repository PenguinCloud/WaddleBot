"""`blueprints/v1/community_music_queue.py`'s internal (service-key) enqueue route.

Standalone Quart app registering `music_internal_bp` against the
`music_station_db` fixture (`tests/conftest.py`) -- the chat-command path
(`core/svc_action/bundles/social_music_action.py`, `!sr`/`!songrequest`)
has no user JWT, so it calls this route with `X-Service-Key` auth instead
of the admin-scoped `music_queue_bp` route
(`tests/test_v1_community_music_queue_blueprint.py` covers that one, and
owns `fake_resolve`'s own real-`resolve()`-vs-mocked rationale, not
re-derived here).
"""

from __future__ import annotations

from typing import Any

import pytest
from quart import Quart
from quart_schema import QuartSchema

from blueprints.v1.community_music_queue import music_internal_bp, music_queue_bp
from config import HubAPIConfig
from services import music_status_service
from services.music_providers.track import Track
from tests.conftest import TENANT_SLUG

SERVICE_API_KEY = "test-service-key"
_ROUTE = "/api/v1/internal/music/queue/requests"
_STATUS_ROUTE = "/api/v1/internal/music/status"


def _test_config() -> HubAPIConfig:
    return HubAPIConfig(
        module_name="hub-api-test",
        module_version="0.0.0-test",
        module_port=8205,
        grpc_port=50205,
        database_url="sqlite:memory",
        database_read_replica_url=None,
        db_pool_size=1,
        db_max_retries=1,
        db_retry_delay=1,
        secret_key="change-me-in-production",
        jwt_algorithm="HS256",
        default_tenant_slug="global",
        posthog_api_key=None,
        posthog_host="https://license.penguintech.io",
        license_server_url="https://license.penguintech.io",
        identity_callback_base_url="http://localhost:8205",
        frontend_origin="http://localhost:5173",
        log_level="INFO",
    )


@pytest.fixture(autouse=True)
def _service_key_env(monkeypatch: Any) -> None:
    monkeypatch.setenv("SERVICE_API_KEY", SERVICE_API_KEY)


@pytest.fixture
def app(music_station_db: Any) -> Quart:
    quart_app = Quart(__name__)
    QuartSchema(quart_app)
    quart_app.register_blueprint(music_internal_bp)
    quart_app.register_blueprint(music_queue_bp)
    quart_app.config["dal"] = music_station_db.dal
    quart_app.config["async_dal"] = music_station_db
    quart_app.config["HUB_API_CONFIG"] = _test_config()
    return quart_app


@pytest.fixture
def client(app: Quart) -> Any:
    return app.test_client()


@pytest.fixture
def fake_resolve(monkeypatch: Any) -> None:
    """Deterministic stand-in for the real, network-calling `resolve()`."""

    async def _fake(url_or_query: str, provider: str | None = None) -> Track:
        return Track(
            provider=provider or "youtube",
            external_id=url_or_query,
            title=f"Track for {url_or_query}",
            artist="Test Artist",
            duration_ms=210000,
            artwork_url=None,
            url=url_or_query,
        )

    monkeypatch.setattr("services.community_music_queue_service.resolve", _fake)


def _seed_community(db: Any) -> int:
    tenant_row = db.dal(db.dal.tenants.slug == TENANT_SLUG).select().first()
    community_id = db.dal.communities.insert(name="test-community", tenant_id=tenant_row.id)
    db.dal.commit()
    return int(community_id)


class TestServiceKeyAuth:
    """Fail-first gate: no valid `X-Service-Key` -> 401, never a bare-JWT bypass."""

    async def test_missing_service_key_is_401(self, client: Any, music_station_db: Any) -> None:
        community_id = _seed_community(music_station_db)
        response = await client.post(
            _ROUTE, json={"communityId": community_id, "urlOrQuery": "some song"}
        )
        assert response.status_code == 401

    async def test_wrong_service_key_is_401(self, client: Any, music_station_db: Any) -> None:
        community_id = _seed_community(music_station_db)
        response = await client.post(
            _ROUTE,
            headers={"X-Service-Key": "wrong-key"},
            json={"communityId": community_id, "urlOrQuery": "some song"},
        )
        assert response.status_code == 401


class TestEnqueue:
    """Service-key-authenticated enqueue -- payload validation, tenant derivation, resolution."""

    async def test_enqueue_with_service_key_succeeds(
        self, client: Any, music_station_db: Any, fake_resolve: None
    ) -> None:
        community_id = _seed_community(music_station_db)
        response = await client.post(
            _ROUTE,
            headers={"X-Service-Key": SERVICE_API_KEY},
            json={
                "communityId": community_id,
                "urlOrQuery": "never gonna give you up",
                "platform": "twitch",
                "platformUserId": "abc123",
                "requestedByDisplay": "penguin",
            },
        )
        assert response.status_code == 201
        body = await response.get_json()
        assert body["success"] is True
        assert body["item"]["track"]["title"] == "Track for never gonna give you up"
        assert body["item"]["communityId"] == community_id
        assert body["item"]["requestedBy"] is None  # unlinked platform identity
        # Sole item in an empty queue: nothing ahead, nothing playing -> "next up" (0).
        assert body["item"]["etaSeconds"] == 0

    async def test_enqueue_resolves_hub_user_id_from_linked_platform_identity(
        self, client: Any, music_station_db: Any, fake_resolve: None
    ) -> None:
        """A viewer whose platform identity is linked in `community_members` gets attribution."""
        community_id = _seed_community(music_station_db)
        music_station_db.dal.community_members.insert(
            community_id=community_id,
            user_id="7",
            platform="twitch",
            platform_user_id="abc123",
        )
        music_station_db.dal.commit()

        response = await client.post(
            _ROUTE,
            headers={"X-Service-Key": SERVICE_API_KEY},
            json={
                "communityId": community_id,
                "urlOrQuery": "some song",
                "platform": "twitch",
                "platformUserId": "abc123",
            },
        )
        assert response.status_code == 201
        body = await response.get_json()
        assert body["item"]["requestedBy"] == 7

    async def test_enqueue_eta_seconds_sums_duration_of_items_ahead(
        self, client: Any, music_station_db: Any, fake_resolve: None
    ) -> None:
        """A second request's ETA = the first (still-queued) item's `durationMs` in seconds."""
        community_id = _seed_community(music_station_db)
        first = await client.post(
            _ROUTE,
            headers={"X-Service-Key": SERVICE_API_KEY},
            json={"communityId": community_id, "urlOrQuery": "song one"},
        )
        assert (await first.get_json())["item"]["etaSeconds"] == 0

        second = await client.post(
            _ROUTE,
            headers={"X-Service-Key": SERVICE_API_KEY},
            json={"communityId": community_id, "urlOrQuery": "song two"},
        )
        assert second.status_code == 201
        body = await second.get_json()
        # fake_resolve() always returns duration_ms=210000 -> 210 seconds ahead.
        assert body["item"]["etaSeconds"] == 210
        assert body["item"]["position"] == 2

    async def test_missing_community_id_is_400(self, client: Any) -> None:
        response = await client.post(
            _ROUTE, headers={"X-Service-Key": SERVICE_API_KEY}, json={"urlOrQuery": "some song"}
        )
        assert response.status_code == 400

    async def test_blank_url_or_query_is_400(self, client: Any, music_station_db: Any) -> None:
        community_id = _seed_community(music_station_db)
        response = await client.post(
            _ROUTE,
            headers={"X-Service-Key": SERVICE_API_KEY},
            json={"communityId": community_id, "urlOrQuery": "   "},
        )
        assert response.status_code == 400

    async def test_unknown_community_is_404(self, client: Any) -> None:
        response = await client.post(
            _ROUTE,
            headers={"X-Service-Key": SERVICE_API_KEY},
            json={"communityId": 999999, "urlOrQuery": "some song"},
        )
        assert response.status_code == 404

    async def test_no_track_found_is_422(self, client: Any, music_station_db: Any) -> None:
        """An unmocked `resolve()` call with an unsupported provider -> deterministic 422."""
        community_id = _seed_community(music_station_db)
        response = await client.post(
            _ROUTE,
            headers={"X-Service-Key": SERVICE_API_KEY},
            json={
                "communityId": community_id,
                "urlOrQuery": "some song",
                "provider": "not-a-real-provider",
            },
        )
        assert response.status_code == 422

    async def test_enqueue_survives_communities_schema_drift(
        self, client: Any, music_station_db: Any, fake_resolve: None
    ) -> None:
        """Regression: `communities.about_extended` (and 4 siblings) are bound in prod.

        `services/schema.py` for pydal query-building but were never added by
        any numbered migration against real Postgres -- a documented,
        pre-existing gap (see that module's docstring, gap 4). This fixture's
        `bind_auth_tables(dal, migrate=True)` auto-creates every bound column
        (including the gap ones), masking the drift -- so it's dropped here to
        reproduce prod's real schema. Before the fix, `internal_enqueue_song_
        request` ran a bare `dal.communities....select()`, which pulls every
        bound field and 500s with `psycopg2.errors.UndefinedColumn` the moment
        a gap column is missing; the fix restricts the select to the two
        columns this handler actually needs.
        """
        community_id = _seed_community(music_station_db)
        music_station_db.dal.executesql("ALTER TABLE communities DROP COLUMN about_extended")
        music_station_db.dal.commit()

        response = await client.post(
            _ROUTE,
            headers={"X-Service-Key": SERVICE_API_KEY},
            json={"communityId": community_id, "urlOrQuery": "some song"},
        )
        assert response.status_code == 201
        body = await response.get_json()
        assert body["success"] is True

    async def test_enqueue_unhandled_error_returns_json_body(
        self, client: Any, music_station_db: Any, fake_resolve: None
    ) -> None:
        """Regression: an unhandled exception must never surface as an empty-body 500.

        `social_music_action._enqueue()`
        (`core/svc_action`) parses `error.message` from the JSON body to
        decide its chat reply and to log the real cause; an empty body logs
        `message=` with no diagnostic value (the exact symptom this fixes).
        Simulates any still-unhandled DB error (not just the schema-drift
        case above, which is now avoided) by dropping a column the handler
        does NOT defend against.
        """
        community_id = _seed_community(music_station_db)
        music_station_db.dal.executesql("ALTER TABLE communities DROP COLUMN tenant_id")
        music_station_db.dal.commit()

        response = await client.post(
            _ROUTE,
            headers={"X-Service-Key": SERVICE_API_KEY},
            json={"communityId": community_id, "urlOrQuery": "some song"},
        )
        assert response.status_code == 500
        body = await response.get_json()
        assert body is not None
        assert body["success"] is False
        assert body["error"]["message"]  # non-empty -- the bug being fixed


class TestMusicStatus:
    """`GET /api/v1/internal/music/status` -- backs `!sr status`'s enabled/error replies."""

    @pytest.fixture(autouse=True)
    def _reset_health_cache(self) -> Any:
        """`check_spotify_health()`'s module-level cache must not leak between tests."""
        music_status_service._health_cache = None
        yield
        music_status_service._health_cache = None

    async def test_missing_service_key_is_401(self, client: Any, music_station_db: Any) -> None:
        community_id = _seed_community(music_station_db)
        response = await client.get(f"{_STATUS_ROUTE}?community_id={community_id}")
        assert response.status_code == 401

    async def test_missing_community_id_is_400(self, client: Any) -> None:
        response = await client.get(_STATUS_ROUTE, headers={"X-Service-Key": SERVICE_API_KEY})
        assert response.status_code == 400

    async def test_non_integer_community_id_is_400(self, client: Any) -> None:
        response = await client.get(
            f"{_STATUS_ROUTE}?community_id=not-a-number",
            headers={"X-Service-Key": SERVICE_API_KEY},
        )
        assert response.status_code == 400

    async def test_unknown_community_is_404(self, client: Any) -> None:
        response = await client.get(
            f"{_STATUS_ROUTE}?community_id=999999", headers={"X-Service-Key": SERVICE_API_KEY}
        )
        assert response.status_code == 404

    async def test_healthy_provider_returns_enabled_state(
        self, client: Any, music_station_db: Any, monkeypatch: Any
    ) -> None:
        community_id = _seed_community(music_station_db)

        async def _healthy() -> music_status_service.ProviderHealth:
            return music_status_service.ProviderHealth(healthy=True, cause=None)

        monkeypatch.setattr("blueprints.v1.community_music_queue.check_spotify_health", _healthy)

        response = await client.get(
            f"{_STATUS_ROUTE}?community_id={community_id}",
            headers={"X-Service-Key": SERVICE_API_KEY},
        )
        assert response.status_code == 200
        body = await response.get_json()
        assert body["status"] == "success"
        assert body["data"]["state"] == "enabled"
        assert body["data"]["cause"] is None
        assert body["data"]["provider"] == "spotify"
        assert body["data"]["queue_length"] == 0

    async def test_unhealthy_provider_returns_error_state_with_cause(
        self, client: Any, music_station_db: Any, monkeypatch: Any
    ) -> None:
        community_id = _seed_community(music_station_db)

        async def _unhealthy() -> music_status_service.ProviderHealth:
            return music_status_service.ProviderHealth(
                healthy=False, cause="spotify oauth token didn't work (401)"
            )

        monkeypatch.setattr("blueprints.v1.community_music_queue.check_spotify_health", _unhealthy)

        response = await client.get(
            f"{_STATUS_ROUTE}?community_id={community_id}",
            headers={"X-Service-Key": SERVICE_API_KEY},
        )
        assert response.status_code == 200
        body = await response.get_json()
        assert body["data"]["state"] == "error"
        assert body["data"]["cause"] == "spotify oauth token didn't work (401)"

    async def test_queue_length_counts_queued_and_playing_but_not_removed(
        self, client: Any, music_station_db: Any, fake_resolve: None, monkeypatch: Any
    ) -> None:
        community_id = _seed_community(music_station_db)

        async def _healthy() -> music_status_service.ProviderHealth:
            return music_status_service.ProviderHealth(healthy=True, cause=None)

        monkeypatch.setattr("blueprints.v1.community_music_queue.check_spotify_health", _healthy)

        await client.post(
            _ROUTE,
            headers={"X-Service-Key": SERVICE_API_KEY},
            json={"communityId": community_id, "urlOrQuery": "song one"},
        )
        second = await client.post(
            _ROUTE,
            headers={"X-Service-Key": SERVICE_API_KEY},
            json={"communityId": community_id, "urlOrQuery": "song two"},
        )
        second_queue_id = (await second.get_json())["item"]["id"]
        # Directly flip one item to `removed` (bypassing the admin-scoped
        # moderation route, which needs a JWT this test module doesn't set
        # up) -- isolates queue_length's own status-filtering logic.
        music_station_db.dal(music_station_db.dal.music_station_queue.id == second_queue_id).update(
            status="removed"
        )
        music_station_db.dal.commit()

        response = await client.get(
            f"{_STATUS_ROUTE}?community_id={community_id}",
            headers={"X-Service-Key": SERVICE_API_KEY},
        )
        body = await response.get_json()
        assert body["data"]["queue_length"] == 1
