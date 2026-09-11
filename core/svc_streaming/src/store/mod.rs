//! Storage-adjacent concerns that don't belong to a single pipeline stage:
//! secret-reference resolution today, `object_store`-backed recording
//! target helpers as a later chunk (`egress::record`) needs them.

pub mod secrets;

pub use secrets::{DefaultSecretResolver, SecretError, SecretRef, SecretResolver};
