# VetClinicSystem documentation

VetClinicSystem is **one** application. It has a **money setting** — **IQ**
(Iraqi dinar: whole dinars, cash rounded to the 250-dinar note) or **JO**
(Jordanian dinar: three decimals, exact to the fils) — chosen by an admin in
Settings before any money is recorded, and locked from then on.

It was built by merging two predecessor apps, *VetClinicSystem IQ* and
*VetClinicSystem JO*, which were separate forks of one codebase. Documents that
describe those two apps are kept in `archive/` for their reasoning, because
code comments throughout this repository cite them.

Code comments cite documents by filename (e.g. "see
`ORPHANED_RECORDS_AUDIT.md` F-12"). Every cited document is in this folder;
`tests/test_frontend.py::test_every_cited_document_can_be_found` fails if a
citation stops resolving.

## Current — read these

| Document | What it is |
|---|---|
| `../CLAUDE.md` | Ground rules for working on this codebase. Read first. |
| `plans/UNIFIED_CODEBASE_PLAN.md` | The plan for merging IQ and JO into this one system, with the decisions taken and progress. **In progress.** |
| `CODE_AUDIT_2026-09-25.md` | The last audit of the two predecessor apps: bugs, parity gaps, design. Every finding is tracked to where it is fixed in the merged system. |
| `RELEASE_WORKFLOW.md` | How to version, tag and publish a release that the in-app updater will accept. |
| `ARABIC_REVIEW.md` | Arabic written during the merge without clinic review — English and Arabic side by side, for a native speaker to confirm. Delete rows as they are confirmed. |
| `SEAM_RULES.md` | Rules that must hold on every sibling code path (the four payment surfaces, the date filters, …), the register of every time one did not, and the checklist for adding a rule. |

## Feature specifications — built

| Document | Feature |
|---|---|
| `features/CLEANUP_FEATURE_PLAN.md` | "Clean Up": a capped staff write-off applied at payment time. |
| `features/MONITORING_FEATURE_PLAN.md` | The four monitoring layers: daily self-check, dashboard banner, heartbeat, restore verification. |
| `features/REWARDS_CARD_PLAN.md` | The rewards card: a member percentage off the eligible lines of a bill. |

## Plans — not executed

| Document | What it is |
|---|---|
| `plans/DEVELOPER_AND_LICENSING_PLAN.md` | The Developer area, signed license keys with read-only expiry, developer-controlled money setting and palette, a private update repo with per-clinic tokens, and native PostgreSQL. Decisions taken 2026-09-25. **Starts after the merge, before 1.0.0.** |
| `plans/HOSTING_MIGRATION_PLAN.md` | Draft: moving an install off the clinic PC onto a VPS. Written for the predecessor apps; re-check before use. |
| `plans/CLINIC_PC_TUNNEL_PLAN.md` | Draft: a Cloudflare-tunnel alternative to the above. Same caveat. |

## Archive — the predecessor apps (IQ and JO)

Read-only history. These describe two separate apps and their differences,
which no longer exist as separate code. Their reasoning is still why a lot of
defensive code looks the way it does — search them before removing a guard
that looks redundant.

| Document | What it is |
|---|---|
| `archive/COMPARISON.md` | The dated, append-only diff between IQ and JO (§1–§63). Section numbers are cited throughout the code, e.g. "`COMPARISON.md` §1.1" for the money model. |
| `archive/audits/ERROR_500_AUDIT.md` | Every action that could raise an unhandled exception (findings E-xx). |
| `archive/audits/ORPHANED_RECORDS_AUDIT.md` | Every way a row could be left with no reachable parent (findings F-xx). |
| `archive/audits/IQ_JO_DIVERGENCE_AUDIT.md` | A line-by-line diff of the two trees. Closed. |
| `archive/FULL_APP_REVIEW_2026-09-10.md` | 37-finding review of both apps. Closed. |
| `archive/SIMULATION_AUDIT_2026-09-11.md` | Both apps driven as real users; six findings. Closed. Its §8 lists what was attacked and held. |
| `archive/CODE_REVIEW_MONITORING_2026-08-27.md` | Review of the monitoring feature. |
| `archive/SOAK_LOG.md` | How the monitoring soak was run. |
| `archive/TRANSITION_NOTES.md` | Hand-over notes for the two-app era. |
| `archive/arabic/ARABIC_LOCALIZATION_PLAN.md` | The Arabic localization plan, including §0's permanent exclusion of PDF exports from translation. |
| `archive/arabic/ARABIC_TRANSLATION_QUESTIONS.md`, `archive/arabic/ARABIC_TRANSLATION_QUESTIONS_REWARDS.md`, `archive/arabic/ARABIC_REWARDS_FILL_IN.md` | The translation questions answered by the clinic. Read before running `pybabel update` on anything. |
| `archive/CHANGELOG_IQ.md`, `archive/CHANGELOG_JO.md` | The two apps' release histories up to IQ v1.17.2 / JO v1.15.2. |

One citation names a document that never existed
(`data_integrity_framework.md`, in one test's history note); its reasoning is
carried inline where it is cited.
