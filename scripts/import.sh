#!/usr/bin/env bash
# Import PDF statements into the local docker-compose service.
# Usage: scripts/import.sh statement.pdf [more.pdf ...]
set -euo pipefail
cd "$(dirname "$0")/.."
for f in "$@"; do
  name=$(basename "$f")
  # stream via stdin into a temp dir owned by the app user, remove afterwards
  docker compose exec -T app sh -c 'd=$(mktemp -d) && cat > "$d/$1" && budget import "$d/$1"; rc=$?; rm -rf "$d"; exit $rc' _ "$name" < "$f"
done
