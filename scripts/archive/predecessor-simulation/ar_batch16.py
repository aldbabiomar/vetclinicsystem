# -*- coding: utf-8 -*-
"""Arabic translations, batch 16 — the page titles, the mixed-node sentences,
the currency column headers, and every user-facing string inside an inline
<script>.

The script strings are the ones a user only sees after doing something: the
empty state under a search box, a confirm dialog, a toast. They were invisible
to every earlier pass because they live in a JS string literal rather than a
text node, and they stayed English on otherwise fully Arabic pages.

`%(name)s` placeholders inside these are substituted in JavaScript with
`.replace()`, so the Arabic may put them in a different position than the
English does — that is the point of using named placeholders rather than a
template literal.
"""

BATCH = {
    # --- page titles and chrome
    "Something went wrong loading this page.": "حدث خطأ أثناء تحميل هذه الصفحة.",
    "Page %(page)s of %(total_pages)s": "صفحة %(page)s من %(total_pages)s",
    "(%(total_count)s total)": "(%(total_count)s بالمجموع)",
    "whole record": "السجل بالكامل",
    "Failed": "فشل",
    "Failed — %(error)s": "فشل — %(error)s",
    "Saved": "محفوظ",
    "Audit": "جرد",
    "Audit — %(audit_date)s": "جرد — %(audit_date)s",
    "Not Allowed": "غير مسموح",
    "Page Not Found": "الصفحة غير موجودة",
    "Something Went Wrong": "حدث خطأ ما",
    "Server Busy": "الخادم مشغول",
    "Consignment Sales by Distributor": "مبيعات الأمانة حسب المورد",

    # --- users and roles
    "Custom: %(cap)s%%": "مخصص: %(cap)s٪",
    "Disabled": "معطّل",
    "Disable": "تعطيل",
    "Enable": "تفعيل",
    "Deactivate": "إلغاء التفعيل",
    "Reactivate": "إعادة التفعيل",
    "1 staff member · always keeps at least one Admin":
        "موظف واحد · يبقى دائمًا مدير واحد على الأقل",
    "%(n)s staff members · always keeps at least one Admin":
        "%(n)s موظفين · يبقى دائمًا مدير واحد على الأقل",
    "1 staff member": "موظف واحد",
    "%(n)s staff members": "%(n)s موظفين",
    "1 staff member currently assigned to %(role)s.":
        "موظف واحد مُسنَد حاليًا إلى %(role)s.",
    "%(count)s staff members currently assigned to %(role)s.":
        "%(count)s موظفين مُسنَدين حاليًا إلى %(role)s.",

    # --- appointments
    "Showing unreachable bookings from any date, including past ones.":
        "تُعرض الحجوزات غير القابلة للوصول من أي تاريخ، بما فيها السابقة.",
    "Cancel %(name)s's appointment?": "إلغاء موعد %(name)s؟",
    "Cancel Appointment": "إلغاء الموعد",
    "Keep It": "الإبقاء عليه",

    # --- inventory audits
    "%(counted)s of %(total)s items have a Stock Counted value entered.":
        "أُدخلت قيمة المخزون المعدود لـ %(counted)s من أصل %(total)s صنفًا.",
    "%(missing)s item(s) have no Stock Counted value and will be skipped (kept unchanged).":
        "%(missing)s صنفًا بلا قيمة مخزون معدود وسيتم تخطيها (تبقى دون تغيير).",
    "%(negative)s item(s) have a negative Stock Counted value — please check before confirming.":
        "%(negative)s صنفًا بقيمة مخزون معدود سالبة — يرجى التحقق قبل التأكيد.",
    "%(zero)s item(s) are counted as 0 in stock — please double-check these.":
        "%(zero)s صنفًا معدود بمخزون صفر — يرجى التأكد منها مرة أخرى.",
    "Audit history tracks actual counts.": "يتتبع سجل الجرد الأعداد الفعلية.",
    "%(total_count)s items shown.": "المعروض %(total_count)s صنفًا.",
    "%(labels)s label(s) across %(items)s item(s).":
        "%(labels)s ملصقًا موزعة على %(items)s صنفًا.",

    # --- currency column headers
    "Total (%(currency_label)s)": "الإجمالي (%(currency_label)s)",
    "Amount (%(currency_label)s)": "المبلغ (%(currency_label)s)",
    "Revenue (%(currency_label)s)": "الإيراد (%(currency_label)s)",
    "Owed (%(currency_label)s)": "المستحق (%(currency_label)s)",
    "Paid (%(currency_label)s)": "المدفوع (%(currency_label)s)",
    "Residual (%(currency_label)s)": "المتبقي (%(currency_label)s)",
    "Outstanding (%(currency_label)s)": "الرصيد القائم (%(currency_label)s)",
    "Balance (%(currency_label)s)": "الرصيد (%(currency_label)s)",
    "Difference (%(currency_label)s)": "الفرق (%(currency_label)s)",
    "Cost (%(currency_label)s)": "التكلفة (%(currency_label)s)",
    "Bill (%(currency_label)s)": "الفاتورة (%(currency_label)s)",
    "Sale (%(currency_label)s)": "البيع (%(currency_label)s)",
    "Rent (%(currency_label)s)": "الإيجار (%(currency_label)s)",
    "Utilities (%(currency_label)s)": "الخدمات (%(currency_label)s)",
    "Marketing (%(currency_label)s)": "التسويق (%(currency_label)s)",
    "Billed Amount (%(currency_label)s)": "المبلغ المفوتر (%(currency_label)s)",

    # --- search boxes and pickers (inline script)
    "Type at least 2 characters.": "اكتب حرفين على الأقل.",
    "No matches.": "لا توجد نتائج مطابقة.",
    "no phone": "لا يوجد هاتف",
    "no price set": "لم يُحدَّد سعر",
    "Could not search patients; check server connection.":
        "تعذّر البحث عن الحيوانات؛ تحقق من الاتصال بالخادم.",
    "Could not search the Price List; check server connection.":
        "تعذّر البحث في قائمة الأسعار؛ تحقق من الاتصال بالخادم.",
    "Could not search inventory; check server connection.":
        "تعذّر البحث في المخزون؛ تحقق من الاتصال بالخادم.",
    "%(name)s has no sale price set in the Price List.":
        "%(name)s ليس له سعر بيع محدد في قائمة الأسعار.",
    "No items added yet.": "لم تُضف أي أصناف بعد.",
    "Add at least one procedure first.": "أضف إجراءً واحدًا على الأقل أولًا.",

    # --- boarding
    "%(total_count)s boarding session(s).": "%(total_count)s جلسة إيواء.",
    "%(total_count)s boarding session(s) currently boarding.":
        "%(total_count)s جلسة إيواء جارية حاليًا.",
    "Expected Dismissal Date is before Entry Date — billing will still count as 1 night. "
    "Please double-check these dates.":
        "تاريخ الخروج المتوقع قبل تاريخ الدخول — ستُحتسب الفاتورة ليلة واحدة على أي حال. "
        "يرجى التأكد من هذين التاريخين.",
    "Same-day boarding is billed as 1 night.":
        "الإيواء في اليوم نفسه يُفوتر ليلة واحدة.",

    # --- cash register
    "Every POS sale, Visit/Inpatient/Boarding payment, and refund on %(day)s — for "
    "end-of-day cash-up against what's physically in the till.":
        "كل عملية بيع في نقطة البيع، ودفعات الزيارات والتنويم والإيواء، والمرتجعات في "
        "%(day)s — لجرد نهاية اليوم مقابل الموجود فعليًا في الصندوق.",
    "Last audited %(at)s by %(who)s — counted %(counted)s %(cur)s cash against a system "
    "total of %(system)s %(cur)s (%(difference)s %(cur)s difference)":
        "آخر جرد %(at)s بواسطة %(who)s — عُدّ %(counted)s %(cur)s نقدًا مقابل إجمالي "
        "النظام %(system)s %(cur)s (بفارق %(difference)s %(cur)s)",
    "Logs cash leaving the till on %(day)s for a reason that isn't a refund — petty cash, "
    "paying a supplier directly out of the drawer, etc.":
        "يسجّل النقد الخارج من الصندوق في %(day)s لسبب غير الاسترداد — مصروفات نثرية، "
        "أو دفع لمورد مباشرة من الصندوق، وما شابه.",

    # --- consignment
    "Locked — has activity": "مقفل — عليه حركة",
    "Period: %(start)s — %(end)s": "الفترة: %(start)s — %(end)s",
    "start": "البداية",
    "%(units)s unit(s) sold since last settlement.":
        "بيعت %(units)s وحدة منذ آخر تسوية.",
    "Damaged/expired Consignment stock, written off before it sold.":
        "مخزون أمانة تالف أو منتهي الصلاحية، شُطب قبل بيعه.",
    "1 entry on file.": "قيد واحد مسجل.",
    "%(total_count)s entries on file.": "%(total_count)s قيدًا مسجلًا.",

    # --- dashboard
    "Snapshot as of today, %(today)s.": "لمحة حتى اليوم، %(today)s.",
    "Staff on the clinic network can reach this app at":
        "يمكن للموظفين على شبكة العيادة الوصول إلى هذا التطبيق عبر",
    "1 bill has no Date Billed set — it is missing from Monthly & Yearly P&L until fixed.":
        "فاتورة واحدة بلا تاريخ فوترة — وهي غير محتسبة في الأرباح والخسائر الشهرية "
        "والسنوية حتى تُصحَّح.",
    "%(unbilled_count)s bills have no Date Billed set — they are missing from Monthly & "
    "Yearly P&L until fixed.":
        "%(unbilled_count)s فاتورة بلا تاريخ فوترة — وهي غير محتسبة في الأرباح والخسائر "
        "الشهرية والسنوية حتى تُصحَّح.",
    "Some schema updates couldn't be applied on the last launch — some newer features may "
    "not work correctly: %(migration_failures)s":
        "تعذّر تطبيق بعض تحديثات قاعدة البيانات عند آخر تشغيل — قد لا تعمل بعض الميزات "
        "الأحدث بشكل صحيح: %(migration_failures)s",
    "This install needs attention": "هذا التثبيت يحتاج إلى انتباه",
    "Health check warning": "تحذير من فحص السلامة",
    "Last checked %(ran_at)s": "آخر فحص %(ran_at)s",
    "don't show again": "عدم الإظهار مرة أخرى",
    "%(wellness_type)s due %(due_date)s": "%(wellness_type)s مستحق في %(due_date)s",

    # --- follow-ups, inpatient, patients, owners
    'Auto-generated from visits marked "follow-up needed". %(total_count)s shown.':
        'تُنشأ تلقائيًا من الزيارات المعلَّمة بـ"يحتاج متابعة". المعروض %(total_count)s.',
    "Admitted %(admission_date)s": "أُدخل في %(admission_date)s",
    "Picked Up": "تم الرد",
    "No Answer": "لا يوجد رد",
    "Patients currently admitted for boarding or ongoing treatment. Use \"All Cases\" to "
    "include discharged patients, or \"Balance Due\" for discharged cases still owing "
    "money (e.g. a procedure billed after the patient already left). %(total_count)s shown.":
        "الحيوانات المُدخلة حاليًا للإيواء أو لعلاج مستمر. استخدم \"كل الحالات\" لتضمين "
        "الحيوانات المخرَجة، أو \"رصيد مستحق\" للحالات المخرَجة التي ما زال عليها مبلغ "
        "(مثل إجراء فُوتر بعد خروج الحيوان). المعروض %(total_count)s.",
    "%(total_count)s shown.": "المعروض %(total_count)s.",
    "Patients (%(count)s)": "الحيوانات (%(count)s)",
    "New Owner": "مالك جديد",
    "Add Owner": "إضافة مالك",
    "Edit Patient": "تعديل الحيوان",
    "Owner: %(owner)s": "المالك: %(owner)s",
    "New patients are created from Log a Visit.":
        "تُنشأ الحيوانات الجديدة من تسجيل زيارة.",
    "Sort:": "الترتيب:",
    "%(total_count)s result(s) for \"%(search)s\".":
        "%(total_count)s نتيجة لـ\"%(search)s\".",
    "%(total_count)s on file.": "%(total_count)s مسجل.",
    "%(total_count)s items.": "%(total_count)s صنفًا.",
    "Admin-only page — visible to Vet/Reception only as a read-only picker while billing.":
        "صفحة للمديرين فقط — تظهر للطبيب والاستقبال كقائمة اختيار للقراءة فقط أثناء الفوترة.",

    # --- barcodes
    "Manage Barcode": "إدارة الباركود",
    "Add Barcode": "إضافة باركود",
    "Manage Barcode — %(name)s": "إدارة الباركود — %(name)s",
    "Manually Entered Barcode": "باركود مُدخل يدويًا",
    "Created Barcode": "باركود منشأ",
    "Enter a barcode first.": "أدخل الباركود أولًا.",
    "Barcode saved.": "تم حفظ الباركود.",
    "Barcode removed.": "تم حذف الباركود.",
    "Could not save that barcode.": "تعذّر حفظ هذا الباركود.",
    "Could not create a barcode.": "تعذّر إنشاء باركود.",
    "Could not remove that barcode.": "تعذّر حذف هذا الباركود.",
    "Could not load barcodes.": "تعذّر تحميل الباركودات.",
    "Could not load barcode status.": "تعذّر تحميل حالة الباركود.",
    "Could not load this item’s barcode.": "تعذّر تحميل باركود هذا الصنف.",
    "Remove this barcode? You can add a new one afterward, but this one will stop "
    "scanning immediately.":
        "حذف هذا الباركود؟ يمكنك إضافة باركود جديد بعد ذلك، لكن هذا سيتوقف عن القراءة فورًا.",
    "Remove this barcode? You can add a new one afterward.":
        "حذف هذا الباركود؟ يمكنك إضافة باركود جديد بعد ذلك.",
    "Could not reach the server.": "تعذّر الوصول إلى الخادم.",

    # --- login
    "You can try logging in again now.": "يمكنك محاولة تسجيل الدخول مرة أخرى الآن.",
    "Account locked — try again in %(m)sm %(s)ss.":
        "الحساب مقفل — حاول مرة أخرى بعد %(m)s د %(s)s ث.",

    # --- POS
    "Sale in progress": "عملية بيع جارية",
    "Only %(stock)s in stock.": "المتوفر في المخزون %(stock)s فقط.",
    "Cash received is %(amount)s %(currency_label)s short of the total.":
        "النقد المستلم أقل من الإجمالي بمقدار %(amount)s %(currency_label)s.",
    "(exact: %(exact)s %(currency_label)s — %(rounding)s %(currency_label)s rounding, "
    "absorbed by clinic)":
        "(بالضبط: %(exact)s %(currency_label)s — %(rounding)s %(currency_label)s تقريب، "
        "تتحمله العيادة)",
    "%(total_count)s retail sales on %(day)s.": "%(total_count)s عملية بيع تجزئة في %(day)s.",
    "%(total_count)s retail sales.": "%(total_count)s عملية بيع تجزئة.",
    "No sales recorded on %(day)s.": "لا توجد مبيعات مسجلة في %(day)s.",
    "No sales yet.": "لا توجد مبيعات بعد.",
    "Sale #%(sale_id)s": "عملية بيع رقم %(sale_id)s",

    # --- refunds
    "No refunds recorded on %(day)s.": "لا توجد مرتجعات مسجلة في %(day)s.",
    "No refunds recorded yet.": "لا توجد مرتجعات مسجلة بعد.",
    "Visit %(visit_id)s": "زيارة %(visit_id)s",
    "Inpatient Case %(case_id)s": "حالة تنويم %(case_id)s",
    "Boarding %(boarding_id)s": "إيواء %(boarding_id)s",
    "Enter a Sale ID.": "أدخل رقم عملية البيع.",
    "Enter a sale ID first.": "أدخل رقم عملية البيع أولًا.",
    "Could not find that sale.": "تعذّر العثور على عملية البيع هذه.",
    "Could not look up that sale; check server connection.":
        "تعذّر البحث عن عملية البيع هذه؛ تحقق من الاتصال بالخادم.",
    "This sale has no items.": "لا توجد أصناف في عملية البيع هذه.",
    "This sale has nothing left to refund.":
        "لم يعد في عملية البيع هذه ما يمكن استرداده.",
    "Look up a sale first.": "ابحث عن عملية بيع أولًا.",
    "Look up a sale and enter at least one refund quantity.":
        "ابحث عن عملية بيع وأدخل كمية استرداد واحدة على الأقل.",
    "Enter a quantity to refund for at least one item.":
        "أدخل كمية للاسترداد لصنف واحد على الأقل.",
    "This sale had a %(cleanup)s %(currency_label)s Clean Up applied — total refunds "
    "against it can't exceed what was actually collected (%(total)s %(currency_label)s).":
        "طُبِّق على عملية البيع هذه إعفاء عن الفئات القليلة بمقدار %(cleanup)s "
        "%(currency_label)s — لا يمكن أن تتجاوز المرتجعات عليها ما حُصِّل فعليًا "
        "(%(total)s %(currency_label)s).",

    # --- reports
    "Showing saved values for %(month)s. Saving will overwrite them.":
        "تُعرض القيم المحفوظة لشهر %(month)s. الحفظ سيستبدلها.",
    "No operating costs saved yet for %(month)s.":
        "لم تُحفظ تكاليف تشغيلية بعد لشهر %(month)s.",

    # --- settings, updates, backups
    "You're on the latest version.": "أنت على أحدث إصدار.",
    "Couldn't check for updates.": "تعذّر التحقق من التحديثات.",
    "The app is restarting — this page will reconnect automatically.":
        "التطبيق قيد إعادة التشغيل — ستُعاد هذه الصفحة تلقائيًا.",
    "Taking longer than expected to come back — check with whoever manages this computer.":
        "العودة تستغرق وقتًا أطول من المتوقع — راجع المسؤول عن هذا الجهاز.",
    "%(job)s failed to start.": "تعذّر بدء %(job)s.",
    "Roll Back": "التراجع عن التحديث",
    "Choose Backup File": "اختيار ملف النسخة الاحتياطية",
    "Could not open that folder.": "تعذّر فتح هذا المجلد.",
    "↑ .. (up one level)": "↑ .. (مستوى للأعلى)",
    "backup files": "ملفات النسخ الاحتياطي",
    "Could not create that folder.": "تعذّر إنشاء هذا المجلد.",
    "Could not start the backup.": "تعذّر بدء النسخ الاحتياطي.",
    "Backup complete.": "اكتمل النسخ الاحتياطي.",
    "Backup failed.": "فشل النسخ الاحتياطي.",
    "Could not start the restore.": "تعذّر بدء الاستعادة.",
    "Restore failed.": "فشلت الاستعادة.",
    "%(message)s. Please log in again.": "%(message)s. يرجى تسجيل الدخول مرة أخرى.",

    # --- visit detail
    '— Exported as "Veterinary Services"': '— يُصدَّر باسم "خدمات بيطرية"',
    "%(total_count)s visits on %(day)s.": "%(total_count)s زيارة في %(day)s.",
    "%(total_count)s visits.": "%(total_count)s زيارة.",
}

# Brand-bearing strings: the app name is part of the sentence, so the msgid
# genuinely differs between the two apps rather than being shared.
for _app, _ar in (("IQ", "IQ"), ("JO", "JO")):
    BATCH.update({
        f"Restarting VetClinicSystem {_app}": f"جارٍ إعادة تشغيل VetClinicSystem {_ar}",
        f"Restarting VetClinicSystem {_app} — this page will reconnect automatically.":
            f"جارٍ إعادة تشغيل VetClinicSystem {_ar} — ستُعاد هذه الصفحة تلقائيًا.",
        f"This will restart VetClinicSystem {_app} for everyone for about 30 seconds. "
        f"A backup will be taken first. Continue?":
            f"سيؤدي هذا إلى إعادة تشغيل VetClinicSystem {_ar} للجميع لنحو ٣٠ ثانية. "
            f"ستُؤخذ نسخة احتياطية أولًا. هل تريد المتابعة؟",
        f"This will roll back to the previous version and restart VetClinicSystem {_app} "
        f"for everyone for about 30 seconds. Continue?":
            f"سيؤدي هذا إلى التراجع إلى الإصدار السابق وإعادة تشغيل VetClinicSystem "
            f"{_ar} للجميع لنحو ٣٠ ثانية. هل تريد المتابعة؟",
        f"This item’s barcode was created by VetClinicSystem {_app}. Print a label to "
        f"stick on the item, or remove it to start over.":
            f"أُنشئ باركود هذا الصنف بواسطة VetClinicSystem {_ar}. اطبع ملصقًا لتثبيته "
            f"على الصنف، أو احذفه للبدء من جديد.",
    })
BATCH["This item's barcode was created by this app. Print a label to stick on the item, "
      "or remove it to start over."] = (
    "أُنشئ باركود هذا الصنف بواسطة هذا التطبيق. اطبع ملصقًا لتثبيته على الصنف، "
    "أو احذفه للبدء من جديد.")
