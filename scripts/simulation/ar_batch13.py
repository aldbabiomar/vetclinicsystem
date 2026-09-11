# -*- coding: utf-8 -*-
"""Arabic translations, batch 13 — the last 36: insights commentary, barcode
and price-list help, refunds guidance, retention explanation, and the Settings
prose (monitoring, backups, restore, updates, autostart).

Several are sentence FRAGMENTS: the surrounding template wraps a <strong> or
<code> mid-sentence, so the prose arrives in pieces. They are translated as
pieces on purpose — joining them would require restructuring the markup, and
the fragments still read correctly in order once rendered.
"""

_APP = {}
for _en, _ar in (("VetClinicSystem IQ", "VetClinicSystem IQ"),
                 ("VetClinicSystem JO", "VetClinicSystem JO")):
    _APP.update({
        f"Every item has at most one barcode — either a real one scanned or typed in from "
        f"its own packaging, or one {_en} creates for you to print. Never both at once: "
        f"setting one up below turns off the other option until you remove it.":
            f"لكل صنف باركود واحد على الأكثر — إما باركود حقيقي يُمسح أو يُكتب من عبوته، أو "
            f"باركود ينشئه {_en} لتطبعه. لا الاثنان معًا أبدًا: إعداد أحدهما أدناه يعطّل الخيار "
            f"الآخر حتى تزيله.",
        f"No barcode on the packaging? {_en} can create one and print a label to stick on the item.":
            f"لا يوجد باركود على العبوة؟ يمكن لـ {_en} إنشاء واحد وطباعة ملصق يُلصق على الصنف.",
        f"current data in {_en} with the contents of a backup file. This can't be undone — "
        f"take a fresh backup first if you're not sure. Uploaded files (X-rays, lab results) "
        f"aren't part of the backup itself and are unaffected by a restore, but any that were attached":
            f"البيانات الحالية في {_en} بمحتويات ملف النسخة الاحتياطية. لا يمكن التراجع عن ذلك — "
            f"خذ نسخة احتياطية جديدة أولًا إن لم تكن متأكدًا. الملفات المرفوعة (الأشعة ونتائج "
            f"المختبر) ليست جزءًا من النسخة الاحتياطية ولا تتأثر بالاستعادة، لكن أي ملفات أُرفقت",
        f"Not available on this operating system — start {_en} manually using the launcher.":
            f"غير متاح على نظام التشغيل هذا — شغّل {_en} يدويًا باستخدام المشغّل.",
        f"Browsing this computer's folders — the one running {_en}, since that's where "
        f"backups are actually read and written.":
            f"تصفح مجلدات هذا الجهاز — الجهاز الذي يشغّل {_en}، لأنه المكان الذي تُقرأ منه "
            f"النسخ الاحتياطية وتُكتب إليه فعليًا.",
    })

BATCH = {
    'Last 30 days\' Cash Register audit status. "Not Audited" means nobody closed out that '
    'day at all — on its own that\'s a documentation gap, not proof of a problem, but a '
    'pattern of skipped audits (or repeated Deficits) is worth looking into.':
        'حالة جرد الصندوق لآخر ٣٠ يومًا. "لم يُجرد" تعني أن أحدًا لم يغلق ذلك اليوم إطلاقًا — '
        'وهذا بحد ذاته ثغرة توثيق لا دليل على وجود مشكلة، لكن تكرار تخطي الجرد (أو تكرار '
        'العجز) يستحق الفحص.',

    "Highlighted rows: this Retail item has no matching entry in the Price List — check "
    "Price List's Linked Inventory Item.":
        "الصفوف المميزة: لا يوجد لهذا الصنف مدخل مطابق في قائمة الأسعار — تحقق من الصنف "
        "المرتبط في قائمة الأسعار.",

    "Retail data inconsistency: no active Retail Price List item is linked to this inventory item.":
        "تعارض في بيانات التجزئة: لا يوجد صنف تجزئة نشط في قائمة الأسعار مرتبط بهذا الصنف.",

    "Click into the box and type, or just scan the barcode already printed on this item's "
    "packaging — a scanner types it in for you.":
        "اضغط داخل المربع واكتب، أو امسح الباركود المطبوع أصلًا على عبوة الصنف — الماسح "
        "سيكتبه نيابة عنك.",

    "Every item with a VetClinicSystem-created barcode. Set how many labels each one needs, "
    "remove any you don't want on this run, then print them all together.":
        "كل صنف له باركود أنشأه VetClinicSystem. حدد عدد الملصقات التي يحتاجها كل صنف، "
        "وأزل ما لا تريده في هذه الطباعة، ثم اطبعها جميعًا معًا.",

    "Auto-calculated from audit history. Read-only — log a new count in Audit history.":
        "محسوب تلقائيًا من سجل الجرد. للقراءة فقط — سجّل عدًا جديدًا من سجل الجرد.",

    "Highlighted rows: Retail item doesn't match an active Retail item in Inventory Catalog "
    "— check the linked item.":
        "الصفوف المميزة: صنف التجزئة لا يطابق صنف تجزئة نشطًا في دليل الأصناف — "
        "تحقق من الصنف المرتبط.",

    "Checked = a discount can be applied to a bill that includes this item. Unchecked = it "
    "blocks any discount on that bill.":
        "محدد = يمكن تطبيق خصم على فاتورة تتضمن هذا الصنف. غير محدد = يمنع أي خصم على تلك الفاتورة.",

    "Retail data inconsistency: this item's Linked Inventory Item doesn't match an active "
    "Retail item in Inventory Catalog.":
        "تعارض في بيانات التجزئة: الصنف المرتبط بهذا السطر لا يطابق صنف تجزئة نشطًا في دليل الأصناف.",

    "Refund a retail sale (restores stock, optional) or reduce revenue for a service. Both "
    "remove the amount from Monthly & Yearly P&L, in the month the refund is processed.":
        "استرد عملية بيع تجزئة (مع إعادة المخزون اختياريًا) أو اخفض إيراد خدمة. كلاهما يزيل "
        "المبلغ من الأرباح والخسائر الشهرية والسنوية، في شهر تنفيذ الاسترداد.",

    'Look up the sale being refunded by its Sale ID (shown on the receipt), then choose '
    'which items and how many to refund — priced at what was actually charged, never '
    'today\'s price. Stock is only put back if you check "Return to stock".':
        'ابحث عن عملية البيع المراد استردادها برقمها (الظاهر على الإيصال)، ثم اختر الأصناف '
        'وعددها — مسعّرة بما حُصِّل فعليًا، لا بسعر اليوم. ولا يُعاد المخزون إلا إذا حددت '
        '"إعادة إلى المخزون".',

    "of Visit ID, Inpatient Case ID or Boarding ID: the refund reverses that specific "
    "record, and the amount is capped at what is still refundable against it. A goodwill "
    "refund with no record behind it belongs in Cash Register instead.":
        "من رقم الزيارة أو رقم حالة التنويم أو رقم الإيواء: يعكس الاسترداد ذلك السجل تحديدًا، "
        "والمبلغ محدود بما تبقى قابلًا للاسترداد عليه. أما الاسترداد كبادرة حسن نية دون سجل "
        "خلفه فمكانه الصندوق.",

    "Force a full recalculation of every month, in case anything ever looks out of sync":
        "فرض إعادة حساب كاملة لكل شهر، تحسبًا لظهور أي تعارض في الأرقام",

    "Same figures as Monthly P&L, rolled up by year. %(total_count)s year(s) shown.":
        "الأرقام نفسها الواردة في الأرباح والخسائر الشهرية، مجمّعة سنويًا. المعروض %(total_count)s سنة.",

    "fell in that month. Each column is how many months later. The cell is the %% of that "
    "group still coming back. Admin only.":
        "وقعت في ذلك الشهر. كل عمود يمثل عدد الأشهر اللاحقة. والخلية هي نسبة من تلك المجموعة "
        "الذين ما زالوا يعودون. للإدارة فقط.",

    "Not enough visit history yet to build a cohort grid — this fills in automatically as "
    "patients return for follow-up visits.":
        "لا يوجد سجل زيارات كافٍ بعد لبناء جدول المجموعات — يمتلئ تلقائيًا مع عودة المرضى "
        "لزيارات المتابعة.",

    'Reading down a column shows whether retention at that stage is improving over time. '
    'Reading across a row shows how fast that group drops off. "—" means that much time '
    'hasn\'t passed yet for that cohort.':
        'قراءة العمود من أعلى إلى أسفل تُظهر ما إذا كان الولاء في تلك المرحلة يتحسن مع الوقت. '
        'وقراءة الصف أفقيًا تُظهر سرعة تراجع تلك المجموعة. و"—" تعني أن تلك المدة لم تمضِ بعد '
        'على تلك المجموعة.',

    "Clinic info, inventory alert thresholds, appointment hours, and the automatic backup "
    "folder. Staff on the clinic network can reach this app at":
        "معلومات العيادة، وحدود تنبيهات المخزون، وساعات المواعيد، ومجلد النسخ الاحتياطي "
        "التلقائي. يمكن للموظفين على شبكة العيادة الوصول إلى التطبيق عبر",

    "Once a day, shortly after the nightly backup, this app checks itself — that backups "
    "are running and restorable, that the backup folder is writable, and that the disk "
    "isn't full — and shows a warning on the Dashboard if something needs attention.":
        "مرة يوميًا، بعد النسخ الاحتياطي الليلي بقليل، يفحص التطبيق نفسه — أن النسخ الاحتياطي "
        "يعمل وقابل للاستعادة، وأن مجلد النسخ قابل للكتابة، وأن القرص ليس ممتلئًا — ويعرض "
        "تحذيرًا على لوحة التحكم إذا احتاج شيء إلى انتباه.",

    "Off unless you fill this in. When set, this clinic sends a short daily status ping — "
    "counts and statuses only, never patient, owner or staff details, and never any "
    "amounts. The point is the":
        "معطّل ما لم تملأ هذا الحقل. عند ضبطه، ترسل هذه العيادة إشارة حالة يومية قصيرة — "
        "أعداد وحالات فقط، دون أي بيانات عن المرضى أو الملاك أو الموظفين، ودون أي مبالغ. "
        "والمقصود هو",

    "ping: if this machine stops sending, whoever maintains the system gets told, which is "
    "the one thing the app cannot report while it is switched off.":
        "الإشارة: إذا توقف هذا الجهاز عن الإرسال، يُبلَّغ من يتولى صيانة النظام، وهو الشيء "
        "الوحيد الذي لا يستطيع التطبيق الإبلاغ عنه وهو متوقف.",

    ". Use a different URL for each clinic, so an alert can say which one went quiet.":
        ". استخدم رابطًا مختلفًا لكل عيادة، ليتمكن التنبيه من تحديد أي عيادة توقفت.",

    "— anyone who has it can send a fake ping and stop a real alert from ever reaching you.":
        "— أي شخص يملكه يستطيع إرسال إشارة زائفة ومنع تنبيه حقيقي من الوصول إليك.",

    "Included in every ping so one monitoring account can watch several clinics.":
        "مضمّن في كل إشارة ليتمكن حساب مراقبة واحد من متابعة عدة عيادات.",

    "The backup history and the restore that reads it, beside the folder they use.":
        "سجل النسخ الاحتياطي والاستعادة التي تقرأ منه، إلى جانب المجلد الذي يستخدمانه.",

    "A restore may not have completed — the app was stopped or crashed partway through the "
    "last one. Check the database carefully before continuing to use the app.":
        "قد تكون عملية استعادة لم تكتمل — توقف التطبيق أو انهار في منتصف آخر عملية. "
        "افحص قاعدة البيانات بعناية قبل متابعة استخدام التطبيق.",

    "the backup being restored was taken will need reconnecting — run":
        "بعد أخذ النسخة التي تُستعاد ستحتاج إلى إعادة ربط — شغّل",

    "from the app folder afterward to find and relink them safely.":
        "من مجلد التطبيق بعد ذلك للعثور عليها وإعادة ربطها بأمان.",

    "Automatic updates aren't set up on this install yet. An administrator can enable them "
    "by running":
        "التحديثات التلقائية غير مُفعّلة على هذا التثبيت بعد. يمكن للمدير تفعيلها بتشغيل",

    "On shutdown or restart, the app takes a final backup and shuts down cleanly before the "
    "computer powers off, so nothing is left mid-write.":
        "عند الإيقاف أو إعادة التشغيل، يأخذ التطبيق نسخة احتياطية أخيرة ويُغلق بشكل سليم قبل "
        "إطفاء الجهاز، فلا يبقى شيء في منتصف الكتابة.",

    "Reminders start 5 days before the next dose date. Flagged for admin if 2+ weeks "
    "overdue and uncontacted. %(total_count)s shown.":
        "تبدأ التذكيرات قبل ٥ أيام من تاريخ الجرعة التالية. ويُنبَّه المدير إذا تأخرت أسبوعين "
        "أو أكثر دون تواصل. المعروض %(total_count)s.",
}

BATCH.update(_APP)
