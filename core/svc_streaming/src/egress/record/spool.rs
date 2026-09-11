//! Free-space probing for the recording local spool.
//!
//! `object_store`'s `fs` feature (on by default) pulls in `nix`
//! transitively for `statvfs`, but this chunk's Cargo.toml edits are scoped
//! to enabling features on the already-declared `object_store` dependency
//! -- not adding a new direct dependency for FFI-based disk stats. Shelling
//! out to POSIX `df` keeps the probe to the standard library only, and
//! reports correctly whether `STREAM_DATA_DIR` is a real filesystem or (as
//! this chart mounts it) a size-limited tmpfs `emptyDir`.

use std::path::Path;
use std::process::Command;

/// Reports free space, in bytes, available at a filesystem path. Injectable
/// so tests can simulate a nearly-full spool without needing a real
/// constrained filesystem.
pub trait FreeSpaceProbe: Send + Sync {
    fn free_bytes(&self, path: &Path) -> std::io::Result<u64>;
}

/// Default probe: `df -Pk <path>` (POSIX output format), parses the
/// "Available" column (reported in 1024-byte blocks).
#[derive(Debug, Default, Clone, Copy)]
pub struct DfFreeSpaceProbe;

impl FreeSpaceProbe for DfFreeSpaceProbe {
    fn free_bytes(&self, path: &Path) -> std::io::Result<u64> {
        let output = Command::new("df").arg("-Pk").arg(path).output()?;
        if !output.status.success() {
            return Err(std::io::Error::other(format!(
                "df exited with status {}: {}",
                output.status,
                String::from_utf8_lossy(&output.stderr)
            )));
        }
        parse_df_available_kb(&String::from_utf8_lossy(&output.stdout))
            .map(|kb| kb.saturating_mul(1024))
            .ok_or_else(|| std::io::Error::other("could not parse df output"))
    }
}

/// Parses the "Available" column (4th, 1-indexed) from POSIX `df -Pk`
/// output. Split out from [`DfFreeSpaceProbe::free_bytes`] so it's testable
/// without shelling out.
fn parse_df_available_kb(stdout: &str) -> Option<u64> {
    let data_line = stdout.lines().nth(1)?;
    data_line.split_whitespace().nth(3)?.parse().ok()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parses_standard_df_output() {
        let stdout = "Filesystem     1024-blocks      Used Available Capacity Mounted on\n\
                       /dev/nvme0n1p1   976563200 654150372 308794588      68% /\n";
        assert_eq!(parse_df_available_kb(stdout), Some(308_794_588));
    }

    #[test]
    fn missing_data_line_returns_none() {
        assert_eq!(
            parse_df_available_kb("Filesystem 1024-blocks Used Available\n"),
            None
        );
    }

    #[test]
    fn malformed_available_column_returns_none() {
        let stdout = "Filesystem 1024-blocks Used Available Capacity Mounted\n\
                       /dev/x 100 50 not-a-number 50% /mnt\n";
        assert_eq!(parse_df_available_kb(stdout), None);
    }

    #[test]
    fn df_free_space_probe_reports_a_positive_value_for_a_real_path() {
        let probe = DfFreeSpaceProbe;
        let free = probe
            .free_bytes(std::env::temp_dir().as_path())
            .expect("df must succeed against a real, existing path");
        assert!(free > 0);
    }

    #[test]
    fn df_free_space_probe_surfaces_a_nonzero_df_exit_as_an_error() {
        let probe = DfFreeSpaceProbe;
        let err = probe
            .free_bytes(Path::new(
                "/definitely/does/not/exist/svc-streaming-spool-test",
            ))
            .expect_err("df must fail against a path that does not exist");
        assert!(
            err.to_string().contains("df exited with status"),
            "unexpected error: {err}"
        );
    }
}
