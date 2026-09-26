"""
The sidebar, as data (audit P1, plan §5.3).

Each link names the endpoint it opens; whether it is drawn is decided by
that endpoint's own permission_required() — read from the view function
(auth.permission_required records it) — so the sidebar offers exactly the
pages a person can open. The template used to draw every clinical, inventory
and POS link for everyone: a role holding only `manage_settings` saw 20 links,
16 of them leading to "access denied".

A link:  Link(label, endpoint, active=(...), also=(...), href=None)
  active  further endpoints that highlight it (its detail pages);
  also    permissions needed IN ADDITION to the page's own (Settlements:
          the overview is its way in, but settling needs its own permission);
  href    a different endpoint to open, when the link's page needs an id.
"""
from dataclasses import dataclass

from flask import current_app

from vcs.messages import N_


@dataclass(frozen=True)
class Link:
    label: str
    endpoint: str
    active: tuple = ()
    also: tuple = ()
    href: str = None

    @property
    def opens(self):
        return self.href or self.endpoint


@dataclass(frozen=True)
class Group:
    key: str
    label: str
    links: tuple
    collapsible: bool = True


NAV = (
    Group("patients", N_("Patients & Visits"), collapsible=False, links=(
        Link(N_("Owners"), "clinical.owners_list",
             active=("clinical.owner_new", "clinical.owner_detail", "clinical.owner_edit")),
        Link(N_("Patients"), "clinical.patients_list",
             active=("clinical.patient_detail", "clinical.patient_edit", "clinical.patient_history")),
        Link(N_("Visits"), "clinical.visits_list",
             active=("clinical.visit_new_start", "clinical.visit_new_existing", "clinical.visit_new_patient",
                     "clinical.visit_detail", "clinical.visit_edit")),
        Link(N_("Follow-Ups"), "clinical.followups_list"),
        Link(N_("Wellness"), "clinical.wellness_list"),
        Link(N_("Grooming"), "clinical.grooming_list"),
        Link(N_("Boarding"), "clinical.boarding_page"),
        Link(N_("Appointments"), "clinical.appointments_page"),
    )),
    Group("inpatient", N_("Inpatient"), collapsible=False, links=(
        Link(N_("Inpatient Cases"), "clinical.inpatient_list",
             active=("clinical.inpatient_new", "clinical.inpatient_detail")),
    )),
    Group("inventory", N_("Inventory"), links=(
        Link(N_("Inventory Status"), "inventory.inventory_status_page"),
        Link(N_("Ordering Sheet"), "inventory.ordering_sheet_page"),
        Link(N_("Audit History"), "inventory.audit_history_list", active=("inventory.audit_session_view",)),
        Link(N_("Inventory Catalog"), "inventory.inventory_catalog"),
        Link(N_("Distributors"), "consignment.distributors_list"),
    )),
    Group("consignment", N_("Consignment"), links=(
        Link(N_("Overview"), "consignment.consignment_overview"),
        Link(N_("Items"), "consignment.consignment_items"),
        Link(N_("Receiving"), "consignment.consignment_receiving_page"),
        Link(N_("Shrinkage"), "consignment.consignment_shrinkage_page"),
        Link(N_("Returns"), "consignment.consignment_returns_page"),
        Link(N_("Sales by Distributor"), "consignment.consignment_sales_page"),
        Link(N_("Settlements"), "consignment.consignment_settlements_page",
             href="consignment.consignment_overview", also=("manage_consignment_settlements",)),
    )),
    Group("sales", N_("Sales & Billing"), links=(
        Link(N_("Point of Sale"), "sales.pos_page", active=("sales.pos_receipt",)),
        Link(N_("Sales History"), "sales.pos_history"),
        Link(N_("Price List"), "inventory.price_list"),
        Link(N_("Refunds"), "sales.refunds_page"),
        Link(N_("Cash Register"), "sales.cash_register_page"),
        Link(N_("Monthly P&L"), "reports.monthly"),
        Link(N_("Yearly P&L"), "reports.yearly"),
        Link(N_("Insights"), "reports.insights"),
        Link(N_("Retention"), "reports.retention"),
    )),
    Group("admin", N_("Admin"), links=(
        Link(N_("Users & Roles"), "admin.admin_users"),
        Link(N_("Logins and Changes"), "admin.admin_logs"),
        Link(N_("Settings"), "settings.settings_page"),
    )),
)


def required(link):
    """The permissions a link needs: its page's own (any one of them), and
    every one of `also`."""
    view = current_app.view_functions[link.opens]
    return tuple(getattr(view, "vz_permissions", ())), tuple(link.also)


def can_open(link, granted):
    any_of, all_of = required(link)
    return (not any_of or any(p in granted for p in any_of)) and all(p in granted for p in all_of)


def visible(granted):
    """The groups, each with only the links these permissions can open; a
    group with none is left out."""
    out = []
    for group in NAV:
        links = [link for link in group.links if can_open(link, granted)]
        if links:
            out.append({"key": group.key, "label": group.label, "collapsible": group.collapsible, "links": links})
    return out
