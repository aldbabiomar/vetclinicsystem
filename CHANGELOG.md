# Changelog

All notable changes to VetClinicSystem are documented in this file, in
[Keep a Changelog](https://keepachangelog.com) style. The in-app updater shows
the entry for a release before Update Now is clicked — to the vendor, in
Developer → Updates — and the clinic's staff live with what it describes, so
every entry is written to be read by both. See `docs/RELEASE_WORKFLOW.md`.

VetClinicSystem merges two predecessor apps, VetClinicSystem IQ and
VetClinicSystem JO, into one system with an IQ/JO money setting. Their release
histories are in `docs/archive/CHANGELOG_IQ.md` and
`docs/archive/CHANGELOG_JO.md`.

## [1.0.0] - Unreleased

In progress — see `docs/plans/UNIFIED_CODEBASE_PLAN.md` for scope and status.

### Added
- Recording a payment on a visit, an inpatient case or a boarding stay now has
  a **Cash Received** field, as the Point of Sale does. It appears when the
  method is Cash, is optional, and shows the change to hand back before the
  payment is saved. Under the IQ money setting the change is rounded down to
  the 250-dinar note; under JO it is exact.
- A payment form that is submitted twice — a double-clicked button — records
  one payment. The second attempt answers "That payment was already recorded."

### Changed
- The warning that an amount "isn't a multiple of 250" (IQ money setting only)
  now appears only for Cash payments on a bill. Card and Transfer payments of
  an odd amount no longer show it.
- An empty payment amount gives the same message on visits, inpatient cases
  and boarding stays.

### Fixed
- On a visit or an inpatient case, paying a bill in full **and** applying a
  Clean Up in the same step is now refused, as it always was on boarding: the
  payment and the Clean Up together can no longer exceed what is owed.
  Previously both were accepted and the bill ended up overpaid by the Clean Up.
