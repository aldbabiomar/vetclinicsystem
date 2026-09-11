# -*- coding: utf-8 -*-
"""Arabic translations, batch 4 — boarding, cash register, consignment,
distributors, inpatient, reports and inventory catalogue labels.

Reuses the agreed vocabulary throughout: الإيواء (boarding), التنويم
(inpatient), الهالك (shrinkage), التسويات (settlements), الصندوق (cash
register), دليل الأصناف (inventory catalog).

Placeholder examples ("e.g. Jordan Lee") are localised rather than copied —
an Arabic UI showing an English example name reads as an untranslated string
even though it is technically "correct".
"""

BATCH = {
    # ---- example/placeholder text ----
    "e.g. Jordan Lee": "مثال: أحمد الراشد",
    "jlee": "ahmad",
    "e.g. Vet Tech": "مثال: مساعد بيطري",
    "e.g. Assists vets, no billing access":
        "مثال: يساعد الأطباء، دون صلاحية الفوترة",
    "e.g. paid the produce delivery driver": "مثال: دفع لسائق توصيل المستلزمات",
    "e.g. counted twice, drawer was short a 5,000 note":
        "مثال: تم العد مرتين، وينقص الصندوق ورقة ٥٬٠٠٠",
    "E.g. slow-moving, discontinued": "مثال: بطيء الحركة، موقوف",
    "E.g. Net 30": "مثال: صافي ٣٠ يومًا",
    "Invoice/delivery note #": "رقم الفاتورة / إشعار التسليم",
    "Distributor's own reference, optional": "مرجع المورد الخاص، اختياري",
    "Search by Distributor Name…": "ابحث باسم المورد…",
    "Search by Product Name…": "ابحث باسم المنتج…",
    "Search by code or service name…": "ابحث بالرمز أو اسم الخدمة…",
    "Bottle, Box, Piece…": "زجاجة، علبة، قطعة…",

    # ---- boarding ----
    "Owner's Response": "رد المالك",
    "Log Incident": "تسجيل حادثة",
    "Record Payment": "تسجيل دفعة",
    "Patient": "المريض",
    "Room": "الغرفة",
    "Entry": "الدخول",
    "Dismissal": "الخروج",
    "Payment": "الدفع",
    "Special Needs": "احتياجات خاصة",
    "Incidents": "الحوادث",
    "Something's Wrong!": "هناك مشكلة!",
    "Mark Picked Up": "تحديد كمُستلَم",
    "Dismissal Date": "تاريخ الخروج",
    "Admitted Items": "الأغراض المستلمة",
    "Save Changes": "حفظ التغييرات",

    # ---- cash register ----
    "Pay From Cash Register": "الصرف من الصندوق",
    "Perform Audit": "تنفيذ جرد",
    "View by Date": "عرض حسب التاريخ",
    "Employee": "الموظف",
    "Discount": "الخصم",
    "Notes (optional)": "ملاحظات (اختياري)",

    # ---- change password ----
    "Change Password": "تغيير كلمة المرور",
    "Current Password": "كلمة المرور الحالية",
    "Confirm New Password": "تأكيد كلمة المرور الجديدة",
    "Update Password": "تحديث كلمة المرور",

    # ---- consignment ----
    "Consignment Items": "أصناف الأمانة",
    "ID": "المعرّف",
    "Consignment?": "أمانة؟",
    "Distributor": "المورد",
    "Locked — has consignment activity": "مقفل — لديه حركة أمانة",
    "Consignment": "الأمانة",
    "Shelf Units": "الوحدات على الرف",
    "Last Settlement": "آخر تسوية",
    "Sold This Month": "المُباع هذا الشهر",
    "Consignment Receiving": "استلام الأمانة",
    "+ Log Receipt": "+ تسجيل استلام",
    "Received Date": "تاريخ الاستلام",
    "Delivery Reference": "مرجع التسليم",
    "Log Receipt": "تسجيل الاستلام",
    "Consignment Returns": "مرتجعات الأمانة",
    "+ Log Return": "+ تسجيل مرتجع",
    "Return Date": "تاريخ الإرجاع",
    "Log Return": "تسجيل المرتجع",
    "From": "من",
    "To": "إلى",
    "Month": "الشهر",
    "Units Sold": "الوحدات المباعة",
    "Current Balance": "الرصيد الحالي",
    "Payment Method": "طريقة الدفع",
    "Record Settlement": "تسجيل تسوية",
    "Settlement History": "سجل التسويات",
    "Period": "الفترة",
    "Recorded By": "سُجِّل بواسطة",
    "Consignment Shrinkage": "هالك الأمانة",
    "+ Log Shrinkage": "+ تسجيل هالك",
    "Liable Party": "الطرف المسؤول",
    "Log Shrinkage": "تسجيل الهالك",
    "Liable": "المسؤول",

    # ---- health / errors ----
    "This install has failed its health check for 3 days running":
        "فشل فحص السلامة لهذا التثبيت ثلاثة أيام متتالية",
    "Not now": "ليس الآن",
    "Deadline Passed": "انقضى الموعد النهائي",
    "Responsible Staff": "الموظف المسؤول",
    "Not allowed in here.": "غير مسموح بالدخول هنا.",
    "Hmm, we can't find that one.": "لم نتمكن من العثور على ذلك.",
    "Something went wrong on our end.": "حدث خطأ من جانبنا.",
    "Copy": "نسخ",
    "The system is busy right now.": "النظام مشغول حاليًا.",

    # ---- distributor bills ----
    "+ Log Bill": "+ تسجيل فاتورة",
    "Bill Date": "تاريخ الفاتورة",
    "Bill / Invoice #": "رقم الفاتورة",
    "Save Bill": "حفظ الفاتورة",
    "Payment Date": "تاريخ الدفع",
    "Delete Bill": "حذف الفاتورة",
    "+ New Distributor": "+ مورد جديد",
    "Distributor Name": "اسم المورد",
    "Product Catalog Link": "رابط دليل المنتجات",
    "Lead Time (Days)": "مدة التوريد (بالأيام)",
    "Payment Terms": "شروط الدفع",
    "Add Distributor": "إضافة مورد",
    "Contact": "جهة الاتصال",
    "Lead Time": "مدة التوريد",
    "Terms": "الشروط",

    # ---- worklists ----
    "Follow-Up Date": "تاريخ المتابعة",
    "Reminder Call": "مكالمة تذكير",
    "Animal": "الحيوان",
    "Grooming Queue": "قائمة العناية والتصفيف",
    "Patient ID": "رقم المريض",
    "Contacted?": "تم التواصل؟",

    # ---- inpatient (clinical: flagged for review) ----
    "Presenting Complaint": "الشكوى الحالية",
    "Physical Exam Findings & Diagnostics": "نتائج الفحص السريري والتشخيص",
    "Physical Exam & Diagnostics": "الفحص السريري والتشخيص",
    "Attending Veterinarian": "الطبيب البيطري المعالج",
    "Supervising Veterinarian": "الطبيب البيطري المشرف",
    "Dismissed": "تم الإخراج",
    "Add a Daily Update — Condition of the Patient":
        "إضافة تحديث يومي — حالة المريض",
    "Log Update": "تسجيل التحديث",
    "Did the Owner Pick Up?": "هل استلم المالك؟",
    "Log Contact Attempt": "تسجيل محاولة تواصل",
    "Add Procedure to Bill": "إضافة إجراء إلى الفاتورة",
    "Add to Bill": "إضافة إلى الفاتورة",
    "Upload": "رفع",
    "Admitted": "تم التنويم",
    "Complaint": "الشكوى",
    "Admit Patient": "تنويم المريض",
    "Admission Date": "تاريخ التنويم",
    "Admit": "تنويم",

    # ---- reports / insights ----
    "Revenue by Service Category": "الإيرادات حسب فئة الخدمة",
    "Payment Method Mix": "توزيع طرق الدفع",
    "Vet Performance": "أداء الأطباء",
    "Vet": "الطبيب البيطري",
    "Avg / Visit": "المتوسط / زيارة",
    "Top Clients by Lifetime Spend": "أفضل العملاء حسب إجمالي الإنفاق",
    "Payments": "الدفعات",
    "Day": "اليوم",
    "Appointments Booked": "المواعيد المحجوزة",
    "Visits Logged (Same Weekday)": "الزيارات المسجلة (نفس يوم الأسبوع)",
    "Approx. Fulfillment": "نسبة الإنجاز التقريبية",
    "Active Inpatient Cases": "حالات التنويم النشطة",
    "Active Boarding Stays": "إقامات الإيواء النشطة",

    # ---- inventory catalogue ----
    "+ New Item": "+ صنف جديد",
    "Item Name": "اسم الصنف",
    "Preferred Distributor": "المورد المفضل",
    "Track Expiry Date": "تتبع تاريخ الانتهاء",
    "Add Item": "إضافة صنف",
    "Barcode": "الباركود",
    "Track Expiry": "تتبع الانتهاء",

    # ---- headings fixed for the entity issue ----
    "Users & Roles": "المستخدمون والصلاحيات",
    "Backups & Restore": "النسخ الاحتياطي والاستعادة",
    "Startup & Shutdown": "التشغيل والإيقاف",
    "Patients & Visits": "المرضى والزيارات",
    "Monthly P&L": "الأرباح والخسائر الشهرية",
    "Yearly P&L": "الأرباح والخسائر السنوية",
}
