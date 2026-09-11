# -*- coding: utf-8 -*-
"""Arabic translations, batch 7 — dashboard, worklists, admin, appointments,
audits, boarding, cash register, consignment and distributor screens.

Enum values that are STORED in the database (Cash/Card/Transfer,
Damaged/Expired/Other, Phone Call/Text Message) are translated here for
display only — they are shown through these labels, while the stored value
stays the English constant the route validates against.
"""

BATCH = {
    "Password reset. The user will be asked to set a new one on next login.":
        "تمت إعادة تعيين كلمة المرور. سيُطلب من المستخدم تعيين كلمة جديدة عند تسجيل الدخول التالي.",

    # ---- pagination / generic ----
    "Back": "رجوع",
    "← Prev": "← السابق",
    "Next →": "التالي →",
    "Visit": "الزيارة",
    "Select Vet…": "اختر الطبيب…",
    "No": "لا",
    "Yes": "نعم",
    "Clear": "مسح",
    "View": "عرض",
    "Open": "فتح",
    "All": "الكل",
    "None": "لا شيء",
    "Staff": "الموظفون",
    "Slot": "الفترة",
    "Active": "نشط",
    "Select…": "اختر…",
    "Loading…": "جارٍ التحميل…",
    "Try Again": "حاول مرة أخرى",
    "Go Back": "رجوع",
    "Message": "الرسالة",
    "PDF": "PDF",

    # ---- admin logs / roles ----
    "Grooming Services": "خدمات العناية والتصفيف",
    "Pick a date to review who logged in and what was changed.":
        "اختر تاريخًا لمراجعة من سجّل الدخول وما الذي تم تغييره.",
    "No changes logged on this date.": "لا توجد تغييرات مسجلة في هذا التاريخ.",
    "No login activity on this date.": "لا يوجد نشاط تسجيل دخول في هذا التاريخ.",
    "Roles & Permissions": "الأدوار والصلاحيات",
    "System role": "دور نظامي",
    "Can be assigned as a vet": "يمكن إسناده كطبيب بيطري",
    "Custom role": "دور مخصص",
    "Unsaved changes": "تغييرات غير محفوظة",
    "+ Add Role": "+ إضافة دور",
    "Inherit from role": "موروث من الدور",
    "Custom override for this person:": "تجاوز مخصص لهذا الشخص:",
    "No one is currently assigned to this role. It can be deleted right away.":
        "لا يوجد أحد مُسند إلى هذا الدور حاليًا. يمكن حذفه مباشرة.",

    # ---- appointments ----
    "This Week": "هذا الأسبوع",
    "Hide past bookings": "إخفاء الحجوزات السابقة",
    "Show past unreachable bookings": "إظهار الحجوزات السابقة غير المتاحة",
    "← Prior Week": "← الأسبوع السابق",
    "Next Week →": "الأسبوع التالي →",
    "Medical": "طبي",

    # ---- stock audit help text ----
    "— what you physically counted on the shelf today.":
        "— ما قمت بعدّه فعليًا على الرف اليوم.",
    "Received Since Prior Audit": "المستلم منذ الجرد السابق",
    "— new stock that arrived since the last confirmed audit (0 if none).":
        "— المخزون الجديد الذي وصل منذ آخر جرد مؤكد (٠ إن لم يوجد).",
    "Critical Item?": "صنف حرج؟",
    "— Y/N; leave blank to keep the last value set.":
        "— نعم/لا؛ اتركه فارغًا للإبقاء على آخر قيمة.",
    "Nearest Expiry Date": "أقرب تاريخ انتهاء",
    "— the soonest expiry date among current stock of this item.":
        "— أقرب تاريخ انتهاء ضمن المخزون الحالي لهذا الصنف.",
    "consignment": "أمانة",
    "deactivated": "معطّل",
    "No audits logged yet — start one above.": "لا توجد عمليات جرد مسجلة بعد — ابدأ واحدة أعلاه.",
    "Could not render this barcode.": "تعذّر عرض هذا الباركود.",
    "Could not render the barcode. Try refreshing the page.":
        "تعذّر عرض الباركود. حاول تحديث الصفحة.",

    # ---- nav groups ----
    "Inventory": "المخزون",
    "Sales & Billing": "المبيعات والفوترة",
    "Admin": "الإدارة",

    # ---- boarding ----
    "Currently Boarding": "في الإيواء حاليًا",
    "All (Incl. Picked Up)": "الكل (بما في ذلك المستلَم)",
    "Patient:": "المريض:",
    "Special Needs?": "احتياجات خاصة؟",
    "Something's Wrong": "هناك مشكلة",
    "Contacted the owner?": "هل تم التواصل مع المالك؟",
    "Phone Call": "مكالمة هاتفية",
    "Text Message": "رسالة نصية",
    "Cash": "نقدًا",
    "Card": "بطاقة",
    "Transfer": "حوالة",
    "Export (PDF)": "تصدير (PDF)",
    "Send WhatsApp Message": "إرسال رسالة واتساب",
    "Add phone to send WhatsApp": "أضف رقم هاتف لإرسال واتساب",
    "No boarding sessions on record.": "لا توجد فترات إيواء مسجلة.",

    # ---- cash register ----
    "Paid Out of Register": "المصروف من الصندوق",
    "Register Payout": "صرف من الصندوق",
    "Perfect": "مطابق",
    "Deficit": "عجز",
    "Surplus": "فائض",
    "Not Audited": "لم يُجرد",
    "System Cash Total": "إجمالي النقد في النظام",
    "System Card Total": "إجمالي البطاقة في النظام",
    "System Transfer Total": "إجمالي الحوالات في النظام",

    # ---- misc ----
    "You need to set a new password before continuing.":
        "عليك تعيين كلمة مرور جديدة قبل المتابعة.",
    "No active Retail items — add one from Inventory Catalog first.":
        "لا توجد أصناف تجزئة نشطة — أضف صنفًا من دليل الأصناف أولًا.",

    # ---- consignment ----
    "Settle": "تسوية",
    "Sales": "المبيعات",
    "No Consignment items flagged yet — start from Consignment > Items.":
        "لم يتم تحديد أي أصناف أمانة بعد — ابدأ من الأمانة > الأصناف.",
    "No receipts logged yet.": "لا توجد عمليات استلام مسجلة بعد.",
    "No returns logged yet.": "لا توجد مرتجعات مسجلة بعد.",
    "All Distributors": "جميع الموردين",
    "No Consignment sales in this range.": "لا توجد مبيعات أمانة في هذه الفترة.",
    "← Back to Overview": "← العودة إلى النظرة العامة",
    "Carried forward from last settlement": "مرحّل من التسوية السابقة",
    "New activity this period": "نشاط جديد في هذه الفترة",
    "Amount Owed Now": "المبلغ المستحق الآن",
    "No settlements recorded yet.": "لا توجد تسويات مسجلة بعد.",
    "Damaged": "تالف",
    "Expired": "منتهي الصلاحية",
    "Other": "غير ذلك",
    "Default for reason (Expired → Distributor, else → Clinic)":
        "الافتراضي حسب السبب (منتهي الصلاحية ← المورد، غير ذلك ← العيادة)",
    "Clinic": "العيادة",
    "(overridden)": "(تم التجاوز)",
    "No shrinkage logged yet.": "لا يوجد هالك مسجل بعد.",

    # ---- dashboard ----
    "+ Log a Visit": "+ تسجيل زيارة",
    "Open Settings →": "فتح الإعدادات →",
    "Open Settings": "فتح الإعدادات",
    "Total Patients on File": "إجمالي المرضى المسجلين",
    "Active / Ongoing Cases": "الحالات النشطة / الجارية",
    "Follow-Ups Due Today": "المتابعات المستحقة اليوم",
    "Currently Admitted (Inpatient)": "المنوّمون حاليًا",
    "View all follow-ups →": "عرض جميع المتابعات →",
    "Nothing due today.": "لا يوجد ما هو مستحق اليوم.",
    "Reminder Calls — Call Today for Tomorrow's Visit":
        "مكالمات التذكير — اتصل اليوم لزيارة الغد",
    "No reminder calls needed today.": "لا توجد مكالمات تذكير مطلوبة اليوم.",
    "Wellness Reminders Due": "تذكيرات الرعاية الوقائية المستحقة",
    "View all wellness reminders →": "عرض جميع تذكيرات الرعاية الوقائية →",
    "No wellness reminders due.": "لا توجد تذكيرات رعاية وقائية مستحقة.",
    "View grooming queue →": "عرض قائمة العناية والتصفيف →",
    "No grooming in progress.": "لا توجد عمليات عناية وتصفيف جارية.",
    "Low Stock": "مخزون منخفض",
    "View ordering sheet →": "عرض كشف النواقص →",
    "Nothing below threshold.": "لا يوجد ما هو دون الحد.",
    "Audit & Expiry Alerts": "تنبيهات الجرد والانتهاء",
    "View inventory status →": "عرض حالة المخزون →",
    "No audit or expiry issues.": "لا توجد مشكلات جرد أو انتهاء.",
    "Missed Items — Needs Admin Review": "عناصر فائتة — تحتاج مراجعة الإدارة",
    "Nothing overdue by more than two weeks.": "لا يوجد ما تأخر أكثر من أسبوعين.",

    # ---- distributors ----
    "Export PDF": "تصدير PDF",
    "Total Billed": "إجمالي المفوتر",
    "Total Paid": "إجمالي المدفوع",
    "Outstanding": "المستحق",
    "Order Bills": "فواتير الطلبات",
    "No payments recorded yet.": "لا توجد دفعات مسجلة بعد.",
    "No bills logged yet for this distributor.": "لا توجد فواتير مسجلة لهذا المورد بعد.",
    "Distributors With a Balance": "الموردون ذوو رصيد",
    "Fully Unpaid Bills": "فواتير غير مدفوعة بالكامل",
    "Who You Owe Most": "من تدين له بالأكثر",
    "Ledger": "دفتر الحسابات",
    "No distributors yet — add your suppliers here.":
        "لا يوجد موردون بعد — أضف مورديك هنا.",

    # ---- error pages ----
    "Back to Dashboard": "العودة إلى لوحة التحكم",
    "You don't have access to that page.": "ليس لديك صلاحية الوصول إلى تلك الصفحة.",
    "Back to Log In": "العودة إلى تسجيل الدخول",
    "Details for support — safe to copy and send":
        "تفاصيل للدعم الفني — يمكن نسخها وإرسالها بأمان",
    "Too many people are using it at once. Wait a moment, then try again.":
        "عدد المستخدمين في الوقت نفسه كبير. انتظر لحظة ثم حاول مرة أخرى.",

    # ---- worklists ----
    "Pending Only": "المعلّقة فقط",
    "All Follow-Ups": "جميع المتابعات",
    "MISSED": "فائت",
    "Add phone": "أضف رقم هاتف",
    "No follow-ups to show.": "لا توجد متابعات لعرضها.",
    "In Progress": "قيد التنفيذ",
    "Include Finished": "تضمين المنتهية",
    "Nothing in the grooming queue.": "لا يوجد شيء في قائمة العناية والتصفيف.",

    # ---- inpatient ----
    "Export Inpatient (PDF)": "تصدير التنويم (PDF)",
    "Info": "معلومات",
    "Daily Updates": "التحديثات اليومية",
    "Contact Log": "سجل التواصل",
    "Billing": "الفوترة",
}
