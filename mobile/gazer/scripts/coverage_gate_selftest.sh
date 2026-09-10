#!/usr/bin/env bash
# Synthetic-fixture self-check for coverage_gate.sh's lcov generated-file
# filtering (R20). Proves, against fabricated lcov records (never real
# coverage output), that:
#   (a) a fixture mixing one generated-path record with one real record
#       counts only the real one;
#   (b) a fixture containing only generated-path records fails with the
#       zero-denominator message, not a false pass.
#
# This never touches the real coverage/lcov.info -- it is pure fixture
# data written to a scratch directory, cleaned up on exit.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GATE="${SCRIPT_DIR}/coverage_gate.sh"
WORKDIR="$(mktemp -d "${TMPDIR:-/tmp}/coverage_gate_selftest.XXXXXX")"
trap 'rm -rf "${WORKDIR}"' EXIT

FAILURES=0

# --- Fixture (a): one generated record + one real record -----------------
# The generated record (lib/models/foo.g.dart) has terrible coverage
# (0/10 lines hit); the real record (lib/models/foo.dart) has perfect
# coverage (5/5). If the generated record were counted, the blended
# percentage would be 5/15 = 33%, which fails a 90% threshold. If it is
# correctly excluded, the percentage is 5/5 = 100%, which passes.
MIXED_LCOV="${WORKDIR}/mixed.info"
cat > "${MIXED_LCOV}" <<'EOF'
SF:lib/models/foo.g.dart
DA:1,0
LF:10
LH:0
end_of_record
SF:lib/models/foo.dart
DA:1,1
DA:2,1
DA:3,1
DA:4,1
DA:5,1
LF:5
LH:5
end_of_record
EOF

MIXED_OUTPUT="$(mktemp "${WORKDIR}/mixed_output.XXXXXX")"
MIXED_STATUS=0
"${GATE}" 90 "${MIXED_LCOV}" lcov > "${MIXED_OUTPUT}" 2>&1 || MIXED_STATUS=$?

echo "--- fixture (a): mixed generated + real ---"
cat "${MIXED_OUTPUT}"

if [[ "${MIXED_STATUS}" -ne 0 ]]; then
  echo "SELFTEST FAIL (a): expected exit 0 (real-only coverage is 100%), got ${MIXED_STATUS}" >&2
  FAILURES=$((FAILURES + 1))
fi
if ! grep -q "excluded 1 generated-file record(s) of 2 total, 1 remaining" "${MIXED_OUTPUT}"; then
  echo "SELFTEST FAIL (a): expected exclusion count line not found" >&2
  FAILURES=$((FAILURES + 1))
fi
if ! grep -q "1 files examined, 5/5 lines covered" "${MIXED_OUTPUT}"; then
  echo "SELFTEST FAIL (a): expected the generated file's 0/10 lines to be excluded from the LF/LH totals" >&2
  FAILURES=$((FAILURES + 1))
fi

# --- Fixture (b): only generated records ----------------------------------
# Every SF: record matches a generated-path pattern, so after filtering
# zero records remain -- this must fail with the zero-denominator message,
# never a false pass.
GENERATED_ONLY_LCOV="${WORKDIR}/generated_only.info"
cat > "${GENERATED_ONLY_LCOV}" <<'EOF'
SF:lib/models/foo.g.dart
DA:1,1
LF:1
LH:1
end_of_record
SF:lib/models/bar.freezed.dart
DA:1,1
LF:1
LH:1
end_of_record
SF:lib/pigeon/pipeline.g.dart
DA:1,1
LF:1
LH:1
end_of_record
SF:lib/l10n/app_localizations_en.dart
DA:1,1
LF:1
LH:1
end_of_record
EOF

GENERATED_ONLY_OUTPUT="$(mktemp "${WORKDIR}/generated_only_output.XXXXXX")"
GENERATED_ONLY_STATUS=0
"${GATE}" 90 "${GENERATED_ONLY_LCOV}" lcov > "${GENERATED_ONLY_OUTPUT}" 2>&1 || GENERATED_ONLY_STATUS=$?

echo "--- fixture (b): generated-only ---"
cat "${GENERATED_ONLY_OUTPUT}"

if [[ "${GENERATED_ONLY_STATUS}" -eq 0 ]]; then
  echo "SELFTEST FAIL (b): expected non-zero exit (zero denominator after filtering), got 0" >&2
  FAILURES=$((FAILURES + 1))
fi
if ! grep -q "zero SF (source file) records" "${GENERATED_ONLY_OUTPUT}"; then
  echo "SELFTEST FAIL (b): expected the zero-denominator failure message" >&2
  FAILURES=$((FAILURES + 1))
fi
if ! grep -q "excluded 4 generated-file record(s) of 4 total, 0 remaining" "${GENERATED_ONLY_OUTPUT}"; then
  echo "SELFTEST FAIL (b): expected all 4 records to be reported excluded" >&2
  FAILURES=$((FAILURES + 1))
fi

echo "---"
if [[ "${FAILURES}" -gt 0 ]]; then
  echo "coverage_gate_selftest: ${FAILURES} check(s) failed" >&2
  exit 1
fi
echo "coverage_gate_selftest: all checks passed"
