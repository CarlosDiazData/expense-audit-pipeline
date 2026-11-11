#!/usr/bin/env bash
# End-to-end demo: upload every sample, poll to a terminal state, and assert the
# expected policy outcome documented in samples/README.md.
set -euo pipefail

: "${UPLOAD_URL:?Set UPLOAD_URL to the Cloud Run service URL}"
: "${ACCESS_CODE:?Set ACCESS_CODE to the demo access code}"

SAMPLES_DIR="${SAMPLES_DIR:-samples}"
MAX_POLLS="${MAX_POLLS:-60}"
POLL_SECONDS="${POLL_SECONDS:-2}"

json_field() {
  python3 -c 'import json,sys; data=json.load(sys.stdin); print(data.get(sys.argv[1], ""))' "$1"
}

result_field() {
  python3 -c 'import json,sys; data=json.load(sys.stdin); print((data.get("result") or {}).get(sys.argv[1], ""))' "$1"
}

result_reasons() {
  python3 -c 'import json,sys; data=json.load(sys.stdin); print(" ".join((data.get("result") or {}).get("policy_reasons") or []))'
}

expected_policy() {
  case "$1" in
    01_*) echo "VALID" ;;
    02_*) echo "SUSPICIOUS" ;;
    03_*) echo "VALID" ;;
    04_*) echo "SUSPICIOUS" ;;
    05_*) echo "NON_DEDUCTIBLE" ;;
    *) echo "" ;;
  esac
}

required_reason() {
  case "$1" in
    02_*) echo "PER_EXPENSE_LIMIT_EXCEEDED" ;;
    04_*) echo "DUPLICATE_EXPENSE" ;;
    05_*) echo "INVALID_RFC" ;;
    *) echo "" ;;
  esac
}

failures=0
for sample in "$SAMPLES_DIR"/*.pdf; do
  name="$(basename "$sample")"
  printf 'Uploading %s ... ' "$name"

  response="$(curl -fsS -X POST "$UPLOAD_URL/upload" \
    -F "code=$ACCESS_CODE" \
    -F "file=@$sample;type=application/pdf")" || {
    printf 'upload failed\n'
    failures=$((failures + 1))
    continue
  }

  upload_id="$(printf '%s' "$response" | json_field upload_id)"
  status="PENDING"
  body="{}"
  for _ in $(seq 1 "$MAX_POLLS"); do
    body="$(curl -fsS "$UPLOAD_URL/status/$upload_id")"
    status="$(printf '%s' "$body" | json_field status)"
    if [ "$status" = "COMPLETED" ] || [ "$status" = "FAILED" ]; then
      break
    fi
    sleep "$POLL_SECONDS"
  done

  policy_status="$(printf '%s' "$body" | result_field policy_status)"
  reasons="$(printf '%s' "$body" | result_reasons)"
  error_code="$(printf '%s' "$body" | json_field error_code)"

  printf 'status=%s' "$status"
  if [ -n "$policy_status" ]; then
    printf ' policy=%s' "$policy_status"
  fi
  if [ -n "$reasons" ]; then
    printf ' reasons=[%s]' "$reasons"
  fi
  if [ -n "$error_code" ]; then
    printf ' error=%s' "$error_code"
  fi
  printf '\n'

  is_noisy=0
  if [ "${name#06_}" != "$name" ]; then
    is_noisy=1
  fi

  if [ "$status" = "PENDING" ]; then
    echo "  unexpected: still PENDING after $MAX_POLLS polls" >&2
    failures=$((failures + 1))
    continue
  fi

  if [ "$status" = "FAILED" ]; then
    if [ "$is_noisy" -eq 1 ] && [ "$error_code" = "EXTRACTION_FAILED" ]; then
      echo "  controlled noisy-sample outcome (EXTRACTION_FAILED)"
    else
      echo "  unexpected failure: $error_code" >&2
      failures=$((failures + 1))
    fi
    continue
  fi

  if [ "$is_noisy" -eq 0 ]; then
    expected="$(expected_policy "$name")"
    if [ -n "$expected" ] && [ "$policy_status" != "$expected" ]; then
      echo "  unexpected policy: expected $expected, got $policy_status" >&2
      failures=$((failures + 1))
      continue
    fi
    reason="$(required_reason "$name")"
    if [ -n "$reason" ] && [[ " $reasons " != *" $reason "* ]]; then
      echo "  missing expected reason: $reason" >&2
      failures=$((failures + 1))
      continue
    fi
  fi
done

if command -v bq >/dev/null 2>&1 && [ -n "${PROJECT_ID:-}" ] && [ -n "${BQ_DATASET:-}" ]; then
  echo
  echo "Latest BigQuery rows:"
  bq query --use_legacy_sql=false --format=prettyjson \
    "SELECT original_filename, policy_status, policy_reasons
     FROM \`${PROJECT_ID}.${BQ_DATASET}.expenses\`
     ORDER BY created_at DESC
     LIMIT 10"
fi

if [ "$failures" -gt 0 ]; then
  echo "e2e finished with $failures unexpected outcome(s)." >&2
  exit 1
fi

echo "e2e finished successfully."
