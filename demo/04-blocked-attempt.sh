#!/usr/bin/env bash
# Beat 3 proof — a further transfer into the frozen mule bounces with 409.
# Run 03-freeze.sh (or freeze ACC-M001) first.
set -euo pipefail
cd "$(dirname "$0")"; source _common.sh
$CURL -o /dev/null -w "HTTP %{http_code}\n" -X POST "$BASE/api/transaction" \
  -H 'Content-Type: application/json' \
  -d '{"from_account":"ACC-F001","to_account":"ACC-M001","amount":50000,"channel":"IMPS"}'
$CURL -X POST "$BASE/api/transaction" -H 'Content-Type: application/json' \
  -d '{"from_account":"ACC-F001","to_account":"ACC-M001","amount":50000,"channel":"IMPS"}' | pp
