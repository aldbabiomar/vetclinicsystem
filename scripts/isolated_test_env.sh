#!/bin/bash
# Isolated test environment for VetClinicSystem — a throwaway Postgres
# container + Python venv + a running app, never touching any real install's
# database. Use this to replicate a bug live or verify a fix before it ships.
#
# Usage:
#   scripts/isolated_test_env.sh up     iq|jo   # create + start, print connection info
#   scripts/isolated_test_env.sh down   iq|jo   # tear down (container, venv, data dir)
#   scripts/isolated_test_env.sh status iq|jo   # check what's running
#   scripts/isolated_test_env.sh restart iq|jo  # reload the app after a code or catalogue change
#   scripts/isolated_test_env.sh reset   iq|jo  # fresh database (migrations changed in place), app restarted
#
# The second argument is the MONEY SETTING the throwaway clinic runs under —
# iq (whole dinars, 250-note cash rounding) or jo (3-decimal dinars). It is the
# same code either way; the two environments differ only in the money_setting
# row seeded into their databases, and they use different ports so both can
# run at once. Every change should be verified under BOTH.
#
# After `up`, the app is reachable at the printed URL, logged in as
# admin/Admin12345!. A single Retail item (INV301 / PL301) is seeded for
# POS/checkout testing. Stop the app process yourself when you're done testing
# (its PID is printed by `up`), then run `down` to remove the
# container/venv/data — `down` does not kill the app process.
#
# The PID `up` prints is cross-checked against whatever is actually listening
# on the app port before it is reported, and `down` refuses while EITHER that
# PID is alive or the port is still held. Both are here because, in the
# predecessor apps, the recorded PID was once not the app's at all (off by
# two), which left `down`'s only guard unable to fire — it would remove the
# container out from under a running app. docs/archive/COMPARISON.md §44.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(dirname "$SCRIPT_DIR")"

MONEY="${2:-}"
ACTION="${1:-}"

if [[ "$MONEY" != "iq" && "$MONEY" != "jo" ]]; then
  echo "Usage: $0 {up|down|status|restart|reset} {iq|jo}" >&2
  exit 1
fi
APP="$MONEY"   # kept as the name the functions below print

DB_NAME="vetclinicsystem"
ENV_PREFIX="VETCLINICSYSTEM"
case "$MONEY" in
  iq) APP_PORT=5091; DB_PORT=55491 ;;
  jo) APP_PORT=5092; DB_PORT=55492 ;;
esac

CONTAINER="vcs_test_${MONEY}"
VENV_DIR="/tmp/vcs_test_venv_${MONEY}"
DATA_DIR="/tmp/vcs_test_data_${MONEY}"
PID_FILE="/tmp/vcs_test_${MONEY}.pid"

if [[ ! -d "$REPO_DIR" ]]; then
  echo "Repo not found at $REPO_DIR." >&2
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

# Starts the app against the environment's database and verifies that the
# recorded pid is the process actually listening on the port. Used by both
# `up` and `restart`.
launch_app() {
  echo "== Starting the app =="
  [[ -n "${SECRET_KEY:-}" ]] || SECRET_KEY="$(python3 -c 'import secrets; print(secrets.token_hex(32))')"
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
  # container, venv and data dir out from under a live app. docs/archive/COMPARISON.md §44.
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
    # Wait for the port rather than sampling once: the app takes a couple of
    # seconds longer than `sleep 3` on a cold start, and a warning that fires
    # on a perfectly normal startup is worth less than no warning at all --
    # it trains you to read past the one time it is real.
    LISTENER=""
    for _ in $(seq 1 20); do
      LISTENER="$(port_listener_pid || true)"
      [[ -n "$LISTENER" ]] && break
      kill -0 "$APP_PID" 2>/dev/null || break   # died while we waited; say so below
      sleep 1
    done
    if [[ -z "$LISTENER" ]]; then
      echo "  !! Nothing is listening on ${APP_PORT} after 20s — the app failed" >&2
      echo "     to start. Check $DATA_DIR/app_stdout.log" >&2
      tail -5 "$DATA_DIR/app_stdout.log" >&2 || true
      exit 1
    elif [[ "$LISTENER" != "$APP_PID" ]]; then
      echo "  !! Recorded pid $APP_PID is NOT the process on port ${APP_PORT}" >&2
      echo "     (that is $LISTENER). This is the docs/archive/COMPARISON.md §44 bug; do not" >&2
      echo "     trust the pid below, and kill $LISTENER instead." >&2
      exit 1
    fi
  else
    echo "  !! lsof unavailable — could not confirm the pid below is the app." >&2
  fi
}

# Restart the app so it serves the code (and compiled catalogue) currently on
# disk — Flask-Babel and every imported module are loaded once, at start.
#
# Kills by PORT, never by a command pattern: the launch `exec`s into the
# resolved Python.app path, so a `pkill -f ".../bin/python3 app.py"` matches
# nothing, exits 0, and leaves the old process serving — an afternoon of
# "verified" against code that predates the change. And then asserts that the
# listening pid actually CHANGED, because a restart that silently did not
# happen reads exactly like one that did. (docs/archive/COMPARISON.md §57.7.)
restart() {
  echo "== Restarting the $APP test app on port ${APP_PORT} =="
  if ! have_lsof; then
    echo "  !! lsof unavailable — cannot find the app by port. Refusing." >&2
    exit 1
  fi
  local old
  old="$(port_listener_pid || true)"
  if [[ -z "$old" ]]; then
    echo "  !! Nothing is listening on ${APP_PORT} — run \`up\` first." >&2
    exit 1
  fi
  kill $old 2>/dev/null || true
  for _ in $(seq 1 20); do
    port_listener_pid >/dev/null || break
    sleep 0.5
  done
  if port_listener_pid >/dev/null; then
    kill -9 $old 2>/dev/null || true
    sleep 1
  fi
  if port_listener_pid >/dev/null; then
    echo "  !! Port ${APP_PORT} is still held after killing pid(s) $old. Refusing to launch a second copy." >&2
    exit 1
  fi
  [[ -n "${SECRET_KEY:-}" ]] || SECRET_KEY="$(python3 -c 'import secrets; print(secrets.token_hex(32))')"
  launch_app
  local new
  new="$(port_listener_pid || true)"
  if [[ -z "$new" || "$new" == "$old" ]]; then
    echo "  !! The listening pid did not change ($old -> ${new:-none}); the old app may still be serving." >&2
    exit 1
  fi
  echo "  Restarted: pid $old -> $new, http://127.0.0.1:${APP_PORT}"
}

# Migrations + the admin user + one Retail item, into the (empty) test database.
seed_db() {
  echo "== Applying schema + seeding test data =="
  mkdir -p "$DATA_DIR/logs"
  DATABASE_URL="postgresql://postgres:test@localhost:${DB_PORT}/${DB_NAME}" \
    "$VENV_DIR/bin/python3" - "$REPO_DIR" "$MONEY" <<'PYEOF'
import sys, os
sys.path.insert(0, sys.argv[1])
os.chdir(sys.argv[1])
money_setting = sys.argv[2].upper()
import db as dbmod, auth, schema
from datetime import datetime

con = dbmod.connect()
# Exactly what setup.py and the updater run: every migration, then the seed.
schema.apply(con)

# The throwaway clinic's money setting: the second argument to this script.
con.execute(
    "INSERT INTO settings (key, value) VALUES ('money_setting', ?) "
    "ON CONFLICT (key) DO UPDATE SET value = excluded.value", (money_setting,))
admin_role = con.execute("SELECT id FROM roles WHERE name='Admin'").fetchone()
# The first user, so id 1 on a fresh database; tests look it up by username
# (conftest.ADMIN_ID) rather than assuming the number.
con.execute(
    "INSERT INTO users (username, password_hash, full_name, role_id, active, must_change_password, created_at) "
    "VALUES (?,?,?,?,?,?,now())",
    ("admin", auth.hash_password("Admin12345!"), "Test Admin", admin_role["id"], True, False),
)
# Priced in the throwaway clinic's own currency: 5,000 / 1,000 IQD under IQ
# (a real note amount), 5.000 / 1.000 JOD under JO.
cost, price = ("1000", "5000") if money_setting == "IQ" else ("1.000", "5.000")
con.execute(
    "INSERT INTO inventory_list (id, name, category, unit, track_expiry, cost_price, active) "
    "VALUES ('INV301', 'Test Retail Item', 'Retail', 'unit', false, ?, true)", (cost,)
)
con.execute(
    "INSERT INTO price_list (id, name, category, sale_price, active, linked_item_id, can_discount) "
    "VALUES ('PL301', 'Test Retail Item', 'Retail', ?, true, 'INV301', true)", (price,)
)
con.commit()
con.close()
print("Schema applied, admin user + test item seeded.")
PYEOF
}

# Recreate the test DATABASE only — drop it, migrate, seed, restart the app —
# keeping the container and the venv. For when migrations/ changed in place
# (allowed before 1.0.0): `up` would rebuild the venv and Playwright for
# nothing. Refuses unless the container is this environment's own.
reset() {
  echo "== Resetting the $APP test database =="
  if ! docker ps --filter "name=^${CONTAINER}\$" --format '{{.Names}}' | grep -qx "$CONTAINER"; then
    echo "  !! $CONTAINER is not running — use \`up\`." >&2
    exit 1
  fi
  local listener
  listener="$(port_listener_pid || true)"
  if [[ -n "$listener" ]]; then
    kill $listener 2>/dev/null || true
    for _ in $(seq 1 20); do port_listener_pid >/dev/null || break; sleep 0.5; done
  fi
  docker exec "$CONTAINER" psql -U postgres -q -c "DROP DATABASE IF EXISTS ${DB_NAME} WITH (FORCE)" \
    -c "CREATE DATABASE ${DB_NAME}" >/dev/null
  seed_db
  launch_app
  echo "  Reset: fresh ${DB_NAME}, app on http://127.0.0.1:${APP_PORT} (pid $(port_listener_pid))"
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
  # pytest-cov is here so CLAUDE.md section 7's documented coverage command
  # actually runs in the environment that same document tells you to build. It
  # did not, until 2026-09-10: `pytest --cov=.` failed with "unrecognized
  # arguments" and `python -m coverage` with "No module named coverage", which
  # is why the coverage table in section 7 kept being quoted rather than
  # re-measured. Still test-only -- never add it to requirements.txt.
  echo "== Installing test-only deps (pytest, pytest-cov, playwright) =="
  "$VENV_DIR/bin/pip" install -q pytest pytest-cov playwright
  "$VENV_DIR/bin/playwright" install --with-deps chromium >/dev/null 2>&1 \
    || "$VENV_DIR/bin/playwright" install chromium >/dev/null 2>&1 \
    || echo "   !! playwright browser install failed -- the browser tier will be DORMANT."

  seed_db

  launch_app

  echo
  echo "== Ready =="
  echo "  URL:      http://127.0.0.1:${APP_PORT}"
  echo "  Login:    admin / Admin12345!"
  echo "  Test item: INV301 / PL301 (Retail; 5,000 IQD or 5.000 JOD)"
  echo "  App PID:  $(cat "$PID_FILE")  (kill this yourself when done testing)"
  echo "  App log:  $DATA_DIR/app_stdout.log"
  echo "  Errors:   $DATA_DIR/logs/errors.log"
  echo "  DB:       postgresql://postgres:test@localhost:${DB_PORT}/${DB_NAME}"
  echo "  Docker:   docker exec -it $CONTAINER psql -U postgres -d $DB_NAME"
}

down() {
  echo "== Tearing down $APP test environment =="

  # Two independent guards, because the PID one alone was unable to fail.
  # Until 2026-09-09 the recorded PID was not the app's (docs/archive/COMPARISON.md §44),
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
  restart) restart ;;
  reset) reset ;;
  *) echo "Usage: $0 {up|down|status|restart|reset} {iq|jo}" >&2; exit 1 ;;
esac
