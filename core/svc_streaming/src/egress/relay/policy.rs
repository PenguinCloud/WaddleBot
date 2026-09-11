//! Relay tier limits (`RelayPolicy`), enforcing the FREE-tier caps from
//! `docs/plans/2026-08-31-svc-streaming-design.md` §2 cap#3: `FREE_LIMITS`
//! 3 destinations / 6000 kbps / 7-day retention
//! (`video_proxy_module/services/license_service.py:11-16`). Retention is a
//! recording concern (owned by `egress::record`, S8) and is not enforced
//! here; only destination count and aggregate forward bitrate apply to
//! push relay.

use thiserror::Error;

/// Errors returned when a relay operation would exceed the caller's
/// [`RelayPolicy`]. Message text is stable -- surfaced verbatim to
/// operators/API callers.
#[derive(Debug, Error, Clone, Copy, PartialEq, Eq)]
pub enum RelayPolicyError {
    #[error("relay limit: max {0} destinations on this tier")]
    TooManyDestinations(usize),
    #[error("relay limit: {requested_kbps} kbps exceeds max {max_kbps} kbps on this tier")]
    BitrateExceeded { requested_kbps: u32, max_kbps: u32 },
}

/// Per-pipeline relay limits. Defaults to the Free tier (`docs/plans/
/// 2026-08-31-svc-streaming-design.md` §2 cap#3); Professional's
/// `PREMIUM_LIMITS` (10 dest / 15000 kbps / 90d, `license_service.py:18-23`)
/// is a later chunk's concern to wire through license-tier resolution --
/// this type only enforces whatever limits it is constructed with.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct RelayPolicy {
    pub max_destinations: usize,
    pub max_bitrate_kbps: u32,
}

impl RelayPolicy {
    /// Free-tier limits: 3 destinations, 6000 kbps aggregate forward
    /// bitrate.
    pub const FREE: Self = Self {
        max_destinations: 3,
        max_bitrate_kbps: 6000,
    };

    /// Professional-tier limits (`PREMIUM_LIMITS`, `license_service.py:
    /// 18-23`): 10 destinations, 15000 kbps. Not wired to license-tier
    /// resolution yet -- available for callers (tests, a later chunk) that
    /// already know the resolved tier.
    pub const PROFESSIONAL: Self = Self {
        max_destinations: 10,
        max_bitrate_kbps: 15_000,
    };

    /// Errors if adding another destination would push the pipeline's
    /// active target count past `max_destinations`. `prospective_count` is
    /// the count *after* the destination being validated is added.
    pub fn check_destination_count(
        &self,
        prospective_count: usize,
    ) -> Result<(), RelayPolicyError> {
        if prospective_count > self.max_destinations {
            return Err(RelayPolicyError::TooManyDestinations(self.max_destinations));
        }
        Ok(())
    }

    /// Errors if `requested_kbps` (aggregate forward bitrate) exceeds
    /// `max_bitrate_kbps`.
    pub fn check_bitrate_kbps(&self, requested_kbps: u32) -> Result<(), RelayPolicyError> {
        if requested_kbps > self.max_bitrate_kbps {
            return Err(RelayPolicyError::BitrateExceeded {
                requested_kbps,
                max_kbps: self.max_bitrate_kbps,
            });
        }
        Ok(())
    }
}

impl Default for RelayPolicy {
    fn default() -> Self {
        Self::FREE
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn free_tier_allows_up_to_three_destinations() {
        let policy = RelayPolicy::FREE;
        assert!(policy.check_destination_count(1).is_ok());
        assert!(policy.check_destination_count(3).is_ok());
    }

    #[test]
    fn free_tier_rejects_a_fourth_destination_with_stable_message() {
        let policy = RelayPolicy::FREE;
        let err = policy.check_destination_count(4).unwrap_err();
        assert_eq!(
            err.to_string(),
            "relay limit: max 3 destinations on this tier"
        );
    }

    #[test]
    fn free_tier_rejects_bitrate_over_6000_kbps() {
        let policy = RelayPolicy::FREE;
        let err = policy.check_bitrate_kbps(6001).unwrap_err();
        assert!(matches!(
            err,
            RelayPolicyError::BitrateExceeded {
                requested_kbps: 6001,
                max_kbps: 6000
            }
        ));
    }

    #[test]
    fn free_tier_allows_bitrate_at_exactly_the_cap() {
        let policy = RelayPolicy::FREE;
        assert!(policy.check_bitrate_kbps(6000).is_ok());
    }

    #[test]
    fn professional_tier_allows_more_destinations_and_bitrate() {
        let policy = RelayPolicy::PROFESSIONAL;
        assert!(policy.check_destination_count(10).is_ok());
        assert!(policy.check_bitrate_kbps(15_000).is_ok());
        assert!(policy.check_destination_count(11).is_err());
    }

    #[test]
    fn default_policy_is_free_tier() {
        assert_eq!(RelayPolicy::default(), RelayPolicy::FREE);
    }
}
