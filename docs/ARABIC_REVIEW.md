# Arabic awaiting clinic review

Arabic in this system was reviewed by the clinic, string by string, in the
predecessor apps (`archive/arabic/`). Everything written during the merge and
the licensing work **without** that review was gone through by the owner on
2026-10-02: the terms below were chosen, and every other row was confirmed and
removed from this file.

**Flag; do not guess**: a one-letter difference (تهذيب / تشذيب) was once
invisible to a non-speaker. New Arabic you write yourself goes in a new section
here, for the clinic to confirm; when no section is left, delete this file and
its lines in `README.md`, `CLAUDE.md` and `docs/README.md`.

## Terms chosen on 2026-10-02

Used throughout the catalogue (`vcs/translations/ar/LC_MESSAGES/messages.po`).

| English | Arabic | Not |
|---|---|---|
| Money Setting | نظام العملة | إعداد العملة |
| License key | مفتاح التفعيل | مفتاح الترخيص (the *License* page and *license* itself stay الترخيص) |
| Developer Pass | تصريح المطوّر | |
| Vendor ("your vendor") | مزوّد البرنامج | |
| Read-only (the system's mode) | وضع القراءة فقط | للقراءة فقط (a read-only *field* keeps it) |
| Grace period | فترة السماح | |
| Configuration (the vendor's page) | الضبط | التهيئة |
| Monitoring ping | إشارة (the address: رابط المراقبة) | نبضة |
| Support bundle | ملف الدعم الفني | حزمة الدعم |
| Self-check (the daily one) | فحص صحة النظام | فحص السلامة (a *release's* health check keeps it) |
| Data export | تصدير البيانات | |
| Installation / Installation ID | التثبيت / معرّف التثبيت | |
| Colour palette names | as shipped (قرمزي، مريمية، … ) | |
| "Their changes" in an edit conflict | masculine, as shipped | |

## Still to do

**Counted forms.** The owner chose proper Arabic plurals after a count (3–10 a
plural noun, 11+ a singular noun) in place of the singular the catalogue uses
now ("%(n)s موعد"). It needs `ngettext` at each place a count is shown (the
appointment, staff-member, schema-update and consignment messages, and the
browser scripts' "%(n)s items"), a plural entry for each in the catalogue, and
a test. None of it is done yet.
