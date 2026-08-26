#!/bin/bash
# Monthly restore drill for VetClinicSystem_IQ / VetClinicSystem_JO.
#
# WHY THIS EXISTS
# ---------------
# Both apps take backups: nightly on a schedule, before every in-app
# update, and on shutdown. None of that is worth anything until a backup
# has been restored and checked. An unreadable dump file looks exactly
# like a good one on disk — same name, plausible size, listed happily in
# the Settings UI — right up until the day you need it.
#
# This script proves a real backup can actually be restored, by restoring
# it into a throwaway Postgres container and inspecting the result. It
# NEVER touches either app's real database, and it only ever reads the
# backup file.
#
# Usage:
#   scripts/restore_drill.sh iq|jo [path/to/file.dump]
#
# With no path it picks the newest .dump it can find for that app. Exits
# 0 if the drill passes, 1 if it fails — so it can be wired to a reminder
# or a cron job later if you want it unattended.
#
# RUN IT ONCE A MONTH. A backup you have never restored is a hope, not a
# backup.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PARENT_DIR="$(dirname "$SCRIPT_DIR")"

APP="${1:-}"
DUMP_ARG="${2:-}"

if [[ "$APP" != "iq" && "$APP" != "jo" ]]; then
  echo "Usage: $0 {iq|jo} [path/to/file.dump]" >&2
  exit 1
fi

case "$APP" in
  iq)
    REPO_DIR="$PARENT_DIR/webapps/vetclinicsystem_iq-main"
    DB_NAME="vetclinicsystemiq"
    SEARCH_DIRS=("$HOME/Downloads/vetclinicsystemiq-data/backups" "$HOME/Desktop/backups")
    MONEY_LABEL="IQD (whole numbers, 250-note rounding)"
    ;;
  jo)
    REPO_DIR="$PARENT_DIR/webapps/vetclinicsystem_jo-main"
    DB_NAME="vetclinicsystemjo"
    SEARCH_DIRS=("$HOME/Downloads/vetclinicsystemjo-data/backups" "$HOME/Desktop/backups")
    MONEY_LABEL="JOD (exact 3-decimal Decimal)"
    ;;
esac

# Deliberately different port and container name from isolated_test_env.sh,
# so a drill can run while a test environment is up without colliding.
CONTAINER="vz_${APP}_drill"
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

echo "== Restore drill: $APP =="
echo "   $(date '+%Y-%m-%d %H:%M')"
echo ""

# ---------------------------------------------------------------------------
# 1. Find the backup
# ---------------------------------------------------------------------------
echo "1. Locating a backup"
if [[ -n "$DUMP_ARG" ]]; then
  DUMP="$DUMP_ARG"
else
  DUMP=""
  for d in "${SEARCH_DIRS[@]}"; do
    [[ -d "$d" ]] || continue
    newest=$(find "$d" -name "${DB_NAME}_backup_*.dump" -type f -print0 2>/dev/null \
             | xargs -0 ls -t 2>/dev/null | head -1)
    if [[ -n "$newest" ]]; then
      if [[ -z "$DUMP" || "$newest" -nt "$DUMP" ]]; then DUMP="$newest"; fi
    fi
  done
fi

if [[ -z "$DUMP" || ! -f "$DUMP" ]]; then
  fail "No backup found for $APP. Looked in: ${SEARCH_DIRS[*]}"
  echo ""
  echo "== DRILL FAILED — there is nothing to restore =="
  echo "   That is itself the finding: this app has no reachable backup."
  exit 1
fi

SIZE=$(du -h "$DUMP" | cut -f1)
AGE_DAYS=$(( ( $(date +%s) - $(stat -f %m "$DUMP") ) / 86400 ))
pass "Found $(basename "$DUMP")"
info "path: $DUMP"
info "size: $SIZE, taken $AGE_DAYS day(s) ago"
if (( AGE_DAYS > 7 )); then
  warn "Newest backup is $AGE_DAYS days old — nightly backups may not be running."
fi

# ---------------------------------------------------------------------------
# 2. Is the file even readable as a dump?
# ---------------------------------------------------------------------------
echo ""
echo "2. Checking the file is a valid pg_dump archive"
if ! command -v pg_restore >/dev/null 2>&1; then
  info "no local pg_restore — will check inside the container instead"
  TOC_COUNT=""
else
  TOC=$(pg_restore --list "$DUMP" 2>/dev/null)
  if [[ -z "$TOC" ]]; then
    fail "pg_restore cannot read this file — the backup is corrupt or truncated"
    echo ""
    echo "== DRILL FAILED =="
    exit 1
  fi
  TOC_COUNT=$(echo "$TOC" | grep -c "TABLE DATA" || true)
  pass "Readable archive, $TOC_COUNT table-data entries"
fi

# ---------------------------------------------------------------------------
# 3. Throwaway Postgres
# ---------------------------------------------------------------------------
echo ""
echo "3. Starting a throwaway Postgres (never your real database)"
docker rm -f "$CONTAINER" >/dev/null 2>&1 || true
if ! docker run -d --name "$CONTAINER" \
      -e POSTGRES_PASSWORD="$PGPASS" -e POSTGRES_DB="$DB_NAME" \
      -p "${DB_PORT}:5432" postgres:16 >/dev/null 2>&1; then
  fail "Could not start the container — is Docker running?"
  exit 1
fi
for i in $(seq 1 45); do
  if docker exec "$CONTAINER" pg_isready -U postgres >/dev/null 2>&1; then break; fi
  sleep 1
done
if ! docker exec "$CONTAINER" pg_isready -U postgres >/dev/null 2>&1; then
  fail "Postgres never became ready"
  exit 1
fi
pass "Container up on port $DB_PORT"

# ---------------------------------------------------------------------------
# 4. The actual restore
# ---------------------------------------------------------------------------
echo ""
echo "4. Restoring"
docker cp "$DUMP" "$CONTAINER:/tmp/drill.dump" >/dev/null 2>&1
RESTORE_LOG=$(docker exec -e PGPASSWORD="$PGPASS" "$CONTAINER" \
  pg_restore --clean --if-exists --no-owner --no-privileges \
  -U postgres -d "$DB_NAME" /tmp/drill.dump 2>&1)
RESTORE_RC=$?

# pg_restore exits non-zero on warnings too (a missing role, an extension
# it cannot recreate). Those are noise here; real failures show up as the
# checks below finding nothing.
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

# Trims surrounding whitespace only. An earlier version used `tr -d ' '`,
# which also ate the space inside type names -- "double precision" came back
# as "doubleprecision" and the money-type check failed against a database
# that was in fact perfectly correct.
q() { docker exec -e PGPASSWORD="$PGPASS" "$CONTAINER" \
        psql -U postgres -d "$DB_NAME" -t -A -c "$1" 2>/dev/null \
        | sed 's/^[[:space:]]*//; s/[[:space:]]*$//'; }

# ---------------------------------------------------------------------------
# 5. Did the schema come back?
# ---------------------------------------------------------------------------
echo ""
echo "5. Verifying the schema"
TABLES=$(q "SELECT count(*) FROM information_schema.tables WHERE table_schema='public';")
# Count real statements, not prose. Comments in the schema file mention
# "CREATE TABLE IF NOT EXISTS" when explaining why something lives where it
# does, and a plain grep counted those too -- inflating the expected total
# and making a complete restore look short.
EXPECTED=$(grep -cE '^[[:space:]]*CREATE TABLE' "$REPO_DIR/schema_postgres.sql" 2>/dev/null || echo 0)
if [[ "${TABLES:-0}" -gt 0 ]]; then
  pass "$TABLES tables restored (current schema defines $EXPECTED)"
  if [[ "${TABLES:-0}" -lt "$EXPECTED" ]]; then
    info "fewer than today's schema — expected if the backup predates recent migrations"
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

ADMINS=$(q "SELECT count(*) FROM users WHERE role_id IS NOT NULL;")
if [[ "${ADMINS:-0}" -gt 0 ]]; then
  pass "$ADMINS user account(s) present — the clinic could log in after this restore"
else
  fail "No user accounts — nobody could log into a system restored from this backup"
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
info "model: $MONEY_LABEL"
# NOTE: a check that silently skips is worse than no check -- it reports as a
# pass. If the column this drill relies on is absent, that is a finding about
# the backup, not a reason to move on quietly.
HAS_BILLING=$(q "SELECT to_regclass('public.billing') IS NOT NULL;")
if [[ "$HAS_BILLING" != "t" ]]; then
  fail "No billing table in this backup — money could not be verified at all"
else
  MONEY_COL=$(q "SELECT data_type FROM information_schema.columns WHERE table_name='billing' AND column_name='total';")
  if [[ -z "$MONEY_COL" ]]; then
    fail "billing.total is missing — this backup cannot reproduce what anyone was charged"
  else
    ROWS=$(q "SELECT count(*) FROM billing;")
    SUM=$(q "SELECT COALESCE(SUM(total),0) FROM billing;")
    NEG=$(q "SELECT count(*) FROM billing WHERE total < 0;")
    info "$ROWS bill(s), total billed: $SUM, negative rows: $NEG"

    # The column TYPE is the thing that silently destroys money. A JO
    # backup restoring numeric as double precision would keep every value
    # looking right today and lose fils on the next write.
    case "$APP" in
      jo)
        if [[ "$MONEY_COL" == "numeric" ]]; then
          pass "billing.total restored as numeric — 3-decimal precision preserved"
        else
          fail "JO money restored as '$MONEY_COL', not numeric — precision would be lost"
        fi
        OVER=$(q "SELECT count(*) FROM billing WHERE scale(total) > 3;")
        if [[ "${OVER:-0}" == "0" ]]; then
          pass "No bill exceeds 3 decimal places (1 fils)"
        else
          fail "$OVER bill(s) carry more than 3 decimals — beyond what NUMERIC(12,3) stores"
        fi
        ;;
      iq)
        if [[ "$MONEY_COL" == "double precision" ]]; then
          pass "billing.total restored as double precision — matches IQ's money model"
        else
          fail "IQ money restored as '$MONEY_COL', not double precision"
        fi
        # IQ's defining invariant: every payable figure must be handable in
        # real notes. A restore that rounded or coerced values breaks this
        # and nothing else in the drill would notice.
        NOTES=$(q "SELECT count(*) FROM billing WHERE total > 0 AND (total::numeric % 250) <> 0;")
        if [[ "${NOTES:-0}" == "0" ]]; then
          pass "Every non-zero bill is a whole multiple of 250 IQD"
        else
          fail "$NOTES bill(s) are not payable in real notes — 250-rounding did not survive"
        fi
        ;;
    esac

    if [[ "${NEG:-0}" != "0" ]]; then
      warn "$NEG bill(s) have a negative total — expected only if refunds are modelled that way"
    fi
  fi
fi

# ---------------------------------------------------------------------------
# 8. Can the app actually boot against it?
# ---------------------------------------------------------------------------
echo ""
echo "8. Booting the app against the restored database"
if [[ -d "$REPO_DIR" ]]; then
  BOOT=$(cd "$REPO_DIR" && \
    SECRET_KEY="drill-only-key" \
    DATABASE_URL="postgresql://postgres:${PGPASS}@localhost:${DB_PORT}/${DB_NAME}" \
    python3 -c "
import sys; sys.path.insert(0, '.')
try:
    import db as dbmod
    con = dbmod.connect()
    n = con.execute('SELECT count(*) AS c FROM users').fetchone()['c']
    con.close()
    print('OK', n)
except Exception as e:
    print('ERR', type(e).__name__, str(e)[:90])
" 2>&1 | tail -1)
  if [[ "$BOOT" == OK* ]]; then
    pass "App connects and queries the restored database (${BOOT#OK })"
  else
    fail "App could not use the restored database: $BOOT"
  fi
else
  warn "Repo not found at $REPO_DIR — skipped the boot check"
fi

# ---------------------------------------------------------------------------
# Verdict
# ---------------------------------------------------------------------------
echo ""
if (( FAILURES == 0 )); then
  echo "== DRILL PASSED =="
  echo "   $(basename "$DUMP") is a genuinely restorable backup."
  (( WARNINGS > 0 )) && echo "   $WARNINGS warning(s) above are worth a look."
  echo "   Throwaway container removed. Your real database was never touched."
  exit 0
else
  echo "== DRILL FAILED — $FAILURES check(s) did not pass =="
  echo "   Do not assume the other backups are fine; they were made the same way."
  echo "   Throwaway container removed. Your real database was never touched."
  exit 1
fi
