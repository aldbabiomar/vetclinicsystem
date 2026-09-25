# Arabic translation — Batch 2: the rewards card

# CLOSED 2026-09-19 — all 41 answered by the clinic, applied and compiled.

> Both catalogues are complete: zero untranslated, zero fuzzy. The answers
> live in each app's `translations/ar/LC_MESSAGES/messages.po`.
>
> **`Member discount` came back as `خصم العضو`** — distinct from `الخصم`
> (staff Discount) and from `الإعفاء عن الفئات القليلة` (Clean Up), so the
> three-way collision §1 warned about does not exist. Worth keeping: applying
> the batch also exposed a template asking for the WRONG string
> (`_('Discount')` on the owner panel, which renders `الخصم`). A translation
> batch cannot fix that; only looking at the rendered page did.

**Original status, kept for the trail: OPEN, and nothing is blocked by it.** An untranslated string falls
back to its English source, so both apps run in Arabic today with the 41
strings below showing in English. Filling them in is a `.po` edit and a
`pybabel compile` — no code change.

**For: the person commissioning the Arabic** (who speaks Arabic and asked to
resolve anything genuinely unclear rather than have it guessed —
`ARABIC_LOCALIZATION_PLAN.md` §3).

---

## Read this first: 21 of these were machine-guessed, and the guesses were wrong

Running `pybabel update` fuzzy-matched 21 of the new strings against existing
entries and produced Arabic that **looks reviewed and is nonsense**:

| String | What Babel guessed | What that actually means |
|---|---|---|
| Rewards Card | تجاهل | "ignore" |
| Member | موظف واحد | "one employee" |
| Member discount | الحد الأقصى للخصم | "maximum discount" — and that is the *discount cap* label |
| Never | مستخدم جديد | "new user" |
| Expires | منتهي الصلاحية | "expired" — wrong tense; this is a label for a future date |

**All 21 were cleared** rather than left in place, so every string below is
honestly untranslated. Both catalogues now compile with zero fuzzy entries.
This is `ARABIC_LOCALIZATION_PLAN.md` §3's rule ("don't guess") being real
rather than theoretical — the same way Batch 1's الخصم collision was.

---

## §1 The collision risk — please answer this one first

`الخصم` **already means two things** in these apps. Batch 1 established:

- **Discount** (the staff discount) → الخصم
- **Clean Up** (the write-off) → الإعفاء عن الفئات القليلة, deliberately NOT الخصم

This feature adds a **third** discount concept. A cashier has to be able to
tell them apart in a refusal message, because the refusal for one is not the
refusal for the other.

| # | English | Where it appears | Note |
|---|---|---|---|
| 1 | **Member discount** | the bill screens, the receipt, the POS preview | must be distinguishable from الخصم at a glance |
| 2 | **Rewards Card** | the owner page panel, the Settings section | the programme's name; the clinic may already have a name it uses with customers |
| 3 | **Member** | badge on the owners list, `/insights`, POS results | |
| 4 | **Member Discount (%)** | Settings field label | |
| 5 | **Manage Rewards Members** | the role permission checkbox | |

## §2 Membership vocabulary

| # | English | Where |
|---|---|---|
| 6 | Issue Card | button, owner page |
| 7 | Revoke Card | button, owner page |
| 8 | Card Number | owner page |
| 9 | Card Number (optional) | enrol form |
| 10 | Member Since | owner page |
| 11 | Issued By | owner page |
| 12 | Not a member. | owner page |
| 13 | Rewards card issued. | confirmation |
| 14 | Rewards card revoked. | confirmation |
| 15 | That card number is already issued to another owner. | error |
| 16 | Customer (optional) | POS |
| 17 | Name, phone or card number | POS search placeholder |
| 18 | Could not search customers; check server connection. | POS error |

## §3 Expiry vocabulary

Cards are **fixed-term** (default 12 months, set in Settings).

| # | English | Where |
|---|---|---|
| 19 | Expires | owner page label, for a **future** date |
| 20 | Never | shown in the Expires field when a card has no expiry |
| 21 | Expires in %(days)s days | warning badge, within 30 days |
| 22 | Card Valid For (Months) | Settings |
| 23 | This card lapsed on %(date)s. Issuing a new one starts a fresh term. | owner page |
| 24 | Pre-filled from the term in Settings. Clear it for a card that never expires. | enrol form help |
| 25 | Pre-fills the expiry date when a card is issued. Existing cards keep the date they were given. | Settings help |

## §4 The rules, as staff and customers will read them

These carry the actual policy. If any English below is ambiguous, **say so** —
Batch 1 changed an English string rather than just translating it, and that was
the right outcome.

| # | English | Where |
|---|---|---|
| 26 | %(rate)s%% on eligible items | owner page, bill screens |
| 27 | Some items on this bill are not eligible and are charged in full. | bill screens |
| 28 | This bill carries a rewards-card discount. A staff discount can't be added on top of it, and can't replace it. | refusal, all three bill screens |
| 29 | This stay carries a rewards-card discount, which this form cannot change. | boarding payment |
| 30 | Rewards card: {rate} off eligible items. A staff discount cannot be added on top. | POS |
| 31 | This bill doesn't carry a rewards-card discount. | refusal, removal action |
| 32 | Rewards-card discount removed from this bill. | confirmation |
| 33 | That bill no longer exists. | error |
| 34 | Remove | button beside a member discount (admin only) |
| 35 | The rewards programme is switched off in Settings. | owner page, when the rate is 0 |
| 36 | 0 switches the rewards programme off. Applies to eligible Price List items only. | Settings help |
| 37 | Member discount must be a valid number. | Settings validation |
| 38 | Member discount must be between 0%% and %(max)s%%. | Settings validation |

## §5 The `/insights` labels that changed meaning

These three were **lifetime** figures and are now **trailing 12 months, net of
refunds**. The Arabic has to change with them, not just be carried over.

| # | English (new) | Was |
|---|---|---|
| 39 | Clients Who Paid, Last %(months_back)s Months | "Clients With Paid Visits (Lifetime)" |
| 40 | Avg. Spend / Client, Last %(months_back)s Months (%(currency_label)s) | "Avg. Lifetime Spend / Client" |
| 41 | Top Clients by Spend, Last %(months_back)s Months | "Top Clients by Lifetime Spend" |

Plus the caption under that table, which now reads: *"Payments for visits,
inpatient care and boarding, plus retail sales where a customer was identified
at the till, less any refunds. Walk-in sales with no customer recorded aren't
counted."*

---

## Notes for whoever applies the answers

- **Card numbers are identifiers and are never digit-converted** to Eastern
  Arabic numerals (`ARABIC_LOCALIZATION_PLAN.md` §7.1). The dates, the day
  count and the percentage beside them **are** converted, like every other
  number on the page. Both halves of that rule matter; the Rewards panel is
  the first place in either app where the two sit side by side.
- **PDF exports are deliberately English-only** (`ARABIC_LOCALIZATION_PLAN.md`
  §0), so the "Member discount" row on a receipt PDF is not in this batch.
- After editing the `.po`, run `pybabel compile -d translations -l ar` in each
  app, and re-run each app's suite — `test_placeholder_args.py` will catch a
  translation that drops a `%(name)s`, and `test_arabic_wrapping.py` (IQ only)
  guards the badges.
