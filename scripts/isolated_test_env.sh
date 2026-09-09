#!/bin/bash
# Isolated test environment for VetClinicSystem_IQ or VetClinicSystem_JO —
# a throwaway Postgres container + Python venv, never touching either app's
# real dev database. Use this to replicate a bug live or verify a fix before
# it ships, matching the discipline established across both apps' QA work.
#
# Usage:
#   scripts/isolated_test_env.sh up   iq|jo    # create + start, print connection info
#   scripts/isolated_test_env.sh down iq|jo    # tear down (container, venv, data dir)
#   scripts/isolated_test_env.sh status iq|jo  # check what's running
#
# After `up`, the app is reachable at the printed URL, logged in as
# admin/Admin12345!. A single Retail item (INV301 / PL301, 5.000 sale price)
# is seeded for POS/checkout testing. Stop the app process yourself when
# you're done testing (its PID is printed by `up`), then run `down` to
# remove the container/venv/data — `down` does not kill the app process.
#
# The PID `up` prints is cross-checked against whatever is actually listening
# on the app port before it is reported, and `down` refuses while EITHER that
# PID is alive or the port is still held. Both are here because, until
# 2026-09-09, the recorded PID was not the app's at all (off by two, in both
# apps), which left `down`'s only guard unable to fire — it would remove the
# container out from under a running app. COMPARISON.md §44.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PARENT_DIR="$(dirname "$SCRIPT_DIR")"

APP="${2:-}"
ACTION="${1:-}"

if [[ "$APP" != "iq" && "$APP" != "jo" ]]; then
  echo "Usage: $0 {up|down|status} {iq|jo}" >&2
  exit 1
fi

case "$APP" in
  iq)
    REPO_DIR="$PARENT_DIR/webapps/vetclinicsystem_iq-main"
    DB_NAME="vetclinicsystemiq"
    ENV_PREFIX="VETCLINICSYSTEMIQ"
    APP_PORT=5091
    DB_PORT=55491
    ;;
  jo)
    REPO_DIR="$PARENT_DIR/webapps/vetclinicsystem_jo-main"
    DB_NAME="vetclinicsystemjo"
    ENV_PREFIX="VETCLINICSYSTEMJO"
    APP_PORT=5092
    DB_PORT=55492
    ;;
esac

CONTAINER="vz_${APP}_test"
VENV_DIR="/tmp/vz_${APP}_test_venv"
DATA_DIR="/tmp/vz_${APP}_test_data"
PID_FILE="/tmp/vz_${APP}_test.pid"

if [[ ! -d "$REPO_DIR" ]]; then
  echo "Repo not found at $REPO_DIR — clone it there first." >&2
  exit 1
fi

# What is ACTUALLY listening on the app port, independent of any PID we
# recorded. The PID file used to disagree with this (see the launch comment in
# up()), and every guard that trusted the PID alone was therefore unable to
# fire. When you need to know whether the app is up, ask the port.
#
# Prints nothing and returns 1 when the port is free OR when lsof is
# unavailable; callers must treat "could not tell" as "assume something is
# running", never as "nothing is running".
port_listener_pid() {
  command -v lsof >/dev/null 2>&1 || return 1
  local pids
  pids="$(lsof -ti "tcp:${APP_PORT}" -sTCP:LISTEN 2>/dev/null || true)"
  [[ -n "$pids" ]] || return 1
  echo "$pids"
}

have_lsof() { command -v lsof >/dev/null 2>&1; }

status() {
  echo "== $APP test environment =="
  docker ps -a --filter "name=^${CONTAINER}\$" --format '  container: {{.Names}} — {{.Status}}' || true
  if [[ -f "$PID_FILE" ]] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
    echo "  app: running, pid $(cat "$PID_FILE"), http://127.0.0.1:${APP_PORT}"
  else
    echo "  app: not running"
  fi
  if have_lsof; then
    local listener
    listener="$(port_listener_pid || true)"
    if [[ -n "$listener" ]]; then
      echo "  port ${APP_PORT}: held by pid(s) $(echo "$listener" | tr '\n' ' ')"
    else
      echo "  port ${APP_PORT}: free"
    fi
  else
    echo "  port ${APP_PORT}: UNKNOWN (lsof not available)"
  fi
  [[ -d "$VENV_DIR" ]] && echo "  venv: $VENV_DIR" || echo "  venv: none"
  [[ -d "$DATA_DIR" ]] && echo "  data dir: $DATA_DIR" || echo "  data dir: none"
}

up() {
  echo "== Starting isolated Postgres ($CONTAINER, port $DB_PORT) =="
  docker run -d --name "$CONTAINER" \
    -e POSTGRES_USER=postgres -e POSTGRES_PASSWORD=test -e POSTGRES_DB="$DB_NAME" \
    -p "127.0.0.1:${DB_PORT}:5432" postgres:16-alpine >/dev/null
  sleep 4

  echo "== Setting up Python venv =="
  python3 -m venv "$VENV_DIR"
  "$VENV_DIR/bin/pip" install -q -r "$REPO_DIR/requirements.txt"

  # Test-only dependencies. Deliberately NOT in requirements.txt -- the apps
  # have no build step and no browser dependency, and that stays true.
  #
  # Installed here because without them a whole tier goes dormant SILENTLY:
  # test_browser.py gates on pytest.importorskip at module scope, which
  # collects ZERO tests and reports as "1 skipped", not 13. IQ's browser tier
  # had never once run for this reason, which is how a Settings page that
  # scrolled sideways on every phone reached a soak install. COMPARISON.md
  # §40.3.
  echo "== Installing test-only deps (pytest, playwright) =="
  "$VENV_DIR/bin/pip" install -q pytest playwright
  "$VENV_DIR/bin/playwright" install --with-deps chromium >/dev/null 2>&1 \
    || "$VENV_DIR/bin/playwright" install chromium >/dev/null 2>&1 \
    || echo "   !! playwright browser install failed -- the browser tier will be DORMANT."

  echo "== Applying schema + seeding test data =="
  mkdir -p "$DATA_DIR/logs"
  DATABASE_URL="postgresql://postgres:test@localhost:${DB_PORT}/${DB_NAME}" \
    "$VENV_DIR/bin/python3" - "$REPO_DIR" "$APP" <<'PYEOF'
import sys, os
sys.path.insert(0, sys.argv[1])
os.chdir(sys.argv[1])
app_name = sys.argv[2]
import db as dbmod, auth, setup
from datetime import datetime

con = dbmod.connect()
with open("schema_postgres.sql") as f:
    dbmod.run_script(con, f.read())
con.commit()

# Each app's setup.py wires apply_schema()/apply_incremental_migrations()
# together differently (JO's apply_schema() calls migrations internally;
# IQ's are two separate top-level calls) — mirror setup.py's own main()
# for this app rather than assuming one convention for both.
if app_name == "jo":
    setup.apply_incremental_migrations(con)
else:
    for stmt in setup.INCREMENTAL_SCHEMA_STATEMENTS:
        con.execute(stmt)
    con.commit()

auth.seed_default_roles_and_permissions(con)
con.commit()

admin_role = con.execute("SELECT id FROM roles WHERE name='Admin'").fetchone()
con.execute(
    "INSERT INTO users (id, username, password_hash, full_name, role_id, active, must_change_password, created_at) "
    "VALUES (?,?,?,?,?,?,?,?)",
    ("U001", "admin", auth.hash_password("Admin12345!"), "Test Admin", admin_role["id"],
     True, False, datetime.now().isoformat(timespec="seconds")),
)
con.execute(
    "INSERT INTO inventory_list (id, name, category, unit, track_expiry, cost_price, active) "
    "VALUES ('INV301', 'Test Retail Item', 'Retail', 'unit', false, 1.000, true)"
)
con.execute(
    "INSERT INTO price_list (id, name, category, sale_price, active, linked_item_id, can_discount) "
    "VALUES ('PL301', 'Test Retail Item', 'Retail', 5.000, true, 'INV301', true)"
)
con.commit()
con.close()
print("Schema applied, admin user + test item seeded.")
PYEOF

  echo "== Starting the app =="
  SECRET_KEY="$(python3 -c 'import secrets; print(secrets.token_hex(32))')"
  # `${ENV_PREFIX}_HOST=val cmd` does NOT work as an env-assignment prefix in
  # bash — assignment-prefix detection is purely lexical (checks for a literal
  # `identifier=` token before any expansion happens), so a dynamically-built
  # name like `${ENV_PREFIX}_HOST=` is never recognized as an assignment; bash
  # instead tries to execute the expanded string itself as a command and fails
  # with "No such file or directory". `env NAME=value ...` sets each pair at
  # runtime, after expansion, so it works for a variable name built at runtime.
  # `exec` is load-bearing, and this used to be wrong. Written as
  #
  #     ( cd "$REPO_DIR" && nohup env ... app.py > log 2>&1 &
  #       echo $! > "$PID_FILE" )
  #
  # the trailing `&` backgrounds the whole `cd && nohup ...` AND-list, so `$!`
  # named the shell wrapping the launch rather than the interpreter that
  # survives it -- measured off by two in both apps on 2026-09-09. Killing the
  # recorded PID left the app serving, and `down`'s "still running" guard,
  # which tests that same PID, could never fire: it would remove the
  # container, venv and data dir out from under a live app. COMPARISON.md §44.
  #
  # Backgrounding the SUBSHELL and `exec`ing inside it fixes that: exec
  # replaces the subshell with nohup, which execs env, which execs python3 --
  # all in place, so the pid `$!` reports is the interpreter itself.
  ( cd "$REPO_DIR" && exec nohup env \
      DATABASE_URL="postgresql://postgres:test@localhost:${DB_PORT}/${DB_NAME}" \
      "${ENV_PREFIX}_DATA_DIR=$DATA_DIR" \
      "${ENV_PREFIX}_HOST=127.0.0.1" \
      "${ENV_PREFIX}_PORT=$APP_PORT" \
      SECRET_KEY="$SECRET_KEY" \
      "$VENV_DIR/bin/python3" app.py > "$DATA_DIR/app_stdout.log" 2>&1 ) &
  echo $! > "$PID_FILE"
  sleep 3

  # And then verify it, because "the PID looks plausible" is exactly how the
  # old bug read for weeks. Cross-check the recorded PID against whatever is
  # actually holding the port; a mismatch, or an answer we cannot get, is
  # reported loudly rather than passed over in silence.
  APP_PID="$(cat "$PID_FILE")"
  if ! kill -0 "$APP_PID" 2>/dev/null; then
    echo "  !! The app exited immediately. See $DATA_DIR/app_stdout.log" >&2
    tail -5 "$DATA_DIR/app_stdout.log" >&2 || true
    exit 1
  fi
  if have_lsof; then
    LISTENER="$(port_listener_pid || true)"
    if [[ -z "$LISTENER" ]]; then
      echo "  !! Nothing is listening on ${APP_PORT} yet — the app may still be" >&2
      echo "     starting, or may have failed. Check $DATA_DIR/app_stdout.log" >&2
    elif [[ "$LISTENER" != "$APP_PID" ]]; then
      echo "  !! Recorded pid $APP_PID is NOT the process on port ${APP_PORT}" >&2
      echo "     (that is $LISTENER). This is the COMPARISON.md §44 bug; do not" >&2
      echo "     trust the pid below, and kill $LISTENER instead." >&2
      exit 1
    fi
  else
    echo "  !! lsof unavailable — could not confirm the pid below is the app." >&2
  fi

  echo
  echo "== Ready =="
  echo "  URL:      http://127.0.0.1:${APP_PORT}"
  echo "  Login:    admin / Admin12345!"
  echo "  Test item: INV301 / PL301 (Retail, 5.000)"
  echo "  App PID:  $(cat "$PID_FILE")  (kill this yourself when done testing)"
  echo "  App log:  $DATA_DIR/app_stdout.log"
  echo "  Errors:   $DATA_DIR/logs/errors.log"
  echo "  DB:       postgresql://postgres:test@localhost:${DB_PORT}/${DB_NAME}"
  echo "  Docker:   docker exec -it $CONTAINER psql -U postgres -d $DB_NAME"
}

down() {
  echo "== Tearing down $APP test environment =="

  # Two independent guards, because the PID one alone was unable to fail.
  # Until 2026-09-09 the recorded PID was not the app's (COMPARISON.md §44),
  # so this check passed the moment a wrapper process died and the teardown
  # went ahead while the app was still serving and still writing to the
  # database about to be deleted. The port check is the one that holds even
  # if the PID bookkeeping is wrong again.
  if [[ -f "$PID_FILE" ]] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
    echo "  App process $(cat "$PID_FILE") is still running — kill it first, then re-run down."
    exit 1
  fi

  if have_lsof; then
    LISTENER="$(port_listener_pid || true)"
    if [[ -n "$LISTENER" ]]; then
      echo "  Something is still listening on port ${APP_PORT}: pid(s) $(echo "$LISTENER" | tr '\n' ' ')" >&2
      echo "  Kill it first, then re-run down. (The recorded pid was already gone," >&2
      echo "  which is exactly the case that used to let a teardown proceed.)" >&2
      exit 1
    fi
  else
    echo "  !! lsof unavailable — cannot confirm the app has stopped." >&2
    echo "     Refusing rather than guessing; stop the app and remove $PID_FILE" >&2
    echo "     by hand if you are certain nothing is running." >&2
    exit 1
  fi

  rm -f "$PID_FILE"
  docker rm -f "$CONTAINER" >/dev/null 2>&1 || true
  rm -rf "$VENV_DIR" "$DATA_DIR"
  echo "  Done — container, venv, and data dir removed."
}

case "$ACTION" in
  up) up ;;
  down) down ;;
  status) status ;;
  *) echo "Usage: $0 {up|down|status} {iq|jo}" >&2; exit 1 ;;
esac
