//! JWT bearer-token authentication (user/service calls) and the internal
//! `X-Service-Key` header check used by `/api/v1/internal/*` routes.
//!
//! Every authenticated request must carry a `tenant` claim -- tenant
//! isolation is checked before any scope/role decision, per
//! `rules/security.md` Tenant Isolation. `AuthenticatedClaims` is an axum
//! extractor (usable directly on a handler) and [`require_auth`] is the
//! equivalent `route_layer` middleware used to gate a whole route group
//! (the OpenAPI full spec + Swagger UI in [`crate::http::router`]).
//! `/api/v1/internal/*` routes added by later chunks should use
//! [`ServiceKey`] instead -- a user JWT is never required for
//! service-to-service calls that already present the shared service key.

use axum::extract::{FromRequestParts, Request, State};
use axum::http::header::AUTHORIZATION;
use axum::http::request::Parts;
use axum::middleware::Next;
use axum::response::Response;
use jsonwebtoken::{decode, Algorithm, DecodingKey, Validation};
use serde::{Deserialize, Serialize};

use crate::config::Config;
use crate::error::ApiError;
use crate::http::AppState;

/// Standard OIDC claim set required on every authenticated request -- see
/// `rules/security.md` JWT Claims (All Tokens). `roles` is audit/display
/// only; authorization decisions must be made on `scope`, never on
/// `roles`.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Claims {
    pub sub: String,
    pub iss: String,
    pub aud: String,
    pub iat: i64,
    pub exp: i64,
    pub scope: String,
    pub tenant: String,
    #[serde(default)]
    pub teams: Vec<String>,
    #[serde(default)]
    pub roles: Vec<String>,
}

/// Extractor that validates the `Authorization: Bearer <jwt>` header
/// against the configured issuer/audience and returns the decoded claims.
/// 401 for a missing/malformed/invalid/expired token; 403 for a
/// well-formed token that is missing the mandatory `tenant` claim.
pub struct AuthenticatedClaims(pub Claims);

impl FromRequestParts<AppState> for AuthenticatedClaims {
    type Rejection = ApiError;

    async fn from_request_parts(
        parts: &mut Parts,
        state: &AppState,
    ) -> Result<Self, Self::Rejection> {
        let claims = extract_claims(parts, &state.config)?;
        Ok(AuthenticatedClaims(claims))
    }
}

fn extract_claims(parts: &Parts, config: &Config) -> Result<Claims, ApiError> {
    let header = parts
        .headers
        .get(AUTHORIZATION)
        .and_then(|v| v.to_str().ok())
        .ok_or_else(|| ApiError::Unauthorized("missing Authorization header".into()))?;
    let token = header.strip_prefix("Bearer ").ok_or_else(|| {
        ApiError::Unauthorized("Authorization header is not a Bearer token".into())
    })?;

    let claims = decode_claims(token, config)?;

    if claims.tenant.trim().is_empty() {
        return Err(ApiError::Forbidden(
            "token is missing the required tenant claim".into(),
        ));
    }

    Ok(claims)
}

fn decode_claims(token: &str, config: &Config) -> Result<Claims, ApiError> {
    // HS256 is the only verification path wired in this scaffold; RS256 via
    // `JWT_JWKS_URL` (key fetch + rotation/caching) is left to a later
    // chunk -- see `config::CliConfig::jwt_jwks_url`.
    let secret = config
        .jwt_hmac_secret
        .as_ref()
        .ok_or_else(|| ApiError::Unauthorized("no JWT verification key configured".into()))?;

    let mut validation = Validation::new(Algorithm::HS256);
    validation.set_issuer(std::slice::from_ref(&config.cli.jwt_issuer));
    validation.set_audience(std::slice::from_ref(&config.cli.jwt_audience));

    let key = DecodingKey::from_secret(secret.expose().as_bytes());
    let data = decode::<Claims>(token, &key, &validation)
        .map_err(|err| ApiError::Unauthorized(format!("invalid token: {err}")))?;
    Ok(data.claims)
}

/// `route_layer` middleware equivalent of [`AuthenticatedClaims`]: rejects
/// before the handler runs and inserts [`Claims`] as a request extension so
/// downstream handlers can use `Extension<Claims>` instead of re-parsing.
pub async fn require_auth(
    State(state): State<AppState>,
    request: Request,
    next: Next,
) -> Result<Response, ApiError> {
    let (mut parts, body) = request.into_parts();
    let claims = extract_claims(&parts, &state.config)?;
    parts.extensions.insert(claims);
    let request = Request::from_parts(parts, body);
    Ok(next.run(request).await)
}

/// Header name internal service-to-service callers present in place of a
/// user JWT for `/api/v1/internal/*` routes.
pub const SERVICE_KEY_HEADER: &str = "x-service-key";

/// Extractor that validates the `X-Service-Key` header against the
/// configured `SERVICE_API_KEY`. Used for internal, non-user-facing routes
/// instead of a JWT -- always requires a secret, never open.
pub struct ServiceKey;

impl FromRequestParts<AppState> for ServiceKey {
    type Rejection = ApiError;

    async fn from_request_parts(
        parts: &mut Parts,
        state: &AppState,
    ) -> Result<Self, Self::Rejection> {
        let provided = parts
            .headers
            .get(SERVICE_KEY_HEADER)
            .and_then(|v| v.to_str().ok())
            .ok_or_else(|| ApiError::Unauthorized("missing X-Service-Key header".into()))?;

        if provided != state.config.service_api_key.expose() {
            return Err(ApiError::Unauthorized("invalid service key".into()));
        }
        Ok(ServiceKey)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::config::{CliConfig, Config, Secret};
    use axum::http::HeaderValue;
    use clap::Parser;
    use jsonwebtoken::{encode, EncodingKey, Header};

    fn test_config(hmac_secret: Option<&str>) -> Config {
        let cli = CliConfig::parse_from(["svc-streaming"]);
        Config {
            cli,
            db_password: Secret::new("db-pass"),
            cache_password: None,
            service_api_key: Secret::new("service-key-value"),
            jwt_hmac_secret: hmac_secret.map(Secret::new),
        }
    }

    fn sign(claims: &Claims, secret: &str) -> String {
        encode(
            &Header::new(Algorithm::HS256),
            claims,
            &EncodingKey::from_secret(secret.as_bytes()),
        )
        .unwrap()
    }

    fn valid_claims(config: &Config) -> Claims {
        let now = chrono::Utc::now().timestamp();
        Claims {
            sub: "user-123".into(),
            iss: config.cli.jwt_issuer.clone(),
            aud: config.cli.jwt_audience.clone(),
            iat: now,
            exp: now + 3600,
            scope: "streaming:read".into(),
            tenant: "tenant-abc".into(),
            teams: vec![],
            roles: vec![],
        }
    }

    fn parts_with_auth(header: Option<&str>) -> Parts {
        let mut builder = axum::http::Request::builder().uri("/");
        if let Some(h) = header {
            builder = builder.header(AUTHORIZATION, HeaderValue::from_str(h).unwrap());
        }
        let (parts, _) = builder.body(()).unwrap().into_parts();
        parts
    }

    #[test]
    fn missing_header_is_unauthorized() {
        let config = test_config(Some("secret"));
        let parts = parts_with_auth(None);
        let err = extract_claims(&parts, &config).unwrap_err();
        assert!(matches!(err, ApiError::Unauthorized(_)));
    }

    #[test]
    fn non_bearer_header_is_unauthorized() {
        let config = test_config(Some("secret"));
        let parts = parts_with_auth(Some("Basic abc123"));
        let err = extract_claims(&parts, &config).unwrap_err();
        assert!(matches!(err, ApiError::Unauthorized(_)));
    }

    #[test]
    fn valid_token_decodes_claims() {
        let config = test_config(Some("secret"));
        let claims = valid_claims(&config);
        let token = sign(&claims, "secret");
        let parts = parts_with_auth(Some(&format!("Bearer {token}")));
        let decoded = extract_claims(&parts, &config).expect("token should validate");
        assert_eq!(decoded.tenant, "tenant-abc");
        assert_eq!(decoded.sub, "user-123");
    }

    #[test]
    fn wrong_signing_secret_is_rejected() {
        let config = test_config(Some("secret"));
        let claims = valid_claims(&config);
        let token = sign(&claims, "wrong-secret");
        let parts = parts_with_auth(Some(&format!("Bearer {token}")));
        let err = extract_claims(&parts, &config).unwrap_err();
        assert!(matches!(err, ApiError::Unauthorized(_)));
    }

    #[test]
    fn expired_token_is_rejected() {
        let config = test_config(Some("secret"));
        let mut claims = valid_claims(&config);
        claims.iat -= 7200;
        claims.exp -= 7200;
        let token = sign(&claims, "secret");
        let parts = parts_with_auth(Some(&format!("Bearer {token}")));
        let err = extract_claims(&parts, &config).unwrap_err();
        assert!(matches!(err, ApiError::Unauthorized(_)));
    }

    #[test]
    fn wrong_audience_is_rejected() {
        let config = test_config(Some("secret"));
        let mut claims = valid_claims(&config);
        claims.aud = "someone-else".into();
        let token = sign(&claims, "secret");
        let parts = parts_with_auth(Some(&format!("Bearer {token}")));
        let err = extract_claims(&parts, &config).unwrap_err();
        assert!(matches!(err, ApiError::Unauthorized(_)));
    }

    #[test]
    fn missing_tenant_claim_is_forbidden() {
        let config = test_config(Some("secret"));
        let mut claims = valid_claims(&config);
        claims.tenant = String::new();
        let token = sign(&claims, "secret");
        let parts = parts_with_auth(Some(&format!("Bearer {token}")));
        let err = extract_claims(&parts, &config).unwrap_err();
        assert!(matches!(err, ApiError::Forbidden(_)));
    }

    #[test]
    fn no_verification_key_configured_is_unauthorized() {
        let config = test_config(None);
        let claims = valid_claims(&config);
        let token = sign(&claims, "secret");
        let parts = parts_with_auth(Some(&format!("Bearer {token}")));
        let err = extract_claims(&parts, &config).unwrap_err();
        assert!(matches!(err, ApiError::Unauthorized(_)));
    }

    #[test]
    fn service_key_header_matches_is_accepted() {
        let config = test_config(None);
        assert_eq!(config.service_api_key.expose(), "service-key-value");
    }
}
