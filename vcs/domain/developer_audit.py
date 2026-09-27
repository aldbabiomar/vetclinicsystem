"""
What the vendor did at this clinic (docs/plans/DEVELOPER_AND_LICENSING_PLAN.md
§7.3), in its own table: audit_log is pruned by a clinic setting, and a
vendor's actions must not be erasable by the clinic. Nothing prunes
developer_audit and nothing deletes from it.

Like every helper, record() does not commit: the row lands in the request's
transaction, with the action it describes.
"""
from psycopg.types.json import Jsonb

from vcs import clock
from vcs.messages import N_

OUTCOMES = ("ok", "refused", "failed")

# What a person reads for an action code or an outcome. A code with no label
# is shown as it is.
LABELS = {
    "developer.login": N_("Signed in to the Developer area"),
    "developer.login_failed": N_("Developer sign-in refused"),
    "ok": N_("Done"),
    "refused": N_("Refused"),
    "failed": N_("Failed"),
}


def developer_actor(name):
    return f"dev:{name}"


def user_actor(username):
    return f"user:{username}"


def record(db, action, *, actor, outcome="ok", target=None, pass_id=None, detail=None, remote_addr=None):
    """One row. `detail` is a small dict of facts -- never a secret, never a
    key or a token (plan §13)."""
    if outcome not in OUTCOMES:
        raise ValueError(f"unknown outcome {outcome!r}")
    db.execute(
        "INSERT INTO developer_audit (at, actor, pass_id, action, target, outcome, detail, remote_addr) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
        (clock.now(), actor, pass_id, action, target, outcome, Jsonb(detail or {}), remote_addr))


def recent(db, limit=500):
    """The newest rows first."""
    return db.execute(
        "SELECT id, at, actor, pass_id, action, target, outcome, detail, remote_addr "
        "FROM developer_audit ORDER BY at DESC, id DESC LIMIT %s", (limit,)).fetchall()
