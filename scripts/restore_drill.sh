#!/bin/bash
# Monthly restore drill for VetClinicSystem.
#
# WHY THIS EXISTS
# ---------------
# The app takes backups: nightly on a schedule, before every in-app update,
# and on shutdown. None of that is worth anything until a backup has been
# restored and checked. An unreadable dump file looks exactly like a good one
# on disk — same name, plausible size, listed happily in the Settings UI —
# right up until the day you need it.
#
# This script proves a real backup can actually be restored, by restoring it
# into a throwaway Postgres container and inspecting the result. It NEVER
# touches the clinic's database, and it only ever reads the backup file.
# (The app also verifies its backups by itself — vcs/ops/selfverify.py, the
# fourth monitoring layer. This is the same question asked by hand, from
# outside the running app.)
#
# Usage:
#   scripts/restore_drill.sh path/to/vetclinicsystem_backup_….dump
#   scripts/restore_drill.sh path/to/backup-folder      # its newest backup
#
# Exits 0 if the drill passes, 1 if it fails — so it can be wired to a
# reminder or a cron job if you want it unattended.
#
# RUN IT ONCE A MONTH. A backup you have never restored is a hope, not a
# backup.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(dirname "$SCRIPT_DIR")"
PREFIX="vetclinicsystem_backup_"   # vcs/ops/backup.py FILENAME_PREFIX
DB_NAME="vetclinicsystem"

TARGET="${1:-}"
if [[ -z "$TARGET" ]]; then
  echo "Usage: $0 {backup.dump | folder of backups}" >&2
  exit 1
fi
# This machine may also run the predecessor IQ and JO apps (CLAUDE.md §4).
# Their backups are not this system's, and their data is not ours to read.
case "$TARGET" in
  *vetclinicsystemiq-data*|*vetclinicsystemjo-data*)
    echo "Refusing: $TARGET belongs to a predecessor app's install, not VetClinicSystem." >&2
    exit 1 ;;
esac

# A vcs_test_* name like every throwaway container this repository makes, on
# its own port, so a drill can run while a test environment is up.
CONTAINER="vcs_test_drill"
DB_PORT=55499
PGPASS="drill"
FAILURES=0
WARNINGS=0

pass() { printf "  \033[32m✓\033[0m %s\n" "$1"; }
fail() { printf "  \033[31m✗\033[0m %s\n" "$1"; FAILURES=$((FAILURES + 1)); }
warn() { printf "  \033[33m!\033[0m %s\n" "$1"; WARNINGS=$((WARNINGS + 1)); }
info() { printf "    %s\n" "$1"; }

cleanup() {
  docker rm -f "$CONTAINER" >/dev/null 2>&1 || true
}
# Always tear down, including on Ctrl-C or an unexpected error. Leaving a
# container behind is the one way this script could interfere with anything.
trap cleanup EXIT INT TERM

echo "== Restore drill =="
echo "   $(date '+%Y-%m-%d %H:%M')"
echo ""

# ---------------------------------------------------------------------------
# 1. Find the backup
# ---------------------------------------------------------------------------
echo "1. Locating the backup"
if [[ -d "$TARGET" ]]; then
  DUMP=$(find "$TARGET" -maxdepth 1 -name "${PREFIX}*.dump" -type f -print0 2>/dev/null \
         | xargs -0 ls -t 2>/dev/null | head -1)
else
  DUMP="$TARGET"
fi
if [[ -z "$DUMP" || ! -f "$DUMP" ]]; then
  fail "No backup found at $TARGET (looking for ${PREFIX}*.dump)"
  echo ""
  echo "== DRILL FAILED — there is nothing to restore =="
  echo "   That is itself the finding: there is no reachable backup."
  exit 1
fi

SIZE=$(du -h "$DUMP" | cut -f1)
MTIME=$(stat -f %m "$DUMP" 2>/dev/null || stat -c %Y "$DUMP")
AGE_DAYS=$(( ( $(date +%s) - MTIME ) / 86400 ))
pass "Found $(basename "$DUMP")"
info "path: $DUMP"
info "size: $SIZE, taken $AGE_DAYS day(s) ago"
if (( AGE_DAYS > 7 )); then
  warn "Newest backup is $AGE_DAYS days old — nightly backups may not be running."
fi

# ---------------------------------------------------------------------------
# 2. Throwaway Postgres
# ---------------------------------------------------------------------------
echo ""
echo "2. Starting a throwaway Postgres (never the clinic's database)"
docker rm -f "$CONTAINER" >/dev/null 2>&1 || true
if ! docker run -d --name "$CONTAINER" \
      -e POSTGRES_PASSWORD="$PGPASS" -e POSTGRES_DB="$DB_NAME" \
      -p "127.0.0.1:${DB_PORT}:5432" postgres:16-alpine >/dev/null 2>&1; then
  fail "Could not start the container — is Docker running?"
  exit 1
fi
for _ in $(seq 1 45); do
  if docker exec "$CONTAINER" pg_isready -U postgres >/dev/null 2>&1; then break; fi
  sleep 1
done
if ! docker exec "$CONTAINER" pg_isready -U postgres >/dev/null 2>&1; then
  fail "Postgres never became ready"
  exit 1
fi
pass "Container up on port $DB_PORT"

# ---------------------------------------------------------------------------
# 3. Is the file even readable as a dump? (checked inside the container, so
#    the tools match the server whatever this machine has installed)
# ---------------------------------------------------------------------------
echo ""
echo "3. Checking the file is a valid pg_dump archive"
docker cp "$DUMP" "$CONTAINER:/tmp/drill.dump" >/dev/null 2>&1
TOC_COUNT=$(docker exec "$CONTAINER" pg_restore --list /tmp/drill.dump 2>/dev/null | grep -c "TABLE DATA" || true)
if [[ "${TOC_COUNT:-0}" -eq 0 ]]; then
  fail "pg_restore cannot read this file — the backup is corrupt or truncated"
  echo ""
  echo "== DRILL FAILED =="
  exit 1
fi
pass "Readable archive, $TOC_COUNT table-data entries"

# ---------------------------------------------------------------------------
# 4. The actual restore
# ---------------------------------------------------------------------------
echo ""
echo "4. Restoring"
RESTORE_LOG=$(docker exec -e PGPASSWORD="$PGPASS" "$CONTAINER" \
  pg_restore --clean --if-exists --no-owner --no-privileges \
  -U postgres -d "$DB_NAME" /tmp/drill.dump 2>&1)
RESTORE_RC=$?
# pg_restore exits non-zero on warnings too (a missing role, an extension it
# cannot recreate). Those are noise here; real failures show up as the checks
# below finding nothing.
if [[ $RESTORE_RC -ne 0 ]]; then
  ERRS=$(echo "$RESTORE_LOG" | grep -c "^pg_restore: error" || true)
  if (( ERRS > 0 )); then
    warn "pg_restore reported $ERRS error line(s) — shown below, verifying data anyway"
    echo "$RESTORE_LOG" | grep "^pg_restore: error" | head -5 | sed 's/^/      /'
  else
    info "pg_restore exited $RESTORE_RC with warnings only"
  fi
else
  pass "pg_restore completed cleanly"
fi

# Trims surrounding whitespace only (not inner spaces: "double precision").
q() { docker exec -e PGPASSWORD="$PGPASS" "$CONTAINER" \
        psql -U postgres -d "$DB_NAME" -t -A -c "$1" 2>/dev/null \
        | sed 's/^[[:space:]]*//; s/[[:space:]]*$//'; }

# ---------------------------------------------------------------------------
# 5. Did the schema come back?
# ---------------------------------------------------------------------------
echo ""
echo "5. Verifying the schema"
TABLES=$(q "SELECT count(*) FROM information_schema.tables WHERE table_schema='public';")
# Real statements, not prose, across every migration (a comment that mentions
# CREATE TABLE is not one), plus schema_migrations, which the runner creates.
EXPECTED=$(( $(cat "$REPO_DIR"/vcs/db/migrations/[0-9][0-9][0-9][0-9]_*.sql 2>/dev/null \
             | grep -cE '^[[:space:]]*CREATE TABLE' || echo 0) + 1 ))
if [[ "${TABLES:-0}" -gt 0 ]]; then
  pass "$TABLES tables restored (this checkout's schema defines $EXPECTED)"
  if [[ "${TABLES:-0}" -lt "$EXPECTED" ]]; then
    info "fewer than this checkout's schema — expected if the backup predates recent migrations"
  fi
else
  fail "No tables restored — the backup did not produce a usable database"
fi
FKS=$(q "SELECT count(*) FROM information_schema.table_constraints WHERE constraint_type='FOREIGN KEY' AND table_schema='public';")
if [[ "${FKS:-0}" -gt 0 ]]; then
  pass "$FKS foreign keys restored (referential integrity rules intact)"
else
  fail "No foreign keys — constraints did not survive the restore"
fi

# ---------------------------------------------------------------------------
# 6. Is there actual data, and does it hang together?
# ---------------------------------------------------------------------------
echo ""
echo "6. Verifying the data"
TOTAL_ROWS=0
for t in users owners patients visits billing sales price_list inventory_list; do
  exists=$(q "SELECT to_regclass('public.$t') IS NOT NULL;")
  [[ "$exists" == "t" ]] || continue
  n=$(q "SELECT count(*) FROM $t;")
  TOTAL_ROWS=$((TOTAL_ROWS + ${n:-0}))
  printf "    %-16s %s row(s)\n" "$t" "${n:-?}"
done
if (( TOTAL_ROWS > 0 )); then
  pass "$TOTAL_ROWS rows across the core tables"
else
  fail "Every core table is empty — the schema restored but the data did not"
fi
USERS=$(q "SELECT count(*) FROM users WHERE active AND role_id IS NOT NULL;")
if [[ "${USERS:-0}" -gt 0 ]]; then
  pass "$USERS active user account(s) — the clinic could sign in after this restore"
else
  fail "No active user accounts — nobody could sign in to a system restored from this backup"
fi
# The single most important integrity question: does every child row still
# point at a parent that exists? A dump restored out of order, or with a
# constraint dropped, shows up here and nowhere else.
ORPHANS=$(q "SELECT count(*) FROM patients p LEFT JOIN owners o ON o.id=p.owner_id WHERE p.owner_id IS NOT NULL AND o.id IS NULL;")
if [[ "${ORPHANS:-0}" == "0" ]]; then
  pass "No orphaned patients — parent/child links survived intact"
else
  fail "$ORPHANS patient(s) point at an owner that no longer exists"
fi

# ---------------------------------------------------------------------------
# 7. Money — the part worth being paranoid about
# ---------------------------------------------------------------------------
echo ""
echo "7. Verifying money survived the round trip"
# The money setting travels in the backup (settings.money_setting), and says
# what every amount must look like (vcs/money.py): IQ -- whole dinars, bills
# charged in 250-dinar notes; JO -- three decimals, to the fils.
SETTING=$(q "SELECT value FROM settings WHERE key='money_setting';")
case "$SETTING" in
  IQ) UNIT=250; PLACES=0; info "money setting: IQ (whole dinars, cash unit 250)" ;;
  JO) UNIT=0.001; PLACES=3; info "money setting: JO (three decimals, cash unit 0.001)" ;;
  "") UNIT=""; info "no money setting chosen in this backup — nothing can have been charged yet" ;;
  *) UNIT=""; fail "unknown money setting '$SETTING' in this backup" ;;
esac
# A check that silently skips reports as a pass; a missing column is a
# finding about the backup, not a reason to move on quietly.
MONEY_COL=$(q "SELECT data_type FROM information_schema.columns WHERE table_name='billing' AND column_name='total';")
if [[ -z "$MONEY_COL" ]]; then
  fail "billing.total is missing — this backup cannot reproduce what anyone was charged"
elif [[ "$MONEY_COL" != "numeric" ]]; then
  fail "billing.total restored as '$MONEY_COL', not numeric — amounts would drift"
else
  pass "billing.total restored as numeric — exact amounts"
  ROWS=$(q "SELECT count(*) FROM billing;")
  SUM=$(q "SELECT COALESCE(SUM(total),0) FROM billing;")
  info "$ROWS bill(s), total billed: $SUM"
  if [[ -n "$UNIT" ]]; then
    # The charged figure is rounded to the cash unit before Clean Up comes off
    # (money.payable), so total + Clean Up is a whole number of cash units.
    OFF=$(q "SELECT count(*) FROM billing WHERE total > 0 AND mod(total + COALESCE(cleanup_amount,0), $UNIT) <> 0;")
    if [[ "${OFF:-0}" == "0" ]]; then
      pass "Every bill was charged in whole cash units ($UNIT)"
    else
      fail "$OFF bill(s) were not charged in whole cash units — rounding did not survive"
    fi
    FINE=$(q "SELECT count(*) FROM billing WHERE total <> round(total, $PLACES);")
    if [[ "${FINE:-0}" == "0" ]]; then
      pass "No bill carries more than $PLACES decimal place(s)"
    else
      fail "$FINE bill(s) carry more decimals than the money setting allows"
    fi
  fi
  NEG=$(q "SELECT count(*) FROM billing WHERE total < 0;")
  if [[ "${NEG:-0}" != "0" ]]; then
    fail "$NEG bill(s) have a negative total — the schema refuses that, so the restore did not keep its checks"
  fi
fi

# ---------------------------------------------------------------------------
# 8. Can this checkout's code use it?
# ---------------------------------------------------------------------------
echo ""
echo "8. Connecting this checkout's code to the restored database"
PY="$REPO_DIR/venv/bin/python3"
[[ -x "$PY" ]] || PY="python3"
BOOT=$(cd "$REPO_DIR" && \
  DATABASE_URL="postgresql://postgres:${PGPASS}@localhost:${DB_PORT}/${DB_NAME}" \
  "$PY" -c "
try:
    from vcs.db import pool, migrate
    con = pool.connect()
    n = con.execute('SELECT count(*) AS c FROM users').fetchone()['c']
    pending = [name for _, name in migrate.pending(con)]
    con.close()
    print('OK', n, 'users;', ('pending migrations: ' + ', '.join(pending)) if pending else 'no migrations pending')
except ModuleNotFoundError as e:
    print('NOENV', e.name)
except Exception as e:
    print('ERR', type(e).__name__, str(e)[:120])
" 2>&1 | tail -1)
case "$BOOT" in
  OK*) pass "The app's own code reads it: ${BOOT#OK }" ;;
  NOENV*) warn "Skipped: '$PY' lacks the app's dependencies (${BOOT#NOENV }) — run it with the install's venv" ;;
  *) fail "The app's own code could not use the restored database: $BOOT" ;;
esac

# ---------------------------------------------------------------------------
# Verdict
# ---------------------------------------------------------------------------
echo ""
if (( FAILURES == 0 )); then
  echo "== DRILL PASSED =="
  echo "   $(basename "$DUMP") is a genuinely restorable backup."
  (( WARNINGS > 0 )) && echo "   $WARNINGS warning(s) above are worth a look."
  echo "   Throwaway container removed. The clinic's database was never touched."
  exit 0
else
  echo "== DRILL FAILED — $FAILURES check(s) did not pass =="
  echo "   Do not assume the other backups are fine; they were made the same way."
  echo "   Throwaway container removed. The clinic's database was never touched."
  exit 1
fi
