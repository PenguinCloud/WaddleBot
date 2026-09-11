//! `RecordSink::ffmpeg_output_args` argv-fragment coverage, exercised
//! through the crate's public API (`svc_streaming::egress::record`) rather
//! than the colocated `#[cfg(test)]` unit test in `src/egress/record.rs` --
//! per the S8 task scope's `tests/egress_record_*.rs` requirement.

use std::path::PathBuf;
use std::sync::Arc;

use object_store::memory::InMemory;
use svc_streaming::egress::record::{register_metrics, RecordSink};
use svc_streaming::pipeline::{ObjectStoreRef, PipelineId};
use uuid::Uuid;

fn test_sink(local_root: PathBuf) -> RecordSink {
    let metrics = register_metrics(&prometheus::Registry::new());
    RecordSink::new(local_root, Arc::new(InMemory::new()), metrics)
}

fn target() -> ObjectStoreRef {
    ObjectStoreRef {
        store: "s3-recordings".into(),
        prefix: "tenant-1/community-1".into(),
    }
}

/// Per `docs/plans/2026-09-11-svc-streaming-pipeline-matrix.md` §4 Record:
/// `-f segment -segment_time 60 -reset_timestamps 1 -strftime 1 <path>`.
#[test]
fn ffmpeg_output_args_matches_the_spec_recipe() {
    let root = std::env::temp_dir().join(format!("svc-streaming-record-args-{}", Uuid::new_v4()));
    let sink = test_sink(root);
    let pipeline_id: PipelineId = Uuid::nil();
    let target = target();

    let args = sink.ffmpeg_output_args(pipeline_id, &target);
    let flags: Vec<&str> = args[..8].iter().map(String::as_str).collect();

    assert_eq!(
        flags,
        vec![
            "-f",
            "segment",
            "-segment_time",
            "60",
            "-reset_timestamps",
            "1",
            "-strftime",
            "1",
        ]
    );

    let pattern = &args[8];
    assert!(
        pattern.ends_with("%Y%m%d%H%M%S.ts"),
        "pattern was {pattern}"
    );
    assert!(
        pattern.contains(&format!("{}/{pipeline_id}", target.prefix)),
        "pattern {pattern} must be scoped under the ObjectStoreRef prefix + pipeline id"
    );
}

#[test]
fn ffmpeg_output_args_scopes_different_pipelines_to_different_directories() {
    let root = std::env::temp_dir().join(format!("svc-streaming-record-args-{}", Uuid::new_v4()));
    let sink = test_sink(root);
    let target = target();

    let args_a = sink.ffmpeg_output_args(Uuid::new_v4(), &target);
    let args_b = sink.ffmpeg_output_args(Uuid::new_v4(), &target);

    assert_ne!(
        args_a[8], args_b[8],
        "distinct pipeline ids must not share a segment directory"
    );
}
