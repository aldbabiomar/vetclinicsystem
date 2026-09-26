"""
The crash log, logs/errors.log (in the data dir on a release install).

Every unhandled exception gets a short reference ID shown on the error page
(safe to text/screenshot) and the full exception detail written here (not
safe to show every role — see errors.handle_unexpected_error). A dedicated
file and logger, independent of the database, so a crash caused by the
database itself being unreachable still gets captured. The scheduler and the
heartbeat write here too.
"""
import logging
import logging.handlers
import os

from vcs.config import DATA_DIR
from vcs.paths import ROOT

ERROR_LOG_PATH = os.path.join(DATA_DIR or ROOT, "logs", "errors.log")
os.makedirs(os.path.dirname(ERROR_LOG_PATH), exist_ok=True)

error_logger = logging.getLogger("vetclinicsystem.errors")
error_logger.setLevel(logging.ERROR)
if not error_logger.handlers:
    _handler = logging.handlers.RotatingFileHandler(
        ERROR_LOG_PATH, maxBytes=5_000_000, backupCount=5, encoding="utf-8"
    )
    _handler.setFormatter(logging.Formatter("%(message)s"))
    error_logger.addHandler(_handler)
