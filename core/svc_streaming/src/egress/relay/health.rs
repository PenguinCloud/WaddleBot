//! Per-target health tracking, driven by classifying ffmpeg `-f tee`
//! stderr lines (`[tee @ ...] ...`, `Output #<N> ...`) into a bounded set
//! of failure reasons. Bounded on purpose: `relay_target_failures_total`
//! carries `reason` as a Prometheus label, and an unbounded/free-text
//! label value is a cardinality blowup waiting to happen -- classify into
//! a fixed enum, never echo the raw ffmpeg line into a label.

use std::fmt;

/// Current health of one relay target, as last observed from ffmpeg
/// stderr via `RelaySink::observe_stderr_line`.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum TargetHealth {
    Active,
    Failing(FailureReasonKind),
}

/// A classified relay-target failure reason. Bounded set, fixed
/// `metric_label()` text -- safe to use as a Prometheus label value.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum FailureReasonKind {
    /// TCP connect to the destination was refused.
    ConnectionRefused,
    /// The destination host failed to resolve.
    DnsLookupFailed,
    /// The destination rejected the stream key/publish attempt (RTMP
    /// `NetStream.Publish`/handshake rejection, or an SRT/HTTP-style
    /// unauthorized response).
    StreamKeyRejected,
    /// ffmpeg reported a tee-output failure that didn't match a more
    /// specific pattern above.
    Unclassified,
}

impl FailureReasonKind {
    /// Fixed, bounded-cardinality string used as the
    /// `relay_target_failures_total{reason}` label value.
    pub fn metric_label(&self) -> &'static str {
        match self {
            FailureReasonKind::ConnectionRefused => "destination refused connection",
            FailureReasonKind::DnsLookupFailed => "dns lookup failed",
            FailureReasonKind::StreamKeyRejected => "stream key rejected (rtmp error)",
            FailureReasonKind::Unclassified => "unclassified ffmpeg error",
        }
    }
}

impl fmt::Display for FailureReasonKind {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(self.metric_label())
    }
}

/// Classifies a single ffmpeg stderr line into a [`FailureReasonKind`], or
/// `None` if the line isn't failure-related (progress/informational
/// output). Matching is intentionally coarse substring matching against
/// ffmpeg/librtmp/OS-resolver wording -- ffmpeg's exact phrasing varies by
/// build and muxer, so this favors classifying a genuine failure as
/// `Unclassified` over silently dropping it.
pub fn classify_stderr_line(line: &str) -> Option<FailureReasonKind> {
    let lower = line.to_ascii_lowercase();

    if lower.contains("connection refused") {
        return Some(FailureReasonKind::ConnectionRefused);
    }
    if lower.contains("name or service not known")
        || lower.contains("could not resolve host")
        || lower.contains("nodename nor servname provided")
        || lower.contains("temporary failure in name resolution")
    {
        return Some(FailureReasonKind::DnsLookupFailed);
    }
    if lower.contains("netstream.publish")
        || lower.contains("netconnection.connect.rejected")
        || lower.contains("bad name")
        || lower.contains("unauthorized")
        || lower.contains("forbidden")
        || lower.contains("handshake failed")
    {
        return Some(FailureReasonKind::StreamKeyRejected);
    }
    // `-f tee`'s own failure wording (`onfail=ignore` still logs a failure
    // line) plus a generic ffmpeg output-stream failure -- catch these as
    // Unclassified rather than silently ignoring them.
    if lower.contains("failed to")
        || (lower.contains("output") && lower.contains("error"))
        || lower.contains("av_interleaved_write_frame")
        || lower.contains("i/o error")
    {
        return Some(FailureReasonKind::Unclassified);
    }
    None
}

/// Extracts the `N` from an ffmpeg `Output #N` / `Output 'N'` style line,
/// used to map a stderr line back to the target at that index in the
/// order `tee_slaves` produced them. Returns `None` if no such marker is
/// present.
pub fn extract_output_index(line: &str) -> Option<usize> {
    let lower = line.to_ascii_lowercase();
    let start = lower.find("output #")? + "output #".len();
    let digits: String = line[start..]
        .chars()
        .take_while(|c| c.is_ascii_digit())
        .collect();
    if digits.is_empty() {
        return None;
    }
    digits.parse().ok()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn classifies_connection_refused() {
        let reason = classify_stderr_line(
            "[tee @ 0x55f] Output #1, mpegts, to 'srt://host:9000': Connection refused",
        );
        assert_eq!(reason, Some(FailureReasonKind::ConnectionRefused));
    }

    #[test]
    fn classifies_dns_failure() {
        let reason = classify_stderr_line(
            "[tcp @ 0x55f] Failed to resolve hostname bad.example.invalid: Name or service not known",
        );
        assert_eq!(reason, Some(FailureReasonKind::DnsLookupFailed));
    }

    #[test]
    fn classifies_stream_key_rejection() {
        let reason = classify_stderr_line("Server error: NetStream.Publish.BadName");
        assert_eq!(reason, Some(FailureReasonKind::StreamKeyRejected));
    }

    #[test]
    fn classifies_unauthorized_as_stream_key_rejection() {
        let reason = classify_stderr_line("HTTP error 401 Unauthorized while publishing");
        assert_eq!(reason, Some(FailureReasonKind::StreamKeyRejected));
    }

    #[test]
    fn classifies_generic_tee_failure_as_unclassified() {
        let reason = classify_stderr_line("[tee @ 0x55f] Failed to init output stream 1:0");
        assert_eq!(reason, Some(FailureReasonKind::Unclassified));
    }

    #[test]
    fn progress_lines_are_not_failures() {
        let reason =
            classify_stderr_line("frame=  120 fps= 30 q=-1.0 size=    512kB time=00:00:04.00");
        assert_eq!(reason, None);
    }

    #[test]
    fn metric_label_is_stable_bounded_text() {
        assert_eq!(
            FailureReasonKind::ConnectionRefused.metric_label(),
            "destination refused connection"
        );
        assert_eq!(
            FailureReasonKind::DnsLookupFailed.metric_label(),
            "dns lookup failed"
        );
        assert_eq!(
            FailureReasonKind::StreamKeyRejected.metric_label(),
            "stream key rejected (rtmp error)"
        );
    }

    #[test]
    fn extract_output_index_parses_the_marker() {
        assert_eq!(
            extract_output_index("Output #1, mpegts, to 'srt://host:9000?streamid=x':"),
            Some(1)
        );
        assert_eq!(
            extract_output_index("Output #0, flv, to 'rtmp://host/app/x':"),
            Some(0)
        );
    }

    #[test]
    fn extract_output_index_returns_none_without_a_marker() {
        assert_eq!(extract_output_index("frame= 120 fps= 30"), None);
    }
}
