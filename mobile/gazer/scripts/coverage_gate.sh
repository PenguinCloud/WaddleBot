#!/usr/bin/env bash
# Fails the build when line coverage is below the given threshold, or when
# the coverage report contains zero examined source files -- a scanner
# pointed at nothing is a FAILURE, not a pass (critical-rules.md
# Verification Integrity: assert a non-zero denominator).
#
# Usage: coverage_gate.sh <threshold-percent> [report-path] [lcov|jacoco]
#   lcov mode (default): report-path defaults to coverage/lcov.info
#   jacoco mode: report-path defaults to
#     android/app/build/reports/jacoco/jacocoTestReport/jacocoTestReport.xml
set -euo pipefail

THRESHOLD="${1:?usage: coverage_gate.sh <threshold-percent> [report-path] [lcov|jacoco]}"
REPORT_TYPE="${3:-lcov}"

if [[ "${REPORT_TYPE}" == "jacoco" ]]; then
  REPORT_PATH="${2:-android/app/build/reports/jacoco/jacocoTestReport/jacocoTestReport.xml}"
  if [[ ! -f "${REPORT_PATH}" ]]; then
    echo "coverage_gate: jacoco report not found at ${REPORT_PATH}" >&2
    exit 1
  fi
  read -r MISSED COVERED <<PYOUT
$(python3 - "${REPORT_PATH}" <<'PYEOF'
import sys
import xml.etree.ElementTree as ET

root = ET.parse(sys.argv[1]).getroot()
counters = [c for c in root.findall("counter") if c.get("type") == "LINE"]
if not counters:
    print("0 0")
else:
    counter = counters[0]
    print(f"{counter.get('missed')} {counter.get('covered')}")
PYEOF
)
PYOUT
  TOTAL=$((MISSED + COVERED))
  if [[ "${TOTAL}" -eq 0 ]]; then
    echo "coverage_gate: zero lines examined in ${REPORT_PATH} -- treating as FAILURE, not a pass" >&2
    exit 1
  fi
  PERCENT=$(python3 -c "print(f'{${COVERED} / ${TOTAL} * 100:.2f}')")
  echo "coverage_gate: ${TOTAL} lines examined (jacoco LINE counter), ${COVERED} covered"
else
  REPORT_PATH="${2:-coverage/lcov.info}"
  if [[ ! -f "${REPORT_PATH}" ]]; then
    echo "coverage_gate: lcov report not found at ${REPORT_PATH}" >&2
    exit 1
  fi
  SF_COUNT=$(grep -c '^SF:' "${REPORT_PATH}" || :)   # grep -c prints 0 and exits 1 on no match; the zero is then rejected below
  if [[ "${SF_COUNT}" -eq 0 ]]; then
    echo "coverage_gate: zero SF (source file) records in ${REPORT_PATH} -- treating as FAILURE, not a pass" >&2
    exit 1
  fi
  LF_TOTAL=$(grep '^LF:' "${REPORT_PATH}" | awk -F: '{s+=$2} END {print s+0}')
  LH_TOTAL=$(grep '^LH:' "${REPORT_PATH}" | awk -F: '{s+=$2} END {print s+0}')
  if [[ "${LF_TOTAL}" -eq 0 ]]; then
    echo "coverage_gate: zero lines found (LF) across ${SF_COUNT} files in ${REPORT_PATH} -- treating as FAILURE, not a pass" >&2
    exit 1
  fi
  PERCENT=$(python3 -c "print(f'{${LH_TOTAL} / ${LF_TOTAL} * 100:.2f}')")
  echo "coverage_gate: ${SF_COUNT} files examined, ${LH_TOTAL}/${LF_TOTAL} lines covered"
fi

echo "coverage_gate: ${PERCENT}% (threshold ${THRESHOLD}%)"
awk -v p="${PERCENT}" -v t="${THRESHOLD}" 'BEGIN { exit !(p+0 >= t+0) }'
