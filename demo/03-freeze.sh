#!/usr/bin/env bash
# Beat 3 — contain the ring. Freezes the hub (and, in the UI, the whole ring).
set -euo pipefail
cd "$(dirname "$0")"; source _common.sh
$CURL -X POST "$BASE/api/account/ACC-R001/freeze" | pp
