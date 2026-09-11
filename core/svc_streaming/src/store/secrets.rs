//! Secret reference resolution.
//!
//! Pipeline specs never carry raw secrets (webhook URLs with embedded
//! stream keys, object-store credentials) -- only a [`SecretRef`] pointing
//! at where the real value lives. Resolving a reference is the only place
//! a secret's bytes exist in memory, per `rules/client.md` Secrets &
//! Credentials ("ZERO secrets in distributed builds ... injected at
//! runtime").

use serde::{Deserialize, Serialize};
use thiserror::Error;

use crate::config::Secret;

/// Points at a secret value without embedding it. `Env` reads a named
/// environment variable; `File` reads a mounted Kubernetes Secret volume
/// file -- the standard pattern for Secret-backed credentials in this
/// cluster.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(tag = "source", rename_all = "snake_case")]
pub enum SecretRef {
    Env { var: String },
    File { path: String },
}

/// Errors resolving a [`SecretRef`].
#[derive(Debug, Error)]
pub enum SecretError {
    #[error("environment variable {0} is not set")]
    MissingEnv(String),
    #[error("failed to read secret file {path}: {source}")]
    FileRead {
        path: String,
        #[source]
        source: std::io::Error,
    },
}

/// Resolves a [`SecretRef`] into its underlying [`Secret`] value.
/// Implementations must never log the resolved value.
pub trait SecretResolver: Send + Sync {
    fn resolve(&self, secret_ref: &SecretRef) -> Result<Secret, SecretError>;
}

/// Default resolver: reads `Env` from the process environment and `File`
/// from the local filesystem (Kubernetes Secret volume mount).
#[derive(Debug, Default, Clone, Copy)]
pub struct DefaultSecretResolver;

impl SecretResolver for DefaultSecretResolver {
    fn resolve(&self, secret_ref: &SecretRef) -> Result<Secret, SecretError> {
        match secret_ref {
            SecretRef::Env { var } => std::env::var(var)
                .map(Secret::new)
                .map_err(|_| SecretError::MissingEnv(var.clone())),
            SecretRef::File { path } => std::fs::read_to_string(path)
                .map(|s| Secret::new(s.trim().to_string()))
                .map_err(|source| SecretError::FileRead {
                    path: path.clone(),
                    source,
                }),
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::Mutex;

    static ENV_LOCK: Mutex<()> = Mutex::new(());

    #[test]
    fn env_ref_resolves_from_environment() {
        let _guard = ENV_LOCK.lock().unwrap();
        // SAFETY: serialized by ENV_LOCK.
        unsafe { std::env::set_var("SVC_STREAMING_TEST_SECRET", "resolved-value") };
        let resolver = DefaultSecretResolver;
        let secret_ref = SecretRef::Env {
            var: "SVC_STREAMING_TEST_SECRET".to_string(),
        };
        let resolved = resolver.resolve(&secret_ref).expect("var is set");
        assert_eq!(resolved.expose(), "resolved-value");
        unsafe { std::env::remove_var("SVC_STREAMING_TEST_SECRET") };
    }

    #[test]
    fn env_ref_missing_var_errors() {
        let _guard = ENV_LOCK.lock().unwrap();
        unsafe { std::env::remove_var("SVC_STREAMING_TEST_MISSING") };
        let resolver = DefaultSecretResolver;
        let secret_ref = SecretRef::Env {
            var: "SVC_STREAMING_TEST_MISSING".to_string(),
        };
        assert!(matches!(
            resolver.resolve(&secret_ref),
            Err(SecretError::MissingEnv(_))
        ));
    }

    #[test]
    fn file_ref_resolves_from_disk() {
        let dir = std::env::temp_dir();
        let path = dir.join(format!("svc-streaming-secret-test-{}", std::process::id()));
        std::fs::write(&path, "file-secret-value\n").unwrap();
        let resolver = DefaultSecretResolver;
        let secret_ref = SecretRef::File {
            path: path.to_string_lossy().to_string(),
        };
        let resolved = resolver.resolve(&secret_ref).expect("file exists");
        assert_eq!(resolved.expose(), "file-secret-value");
        std::fs::remove_file(&path).ok();
    }

    #[test]
    fn file_ref_missing_file_errors() {
        let resolver = DefaultSecretResolver;
        let secret_ref = SecretRef::File {
            path: "/nonexistent/path/for/svc-streaming-tests".to_string(),
        };
        assert!(matches!(
            resolver.resolve(&secret_ref),
            Err(SecretError::FileRead { .. })
        ));
    }
}
