#!/usr/bin/env bash
# Restart the throwaway apps so they pick up template/.mo changes.
#
# Kills by PORT, never by a command-line pattern: `exec env ... python3 run.py`
# rewrites the command line to the resolved Python.app path, so `pkill -f
# "vcs_test_venv_iq/bin/python3 run.py"` matches NOTHING and exits quietly.
# Hours of "verified clean" can come from an app that never restarted — the
# same failure isolated_test_env.sh's PID guard was built for (CLAUDE.md §5).
# Every restart here therefore ASSERTS the listening pid actually changed.
set -u
cd /Users/omaraldbabi/Desktop/VetClinicSystem
for a in "$@"; do
  # $a is the MONEY SETTING of the throwaway clinic (see isolated_test_env.sh):
  # the same code, one environment per setting.
  case "$a" in
    iq) port=5091; db=55491 ;;
    jo) port=5092; db=55492 ;;
    *) echo "unknown money setting: $a (iq|jo)" >&2; exit 2 ;;
  esac
  dbn=vetclinicsystem; pre=VETCLINICSYSTEM
  old="$(lsof -ti:$port || true)"
  [ -n "$old" ] && kill $old 2>/dev/null
  for _ in $(seq 1 20); do lsof -ti:$port >/dev/null || break; sleep 0.5; done
  if lsof -ti:$port >/dev/null; then echo "$a: port $port still held; aborting" >&2; exit 1; fi

  DD="/tmp/vcs_test_data_${a}"
  SK="$(python3 -c 'import secrets; print(secrets.token_hex(32))')"
  ( exec nohup env \
      DATABASE_URL="postgresql://postgres:test@localhost:${db}/${dbn}" \
      "${pre}_DATA_DIR=$DD" "${pre}_HOST=127.0.0.1" "${pre}_PORT=$port" \
      SECRET_KEY="$SK" "/tmp/vcs_test_venv_${a}/bin/python3" run.py \
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
