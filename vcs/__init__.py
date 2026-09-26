"""VetClinicSystem.

Importing the package loads the install's .env first (vcs/config.py), so
every module can read os.environ at import time. `create_app()` builds the
Flask application (vcs/web/factory.py); run.py is the launcher.
"""
from vcs import config  # noqa: F401  -- loads .env before anything reads the environment


def create_app():
    """The Flask application. Imported lazily, so that `from vcs import
    money` does not pull in Flask and the whole request layer."""
    from vcs.web.factory import create_app as _create_app
    return _create_app()
