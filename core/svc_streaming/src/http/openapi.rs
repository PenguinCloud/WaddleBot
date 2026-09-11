//! Two-document OpenAPI split.
//!
//! `/api/v1/openapi/public.json` is unauthenticated and documents only
//! `/health` -- safe for a load balancer or uptime checker to fetch.
//! `/api/v1/openapi.json` documents every route this service exposes and
//! sits behind the JWT auth middleware ([`crate::http::auth::require_auth`]),
//! same as the Swagger UI mounted alongside it -- see `rules/security.md`
//! OpenAPI / utoipa-swagger-ui gating.

use axum::{Json, Router};
use utoipa::OpenApi;
use utoipa_swagger_ui::SwaggerUi;

use crate::http::{health, AppState};

/// Full OpenAPI document: every route this service exposes. As later
/// chunks add routes under `/api/v1/*` they should register their
/// `#[utoipa::path]`-annotated handlers here.
#[derive(OpenApi)]
#[openapi(
    paths(health::liveness, health::readiness),
    components(schemas(health::LivenessBody, health::ReadinessBody, health::DependencyStatus))
)]
pub struct FullApiDoc;

/// Public, minimal OpenAPI document: `/health` only. Intentionally omits
/// `/readyz` (leaks dependency topology) and everything under `/api/v1`.
#[derive(OpenApi)]
#[openapi(paths(health::liveness), components(schemas(health::LivenessBody)))]
pub struct PublicApiDoc;

/// `GET /api/v1/openapi/public.json` (unauthenticated).
pub async fn public_spec() -> Json<utoipa::openapi::OpenApi> {
    Json(PublicApiDoc::openapi())
}

/// Swagger UI mounted at `/api/v1/docs`, serving the full (authenticated)
/// spec. `SwaggerUi::url` both registers `GET /api/v1/openapi.json` *and*
/// points the UI at it -- a second, hand-written route for the same path
/// would be an overlapping-route panic at router build time, so this is
/// the only place `/api/v1/openapi.json` is registered. The caller of this
/// function is responsible for wrapping the result in the JWT auth
/// `route_layer` -- see [`crate::http::router`].
pub fn swagger_ui() -> Router<AppState> {
    Router::<AppState>::from(
        SwaggerUi::new("/api/v1/docs").url("/api/v1/openapi.json", FullApiDoc::openapi()),
    )
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn public_doc_only_documents_health() {
        let doc = PublicApiDoc::openapi();
        let paths: Vec<&String> = doc.paths.paths.keys().collect();
        assert_eq!(paths, vec!["/health"]);
    }

    #[test]
    fn full_doc_documents_health_and_readyz() {
        let doc = FullApiDoc::openapi();
        let mut paths: Vec<&String> = doc.paths.paths.keys().collect();
        paths.sort();
        assert_eq!(paths, vec!["/health", "/readyz"]);
    }
}
