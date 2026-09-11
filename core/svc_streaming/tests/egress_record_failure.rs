//! Upload-failure coverage: a segment upload that fails must keep the local
//! file in place, retry with backoff, and eventually succeed once the
//! object store recovers -- per the S8 task scope ("retry with backoff on
//! upload failure (keep the file, WARN with the specific cause)").
//!
//! `FlakyStore` below hand-implements `object_store::ObjectStore` (the
//! crate's own trait, `#[async_trait]`-based) rather than wrapping
//! `InMemory`, since the only methods this test's code path ever calls are
//! `put_opts` -- every other trait method is unreachable here and stubbed
//! to `NotImplemented`.

use std::fmt;
use std::sync::atomic::{AtomicUsize, Ordering};
use std::sync::Arc;
use std::time::Duration;

use async_trait::async_trait;
use futures::stream::BoxStream;
use object_store::path::Path as StorePath;
use object_store::{
    CopyOptions, Error as OsError, Extensions, GetOptions, GetResult, ListResult, MultipartUpload,
    ObjectMeta, ObjectStore, PutMultipartOptions, PutOptions, PutPayload, PutResult,
    Result as OsResult,
};
use svc_streaming::egress::record::{register_metrics, RecordSink};
use svc_streaming::egress::OutputSink;
use svc_streaming::pipeline::{ObjectStoreRef, OutputSpec};
use uuid::Uuid;

/// Fails the first `fail_count` `put_opts` calls with a connection-refused
/// style error (classified by `egress::record::watcher` as
/// `"s3 endpoint unreachable"`), then succeeds. Every other `ObjectStore`
/// method is unreachable in this test and returns `NotImplemented`.
#[derive(Debug)]
struct FlakyStore {
    remaining_failures: AtomicUsize,
    attempts: AtomicUsize,
}

impl FlakyStore {
    fn new(fail_count: usize) -> Self {
        Self {
            remaining_failures: AtomicUsize::new(fail_count),
            attempts: AtomicUsize::new(0),
        }
    }

    fn attempts(&self) -> usize {
        self.attempts.load(Ordering::SeqCst)
    }
}

impl fmt::Display for FlakyStore {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "flaky-test-store")
    }
}

fn not_implemented(operation: &str) -> OsError {
    OsError::NotImplemented {
        operation: operation.to_string(),
        implementer: "FlakyStore".to_string(),
    }
}

#[async_trait]
impl ObjectStore for FlakyStore {
    async fn put_opts(
        &self,
        _location: &StorePath,
        _payload: PutPayload,
        _opts: PutOptions,
    ) -> OsResult<PutResult> {
        self.attempts.fetch_add(1, Ordering::SeqCst);
        let had_failures_remaining = self
            .remaining_failures
            .fetch_update(Ordering::SeqCst, Ordering::SeqCst, |n| n.checked_sub(1))
            .is_ok();
        if had_failures_remaining {
            return Err(OsError::Generic {
                store: "flaky-test-store",
                source: "connection refused".into(),
            });
        }
        Ok(PutResult {
            e_tag: None,
            version: None,
            extensions: Extensions::default(),
        })
    }

    async fn put_multipart_opts(
        &self,
        _location: &StorePath,
        _opts: PutMultipartOptions,
    ) -> OsResult<Box<dyn MultipartUpload>> {
        Err(not_implemented("put_multipart"))
    }

    async fn get_opts(&self, _location: &StorePath, _options: GetOptions) -> OsResult<GetResult> {
        Err(not_implemented("get"))
    }

    fn delete_stream(
        &self,
        _locations: BoxStream<'static, OsResult<StorePath>>,
    ) -> BoxStream<'static, OsResult<StorePath>> {
        Box::pin(futures::stream::empty())
    }

    fn list(&self, _prefix: Option<&StorePath>) -> BoxStream<'static, OsResult<ObjectMeta>> {
        Box::pin(futures::stream::empty())
    }

    async fn list_with_delimiter(&self, _prefix: Option<&StorePath>) -> OsResult<ListResult> {
        Err(not_implemented("list_with_delimiter"))
    }

    async fn copy_opts(
        &self,
        _from: &StorePath,
        _to: &StorePath,
        _options: CopyOptions,
    ) -> OsResult<()> {
        Err(not_implemented("copy"))
    }
}

fn target() -> ObjectStoreRef {
    ObjectStoreRef {
        store: "s3-recordings".into(),
        prefix: "tenant-1/community-1".into(),
    }
}

#[tokio::test(flavor = "multi_thread")]
async fn a_failing_upload_keeps_the_local_file_and_retries_until_it_succeeds() {
    let root =
        std::env::temp_dir().join(format!("svc-streaming-record-failure-{}", Uuid::new_v4()));
    let store = Arc::new(FlakyStore::new(2));
    let metrics = register_metrics(&prometheus::Registry::new());
    let sink = RecordSink::new(root.clone(), store.clone() as Arc<dyn ObjectStore>, metrics)
        .with_poll_interval(Duration::from_millis(30))
        .with_retry_backoff(Duration::from_millis(10), Duration::from_millis(50))
        .with_max_attempts_per_cycle(1); // one attempt per poll cycle -> retries span multiple cycles

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
    // A second, still-open segment so the first is treated as closed.
    tokio::fs::write(dir.join("20260911120100.ts"), vec![0xCD; 128])
        .await
        .expect("write second fake segment");

    // The first two poll cycles fail (file kept); give it several more
    // cycles to succeed on/after the third attempt.
    tokio::time::sleep(Duration::from_millis(400)).await;

    assert!(
        !dir.join("20260911120000.ts").exists(),
        "the segment must eventually be uploaded and deleted after the flaky store recovers"
    );
    assert!(
        store.attempts() >= 3,
        "must have retried at least twice before succeeding, got {} attempts",
        store.attempts()
    );

    let segments = sink.index().list("community-1");
    assert_eq!(segments.len(), 1);
    assert_eq!(segments[0].filename, "20260911120000.ts");

    sink.stop(pipeline_id).await.ok();
    tokio::fs::remove_dir_all(&root).await.ok();
}

#[tokio::test(flavor = "multi_thread")]
async fn an_always_failing_store_never_deletes_the_local_file() {
    let root =
        std::env::temp_dir().join(format!("svc-streaming-record-failure-{}", Uuid::new_v4()));
    // usize::MAX failures -- effectively "never succeeds" for this test's duration.
    let store = Arc::new(FlakyStore::new(usize::MAX));
    let metrics = register_metrics(&prometheus::Registry::new());
    let sink = RecordSink::new(root.clone(), store.clone() as Arc<dyn ObjectStore>, metrics)
        .with_poll_interval(Duration::from_millis(20))
        .with_retry_backoff(Duration::from_millis(5), Duration::from_millis(20))
        .with_max_attempts_per_cycle(2);

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

    tokio::time::sleep(Duration::from_millis(200)).await;

    assert!(
        dir.join("20260911120000.ts").exists(),
        "a permanently failing upload must never delete the local segment"
    );
    assert!(
        sink.index().list("community-1").is_empty(),
        "a failed segment must never be indexed"
    );
    assert!(
        store.attempts() > 1,
        "must have retried more than once, got {} attempts",
        store.attempts()
    );

    sink.stop(pipeline_id).await.ok();
    tokio::fs::remove_dir_all(&root).await.ok();
}
