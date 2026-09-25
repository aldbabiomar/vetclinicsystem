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

To change one: edit its `msgstr` in `translations/ar/LC_MESSAGES/messages.po`,
run `pybabel compile -d translations`, and delete its row here. When this file
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
