#!/bin/bash
set -euo pipefail

# Read worker count from environment (WEB_CONCURRENCY is standard, HYPERCORN_WORKERS is module-specific)
WORKERS="${WEB_CONCURRENCY:-${HYPERCORN_WORKERS:-1}}"

echo "[reputation_module] Startup: workers=$WORKERS, module_port=${MODULE_PORT:-8021}, grpc_port=${GRPC_PORT:-50021}"
echo "[reputation_module] gRPC TLS mode: GRPC_TLS_INSECURE_DEV=${GRPC_TLS_INSECURE_DEV:-false}"

exec hypercorn app:app \
  --bind "0.0.0.0:${MODULE_PORT:-8021}" \
  --workers "$WORKERS" \
  "$@"
