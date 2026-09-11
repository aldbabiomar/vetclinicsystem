# Arabic translation — Batch 1: CLOSED 2026-09-11

> **All 24 answered, applied, compiled and pushed. The catalogue is 46/46.**
> Kept as the decision trail — what was asked, what was answered, and the two
> places the answer changed the code rather than just the catalogue.
>
> **Two outcomes worth carrying forward:**
>
> 1. **"Clean Up" is الإعفاء عن الفئات القليلة, never الخصم.** The first
>    rendering supplied was الخصم, which is what *Discount* already reads as —
>    two separate features whose refusal messages would have been
>    indistinguishable to a cashier. Flagged before applying; a distinct term
>    was supplied. This is the §3 collision risk being real, not theoretical.
> 2. **A translation pass reviewed the English.** The cap message read
>    *"Clean Up can't exceed 1000 IQD total on this bill"*, which the
>    translator — reasonably — read as "the bill's total". The rule is a flat
>    per-bill ceiling on the cumulative write-off. The **English was changed**
>    to "Clean Up on this bill can't exceed %(cap)s IQD in total." Worth
>    remembering that an ambiguous source string is a defect in the source.
>
> Note the two apps' caps genuinely differ: IQ 1,000 IQD, JO `Decimal("1.000")`
> = **one** JOD. The Arabic renders that as ١.٠٠٠ in JO, which an Arabic reader
> could plausibly read as one thousand. Not changed — flagging it as the one
> loose thread in this batch.

**For: the person commissioning the Arabic toggle** (who speaks Arabic and
asked to resolve anything genuinely unclear rather than have it guessed —
`ARABIC_LOCALIZATION_PLAN.md` §3).

**Status:** the mechanism is built, tested and working in both apps, and the
three decisions in §4 are ANSWERED and shipped. **What remains is §1–§3 below
— the 24 strings.** The toggle flips, `<html lang>`/`dir` flip server-side, RTL layout
works, and money renders in Arabic-Indic digits. **22 of 46 extracted strings
are translated** — the ones §3 names as safe to do directly. The 24 below are
the ones §3 says to stop and ask about.

**Nothing is blocked by this file.** An untranslated string falls back to its
English source, so both apps work in Arabic today with these 24 items showing
in English. Answer at your convenience; filling them in is a `.po` edit and a
`pybabel compile`, no code change.

Same answers apply to **both apps** unless a row says otherwise — the two
share this vocabulary, and §3 says to ask once.

---

## 1. Clinical and operational vocabulary (14)

These are the terms where an imprecise rendering could actually mislead
someone reading a clinical or inventory record, which is §3's first category.

| # | English | Where it appears | What I'd like your call on |
|---|---|---|---|
| 1 | **Follow-Ups** | sidebar; the worklist of visits needing a callback | Is this المتابعات, or something that reads more like "recall"? It is specifically *the clinic contacting the owner after a visit*, not a return appointment. |
| 2 | **Wellness** | sidebar; vaccination/preventive-care worklist | Preventive-care sense, not "wellbeing". الرعاية الوقائية? اللقاحات? It covers vaccination schedules and next-dose dates. |
| 3 | **Grooming** | sidebar; the grooming worklist | العناية? التجميل? Which reads right for a vet clinic rather than a salon? |
| 4 | **Inventory Catalog** | sidebar; the master list of stock items | Distinguish from **Inventory Status** (#5) and **Price List** (already translated as قائمة الأسعار). These three are separate screens and should not collapse into one another. |
| 5 | **Inventory Status** | sidebar; current stock levels per item | See #4 — the pair needs to stay distinguishable. |
| 6 | **Ordering Sheet** | sidebar; what to reorder and how much | أمر الشراء? قائمة الطلب? It is a *suggestion* sheet, not a purchase order that has been placed. |
| 7 | **Audit History** | sidebar; the record of past stock counts | "Audit" here means **a physical stock count**, not a financial audit and not the change log. That distinction is the whole question — compare #14. |
| 8 | **Shrinkage** | sidebar + consignment; stock written off as damaged/expired/lost | The inventory sense (الهالك? الفاقد?). This one carries liability wording next to it (clinic-liable vs distributor-liable), so it should read as a formal record. |
| 9 | **Settlements** | consignment; paying a distributor for consignment stock sold | التسويات? المحاسبة? Money changing hands with a supplier, periodically. |
| 10 | **Sales by Distributor** | consignment report | A report grouping sales by which supplier owns the stock. |
| 11 | **Point of Sale** | sidebar; the till screen | نقطة البيع is the standard rendering — confirm, since it is also the most-used screen in the app and worth getting right. |
| 12 | **Sales History** | sidebar; past till transactions | |
| 13 | **Cash Register** | sidebar; the end-of-day drawer count | الصندوق? الخزنة? It means the physical drawer and its reconciliation, not "cashier". |
| 14 | **Logins and Changes** | admin; the audit trail of who did what | Compare #7 — this is the *change log*, that one is a *stock count*. If both naturally translate to something with مراجعة, they will be confusable in the sidebar. |

---

## 2. Money, and anything a clinic owner treats as a record (5)

§3's "money/legal/compliance-adjacent" category. These are the actual
user-facing validation messages, so tone matters as much as wording.

| # | English (exact) | Context |
|---|---|---|
| 15 | `%(label)s is required.` | Generic required-field error. `%(label)s` is substituted with a field name — so the sentence needs to work with an inserted noun, and **Arabic agreement may not fall out of a single template**. If it cannot, tell me and I will restructure it per field. |
| 16 | `Discount must be between 0% and %(cap)s% for your role.` | Refused discount. `%(cap)s` is a number. |
| 17 | `Clean Up amount can't be negative.` | "Clean Up" is this app's name for a **capped staff write-off** of a small remaining balance. It is a proper feature name, so: translate it, or keep it in English as a term of art? |
| 18 | `Clean Up can't exceed %(cap)s IQD total on this bill.` | As #17. **IQ says IQD, JO says JOD** — the only string in this file that genuinely differs between the apps. |
| 19 | `Clean Up can't exceed the remaining balance.` | As #17. |

---

## 3. Report headings (5)

| # | English | Note |
|---|---|---|
| 20 | **Monthly P&L** | "P&L" is an abbreviation. Spell it out in Arabic (الأرباح والخسائر), keep the Latin abbreviation, or use a shorter Arabic equivalent? It appears in a narrow sidebar, so length matters. |
| 21 | **Yearly P&L** | As #20, and should match it. |
| 22 | **Insights** | Analytics overview page. رؤى is literal but may read oddly as a nav label. |
| 23 | **Retention** | Client-retention analytics — how many owners come back. Not "data retention", which is a different feature in this app (log trimming), so a rendering that could be read either way would be actively wrong. |
| 24 | **Users & Roles** | Admin screen. |

---

## 4. Three decisions — ANSWERED 2026-09-11, implemented and pinned by tests

All three were confirmed and are live in both apps. Recorded here as the
decision trail; each is one line to revisit.

| Decision | Answer | What shipped |
|---|---|---|
| Numeric column alignment | **Always right-aligned** | Fixed `text-align: right` on `.num-col`/`.cell-input.num`; digits stay put when the UI flips. Prose alignment is still direction-aware |
| Dates | **Arabic-Indic digits too** | `\|localdate` applied to 34 read-only date renders per app. `<input type="date">` deliberately still carries a Western ISO value — the browser cannot parse anything else |
| Currency label | **Arabic abbreviation** (د.ع / د.أ), same position | `currency_label()` template global across ~110 sites. `pdf_export.py` keeps the Latin code permanently (§0) |

### Superseded — the original wording of these three



These were not in §3's "must ask" list, but they are choices rather than
facts, and each is a one-line change to reverse.

1. **Numeric columns now use `text-align: end`** rather than a fixed right
   alignment, so numbers follow the reading direction and sit on the left in
   Arabic. §6.2 flags this as genuinely debatable — a lot of Arabic business
   software keeps numeric columns visually right-aligned. English rendering is
   unchanged either way. Say the word and it becomes `start`, or a fixed
   `right`.
2. **Dates render with Arabic-Indic digits** when Arabic is active
   (`٢٠٢٦-٠٩-١١`), via a new `|localdate` filter. §7.3 explicitly flags this
   as debatable — an ISO-style date reads more like a computer value than a
   spoken number, and much Arabic software leaves dates in Western digits.
   **Currently this filter exists but is applied nowhere**, so today dates
   stay Western in both languages; deciding this costs nothing yet.
3. **Currency position** is unchanged — the existing "250 IQD" ordering is
   kept as-is. §7.3 asks whether Arabic convention wants the currency word
   elsewhere relative to the number. Untouched pending your answer.

---

## Batch 2 — one grooming service whose English is unclear

Opened 2026-09-11, while rebuilding `enum_labels.py` from the constants the
code actually uses. Ten grooming services became translatable at once
(`logic.GROOMING_SERVICES`); nine have a plain reading and are applied. One
does not, and it is not an Arabic problem — **"Zoning" is not a standard
grooming term in English either**, so guessing the Arabic would just move the
ambiguity somewhere harder to find.

| # | English | Applied now | What I assumed |
|---|---|---|---|
| 25 | `Zoning` | `تشذيب المنطقة الحساسة` | that it means a sanitary trim — the grooming sense closest to "zone" |

If the clinic means something else by it (a coat-pattern trim, a specific
package, a word staff already use), give the Arabic and the English gets
corrected too — the same way "Clean Up" did in Batch 1, where the confusing
English was the actual bug.

The nine applied without a question: Bath `استحمام`, Haircut `قص الشعر`,
De-shedding `إزالة الوبر المتساقط`, Nail Trim `تقليم الأظافر`, Ear Cleaning
`تنظيف الأذن`, Ear Mites Cleaning `تنظيف سوس الأذن`, Paw Clipping
`قص شعر الكفوف`, Nail Caps `أغطية الأظافر`, Anal Gland Emptying
`تفريغ الغدد الشرجية`.

---

## How to apply your answers

Either reply with the Arabic for each number, or edit the `.po` files
directly — they are plain text, one `msgid`/`msgstr` pair per string:

```
webapps/vetclinicsystem_iq-main/translations/ar/LC_MESSAGES/messages.po
webapps/vetclinicsystem_jo-main/translations/ar/LC_MESSAGES/messages.po
```

Then, **in each app** (the step whose symptom when forgotten is "I translated
this and nothing changed", not an error):

```bash
pybabel compile -d translations
```

`tests/test_localization.py` has a guard for exactly that mistake — it fails
if `messages.mo` is older than `messages.po` — plus one asserting that every
non-empty `msgstr` actually contains Arabic characters, so a half-finished
entry cannot quietly render as English.
