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
from services.music_providers.track import Track
from tests.conftest import TENANT_SLUG

SERVICE_API_KEY = "test-service-key"
_ROUTE = "/api/v1/internal/music/queue/requests"


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
