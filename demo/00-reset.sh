#!/usr/bin/env bash
# Beat 0 — back to a normal afternoon. Nothing flagged.
set -euo pipefail
cd "$(dirname "$0")"; source _common.sh
$CURL -X POST "$BASE/api/demo/reset" | pp
