#!/usr/bin/env bash
# Beat 1 — the victim's transfers. Lands the victim at 35 (Enhanced monitoring).
# Monitor only: a single unusual customer is not yet a mule ring.
set -euo pipefail
cd "$(dirname "$0")"; source _common.sh
$CURL -X POST "$BASE/api/demo/beat/1?stagger_ms=500" | pp
echo "--- victim case ---"
$CURL "$BASE/api/account/ACC-V001" | pp
