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
#
# lcov mode also drops generated-code SF: records before counting (R20):
# lib/**/*.g.dart, lib/**/*.freezed.dart, lib/pigeon/**, and
# lib/l10n/app_localizations*.dart are never hand-tested, so counting them
# either dilutes real coverage or masks it behind stale generated output.
# Whole SF:..end_of_record blocks are dropped, never partial edits inside
# a record. See scripts/coverage_gate_selftest.sh for the synthetic-fixture
# proof of this filtering behavior.
set -euo pipefail

THRESHOLD="${1:?usage: coverage_gate.sh <threshold-percent> [report-path] [lcov|jacoco]}"
REPORT_TYPE="${3:-lcov}"

# Portable (bash 3.2 compatible -- no mapfile/declare -A) filter: reads an
# lcov file on stdin, writes the lcov file with generated-path records
# removed to stdout, and writes "<total> <excluded>" (SF: record counts) to
# the file path given as $1.
filter_generated_lcov_records() {
  local counts_file="$1"
  awk -v counts_file="${counts_file}" '
    function is_generated(path) {
      if (path ~ /(^|\/)lib\/.*\.g\.dart$/)                         return 1
      if (path ~ /(^|\/)lib\/.*\.freezed\.dart$/)                   return 1
      if (path ~ /(^|\/)lib\/pigeon\//)                             return 1
      if (path ~ /(^|\/)lib\/l10n\/app_localizations[^\/]*\.dart$/) return 1
      return 0
    }
    /^SF:/ {
      total++
      path = $0
      sub(/^SF:/, "", path)
      skip = is_generated(path)
      if (skip) excluded++
      buffer = $0 "\n"
      next
    }
    {
      buffer = buffer $0 "\n"
      if ($0 == "end_of_record") {
        if (!skip) printf "%s", buffer
        buffer = ""
      }
      next
    }
    END {
      printf "%d %d\n", total + 0, excluded + 0 > counts_file
    }
  '
}

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
  RAW_REPORT_PATH="${2:-coverage/lcov.info}"
  if [[ ! -f "${RAW_REPORT_PATH}" ]]; then
    echo "coverage_gate: lcov report not found at ${RAW_REPORT_PATH}" >&2
    exit 1
  fi

  FILTERED_REPORT="$(mktemp "${TMPDIR:-/tmp}/coverage_gate.filtered.XXXXXX")"
  COUNTS_FILE="$(mktemp "${TMPDIR:-/tmp}/coverage_gate.counts.XXXXXX")"
  trap 'rm -f "${FILTERED_REPORT}" "${COUNTS_FILE}"' EXIT

  filter_generated_lcov_records "${COUNTS_FILE}" < "${RAW_REPORT_PATH}" > "${FILTERED_REPORT}"
  read -r RAW_SF_COUNT EXCLUDED_SF_COUNT < "${COUNTS_FILE}"
  REPORT_PATH="${FILTERED_REPORT}"

  SF_COUNT=$(grep -c '^SF:' "${REPORT_PATH}" || :)   # grep -c prints 0 and exits 1 on no match; the zero is then rejected below
  echo "coverage_gate: excluded ${EXCLUDED_SF_COUNT} generated-file record(s) of ${RAW_SF_COUNT} total, ${SF_COUNT} remaining"
  if [[ "${SF_COUNT}" -eq 0 ]]; then
    echo "coverage_gate: zero SF (source file) records in ${RAW_REPORT_PATH} after excluding generated files -- treating as FAILURE, not a pass" >&2
    exit 1
  fi
  LF_TOTAL=$(grep '^LF:' "${REPORT_PATH}" | awk -F: '{s+=$2} END {print s+0}')
  LH_TOTAL=$(grep '^LH:' "${REPORT_PATH}" | awk -F: '{s+=$2} END {print s+0}')
  if [[ "${LF_TOTAL}" -eq 0 ]]; then
    echo "coverage_gate: zero lines found (LF) across ${SF_COUNT} files in ${RAW_REPORT_PATH} -- treating as FAILURE, not a pass" >&2
    exit 1
  fi
  PERCENT=$(python3 -c "print(f'{${LH_TOTAL} / ${LF_TOTAL} * 100:.2f}')")
  echo "coverage_gate: ${SF_COUNT} files examined, ${LH_TOTAL}/${LF_TOTAL} lines covered"
fi

echo "coverage_gate: ${PERCENT}% (threshold ${THRESHOLD}%)"
awk -v p="${PERCENT}" -v t="${THRESHOLD}" 'BEGIN { exit !(p+0 >= t+0) }'
