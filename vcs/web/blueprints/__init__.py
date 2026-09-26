"""The blueprints: one per area of the app, each exposing `bp`.

They import shared request-layer pieces from vcs.web.core and the rest of
`vcs`, never from the factory that registers them (vcs/web/factory.py) — that
direction would be circular.
"""
from vcs.web.blueprints import admin, clinical, consignment, inventory, main, reports, sales, settings

# Registration order is not significant: no two blueprints share a URL.
BLUEPRINTS = [main.bp, reports.bp, settings.bp, clinical.bp, sales.bp, inventory.bp, consignment.bp, admin.bp]
