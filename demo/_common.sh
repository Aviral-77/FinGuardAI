# Shared config for the FinGuard AI demo scripts.
# Override the host with:  BASE=http://otherhost:8000 ./01-victim-transfer.sh
BASE="${BASE:-http://127.0.0.1:8000}"
CURL="curl -s --noproxy *"
pp() { python3 -m json.tool 2>/dev/null || cat; }
