#!/usr/bin/env bash
# End-to-end demo: upload every sample and poll until each reaches a terminal state.
set -euo pipefail

: "${UPLOAD_URL:?Set UPLOAD_URL to the Cloud Run service URL}"
: "${ACCESS_CODE:?Set ACCESS_CODE to the demo access code}"

SAMPLES_DIR="${SAMPLES_DIR:-samples}"
MAX_POLLS="${MAX_POLLS:-60}"
POLL_SECONDS="${POLL_SECONDS:-2}"

json_field() {
  python3 -c 'import json,sys; data=json.load(sys.stdin); print(data.get(sys.argv[1], ""))' "$1"
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

  policy_status="$(printf '%s' "$body" | python3 -c \
    'import json,sys; data=json.load(sys.stdin); print((data.get("result") or {}).get("policy_status", ""))' 2>/dev/null || true)"
  error_code="$(printf '%s' "$body" | json_field error_code)"

  printf 'status=%s' "$status"
  if [ -n "$policy_status" ]; then
    printf ' policy=%s' "$policy_status"
  fi
  if [ -n "$error_code" ]; then
    printf ' error=%s' "$error_code"
  fi
  printf '\n'

  if [ "$status" != "COMPLETED" ] && [ "${name#06_}" = "$name" ]; then
    failures=$((failures + 1))
  fi
  if [ "${name#06_}" != "$name" ] && [ "$status" = "FAILED" ] && [ "$error_code" != "EXTRACTION_FAILED" ]; then
    failures=$((failures + 1))
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
