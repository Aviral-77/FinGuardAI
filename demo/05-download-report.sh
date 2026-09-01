#!/usr/bin/env bash
# Download the full case PDF for the ring hub.
set -euo pipefail
cd "$(dirname "$0")"; source _common.sh
out="finguard-case-ACC-R001.pdf"
$CURL -o "$out" "$BASE/api/account/ACC-R001/report.pdf"
echo "saved $out ($(wc -c < "$out") bytes)"
