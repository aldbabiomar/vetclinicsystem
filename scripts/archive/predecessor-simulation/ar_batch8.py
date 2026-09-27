# -*- coding: utf-8 -*-
"""Arabic translations, batch 8 — the remainder: inpatient detail, insights,
inventory, owners, patients, POS, refunds, reports, settings and visit forms.

Two things deliberately NOT translated, and they are translated to themselves
so they render unchanged rather than sitting blank:
  - shell commands (`python3 setup.py --enable-updates`) — these are typed
    verbatim into a terminal; translating them would make them wrong.
  - the product name inside palette labels.
"""

BATCH = {
    # ---- inpatient detail ----
    "Attachments": "المرفقات",
    "Species / Sex / Age": "النوع / الجنس / العمر",
    "Last 3 Days": "آخر ٣ أيام",
    "No updates logged yet.": "لا توجد تحديثات مسجلة بعد.",
    "Earlier Entries": "السجلات الأقدم",
    "No contact attempts logged yet.": "لا توجد محاولات تواصل مسجلة بعد.",
    "Bill so Far": "الفاتورة حتى الآن",
    "No procedures billed yet.": "لم تتم فوترة أي إجراءات بعد.",
    "Clean Up applied": "تم تطبيق الإعفاء عن الفئات القليلة",
    "No files uploaded yet.": "لم يتم رفع أي ملفات بعد.",
    "+ Admit Patient": "+ تنويم مريض",
    "Currently Admitted": "المنوّمون حاليًا",
    "All Cases": "جميع الحالات",
    "Balance Due": "الرصيد المستحق",

    # ---- insights / retention ----
    "Retention →": "ولاء العملاء →",
    "Clients With Paid Visits (Lifetime)": "العملاء ذوو زيارات مدفوعة (الإجمالي)",
    "Vets Billing This Window": "الأطباء الذين فوتروا في هذه الفترة",
    "No billed visits with a recorded vet in this window.":
        "لا توجد زيارات مفوترة بطبيب مسجل في هذه الفترة.",
    "No payments on file yet.": "لا توجد دفعات مسجلة بعد.",
    "Appointment Demand by Day of Week": "الطلب على المواعيد حسب يوم الأسبوع",
    "Weekend": "عطلة نهاية الأسبوع",
    "Inpatient & Boarding Load": "حِمل التنويم والإيواء",
    "Avg. Inpatient Stay (Days)": "متوسط مدة التنويم (بالأيام)",
    "Avg. Boarding Stay (Days)": "متوسط مدة الإيواء (بالأيام)",
    "Cash Register Health": "سلامة الصندوق",

    # ---- inventory ----
    "Include Inactive": "تضمين غير النشط",
    "No inventory items yet.": "لا توجد أصناف في المخزون بعد.",
    "Manually Enter Barcode": "إدخال الباركود يدويًا",
    "Create Barcode": "إنشاء باركود",
    "Nothing left to print.": "لا يوجد ما يُطبع.",
    "Audit Overdue": "الجرد متأخر",
    "Expiring / Expired": "قارب على الانتهاء / منتهي",
    "critical": "حرج",
    "No items match this filter.": "لا توجد أصناف تطابق هذا المرشّح.",
    "Sorted by priority — use this to place your monthly order.":
        "مرتبة حسب الأولوية — استخدمها لتقديم طلبك الشهري.",

    # ---- owners / patients ----
    "Edit Owner": "تعديل المالك",
    "No patients under this owner yet.": "لا يوجد مرضى لهذا المالك بعد.",
    "+ New Owner": "+ مالك جديد",
    "No owners match.": "لا يوجد ملاك مطابقون.",
    "Full History": "السجل الكامل",
    "Export Patient File (PDF)": "تصدير ملف المريض (PDF)",
    "Export Billing (PDF)": "تصدير الفوترة (PDF)",
    "+ Log Visit": "+ تسجيل زيارة",
    "Microchip": "الشريحة",
    "No visits logged yet.": "لا توجد زيارات مسجلة بعد.",
    "Back to Patient": "العودة إلى المريض",
    "Open visit →": "فتح الزيارة →",
    "Open case →": "فتح الحالة →",
    "View boarding record →": "عرض سجل الإيواء →",
    "No history recorded yet.": "لا يوجد سجل مسجل بعد.",
    "No patients match.": "لا يوجد مرضى مطابقون.",

    # ---- POS ----
    "Scan or search a Retail item to add it to the sale.":
        "امسح أو ابحث عن صنف تجزئة لإضافته إلى عملية البيع.",
    "Current Sale": "عملية البيع الحالية",
    "Cart is empty.": "السلة فارغة.",
    "Change Due": "الباقي",
    "Export Bill (PDF)": "تصدير الفاتورة (PDF)",
    "New Sale": "عملية بيع جديدة",
    "Cash Received": "النقد المستلم",
    "Can Be Discounted?": "قابل للخصم؟",
    "No priced items yet.": "لا توجد أصناف مسعّرة بعد.",

    # ---- refunds ----
    "Retail Refund": "استرداد تجزئة",
    "Sale #": "رقم عملية البيع",
    "Refund Total": "إجمالي الاسترداد",
    "Return item(s) to stock": "إعادة الأصناف إلى المخزون",
    "Service Refund": "استرداد خدمة",
    "Removes a revenue amount only — no stock is touched. Enter":
        "يزيل مبلغ إيراد فقط — دون المساس بالمخزون. أدخل",
    "exactly one": "واحدًا فقط",
    "Visit ID": "رقم الزيارة",
    "(one of these three)": "(واحد من هذه الثلاثة)",
    "Inpatient Case ID": "رقم حالة التنويم",
    "Boarding ID": "رقم الإيواء",
    "Recent Refunds": "المرتجعات الأخيرة",
    "Retail": "تجزئة",
    "Restocked": "أُعيد للمخزون",
    "Not restocked": "لم يُعد للمخزون",
    "Service": "خدمة",

    # ---- reports ----
    "Revenue from billing & retail sales, COGS from measured usage. Admin only.":
        "الإيرادات من الفوترة ومبيعات التجزئة، وتكلفة البضاعة من الاستهلاك المقاس. للإدارة فقط.",
    "Rebuild Report Data": "إعادة بناء بيانات التقارير",
    "Yearly P&L →": "الأرباح والخسائر السنوية →",
    "Enter Operating Costs for a Month": "أدخل التكاليف التشغيلية لشهر",
    "← Monthly P&L": "← الأرباح والخسائر الشهرية",
    "Not enough data yet.": "لا توجد بيانات كافية بعد.",
    "Each row is the group of clients whose": "كل صف يمثل مجموعة العملاء الذين",
    "first-ever visit": "زيارتهم الأولى",
    "← Insights": "← التحليلات",

    # ---- settings ----
    "Saved with the button below": "يُحفظ بالزر أدناه",
    "Nothing here takes effect until you press Save Settings.":
        "لا شيء هنا يسري حتى تضغط على حفظ الإعدادات.",
    "Pastel — Vetzone IQ": "ألوان هادئة — Vetzone IQ",
    "Blue Shades — ChamPet IQ": "درجات الأزرق — ChamPet IQ",
    "Inventory Alerts": "تنبيهات المخزون",
    "Backups": "النسخ الاحتياطي",
    "Health Check": "فحص السلامة",
    "Daily Health Check": "فحص السلامة اليومي",
    "Run the daily health check and show its warnings":
        "تشغيل فحص السلامة اليومي وإظهار تحذيراته",
    "Remote Monitoring (optional)": "المراقبة عن بُعد (اختياري)",
    "missing": "مفقود",
    "Must start with": "يجب أن يبدأ بـ",
    "Treat it like a password": "تعامل معه ككلمة مرور",
    "This Install's ID": "معرّف هذا التثبيت",
    "Saves the sections above.": "يحفظ الأقسام أعلاه.",
    "Runs when you click": "يعمل عند الضغط على",
    "Set a backup folder above and save, then you can back up.":
        "حدد مجلد النسخ الاحتياطي أعلاه واحفظ، ثم يمكنك أخذ نسخة.",
    "Recent Backups": "النسخ الاحتياطية الأخيرة",
    "Success": "نجح",
    "Running": "قيد التشغيل",
    "Restore From Backup": "الاستعادة من نسخة احتياطية",
    "Replaces": "يستبدل",
    "all": "كل",
    "after": "بعد",
    # A shell command: typed verbatim into a terminal, so it must NOT change.
    "python3 reconcile_attachments.py": "python3 reconcile_attachments.py",
    "python3 setup.py --enable-updates": "python3 setup.py --enable-updates",
    "Recent Restores": "عمليات الاستعادة الأخيرة",
    "Current Version": "الإصدار الحالي",
    "Version": "الإصدار",
    "is available": "متاح",
    "on the computer running VetClinicSystem IQ.":
        "على الجهاز الذي يشغّل VetClinicSystem IQ.",
    "on the computer running VetClinicSystem JO.":
        "على الجهاز الذي يشغّل VetClinicSystem JO.",
    "Applies immediately": "يسري فورًا",
    "Start VetClinicSystem IQ automatically when this computer starts":
        "تشغيل VetClinicSystem IQ تلقائيًا عند بدء تشغيل هذا الجهاز",
    "Start VetClinicSystem JO automatically when this computer starts":
        "تشغيل VetClinicSystem JO تلقائيًا عند بدء تشغيل هذا الجهاز",

    # ---- visit forms ----
    "Export Visit (PDF)": "تصدير الزيارة (PDF)",
    "Case": "الحالة",
    "Weight": "الوزن",
    "BCS": "درجة الحالة الجسدية",
    "Wellness Reminder": "تذكير الرعاية الوقائية",
    "Contacted": "تم التواصل",
    "Automatic Calculation": "حساب تلقائي",
    "Manual Entry": "إدخال يدوي",
    "Paid": "مدفوع",
    "Clinical Notes": "ملاحظات سريرية",
    "Grooming Status": "حالة العناية والتصفيف",
    "Selected patient:": "المريض المختار:",
    "Owner Details": "بيانات المالك",
    "Patient Details": "بيانات المريض",
    "Intact": "غير معقّم",
    "Neutered": "مخصي",
    "Spayed": "معقّمة",
    "Indoor": "داخل المنزل",
    "Outdoor": "خارج المنزل",
    "Stray": "سائب",
    "Is this for a patient already on file, or a new one?":
        "هل هذه لمريض مسجل بالفعل أم لمريض جديد؟",
    "Search by patient name, patient ID, owner name, or owner phone number.":
        "ابحث باسم المريض أو رقمه أو اسم المالك أو رقم هاتفه.",
    "Fill in owner details and patient details, then log the visit.":
        "أدخل بيانات المالك وبيانات المريض، ثم سجّل الزيارة.",
    "Date (Default)": "التاريخ (الافتراضي)",
    "Clear Filters": "مسح المرشّحات",
    "No visits match.": "لا توجد زيارات مطابقة.",
    "DUE": "مستحق",
    "No wellness reminders on file.": "لا توجد تذكيرات رعاية وقائية مسجلة.",
}
