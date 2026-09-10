/// App-wide constants: license server base URL, GitHub releases endpoint
/// for the update checker, and shared licensing timing knobs.
///
/// Single source of truth — every service needing one of these values
/// imports it from here rather than hardcoding it inline.
library;

/// Base URL for the PenguinTech license server's Gazer-facing API.
const String kLicenseBaseUrl = 'https://license.penguintech.io/api/v2';

/// GitHub Releases API endpoint polled by `UpdateChecker`.
const String kGithubReleasesUrl =
    'https://api.github.com/repos/penguintechinc/waddlebot/releases';

/// Interval between license keepalive pings while the app is foregrounded.
const Duration kLicenseKeepaliveInterval = Duration(minutes: 5);

/// Offline grace period: a cached license result stays usable this long
/// after the last successful fetch, even if the server is unreachable.
const Duration kLicenseGracePeriod = Duration(days: 7);
