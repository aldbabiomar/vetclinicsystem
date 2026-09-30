"""
Starting the full data export and handing over its file: the same work
behind Settings -> Data Export (clinic admins with `manage_maintenance`, plan
A8) and Developer -> Data Export, so the two cannot drift
(docs/plans/DEVELOPER_AND_LICENSING_PLAN.md §11.4, L-5).

Each export is recorded in the Developer Audit, whoever made it -- the
clinic can read it, and nothing deletes it (A10).
"""
import traceback

from flask import abort, request, send_file

from vcs import jobs
from vcs.db import pool as dbmod
from vcs.domain import developer_audit
from vcs.errorlog import error_logger
from vcs.messages import Msg, N_
from vcs.ops import data_export
from vcs.web.core import shown


def start(actor, pass_id=None):
    """Starts the job; returns (JSON payload, HTTP status)."""
    remote_addr = request.remote_addr

    def task(update):
        # Its own connection: the request's is closed long before this ends,
        # and the export reads in a snapshot of its own (data_export.run).
        conn = dbmod.connect()
        try:
            try:
                name = data_export.run(conn, on_progress=update)
            except Exception:
                error_logger.error("The data export failed:\n" + traceback.format_exc())
                developer_audit.record(conn, "export.generated", actor=actor, pass_id=pass_id,
                                       outcome="failed", remote_addr=remote_addr)
                conn.commit()
                return {"ok": False, "message": Msg(N_("The export could not be made. "
                                                       "The error log has the details."))}
            developer_audit.record(conn, "export.generated", actor=actor, pass_id=pass_id, target=name,
                                   remote_addr=remote_addr)
            conn.commit()
            return {"ok": True, "message": Msg(N_("The export is ready: %(name)s."), name=name)}
        finally:
            conn.close()

    return {"job_id": jobs.start([shown(Msg(step)) for step in data_export.STEPS], task)}, 200


def download(name):
    """The export named, as a download; 404 for anything else."""
    path = data_export.path_of(name)
    if path is None:
        abort(404)
    response = send_file(path, mimetype="application/zip", as_attachment=True, download_name=name)
    response.headers["Cache-Control"] = "no-store"
    return response
