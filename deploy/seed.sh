#!/usr/bin/env bash
#
# Load documents into a freshly started stack.
#
#   bash deploy/seed.sh                    # ingests seed/*.txt
#   bash deploy/seed.sh path/to/notes.txt  # ingests one file
#
# This exists so the instance can be thrown away rather than parked as a paid
# snapshot. The documents live in the repository; the server holds no state
# worth keeping, so deleting it costs nothing and rebuilding restores
# everything.
#
# The title of each document is its filename with underscores turned into
# spaces.

set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
API="${API:-http://localhost/api}"

log() { printf '\n\033[1m==> %s\033[0m\n' "$*"; }
die() { printf '\n\033[31merror: %s\033[0m\n' "$*" >&2; exit 1; }

command -v curl >/dev/null || die "curl is not installed"

curl -fsS --max-time 10 "$API/health" >/dev/null \
  || die "no API at $API — is the stack up? (docker compose -f docker-compose.yaml ps)"

if [[ $# -gt 0 ]]; then
  files=("$@")
else
  shopt -s nullglob
  files=("$REPO_DIR"/seed/*.txt)
  shopt -u nullglob
fi

[[ ${#files[@]} -gt 0 ]] || die "nothing to ingest — pass a file, or put .txt files in seed/"

for file in "${files[@]}"; do
  [[ -f $file ]] || die "no such file: $file"

  title="$(basename "$file" .txt | tr '_' ' ')"
  log "ingesting: $title"

  # python3 builds the JSON so quotes, newlines and unicode in the notes
  # cannot break the request.
  python3 - "$file" "$title" <<'PY' > /tmp/seed-payload.json
import json, sys
path, title = sys.argv[1], sys.argv[2]
with open(path, encoding="utf-8") as f:
    print(json.dumps({"title": title, "text": f.read()}))
PY

  curl -fsS -X POST "$API/documents" \
    -H 'content-type: application/json' \
    -d @/tmp/seed-payload.json \
    | python3 -c 'import json,sys; d=json.load(sys.stdin); print("    %s chunks stored (id %s)" % (d["chunk_count"], d["id"]))'
done

rm -f /tmp/seed-payload.json
log "done — $(curl -fsS "$API/documents" | python3 -c 'import json,sys; print(len(json.load(sys.stdin)))') document(s) in the store"
