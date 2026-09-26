# Arabic awaiting clinic review

Arabic in this system was reviewed by the clinic, string by string, in the
predecessor apps (`archive/arabic/`). The strings below were written during
the merge **without** that review. Each one reuses the catalogue's existing,
reviewed vocabulary — الإعفاء عن الفئات القليلة for Clean Up, الصندوق for the
Cash Register, جرد for an audit, بطاقة المكافآت, قائمة الأسعار — but the
sentences themselves have not been read by a native speaker at the clinic.
**Flag; do not guess**: a one-letter difference (تهذيب / تشذيب) was once
invisible to a non-speaker.

Placeholders such as `%(currency)s` and `{price}` are filled in by the app
(`%(currency)s` becomes د.ع or د.أ) and must stay exactly as written.

To change one: edit its `msgstr` in `vcs/translations/ar/LC_MESSAGES/messages.po`,
run `pybabel compile -d vcs/translations`, and delete its row here. When this file
has no rows left, delete the file and its line in `README.md` and `CLAUDE.md`.

## 1. The money setting — new text (15)

**One term to confirm first:** "Money Setting" is translated **إعداد العملة**
("currency setting"), and it recurs through this section.

| # | English | Arabic (as shipped) |
|---|---|---|
| 1 | IQ — Iraqi dinar (IQD) | IQ — الدينار العراقي (د.ع) |
| 2 | JO — Jordanian dinar (JOD) | JO — الدينار الأردني (د.أ) |
| 3 | Money Setting | إعداد العملة |
| 4 | — Choose IQ or JO — | — اختر IQ أو JO — |
| 5 | Choose the money setting before recording any price or amount. Billing, payments, the point of sale and the price list stay locked until it is set. | اختر إعداد العملة قبل تسجيل أي سعر أو مبلغ. تبقى الفوترة والدفعات ونقطة البيع وقائمة الأسعار مقفلة حتى يتم تحديده. |
| 6 | Locked: money has been recorded in %(currency)s, so the setting can no longer change. | مقفل: سُجّلت مبالغ بـ %(currency)s، لذا لم يعد بالإمكان تغيير هذا الإعداد. |
| 7 | Can be changed until the first price or amount is recorded; then it locks. | يمكن تغييره إلى أن يُسجَّل أول سعر أو مبلغ، ثم يُقفل. |
| 8 | IQ: whole dinars, cash rounded to the 250-dinar note, +964 phone numbers. JO: three decimals, exact to the fils, +962 phone numbers. | IQ: دنانير صحيحة، ويُقرَّب النقد إلى فئة ٢٥٠ دينارًا، وأرقام هواتف ‎+964. JO: ثلاث خانات عشرية، دقيقة حتى الفلس، وأرقام هواتف ‎+962. |
| 9 | Choose the clinic's money setting (IQ or JO) first — nothing with a price or an amount can be recorded until it is set. | اختر إعداد العملة للعيادة (IQ أو JO) أولًا — لا يمكن تسجيل أي سعر أو مبلغ حتى يتم تحديده. |
| 10 | Billing, payments and prices aren't available yet: an admin needs to choose the clinic's money setting in Settings first. | الفوترة والدفعات والأسعار غير متاحة بعد: يجب على أحد المديرين اختيار إعداد العملة للعيادة من الإعدادات أولًا. |
| 11 | Choose the clinic's money setting (IQ or JO) before recording any price or amount. | اختر إعداد العملة للعيادة (IQ أو JO) قبل تسجيل أي سعر أو مبلغ. |
| 12 | Billing, payments and prices are not available yet: an admin needs to choose the clinic's money setting in Settings first. | الفوترة والدفعات والأسعار غير متاحة بعد: يجب على أحد المديرين اختيار إعداد العملة للعيادة من الإعدادات أولًا. |
| 13 | Not a valid money setting. | إعداد العملة غير صالح. |
| 14 | The money setting can't be changed once money has been recorded — every stored amount is in %(currency)s. | لا يمكن تغيير إعداد العملة بعد تسجيل أي مبلغ — كل المبالغ المحفوظة بـ %(currency)s. |
| 15 | Money setting saved: %(name)s. It locks itself once the first price or amount is recorded. | تم حفظ إعداد العملة: %(name)s. سيُقفل تلقائيًا بمجرد تسجيل أول سعر أو مبلغ. |

## 2. Messages that were never translated before (18)

These were shown in English even in an Arabic clinic, in both predecessor apps
(`CODE_AUDIT_2026-09-25.md` F1/F2). They are translated now for the first time.

| # | English | Arabic (as shipped) |
|---|---|---|
| 1 | Heads up: this amount isn't a multiple of %(unit)s %(currency)s. It'll still save as entered, but the Cash Register's end-of-day audit compares against physical notes, so an odd amount here can make an otherwise-correct day look slightly off. | تنبيه: هذا المبلغ ليس من مضاعفات %(unit)s %(currency)s. سيُحفظ كما أُدخل، لكن جرد نهاية اليوم في الصندوق يُقارَن بالأوراق النقدية الفعلية، لذا قد يجعل مبلغ كهذا يومًا صحيحًا يبدو مختلًّا قليلًا. |
| 2 | Cart quantities must be valid numbers. | يجب أن تكون كميات السلة أرقامًا صالحة. |
| 3 | Item %(iid)s has no sale price set in the Price List — skipped. | الصنف %(iid)s ليس له سعر بيع محدد في قائمة الأسعار — تم تجاهله. |
| 4 | %(name)s hasn't been through an inventory audit yet — run an audit before selling it. | %(name)s لم يُجرد بعد — أجرِ جردًا قبل بيعه. |
| 5 | Only %(stock)s %(unit)s of %(name)s in stock — sale blocked. | المتوفر في المخزون من %(name)s هو %(stock)s %(unit)s فقط — تم منع البيع. |
| 6 | Cash Received must be a valid number. | يجب أن يكون النقد المستلم رقمًا صالحًا. |
| 7 | Cash received (%(received)s %(currency)s) is less than the total (%(total)s %(currency)s) — collect the full amount before completing the sale. | النقد المستلم (%(received)s %(currency)s) أقل من الإجمالي (%(total)s %(currency)s) — حصّل المبلغ كاملًا قبل إتمام البيع. |
| 8 | That customer no longer exists — search again. | هذا العميل لم يعد موجودًا — ابحث مرة أخرى. |
| 9 | This customer's rewards card already discounts this sale — a staff discount can't be added on top of it. | بطاقة المكافآت لهذا العميل تخصم من هذه العملية بالفعل — لا يمكن إضافة خصم الموظفين فوقها. |
| 10 | Can't apply a discount — the cart includes item(s) marked as not discountable: %(names)s. | تعذّر تطبيق الخصم — تتضمن السلة أصنافًا غير قابلة للخصم: %(names)s. |
| 11 | Nothing to sell. | لا يوجد ما يُباع. |
| 12 | Pick how this refund was actually paid out: %(methods)s. | اختر الطريقة التي صُرف بها هذا الاسترداد فعليًا: %(methods)s. |
| 13 | Refund of %(amount)s %(currency)s recorded and stock restored. | تم تسجيل استرداد بقيمة %(amount)s %(currency)s وإعادة المخزون. |
| 14 | Refund of %(amount)s %(currency)s recorded. | تم تسجيل استرداد بقيمة %(amount)s %(currency)s. |
| 15 | stock: {stock} | المخزون: {stock} |
| 16 | {price} %(currency)s each | {price} %(currency)s للوحدة |
| 17 | {price} %(currency)s each — {remaining} left refundable | {price} %(currency)s للوحدة — {remaining} متبقية قابلة للاسترداد |
| 18 | Only {remaining} left refundable for {name}. | لم يتبقَّ سوى {remaining} قابلة للاسترداد من {name}. |

## 3. Reviewed Arabic, generalised (3)

The predecessor IQ app had reviewed Arabic for these, naming the 250-dinar note
directly. The merged system names the cash unit of whichever money setting is
active, so the wording was generalised ("أصغر مبلغ يمكن صرفه" — the smallest
amount that can be paid out — where it said أصغر فئة نقدية).

| # | English | Arabic (as shipped) |
|---|---|---|
| 1 | Heads up: this price isn't a multiple of %(unit)s %(currency)s — totals including this item are rounded to it at checkout (this is handled automatically). | تنبيه: هذا السعر ليس من مضاعفات %(unit)s %(currency)s — تُقرَّب الإجماليات التي تتضمن هذا الصنف إليها عند الدفع (يتم ذلك تلقائيًا). |
| 2 | This sale has no refundable value left to pay out — the smallest amount that can be paid out is %(unit)s %(currency)s and only %(left)s %(currency)s of this sale is still refundable. | لم تعد لهذه العملية قيمة قابلة للاسترداد — أصغر مبلغ يمكن صرفه هو %(unit)s %(currency)s ولم يتبقَّ سوى %(left)s %(currency)s قابلة للاسترداد من هذه العملية. |
| 3 | This record has no refundable value left to pay out — the smallest amount that can be paid out is %(unit)s %(currency)s. | لم تعد لهذا السجل قيمة قابلة للاسترداد — أصغر مبلغ يمكن صرفه هو %(unit)s %(currency)s. |

## 4. Schema-update warnings (2)

Shown to an admin when the database has not received every update the running
version needs. They replace two reviewed messages about updates that failed to
apply, and reuse their wording (تحديثات for "updates").

| # | English | Arabic (as shipped) |
|---|---|---|
| 1 | The database is missing %(count)s schema update(s) this version needs (%(files)s). Run setup again. | تنقص قاعدة البيانات %(count)s من التحديثات التي يحتاجها هذا الإصدار (%(files)s). شغّل الإعداد مرة أخرى. |
| 2 | The database is missing %(count)s schema update(s) this version needs (%(files)s) — some features will not work until setup is run again. | تنقص قاعدة البيانات %(count)s من التحديثات التي يحتاجها هذا الإصدار (%(files)s) — لن تعمل بعض الميزات حتى يُشغَّل الإعداد مرة أخرى. |

## 5. Consignment write-off and return refusals (4)

Shown in English before (audit F1). Built from the reviewed consignment terms:
شطب (write off), الرف (the shelf), إعادة (return), and the existing
"لم يُجرد بعد — أجرِ جردًا" wording.

| # | English | Arabic (as shipped) |
|---|---|---|
| 1 | Only %(stock)s unit(s) on the shelf — can't write off %(quantity)s. | على الرف %(stock)s وحدة فقط — لا يمكن شطب %(quantity)s. |
| 2 | Only %(stock)s unit(s) on the shelf — can't return %(quantity)s. | على الرف %(stock)s وحدة فقط — لا يمكن إعادة %(quantity)s. |
| 3 | This item hasn't been through an inventory audit yet — run an audit before writing off stock. | هذا الصنف لم يُجرد بعد — أجرِ جردًا قبل شطب المخزون. |
| 4 | This item hasn't been through an inventory audit yet — run an audit before returning stock. | هذا الصنف لم يُجرد بعد — أجرِ جردًا قبل إعادة المخزون. |

## 6. The Time Zone setting (4)

A new setting chosen by the owner on 2026-09-25. The zone names themselves
(Asia/Baghdad, …) are IANA identifiers and stay in Latin script, like IQ/JO.

| # | English | Arabic (as shipped) |
|---|---|---|
| 1 | Not a valid time zone. | المنطقة الزمنية غير صالحة. |
| 2 | Time Zone | المنطقة الزمنية |
| 3 | Automatic — %(zone)s | تلقائي — %(zone)s |
| 4 | What "today" and every time in the app mean. Automatic follows the money setting (IQ: Asia/Baghdad, JO: Asia/Amman), or this computer until one is chosen. | ما يعنيه "اليوم" وكل وقت في التطبيق. الخيار التلقائي يتبع إعداد العملة (IQ: Asia/Baghdad، JO: Asia/Amman)، أو هذا الحاسوب إلى أن يُختار. |

## 7. Privilege refusals (2)

Audit S1 and S2 (2026-09-25): a role may no longer hand out, reach, or post
settings beyond its own permissions. Built from the reviewed terms صلاحية
(permission), دور (role), المدير (the Admin, as in "لا يمكن تعديل دور
المدير") and النسخ الاحتياطي (backups).

| # | English | Arabic (as shipped) |
|---|---|---|
| 1 | You can't give or reach access you don't hold yourself — ask an Admin. | لا يمكنك منح صلاحيات لا تملكها بنفسك أو الوصول إليها — اطلب ذلك من المدير. |
| 2 | Nothing was saved: your role can't change the backup and log-retention settings. | لم يُحفظ أي شيء: لا يملك دورك صلاحية تغيير إعدادات النسخ الاحتياطي ومدة الاحتفاظ بالسجلات. |

## 8. Date refusals (3)

Audit B1 (2026-09-25). #1 was shown in English before. #2 and #3 are new:
an audit sheet's expiry date is now checked instead of reaching the
database raw. They are built from the reviewed "التاريخ غير صالح — يتم عرض
تاريخ اليوم بدلًا منه" and the audit sheet's own "لم تُحفظ المسودة" / "لم
يتم تأكيد شيء", with تاريخ الانتهاء as in "أقرب تاريخ انتهاء".

| # | English | Arabic (as shipped) |
|---|---|---|
| 1 | That date wasn't valid — showing all dates instead. | التاريخ غير صالح — يتم عرض كل التواريخ بدلًا منه. |
| 2 | An expiry date isn't a valid date. The draft was not saved — please correct it. | أحد تواريخ الانتهاء غير صالح. لم تُحفظ المسودة — يرجى تصحيحه. |
| 3 | An expiry date isn't a valid date. Nothing was confirmed — please correct it. | أحد تواريخ الانتهاء غير صالح. لم يتم تأكيد شيء — يرجى تصحيحه. |

## 9. POS refusal for a deactivated item (1)

Audit B5 (2026-09-25). Built from دليل الأصناف (Inventory Catalog), إلغاء
التفعيل (Deactivate) and السلة (the cart).

| # | English | Arabic (as shipped) |
|---|---|---|
| 1 | %(name)s is no longer sold — it was deactivated in the catalogue. Remove it from the cart. | %(name)s لم يعد يُباع — تم إلغاء تفعيله في دليل الأصناف. أزِله من السلة. |

## 10. Edit conflicts (6)

Audit B4 (2026-09-25). #1–3 replace an English-only message. The record
names are the reviewed ones from "… غير موجودة" (الزيارة، فترة الإقامة الفندقية،
حالة الإقامة المرضية), and "أعد تحميل الصفحة" is the catalogue's wording for
"reload the page". "Their" is rendered as the masculine singular (تغييراته،
نسخته), which is the catalogue's usual default for an unnamed person. A
native speaker should confirm that it reads naturally.

| # | English | Arabic (as shipped) |
|---|---|---|
| 1 | Someone else saved this visit while you had it open, so your changes were not saved. Their changes are listed below. | حفظ شخص آخر هذه الزيارة أثناء فتحك لها، لذلك لم تُحفظ تغييراتك. تغييراته مدرجة أدناه. |
| 2 | Someone else saved this boarding stay while you had it open, so your changes were not saved. Their changes are listed below. | حفظ شخص آخر فترة الإقامة الفندقية هذه أثناء فتحك لها، لذلك لم تُحفظ تغييراتك. تغييراته مدرجة أدناه. |
| 3 | Someone else saved this inpatient case while you had it open, so your changes were not saved. Their changes are listed below. | حفظ شخص آخر حالة الإقامة المرضية هذه أثناء فتحك لها، لذلك لم تُحفظ تغييراتك. تغييراته مدرجة أدناه. |
| 4 | Saved by someone else since you opened this form: | ما حفظه شخص آخر منذ أن فتحت هذا النموذج: |
| 5 | Your version is still in the form. Reload the page to start again from theirs, or save yours over it: | نسختك ما زالت في النموذج. أعد تحميل الصفحة لتبدأ من نسخته، أو احفظ نسختك فوقها: |
| 6 | Save my version over their changes | احفظ نسختي فوق تغييراته |

## 11. Payment method refusal (1)

Audit B10 (2026-09-25): every payment now needs a valid method, not only
refunds. Built from the reviewed "اختر الطريقة التي صُرف بها هذا الاسترداد
فعليًا" and طريقة الدفع (Payment Method).

| # | English | Arabic (as shipped) |
|---|---|---|
| 1 | Pick how this was paid: %(methods)s. | اختر طريقة الدفع: %(methods)s. |

## 12. Refund date refusals (2)

Audit B16 (2026-09-25): a refund is dated between the day the money came in
and today. Built from الاسترداد (refund) as in the reviewed refund messages.

| # | English | Arabic (as shipped) |
|---|---|---|
| 1 | A refund can't be dated after today. | لا يمكن أن يكون تاريخ الاسترداد بعد اليوم. |
| 2 | A refund can't be dated before %(date)s, when what it pays back was recorded. | لا يمكن أن يكون تاريخ الاسترداد قبل %(date)s، وهو تاريخ تسجيل ما يُعاد دفعه. |

## 13. Audit sheet hint (1)

Audit B18 (2026-09-25): the "received since prior" column is pre-filled
from Consignment Receiving, and says so. Built from the reviewed
"استلام الأمانة" (Consignment Receiving).

| # | English | Arabic (as shipped) |
|---|---|---|
| 1 | Includes %(qty)s from Consignment Receiving | يشمل %(qty)s من استلام الأمانة |

## 14. The "restoring a backup" page (2)

Audit S3 (2026-09-25). `vcs/static/restoring.html` is shown to every workstation
while a backup is restored. It is a static file, not a template, because
rendering a template reads the clinic's language from a table that is being
reloaded. So it carries both languages, and **its Arabic is edited in that
file, not the catalogue**. Built from استعادة (restore) and نسخة احتياطية
(backup), as in the Settings page.

| # | English | Arabic (as shipped) |
|---|---|---|
| 1 | Restoring a backup | جارٍ استعادة نسخة احتياطية |
| 2 | The clinic's data is being restored from a backup. Nothing can be saved until it is finished. This page reloads by itself, and will be back where you were in a minute or two. | تُستعاد بيانات العيادة الآن من نسخة احتياطية، ولا يمكن حفظ أي شيء حتى تنتهي. ستُعاد تحميل هذه الصفحة تلقائيًا، وستعود إلى ما كنت عليه خلال دقيقة أو دقيقتين. |

## 15. Messages that were English-only (audit F1) (109)

Flash messages, JSON errors and the backup / restore / update / automatic-startup
results that were never wrapped for translation. Built from the reviewed terms:
نسخة احتياطية / استعادة / تحديث / إصدار, التشغيل التلقائي (as in "تشغيل
VetClinicSystem تلقائيًا"), الدور / موظف / المواعيد / "بحاجة إلى انتباه",
الصنف / المورد / الأمانة / الباركود. GitHub, VERSION, setup.py and file names stay
in Latin script. **Plural agreement** after a count ("%(n)s موعد") uses the
singular form throughout, as the catalogue already does ("%(orphaned)s موعد") —
a native speaker may prefer the counted forms.

| # | English | Arabic (as shipped) |
|---|---|---|
| 1 | "%(name)s" deleted. | تم حذف "%(name)s". |
| 2 | "%(name)s" role added. | تمت إضافة الدور "%(name)s". |
| 3 | "%(name)s" role saved. | تم حفظ الدور "%(name)s". |
| 4 | %(count)s staff member(s) moved to %(target)s · "%(role)s" deleted. | نُقل %(count)s موظف إلى %(target)s · وحُذف الدور "%(role)s". |
| 5 | %(field)s must be a valid date (YYYY-MM-DD). | يجب أن يكون %(field)s تاريخًا صالحًا (YYYY-MM-DD). |
| 6 | %(tag)s failed its health check and was never switched to: %(reason)s | فشل %(tag)s في فحص السلامة ولم يُحوَّل إليه: %(reason)s |
| 7 | %(tag)s failed to install or boot: %(error)s | تعذّر تثبيت %(tag)s أو تشغيله: %(error)s |
| 8 | %(tag)s's database changes failed to apply: %(error)s | تعذّر تطبيق تغييرات قاعدة البيانات الخاصة بـ %(tag)s: %(error)s |
| 9 | A backup, restore, or another update is already running — try again once it finishes. | هناك نسخ احتياطي أو استعادة أو تحديث آخر قيد التشغيل — حاول مرة أخرى بعد انتهائه. |
| 10 | A barcode already exists for this item. | يوجد باركود لهذا الصنف بالفعل. |
| 11 | A role named "%(name)s" already exists. | يوجد دور باسم "%(name)s" بالفعل. |
| 12 | Already on the latest version. | أنت على أحدث إصدار بالفعل. |
| 13 | Another backup, restore, or update is already running — try again once it finishes. | هناك نسخ احتياطي أو استعادة أو تحديث آخر قيد التشغيل — حاول مرة أخرى بعد انتهائه. |
| 14 | Appointment type must be one of: %(choices)s. | يجب أن يكون نوع الموعد أحد التالي: %(choices)s. |
| 15 | Automatic startup is already off. | التشغيل التلقائي متوقف بالفعل. |
| 16 | Automatic startup isn't supported on this operating system. | التشغيل التلقائي غير مدعوم على نظام التشغيل هذا. |
| 17 | Automatic startup turned off. | تم إيقاف التشغيل التلقائي. |
| 18 | Backup failed — update aborted, nothing was changed. | فشل النسخ الاحتياطي — أُلغي التحديث ولم يتغير شيء. |
| 19 | Backup failed: %(error)s | فشل النسخ الاحتياطي: %(error)s |
| 20 | Backup folder isn't writable: %(error)s | لا يمكن الكتابة في مجلد النسخ الاحتياطي: %(error)s |
| 21 | Backup saved to %(path)s | حُفظت النسخة الاحتياطية في %(path)s |
| 22 | Billing type must be one of: %(choices)s. | يجب أن يكون نوع الفوترة أحد التالي: %(choices)s. |
| 23 | Can't delete this distributor — it still has %(linked)s linked to it. Remove or reassign those first. | لا يمكن حذف هذا المورد — ما زالت مرتبطة به %(linked)s. أزِلها أو انقلها أولًا. |
| 24 | Can’t open that folder: %(error)s | تعذّر فتح هذا المجلد: %(error)s |
| 25 | Case status must be one of: %(choices)s. | يجب أن تكون حالة الزيارة أحد التالي: %(choices)s. |
| 26 | Category must be one of: %(choices)s. | يجب أن تكون الفئة أحد التالي: %(choices)s. |
| 27 | Choose a backup file to restore from. | اختر ملف نسخة احتياطية للاستعادة منه. |
| 28 | Choose a valid backup file to restore from. | اختر ملف نسخة احتياطية صالحًا للاستعادة منه. |
| 29 | Cost Price is required and must be a valid number to flag an item as Consignment. | سعر التكلفة مطلوب ويجب أن يكون رقمًا صالحًا لتحديد الصنف كأمانة. |
| 30 | Could not find this account's Startup folder (the APPDATA setting is missing). | تعذّر العثور على مجلد بدء التشغيل لهذا الحساب (إعداد APPDATA مفقود). |
| 31 | Could not find “Start VetClinicSystem.bat” at %(path)s — can't set up automatic startup. | تعذّر العثور على “Start VetClinicSystem.bat” في %(path)s — لا يمكن إعداد التشغيل التلقائي. |
| 32 | Could not find “Start VetClinicSystem.command” at %(path)s — can't set up automatic startup. | تعذّر العثور على “Start VetClinicSystem.command” في %(path)s — لا يمكن إعداد التشغيل التلقائي. |
| 33 | Could not register automatic startup: %(error)s | تعذّر تسجيل التشغيل التلقائي: %(error)s |
| 34 | Could not remove automatic startup: %(error)s | تعذّر إلغاء التشغيل التلقائي: %(error)s |
| 35 | Could not remove the startup task — it may need Administrator. %(error)s | تعذّر حذف مهمة بدء التشغيل — قد يتطلب ذلك صلاحيات المسؤول (Administrator). %(error)s |
| 36 | Could not set up automatic startup: %(error)s | تعذّر إعداد التشغيل التلقائي: %(error)s |
| 37 | Couldn't check for updates — GitHub could not be reached. | تعذّر التحقق من التحديثات — تعذّر الوصول إلى GitHub. |
| 38 | Couldn't download %(tag)s — update aborted, nothing was changed. | تعذّر تنزيل %(tag)s — أُلغي التحديث ولم يتغير شيء. |
| 39 | Couldn't reach GitHub — this computer appears to be offline. | تعذّر الوصول إلى GitHub — يبدو أن هذا الجهاز غير متصل بالإنترنت. |
| 40 | Couldn't remove the file from disk (%(error)s) — the attachment was not deleted. | تعذّر حذف الملف من القرص (%(error)s) — لم يُحذف المرفق. |
| 41 | Couldn't save the file to disk: %(error)s | تعذّر حفظ الملف على القرص: %(error)s |
| 42 | Couldn’t create that folder: %(error)s | تعذّر إنشاء هذا المجلد: %(error)s |
| 43 | Downloaded release failed validation: %(reason)s | فشل الإصدار الذي تم تنزيله في التحقق: %(reason)s |
| 44 | Downloaded release has no VERSION file. | الإصدار الذي تم تنزيله لا يحتوي على ملف VERSION. |
| 45 | Downloaded release is missing %(file)s. | الإصدار الذي تم تنزيله ينقصه %(file)s. |
| 46 | Enter a barcode. | أدخل باركودًا. |
| 47 | Enter a plain folder name (no slashes). | أدخل اسم مجلد بسيطًا (دون شرطات مائلة). |
| 48 | File uploaded. | تم رفع الملف. |
| 49 | GitHub has no published release to compare against, or the configured repository name is wrong. | لا يوجد على GitHub إصدار منشور للمقارنة به، أو أن اسم المستودع المُعَدّ غير صحيح. |
| 50 | GitHub rejected the access token for this install — it may have expired or been revoked. | رفض GitHub رمز الوصول الخاص بهذا التثبيت — ربما انتهت صلاحيته أو أُلغي. |
| 51 | GitHub returned an error (HTTP %(status)s) when asked for the latest release. | أعاد GitHub خطأ (HTTP %(status)s) عند طلب أحدث إصدار. |
| 52 | GitHub's hourly limit for this network has been reached — try again after %(time)s. Nothing is wrong with this computer or the internet connection. | بلغت هذه الشبكة الحد الأقصى لطلبات GitHub في الساعة — حاول مرة أخرى بعد %(time)s. لا توجد مشكلة في هذا الجهاز أو في الاتصال بالإنترنت. |
| 53 | GitHub's hourly limit for this network has been reached. Nothing is wrong with this computer or the internet connection. | بلغت هذه الشبكة الحد الأقصى لطلبات GitHub في الساعة. لا توجد مشكلة في هذا الجهاز أو في الاتصال بالإنترنت. |
| 54 | Heads up: %(n)s upcoming appointment(s) were booked against this person — they won't show on the Appointments grid anymore. Check Appointments for the "need attention" list to reschedule them. | تنبيه: %(n)s موعد قادم محجوز باسم هذا الشخص — لن يظهر في جدول المواعيد بعد الآن. راجع قائمة "بحاجة إلى انتباه" في المواعيد لإعادة جدولتها. |
| 55 | Heads up: %(total)s upcoming appointment(s) across %(staff)s staff member(s) just moved off a vet-eligible role won't show on the Appointments grid anymore. Check Appointments for the "need attention" list to reschedule them. | تنبيه: %(total)s موعد قادم لدى %(staff)s موظف نُقلوا للتو من دور مؤهل للطبيب البيطري لن تظهر في جدول المواعيد بعد الآن. راجع قائمة "بحاجة إلى انتباه" في المواعيد لإعادة جدولتها. |
| 56 | Heads up: %(total)s upcoming appointment(s) across %(staff)s staff member(s) on this role won't show on the Appointments grid anymore. Check Appointments for the "need attention" list to reschedule them. | تنبيه: %(total)s موعد قادم لدى %(staff)s موظف في هذا الدور لن تظهر في جدول المواعيد بعد الآن. راجع قائمة "بحاجة إلى انتباه" في المواعيد لإعادة جدولتها. |
| 57 | Heads up: changing the scheduling hours/slot length just made %(n)s upcoming appointment(s) stop matching a slot on the grid. They're still booked — check Appointments for the "need attention" list to reschedule them. | تنبيه: تغيير ساعات العمل أو مدة الموعد جعل %(n)s موعد قادم لا يطابق أي فترة في الجدول. ما زالت محجوزة — راجع قائمة "بحاجة إلى انتباه" في المواعيد لإعادة جدولتها. |
| 58 | Item deactivated. | تم إلغاء تفعيل الصنف. |
| 59 | Item reactivated. | تمت إعادة تفعيل الصنف. |
| 60 | Name is required. | الاسم مطلوب. |
| 61 | No backup folder configured yet — set one above, then Save Settings, before backing up. | لم يُحدَّد مجلد للنسخ الاحتياطي بعد — عيّن واحدًا أعلاه ثم احفظ الإعدادات قبل النسخ الاحتياطي. |
| 62 | No backup folder configured yet — set one on the Settings page. | لم يُحدَّد مجلد للنسخ الاحتياطي بعد — عيّن واحدًا من صفحة الإعدادات. |
| 63 | No backup folder is configured yet — set one on the Settings page. | لم يُحدَّد مجلد للنسخ الاحتياطي بعد — عيّن واحدًا من صفحة الإعدادات. |
| 64 | No previous release available to roll back to. | لا يوجد إصدار سابق متاح للرجوع إليه. |
| 65 | No sale with that ID. | لا توجد عملية بيع بهذا الرقم. |
| 66 | Only PDF and JPG/JPEG files are allowed. | يُسمح فقط بملفات PDF وJPG/JPEG. |
| 67 | Only letters, numbers, spaces, and . - _ are allowed. | يُسمح فقط بالأحرف والأرقام والمسافات و . - _ |
| 68 | Password can't contain the username. | لا يمكن أن تحتوي كلمة المرور على اسم المستخدم. |
| 69 | Password must be at least %(n)s characters. | يجب ألا تقل كلمة المرور عن %(n)s حرفًا. |
| 70 | Pick a distributor to flag this item as Consignment. | اختر موردًا لتحديد هذا الصنف كأمانة. |
| 71 | Resource type must be one of: %(choices)s. | يجب أن يكون نوع المورد المحجوز أحد التالي: %(choices)s. |
| 72 | Restore failed: %(error)s | فشلت الاستعادة: %(error)s |
| 73 | Restore failed: %(error)s — nothing was changed; the database is as it was before the restore started. | فشلت الاستعادة: %(error)s — لم يتغير شيء؛ قاعدة البيانات كما كانت قبل بدء الاستعادة. |
| 74 | Restore succeeded, but bringing the restored database up to this app version's schema failed: %(error)s. The data is restored, but some newer features may not work until this is resolved. | نجحت الاستعادة، لكن تعذّر تحديث بنية قاعدة البيانات المستعادة لتوافق هذا الإصدار: %(error)s. البيانات مستعادة، لكن قد لا تعمل بعض الميزات الأحدث حتى تُحل هذه المشكلة. |
| 75 | Restored from %(path)s | تمت الاستعادة من %(path)s |
| 76 | Restoring database (%(done)s/%(total)s objects) | جارٍ استعادة قاعدة البيانات (%(done)s/%(total)s عنصر) |
| 77 | Rolling back to %(tag)s. This page will reconnect in a few seconds. | جارٍ الرجوع إلى %(tag)s. ستُعاد هذه الصفحة الاتصال خلال ثوانٍ. |
| 78 | That barcode is already used by "%(name)s". | هذا الباركود مستخدم بالفعل للصنف "%(name)s". |
| 79 | That barcode was just claimed by another item — try again. | استُخدم هذا الباركود للتو لصنف آخر — حاول مرة أخرى. |
| 80 | That code was just claimed by another item — try again. | استُخدم هذا الرمز للتو لصنف آخر — حاول مرة أخرى. |
| 81 | That doesn't look like a VetClinicSystem backup file (expected a %(suffix)s file). | لا يبدو هذا ملف نسخة احتياطية من VetClinicSystem (المتوقع ملف %(suffix)s). |
| 82 | That file isn't in this app's own backup history — restore is only allowed for backups VetClinicSystem itself created (see Recent Backups on the Settings page). | هذا الملف ليس ضمن سجل النسخ الاحتياطية لهذا التطبيق — لا يُسمح بالاستعادة إلا من نسخ أنشأها VetClinicSystem نفسه (انظر النسخ الاحتياطية الأخيرة في صفحة الإعدادات). |
| 83 | That file isn't inside the configured backup folder. | هذا الملف ليس داخل مجلد النسخ الاحتياطي المُعَدّ. |
| 84 | That folder is outside the areas this app can browse (%(where)s). | هذا المجلد خارج المواقع التي يمكن لهذا التطبيق تصفحها (%(where)s). |
| 85 | That inventory item is already linked to %(row)s — an item can only be linked from one active row at a time. | هذا الصنف مرتبط بالفعل بـ %(row)s — يمكن ربط الصنف من صف نشط واحد فقط في كل مرة. |
| 86 | That parent folder no longer exists. | المجلد الأصلي لم يعد موجودًا. |
| 87 | That password is one of the most commonly guessed ones — please choose another. | كلمة المرور هذه من أكثر كلمات المرور تخمينًا — يرجى اختيار غيرها. |
| 88 | That's too long to be a real barcode — check what you entered. | هذا أطول من أن يكون باركودًا حقيقيًا — تحقق مما أدخلته. |
| 89 | The backup folder is gone. Backups were being written there, so this looks like a drive or synced folder that is no longer connected — reconnect it, or set a new folder on the Settings page. Nothing was written, deliberately: a backup saved somewhere unexpected is worse than one that failed loudly. | مجلد النسخ الاحتياطي غير موجود. كانت النسخ الاحتياطية تُحفظ فيه، لذا يبدو أنه قرص أو مجلد متزامن لم يعد متصلًا — أعد توصيله، أو عيّن مجلدًا جديدًا من صفحة الإعدادات. لم يُكتب شيء عن قصد: نسخة احتياطية محفوظة في مكان غير متوقع أسوأ من نسخة فشلت بشكل واضح. |
| 90 | The new release didn't pass its health check within %(seconds)s seconds. | لم يجتز الإصدار الجديد فحص السلامة خلال %(seconds)s ثانية. |
| 91 | The new release's process exited before it became healthy. | توقفت عملية الإصدار الجديد قبل أن تصبح سليمة. |
| 92 | The system is busy right now — try again in a moment. | النظام مشغول الآن — حاول مرة أخرى بعد قليل. |
| 93 | This file's contents don't match a PDF or JPEG (it may have been renamed). | محتوى هذا الملف لا يطابق ملف PDF أو JPEG (ربما تمت إعادة تسميته). |
| 94 | Updated to %(tag)s. Restarting now — this page will reconnect in a few seconds. | تم التحديث إلى %(tag)s. جارٍ إعادة التشغيل الآن — ستُعاد هذه الصفحة الاتصال خلال ثوانٍ. |
| 95 | Updates aren't set up on this install yet — see setup.py --enable-updates. | التحديثات غير مُعَدّة على هذا التثبيت بعد — راجع setup.py --enable-updates. |
| 96 | Updates aren't set up on this install yet. | التحديثات غير مُعَدّة على هذا التثبيت بعد. |
| 97 | VERSION file says %(version)s, but the release tag is %(tag)s. | ملف VERSION يذكر %(version)s، لكن وسم الإصدار هو %(tag)s. |
| 98 | VetClinicSystem will now start automatically when this computer starts up, even before anyone signs in. | سيعمل VetClinicSystem الآن تلقائيًا عند بدء تشغيل هذا الجهاز، حتى قبل أن يسجّل أي شخص الدخول. |
| 99 | VetClinicSystem will now start automatically when you log in. | سيعمل VetClinicSystem الآن تلقائيًا عند تسجيل دخولك. |
| 100 | VetClinicSystem will now start automatically when you sign in. It could not be set to start at boot as well, which needs Administrator — so if this computer restarts overnight, the app won't run (and no backup will be taken) until someone signs in. To fix that, run this app as an administrator once and turn this setting on again. | سيعمل VetClinicSystem الآن تلقائيًا عند تسجيل دخولك. تعذّر ضبطه ليعمل عند إقلاع الجهاز أيضًا، إذ يتطلب ذلك صلاحيات المسؤول (Administrator) — لذا إذا أُعيد تشغيل هذا الجهاز ليلًا فلن يعمل التطبيق (ولن تُؤخذ نسخة احتياطية) حتى يسجّل أحد الدخول. لإصلاح ذلك، شغّل هذا التطبيق كمسؤول مرة واحدة ثم فعّل هذا الإعداد مرة أخرى. |
| 101 | consignment receipt(s) | عمليات استلام أمانة |
| 102 | consignment return(s) | مرتجعات أمانة |
| 103 | consignment settlement(s) | تسويات أمانة |
| 104 | consignment shrinkage entry/entries | قيود هالك أمانة |
| 105 | distributor bill(s) | فواتير مورد |
| 106 | inventory item(s) | أصناف مخزون |
| 107 | launcher not found | لم يُعثر على ملف التشغيل |
| 108 | the backup folder | مجلد النسخ الاحتياطي |
| 109 | “%(path)s” isn’t a folder VetClinicSystem can see on this computer. | “%(path)s” ليس مجلدًا يمكن لـ VetClinicSystem رؤيته على هذا الجهاز. |

## 16. Text shown by the browser scripts (audit F2) (33)

The unsaved-changes dialogs, upload progress, job progress, the phone check,
the toast's close button, and a few inline page scripts. Reuses
حفظ / تجاهل / رفع / جارٍ …, المالك, الشريحة, and the catalogue's
"%(n)s عنصر" singular-after-count style.

| # | English | Arabic (as shipped) |
|---|---|---|
| 1 | %(file)s is %(size)s — that's over the %(max)s MB limit. Please choose a smaller file. | حجم %(file)s هو %(size)s — وهذا يتجاوز الحد الأقصى %(max)s ميجابايت. يرجى اختيار ملف أصغر. |
| 2 | %(names)s, and %(n)s more | %(names)s، و%(n)s غيرها |
| 3 | Backup | النسخ الاحتياطي |
| 4 | Barcode %(code)s created. | تم إنشاء الباركود %(code)s. |
| 5 | Copied | تم النسخ |
| 6 | Couldn't reach the server — please check your connection and try again. | تعذّر الوصول إلى الخادم — يرجى التحقق من الاتصال والمحاولة مرة أخرى. |
| 7 | Delete %(role)s? | حذف %(role)s؟ |
| 8 | Discard Changes | تجاهل التغييرات |
| 9 | Dismiss | إغلاق |
| 10 | Keep Editing | متابعة التعديل |
| 11 | Loading | جارٍ التحميل |
| 12 | Lost track of this job — the server may have restarted. Try again. | فُقد تتبّع هذه المهمة — ربما أُعيد تشغيل الخادم. حاول مرة أخرى. |
| 13 | Max file size: %(max)s MB. | الحد الأقصى لحجم الملف: %(max)s ميجابايت. |
| 14 | Microchip: | الشريحة: |
| 15 | No backup files here. | لا توجد ملفات نسخ احتياطي هنا. |
| 16 | No subfolders here. | لا توجد مجلدات فرعية هنا. |
| 17 | Owner: | المالك: |
| 18 | Restore | الاستعادة |
| 19 | Save & Continue | حفظ ومتابعة |
| 20 | Save Changes (%(n)s) | حفظ التغييرات (%(n)s) |
| 21 | Saving… | جارٍ الحفظ… |
| 22 | Selected: %(file)s (%(size)s). Max %(max)s MB. | المحدد: %(file)s (%(size)s). الحد الأقصى %(max)s ميجابايت. |
| 23 | Some changes couldn't be saved — please check your connection and try again. The items that failed are still highlighted. | تعذّر حفظ بعض التغييرات — يرجى التحقق من الاتصال والمحاولة مرة أخرى. العناصر التي فشل حفظها ما زالت مميّزة. |
| 24 | Some changes couldn't be saved — please check your connection and try again. You're still on this page and nothing else has been lost. | تعذّر حفظ بعض التغييرات — يرجى التحقق من الاتصال والمحاولة مرة أخرى. ما زلت على هذه الصفحة ولم يُفقد أي شيء آخر. |
| 25 | Something went wrong. | حدث خطأ ما. |
| 26 | Unsaved Changes | تغييرات غير محفوظة |
| 27 | Upload failed (server returned %(status)s). Please try again. | فشل الرفع (أعاد الخادم %(status)s). يرجى المحاولة مرة أخرى. |
| 28 | Upload failed — check your connection and try again. | فشل الرفع — تحقق من الاتصال وحاول مرة أخرى. |
| 29 | Uploading %(file)s… | جارٍ رفع %(file)s… |
| 30 | Working | قيد التنفيذ |
| 31 | You have unsaved changes on %(n)s items (%(names)s). Save them before leaving, or discard them? | لديك تغييرات غير محفوظة في %(n)s عنصر (%(names)s). هل تريد حفظها قبل المغادرة أم تجاهلها؟ |
| 32 | You have unsaved changes on 1 item (%(names)s). Save them before leaving, or discard them? | لديك تغييرات غير محفوظة في عنصر واحد (%(names)s). هل تريد حفظها قبل المغادرة أم تجاهلها؟ |
| 33 | You have unsaved changes on this page. Leave without saving? | لديك تغييرات غير محفوظة في هذه الصفحة. هل تريد المغادرة دون حفظ؟ |

## 17. Parity ports (4)

Audit P7 (the consignment shortfall on confirming an audit) and P20 (the
attachment delete button). Built from الأمانة / الهالك / المستحق للمورد and
the reviewed "حذف".

| # | English | Arabic (as shipped) |
|---|---|---|
| 1 | %(name)s (%(distributor)s): short %(quantity)s | %(name)s (%(distributor)s): ناقص %(quantity)s |
| 2 | Consignment item(s) came in under the expected count — %(items)s. If this wasn't just a counting difference, log it as shrinkage from Consignment > Shrinkage so it's reflected in what's owed. | جاء عدّ بعض أصناف الأمانة أقل من المتوقع — %(items)s. إن لم يكن ذلك مجرد فرق في العدّ، فسجّله كهالك من الأمانة > الهالك ليظهر في المستحق للمورد. |
| 3 | Delete %(name)s | حذف %(name)s |
| 4 | Delete %(name)s? This removes the file permanently, including the copy on disk. | حذف %(name)s؟ سيؤدي ذلك إلى حذف الملف نهائيًا، بما في ذلك النسخة المحفوظة على القرص. |

## 18. An item with no sale price (1)

Visit and inpatient billing now skip an item whose Price List row has no sale
price, as the billing search already does (restructure R4). Built from the
shipped "بعض الأصناف المختارة … وتم تجاهلها" and "ليس له سعر بيع محدد في
قائمة الأسعار".

| # | English | Arabic (as shipped) |
|---|---|---|
| 1 | Some selected items have no sale price in the Price List and were skipped. | بعض الأصناف المختارة ليس لها سعر بيع محدد في قائمة الأسعار وتم تجاهلها. |
