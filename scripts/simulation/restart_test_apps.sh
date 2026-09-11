#!/usr/bin/env bash
# Restart the throwaway apps so they pick up template/.mo changes.
#
# Kills by PORT, never by a command-line pattern: `exec env ... python3 app.py`
# rewrites the command line to the resolved Python.app path, so `pkill -f
# "vz_iq_test_venv/bin/python3 app.py"` matches NOTHING and exits quietly.
# Hours of "verified clean" can come from an app that never restarted — the
# same failure isolated_test_env.sh's PID guard was built for (CLAUDE.md §5).
# Every restart here therefore ASSERTS the listening pid actually changed.
set -u
cd /Users/omaraldbabi/Desktop/VetClinicSystem
for a in "$@"; do
  case "$a" in
    iq) port=5091; db=55491; dbn=vetclinicsystemiq; pre=VETCLINICSYSTEMIQ ;;
    jo) port=5092; db=55492; dbn=vetclinicsystemjo; pre=VETCLINICSYSTEMJO ;;
    *) echo "unknown app: $a" >&2; exit 2 ;;
  esac
  old="$(lsof -ti:$port || true)"
  [ -n "$old" ] && kill $old 2>/dev/null
  for _ in $(seq 1 20); do lsof -ti:$port >/dev/null || break; sleep 0.5; done
  if lsof -ti:$port >/dev/null; then echo "$a: port $port still held; aborting" >&2; exit 1; fi

  DD="/tmp/vz_${a}_test_data"
  SK="$(python3 -c 'import secrets; print(secrets.token_hex(32))')"
  ( cd "webapps/vetclinicsystem_${a}-main" && exec nohup env \
      DATABASE_URL="postgresql://postgres:test@localhost:${db}/${dbn}" \
      "${pre}_DATA_DIR=$DD" "${pre}_HOST=127.0.0.1" "${pre}_PORT=$port" \
      SECRET_KEY="$SK" "/tmp/vz_${a}_test_venv/bin/python3" app.py \
      > "$DD/app_stdout.log" 2>&1 ) &
  for _ in $(seq 1 40); do
    code="$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:$port/login" || true)"
    [ "$code" = "200" ] && break
    sleep 0.5
  done
  new="$(lsof -ti:$port || true)"
  if [ "$code" != "200" ]; then
    echo "$a: did not come up (HTTP $code)"; tail -5 "$DD/app_stdout.log"; exit 1
  fi
  if [ -n "$old" ] && [ "$new" = "$old" ]; then
    echo "$a: SAME pid $new — it never restarted"; exit 1
  fi
  echo "$a: up on $port, pid $old -> $new"
done
