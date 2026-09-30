"""
The one place that finds PostgreSQL's client tools
(docs/plans/DEVELOPER_AND_LICENSING_PLAN.md §12.2): backup, restore, the
restore check and Developer -> System all ask here, and nothing else calls
`shutil.which("pg_dump")` (seam rule 16, tests/test_seam_rules.py).

Where it looks:
  * VETCLINICSYSTEM_PG_BIN_DIR, when set -- and only there. A tool missing
    from it is an error, never a quiet fallback to some other copy.
  * Otherwise PATH, then the places the usual installers put them, newest
    version first: Homebrew's postgresql@N and Postgres.app on macOS,
    C:\\Program Files\\PostgreSQL\\N\\bin on Windows (its installer does not
    touch PATH), /usr/lib/postgresql/N/bin on Linux.

A tool is usable only at least at the server's major version: pg_dump
refuses a newer server outright, and an older pg_restore can misread a
newer dump.

How the tools run depends on the database mode (config.DB_MODE, A11):
  * "native": local tools or nothing. Never Docker -- there is no container,
    and "install Docker Desktop" would be wrong advice.
  * "docker": local tools when they are usable, else `docker exec` into the
    database's container, as before.
"""
import glob
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass

from vcs import config

TOOLS = ("pg_dump", "pg_restore")
BIN_DIR_ENV = "VETCLINICSYSTEM_PG_BIN_DIR"
_VERSION = re.compile(r"\(PostgreSQL\)\s+(\d+)")


class ToolError(RuntimeError):
    """A tool that cannot be used. The message names the mode and the tool."""


@dataclass(frozen=True)
class Tool:
    """How to run one tool: `path` of a local binary (kind "local"), or of
    the docker command that runs it in the container (kind "docker")."""
    name: str
    kind: str
    path: str
    version: int = None


def mode():
    return config.DB_MODE


def _versioned_dirs(pattern):
    """Directories matching `pattern` (one * standing for the version),
    newest version first."""
    found = []
    for d in glob.glob(pattern):
        m = re.search(r"(\d+)(?:\.\d+)?(?=[^\d]*$)", d.replace(os.sep + "bin", ""))
        found.append((int(m.group(1)) if m else 0, d))
    return [d for _v, d in sorted(found, reverse=True)]


def search_dirs():
    """Where the usual installers put the tools on this platform."""
    if sys.platform == "win32":
        roots = [os.environ.get("ProgramFiles", r"C:\Program Files"), os.environ.get("ProgramW6432", "")]
        dirs = []
        for root in filter(None, dict.fromkeys(roots)):
            dirs += _versioned_dirs(os.path.join(root, "PostgreSQL", "*", "bin"))
        return dirs
    if sys.platform == "darwin":
        return (_versioned_dirs("/opt/homebrew/opt/postgresql@*/bin")
                + _versioned_dirs("/usr/local/opt/postgresql@*/bin")
                + _versioned_dirs("/Applications/Postgres.app/Contents/Versions/*/bin"))
    return _versioned_dirs("/usr/lib/postgresql/*/bin")


def _executable(directory, name):
    path = os.path.join(directory, name + (".exe" if sys.platform == "win32" else ""))
    return path if os.path.isfile(path) and os.access(path, os.X_OK) else None


def candidates(name):
    """Every copy of `name` this finder would consider, in order."""
    bin_dir = os.environ.get(BIN_DIR_ENV, "").strip()
    if bin_dir:
        found = _executable(bin_dir, name)
        return [found] if found else []
    out = [shutil.which(name)] + [_executable(d, name) for d in search_dirs()]
    return list(dict.fromkeys(p for p in out if p))


def version_of(path):
    """The major version a tool reports, or None when it will not say."""
    try:
        result = subprocess.run([path, "--version"], capture_output=True, text=True, timeout=15)
    except (OSError, subprocess.SubprocessError):
        return None
    m = _VERSION.search(result.stdout or "")
    return int(m.group(1)) if m else None


def server_major(db=None):
    """The database server's major version, from `db` or a short connection
    of its own; None when the server cannot be asked."""
    try:
        if db is not None:
            return int(db.execute("SHOW server_version_num").fetchone()["server_version_num"]) // 10000
        import psycopg
        from vcs.db import pool
        with psycopg.connect(pool.database_url(), connect_timeout=10) as con:
            return int(con.execute("SHOW server_version_num").fetchone()[0]) // 10000
    except Exception:
        return None


def find(name, server=None):
    """A usable local copy of `name`: at least the server's major version
    (when it is known). Raises ToolError saying what was wrong."""
    paths = candidates(name)
    bin_dir = os.environ.get(BIN_DIR_ENV, "").strip()
    where = (f"in {bin_dir} ({BIN_DIR_ENV})" if bin_dir
             else "on PATH or in the usual PostgreSQL install folders")
    if not paths:
        raise ToolError(f"{name} was not found {where}. Install the PostgreSQL client tools"
                        + (f", version {server} or newer" if server else "")
                        + f", or set {BIN_DIR_ENV} to the folder that holds them.")
    too_old = []
    for path in paths:
        version = version_of(path)
        if server is None or (version is not None and version >= server):
            return Tool(name, "local", path, version)
        too_old.append(f"{path} is version {version if version is not None else 'unknown'}")
    raise ToolError(f"{name} must be version {server} or newer, the database server's version; "
                    f"{'; '.join(too_old)}. Install newer PostgreSQL client tools"
                    + (f" or point {BIN_DIR_ENV} at them." if not bin_dir else f" into {bin_dir}."))


def docker():
    """The docker command, or None. Only ever asked in docker mode."""
    return shutil.which("docker")


def choose(name, server=None):
    """How to run `name` in this install's mode. Raises ToolError."""
    if mode() == "native":
        try:
            return find(name, server)
        except ToolError as e:
            raise ToolError(f"Native PostgreSQL mode: {e}") from None
    try:
        return find(name, server)
    except ToolError as local_problem:
        path = docker()
        if path:
            return Tool(name, "docker", path)
        raise ToolError(f"Could not run {name}: {local_problem} The 'docker' command is not "
                        "available either -- install Docker Desktop (recommended) or the PostgreSQL "
                        "client tools.") from None


def describe(server=None):
    """For Developer -> System and the support bundle: each tool as this
    install would run it, or why it cannot."""
    out = {"mode": mode(), "bin_dir": os.environ.get(BIN_DIR_ENV, "").strip() or None}
    for name in TOOLS:
        try:
            tool = choose(name, server)
            out[name] = {"kind": tool.kind, "path": tool.path, "version": tool.version}
        except ToolError as e:
            out[name] = {"kind": None, "path": None, "error": str(e)}
    return out
