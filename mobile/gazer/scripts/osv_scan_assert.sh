#!/usr/bin/env bash
# Runs osv-scanner against one lockfile and asserts a non-zero package count in addition to
# osv-scanner's own exit code -- a scan that examines zero packages (misconfigured path, moved
# lockfile, wrong flag) must be a FAILURE, not a vacuous pass (critical-rules.md Verification
# Integrity: assert a non-zero denominator). Shared by the Makefile's mobile-security target and
# the CI security job so both enforce an identical gate.
#
# Usage: osv_scan_assert.sh <lockfile-path>
set -euo pipefail

LOCKFILE="${1:?usage: osv_scan_assert.sh <lockfile-path>}"

if OUTPUT=$(osv-scanner --lockfile="${LOCKFILE}" 2>&1); then
  STATUS=0
else
  STATUS=$?
fi
echo "${OUTPUT}"

COUNT=$(printf '%s' "${OUTPUT}" | grep -oE 'found [0-9]+ packages' | grep -oE '[0-9]+' | head -1)
if [[ -z "${COUNT}" || "${COUNT}" -eq 0 ]]; then
  echo "osv-scanner: zero (or unparsed) packages examined for ${LOCKFILE} -- treating as FAILURE, not a pass" >&2
  exit 1
fi
echo "osv-scanner: ${COUNT} packages examined (${LOCKFILE})"
exit "${STATUS}"
