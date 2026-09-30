# Running VetClinicSystem on a native PostgreSQL

By default an install runs its database in Docker (`docker compose`, set up by
`setup.py`). **Native mode** uses a PostgreSQL server installed on the clinic's
computer instead, for a machine where Docker Desktop is unwelcome or unavailable
(docs/plans/DEVELOPER_AND_LICENSING_PLAN.md §12). The app itself does not care
which: it only ever connects to `DATABASE_URL`.

In native mode `setup.py` never runs Docker, and neither do backups, restores or
the monthly restore check: they use the PostgreSQL client tools on the machine,
and an error names the missing tool rather than suggesting Docker.

## What is needed

- **PostgreSQL 16 or newer.** Setup refuses an older server.
- **Its client tools** (`pg_dump`, `pg_restore`) at least at the server's
  version. They come with every server install below. The app looks on `PATH`,
  then where the installers put them — Homebrew's `postgresql@N` and
  Postgres.app on macOS, `C:\Program Files\PostgreSQL\N\bin` on Windows (its
  installer does not add this to `PATH`), `/usr/lib/postgresql/N/bin` on Linux —
  newest first. To use one particular folder, and only that one, set
  `VETCLINICSYSTEM_PG_BIN_DIR` in the install's `.env`.
- **A role that owns the app's database and has `CREATEDB`** — nothing more: no
  superuser, and no extensions are used. `CREATEDB` is for the monthly check that
  the latest backup really restores, which restores it into a throwaway database
  and drops it. Without it the app works, and the self-check says, as its own
  finding, that backups cannot be test-restored.

## Creating the role and the database

Choose a long password. If it contains characters other than letters and digits,
percent-encode them in `DATABASE_URL` (`@` is `%40`, `/` is `%2F`, `:` is `%3A`).

The SQL is the same everywhere:

```sql
CREATE ROLE vetclinicsystem LOGIN PASSWORD 'the-password' CREATEDB;
CREATE DATABASE vetclinicsystem OWNER vetclinicsystem;
```

### macOS

Homebrew:

```bash
brew install postgresql@16
brew services start postgresql@16
/opt/homebrew/opt/postgresql@16/bin/psql postgres
```

`brew services` starts it at every login from then on. With **Postgres.app**
instead, tick *Automatically start at login* in its settings and open `psql`
from its menu. Paste the SQL above into `psql`, then `\q`.

### Windows

Install PostgreSQL 16 with the installer from postgresql.org (EnterpriseDB). It
registers a Windows service (`postgresql-x64-16`) that starts at boot — which
is also what makes the app's own start-at-boot task useful. Open *SQL Shell
(psql)* from the Start menu, sign in as `postgres`, and paste the SQL above.

### Linux (Debian and Ubuntu)

```bash
sudo apt install postgresql          # 16 or newer; on an older release, add apt.postgresql.org first
sudo systemctl enable --now postgresql
sudo -u postgres psql
```

Paste the SQL above.

## Running setup

```bash
python3 setup.py --db-mode native \
    --database-url postgresql://vetclinicsystem:the-password@127.0.0.1:5432/vetclinicsystem \
    --money-setting IQ --license-key '<the key your vendor sent>'
```

Setup waits for the server (and says which host and port it is waiting for),
checks its version and the role's `CREATEDB`, writes `.env` with
`VETCLINICSYSTEM_DB_MODE=native` and that `DATABASE_URL`, and carries on as a
Docker install does. It does not move an existing install from one mode to the
other.

## Afterwards

- **Backups** (nightly, and Back Up Now) and **restores** run `pg_dump` and
  `pg_restore` from the folders above, in every license state.
- **Developer → System** shows the mode, the server's version, and which
  `pg_dump` and `pg_restore` will be used — or why none can.
- If the server is not running, the app's pages fail and the daily self-check
  reports the database as unreachable: start the service (above).
