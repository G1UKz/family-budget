#!/bin/sh
# Usage: budget-backup backup | restore-check
# Env: DATABASE_URI, RESTIC_REPOSITORY, RESTIC_PASSWORD (+ AWS_* for S3), TAG, RESTIC_KEEP
set -eu
W=/work
mkdir -p "$W"
TAG=${TAG:-family-budget}

backup() {
  restic cat config >/dev/null 2>&1 || restic init
  pg_dump --format=custom --no-owner --file "$W/budget.dump" "$DATABASE_URI"
  pg_restore --list "$W/budget.dump" >/dev/null   # dump is readable
  restic backup --tag "$TAG" --host k8s "$W/budget.dump"
  # shellcheck disable=SC2086
  restic forget --tag "$TAG" --prune $RESTIC_KEEP
  restic check --read-data-subset=5%
}

restore_check() {
  # Restore the latest snapshot into a throwaway local Postgres inside this pod
  # (production database is not touched) and verify the data is usable.
  restic restore latest --tag "$TAG" --target "$W/restore"
  dump=$(find "$W/restore" -name budget.dump | head -1)
  [ -n "$dump" ] || { echo "no dump in snapshot"; exit 1; }
  age=$(restic snapshots --tag "$TAG" --latest 1 --json | sed -n 's/.*"time":"\([^"]*\)".*/\1/p' | cut -c1-19)
  echo "latest snapshot: $age"
  mkdir -p "$W/run"
  initdb -D "$W/pg" -U check --auth=trust >/dev/null
  pg_ctl -D "$W/pg" -o "-k $W/run -c listen_addresses=''" -w start >/dev/null
  trap 'pg_ctl -D "$W/pg" -m fast stop >/dev/null' EXIT
  createdb -h "$W/run" -U check restored
  pg_restore --no-owner --no-acl -h "$W/run" -U check -d restored "$dump"
  q() { psql -h "$W/run" -U check -d restored -Atc "$1"; }
  tx=$(q "select count(*) from transactions")
  imports=$(q "select count(*) from imports")
  bad=$(q "select count(*) from imports where not reconciled")
  last=$(q "select coalesce(max(date)::text, 'none') from transactions")
  echo "restored: transactions=$tx imports=$imports unreconciled=$bad last_tx=$last"
  [ "$tx" -gt 0 ] || { echo "RESTORE CHECK FAILED: no transactions"; exit 1; }
  echo "RESTORE CHECK OK"
}

case "${1:-}" in
  backup) backup ;;
  restore-check) restore_check ;;
  *) echo "usage: $0 backup|restore-check"; exit 2 ;;
esac
