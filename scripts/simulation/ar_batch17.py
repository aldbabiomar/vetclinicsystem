# -*- coding: utf-8 -*-
"""Arabic translations, batch 17 — the same messages as batch 16, re-keyed.

Nothing here is a new string. These are the twenty whose placeholder had to
change from `%(name)s` to `{name}` because JavaScript, not Jinja, fills it:
Jinja's gettext runs `rv % variables` unconditionally, so a `%(name)s` the
call does not supply is a KeyError while the page renders. Changing the
placeholder changes the msgid, so the translation had to be re-keyed with it.

`%(currency_label)s` stays `%`-style in the mixed ones — Jinja does fill that
one, in the same call.
"""

BATCH = {
    "1 staff member currently assigned to {role}.":
        "موظف واحد مُسنَد حاليًا إلى {role}.",
    "{count} staff members currently assigned to {role}.":
        "{count} موظفين مُسنَدين حاليًا إلى {role}.",
    "Move & Delete": "النقل والحذف",
    "Moving & deleting…": "جارٍ النقل والحذف…",
    "Cancel {name}'s appointment?": "إلغاء موعد {name}؟",
    "{counted} of {total} items have a Stock Counted value entered.":
        "أُدخلت قيمة المخزون المعدود لـ {counted} من أصل {total} صنفًا.",
    "{missing} item(s) have no Stock Counted value and will be skipped (kept unchanged).":
        "{missing} صنفًا بلا قيمة مخزون معدود وسيتم تخطيها (تبقى دون تغيير).",
    "{negative} item(s) have a negative Stock Counted value — please check before confirming.":
        "{negative} صنفًا بقيمة مخزون معدود سالبة — يرجى التحقق قبل التأكيد.",
    "{zero} item(s) are counted as 0 in stock — please double-check these.":
        "{zero} صنفًا معدود بمخزون صفر — يرجى التأكد منها مرة أخرى.",
    "{name} has no sale price set in the Price List.":
        "{name} ليس له سعر بيع محدد في قائمة الأسعار.",
    "Manage Barcode — {name}": "إدارة الباركود — {name}",
    "Account locked — try again in {m}m {s}s.":
        "الحساب مقفل — حاول مرة أخرى بعد {m} د {s} ث.",
    "Only {stock} in stock.": "المتوفر في المخزون {stock} فقط.",
    "Cash received is {amount} %(currency_label)s short of the total.":
        "النقد المستلم أقل من الإجمالي بمقدار {amount} %(currency_label)s.",
    "(exact: {exact} %(currency_label)s — {rounding} %(currency_label)s rounding, "
    "absorbed by clinic)":
        "(بالضبط: {exact} %(currency_label)s — {rounding} %(currency_label)s تقريب، "
        "تتحمله العيادة)",
    "This sale had a {cleanup} %(currency_label)s Clean Up applied — total refunds "
    "against it can't exceed what was actually collected ({total} %(currency_label)s).":
        "طُبِّق على عملية البيع هذه إعفاء عن الفئات القليلة بمقدار {cleanup} "
        "%(currency_label)s — لا يمكن أن تتجاوز المرتجعات عليها ما حُصِّل فعليًا "
        "({total} %(currency_label)s).",
    "Showing saved values for {month}. Saving will overwrite them.":
        "تُعرض القيم المحفوظة لشهر {month}. الحفظ سيستبدلها.",
    "No operating costs saved yet for {month}.":
        "لم تُحفظ تكاليف تشغيلية بعد لشهر {month}.",
    "{job} failed to start.": "تعذّر بدء {job}.",
    "{message}. Please log in again.": "{message}. يرجى تسجيل الدخول مرة أخرى.",
}
