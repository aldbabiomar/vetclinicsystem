# -*- coding: utf-8 -*-
"""Arabic translations, batch 18 — the computed status badges, and the five
help sentences that were re-joined into one msgid each.

The five long ones are not new text. They were each split across three to six
msgids by a mid-sentence `<strong>`/`<em>`/`<code>`, which forced the Arabic to
follow English word order around the markup — visible on the Settings page,
where the tail of the restore warning began with the same word the `<em>`
before it contained, so it read "بعد بعد". Re-joined, the emphasised phrase is
a placeholder and Arabic puts it where Arabic puts it.
"""

BATCH = {
    # logic.inventory_status() — computed badges, rendered through |tr
    "Never audited": "لم يُجرد قط",
    "OVERDUE": "متأخر",
    "OK": "سليم",
    "EXPIRED": "منتهي الصلاحية",
    "EXPIRING SOON": "قارب على الانتهاء",

    "No discharged cases with a balance due.": "لا توجد حالات مخرَجة عليها رصيد مستحق.",
    "No inpatient cases.": "لا توجد حالات تنويم.",

    "Removes a revenue amount only — no stock is touched. Enter %(exactly_one)s of Visit "
    "ID, Inpatient Case ID or Boarding ID: the refund reverses that specific record, and "
    "the amount is capped at what is still refundable against it. A goodwill refund with "
    "no record behind it belongs in Cash Register instead.":
        "يزيل مبلغ إيراد فقط — دون المساس بالمخزون. أدخل %(exactly_one)s من رقم الزيارة أو "
        "رقم حالة التنويم أو رقم الإيواء: يعكس الاسترداد ذلك السجل تحديدًا، والمبلغ محدود "
        "بما تبقّى قابلًا للاسترداد عليه. أما الاسترداد كبادرة حسن نية دون سجل خلفه فمكانه "
        "صندوق النقد.",

    "Each row is the group of clients whose %(first_visit)s fell in that month. Each "
    "column is how many months later. The cell is the %% of that group still coming back. "
    "Admin only.":
        "كل صف هو مجموعة العملاء الذين وقعت %(first_visit)s في ذلك الشهر. وكل عمود هو عدد "
        "الأشهر اللاحقة. والخلية هي %% من تلك المجموعة ممن ما زالوا يعودون. للمديرين فقط.",

    "Off unless you fill this in. When set, this clinic sends a short daily status ping — "
    "counts and statuses only, never patient, owner or staff details, and never any "
    "amounts. The point is the %(missing)s ping: if this machine stops sending, whoever "
    "maintains the system gets told, which is the one thing the app cannot report while "
    "it is switched off.":
        "معطّل ما لم تملأ هذا الحقل. عند ضبطه، ترسل هذه العيادة نبضة حالة يومية قصيرة — "
        "أعدادًا وحالات فقط، دون أي تفاصيل عن الحيوانات أو المالكين أو الموظفين، ودون أي "
        "مبالغ. والمقصود هو النبضة %(missing)s: فإن توقف هذا الجهاز عن الإرسال، يُبلَّغ "
        "المسؤول عن صيانة النظام — وهو الشيء الوحيد الذي لا يستطيع التطبيق الإبلاغ عنه "
        "وهو مطفأ.",

    "Must start with %(scheme)s. Use a different URL for each clinic, so an alert can say "
    "which one went quiet. %(warning)s — anyone who has it can send a fake ping and stop "
    "a real alert from ever reaching you.":
        "يجب أن يبدأ بـ %(scheme)s. استخدم رابطًا مختلفًا لكل عيادة، حتى يتمكن التنبيه من "
        "تحديد أيها توقف. %(warning)s — فمن يحصل عليه يستطيع إرسال نبضة مزيفة ومنع تنبيه "
        "حقيقي من الوصول إليك.",

    "missing": "الغائبة",
    "after": "بعد",
    "all": "كل",
    "exactly one": "واحدًا فقط",
    "first-ever visit": "زيارتهم الأولى على الإطلاق",
    "Treat it like a password": "تعامل معه كأنه كلمة مرور",
}

# The restore warning carries the app's own name, so the msgid differs per app.
for _app, _ar in (("IQ", "IQ"), ("JO", "JO")):
    BATCH[
        f"Replaces %(all)s current data in VetClinicSystem {_app} with the contents of a "
        f"backup file. This can't be undone — take a fresh backup first if you're not "
        f"sure. Uploaded files (X-rays, lab results) aren't part of the backup itself and "
        f"are unaffected by a restore, but any that were attached %(after)s the backup "
        f"being restored was taken will need reconnecting — run %(command)s from the app "
        f"folder afterward to find and relink them safely."
    ] = (
        f"يستبدل %(all)s البيانات الحالية في VetClinicSystem {_ar} بمحتويات ملف نسخة "
        f"احتياطية. لا يمكن التراجع عن ذلك — خذ نسخة احتياطية جديدة أولًا إن لم تكن "
        f"متأكدًا. الملفات المرفوعة (الأشعة ونتائج المختبر) ليست جزءًا من النسخة الاحتياطية "
        f"نفسها ولا تتأثر بالاستعادة، لكن ما أُرفق منها %(after)s أخذ النسخة التي تُستعاد "
        f"سيحتاج إلى إعادة ربط — شغّل %(command)s من مجلد التطبيق بعد ذلك للعثور عليها "
        f"وإعادة ربطها بأمان."
    )
