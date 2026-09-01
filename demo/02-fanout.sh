#!/usr/bin/env bash
# Beat 2 — the fan-out. Scores climb and the ring assembles; the hub crosses 86.
set -euo pipefail
cd "$(dirname "$0")"; source _common.sh
$CURL -X POST "$BASE/api/demo/beat/2?stagger_ms=450" | pp
echo "--- ring hub case ---"
$CURL "$BASE/api/account/ACC-R001" | pp
