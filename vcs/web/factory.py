"""
create_app(): the Flask application — configuration, extensions, the hooks
around every request, the error handlers, what templates can use, and every
blueprint. There is no module-level app: run.py builds the clinic's, and the
tests build theirs (tests/conftest.py).
"""
from datetime import timedelta
from decimal import Decimal

from flask import Flask
from flask.json.provider import DefaultJSONProvider
from flask_wtf import CSRFProtect

from vcs import config, paths
from vcs.web import errors, hooks, templating
from vcs.web.blueprints import BLUEPRINTS


class _DecimalJSONProvider(DefaultJSONProvider):
    """Flask's default JSON provider has no idea what a Decimal is (it only
    special-cases datetime/UUID/dataclass/Markup) and raises TypeError the
    moment jsonify() sees one — every money value read back from the
    database is now a Decimal (see parse_money() for why). Converted to
    float here, once, at the JSON boundary only: JSON/JS have no exact
    decimal type anyway, and this is a one-way trip out to the browser for
    display, not a value that gets computed with server-side afterward."""
    @staticmethod
    def default(o):
        if isinstance(o, Decimal):
            return float(o)
        return DefaultJSONProvider.default(o)


def create_app():
    # root_path is the package, so templates/, static/ and translations/ are
    # the ones inside vcs/.
    app = Flask("vcs", root_path=paths.PACKAGE)
    app.json = _DecimalJSONProvider(app)
    app.secret_key = config.secret_key()
    CSRFProtect(app)

    if config.BEHIND_TLS_PROXY:
        # Trust the proxy's X-Forwarded-* headers for the client's address and
        # scheme (config.py says when this is on).
        from werkzeug.middleware.proxy_fix import ProxyFix
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    app.config["SESSION_COOKIE_SECURE"] = config.BEHIND_TLS_PROXY
    app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(hours=config.SESSION_LIFETIME_HOURS)
    # Flask-WTF defaults WTF_CSRF_TIME_LIMIT to 3600 seconds, and this app never
    # set it -- so the CSRF token expired after ONE hour inside a session that
    # stayed valid for TWELVE. A visit form, an inpatient bill or a POS cart left
    # open across a consultation then failed on submit, threw away everything
    # typed, and sent the person to the login page for what was a stale form
    # token, not an expired session. Tied to the same value so the two cannot
    # drift apart again; raising SESSION_LIFETIME_HOURS now raises both.
    app.config["WTF_CSRF_TIME_LIMIT"] = int(config.SESSION_LIFETIME_HOURS * 3600)
    app.config["MAX_CONTENT_LENGTH"] = config.MAX_UPLOAD_MB * 1024 * 1024

    # Language — English/Arabic, a clinic setting (templating._select_locale).
    # The text is written into the HTML by Jinja on the server, so the locale
    # has to be known before the response is built. request.accept_languages is
    # deliberately not consulted.
    app.config["BABEL_DEFAULT_LOCALE"] = "en"
    app.config["BABEL_TRANSLATION_DIRECTORIES"] = "translations"

    hooks.register(app)
    errors.register(app)
    templating.register(app)

    # Registering a blueprint prefixes its endpoint names: settings_page
    # becomes settings.settings_page. url_for() raises BuildError at render
    # time on a name that no longer exists, so a missed rename fails at the
    # first page load rather than at the first click.
    for bp in BLUEPRINTS:
        app.register_blueprint(bp)
    return app
