//! Bounded local spool coverage: when free space on `STREAM_DATA_DIR` drops
//! below the configured floor, the watcher must stop recording (ERROR +
//! `recording_upload_failures_total{reason="spool_exhausted"}`) rather than
//! keep writing into an exhausted filesystem -- per the S8 task scope.

use std::path::Path;
use std::sync::Arc;
use std::time::Duration;

use object_store::memory::InMemory;
use svc_streaming::egress::record::{register_metrics, FreeSpaceProbe, RecordSink};
use svc_streaming::egress::OutputSink;
use svc_streaming::pipeline::{ObjectStoreRef, OutputSpec};
use uuid::Uuid;

/// Always reports a fixed free-space value, regardless of the real
/// filesystem -- lets this test simulate "nearly full" deterministically.
struct FixedFreeSpace(u64);

impl FreeSpaceProbe for FixedFreeSpace {
    fn free_bytes(&self, _path: &Path) -> std::io::Result<u64> {
        Ok(self.0)
    }
}

fn target() -> ObjectStoreRef {
    ObjectStoreRef {
        store: "s3-recordings".into(),
        prefix: "tenant-1/community-1".into(),
    }
}

#[tokio::test(flavor = "multi_thread")]
async fn a_spool_below_the_free_space_floor_stops_the_watcher_without_uploading() {
    let root = std::env::temp_dir().join(format!("svc-streaming-record-spool-{}", Uuid::new_v4()));
    let metrics = register_metrics(&prometheus::Registry::new());
    let one_gib = 1024 * 1024 * 1024;
    let sink = RecordSink::new(
        root.clone(),
        Arc::new(InMemory::new()) as Arc<dyn object_store::ObjectStore>,
        metrics,
    )
    .with_poll_interval(Duration::from_millis(15))
    .with_min_free_bytes(one_gib)
    // Always below the 1 GiB floor.
    .with_free_space_probe(Arc::new(FixedFreeSpace(1024)));

    let pipeline_id = Uuid::new_v4();
    let dir = root
        .join("tenant-1/community-1")
        .join(pipeline_id.to_string());

    sink.start(
        pipeline_id,
        OutputSpec::Record {
            profile: "1080p60".into(),
            target: target(),
        },
    )
    .await
    .expect("start must succeed");

    // Even a closed segment must be left untouched -- the watcher checks
    // free space before it ever looks at the directory.
    tokio::fs::create_dir_all(&dir)
        .await
        .expect("create segment dir");
    tokio::fs::write(dir.join("20260911120000.ts"), vec![0xAB; 512])
        .await
        .expect("write fake segment");
    tokio::fs::write(dir.join("20260911120100.ts"), vec![0xCD; 128])
        .await
        .expect("write second fake segment");

    tokio::time::sleep(Duration::from_millis(150)).await;

    assert!(
        dir.join("20260911120000.ts").exists(),
        "a spool-exhausted watcher must never upload/delete a segment"
    );
    assert!(sink.index().list("community-1").is_empty());

    // The watcher has already returned on its own (spool exhausted) --
    // `stop` must still be a safe, idempotent no-op (the JoinHandle it
    // would have awaited is gone from the running-watchers map only after
    // `stop` is called explicitly, so this also exercises stopping a
    // watcher that stopped itself).
    sink.stop(pipeline_id)
        .await
        .expect("stop after self-exhaustion must not error");

    tokio::fs::remove_dir_all(&root).await.ok();
}

#[tokio::test(flavor = "multi_thread")]
async fn plenty_of_free_space_lets_recording_proceed_normally() {
    let root = std::env::temp_dir().join(format!("svc-streaming-record-spool-{}", Uuid::new_v4()));
    let metrics = register_metrics(&prometheus::Registry::new());
    let sink = RecordSink::new(
        root.clone(),
        Arc::new(InMemory::new()) as Arc<dyn object_store::ObjectStore>,
        metrics,
    )
    .with_poll_interval(Duration::from_millis(15))
    .with_min_free_bytes(1024)
    .with_free_space_probe(Arc::new(FixedFreeSpace(10 * 1024 * 1024 * 1024)));

    let pipeline_id = Uuid::new_v4();
    let dir = root
        .join("tenant-1/community-1")
        .join(pipeline_id.to_string());

    sink.start(
        pipeline_id,
        OutputSpec::Record {
            profile: "1080p60".into(),
            target: target(),
        },
    )
    .await
    .expect("start must succeed");

    tokio::fs::create_dir_all(&dir)
        .await
        .expect("create segment dir");
    tokio::fs::write(dir.join("20260911120000.ts"), vec![0xAB; 512])
        .await
        .expect("write fake segment");
    tokio::fs::write(dir.join("20260911120100.ts"), vec![0xCD; 128])
        .await
        .expect("write second fake segment");

    tokio::time::sleep(Duration::from_millis(150)).await;

    assert!(
        !dir.join("20260911120000.ts").exists(),
        "with ample free space the closed segment must upload normally"
    );
    assert_eq!(sink.index().list("community-1").len(), 1);

    sink.stop(pipeline_id).await.ok();
    tokio::fs::remove_dir_all(&root).await.ok();
}
