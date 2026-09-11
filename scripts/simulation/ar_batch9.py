# -*- coding: utf-8 -*-
"""Arabic translations, batch 9 — the mixed prose+expression strings.

These are the sentences that carry a value inside them, converted to gettext
templates with named placeholders so the translator can move the value to
wherever Arabic wants it rather than being stuck with English word order.
That reordering freedom is the whole reason they became one msgid each
instead of being wrapped fragment by fragment.

%(currency_label)s resolves to د.ع / د.أ in Arabic and IQD / JOD in English,
so these lines pick up the right currency word without a second msgid.
"""

BATCH = {
    "Password reset. The user will be asked to set a new one on next login.":
        "تمت إعادة تعيين كلمة المرور. سيُطلب من المستخدم تعيين كلمة جديدة عند تسجيل الدخول التالي.",

    # ---- admin ----
    "Changes On %(day)s": "التغييرات في %(day)s",
    "Logins On %(day)s": "عمليات الدخول في %(day)s",
    "Role default (%(u)s%%)": "الافتراضي للدور (%(u)s٪)",

    # ---- appointments ----
    "%(orphaned)s appointment(s) need attention — not shown on the grid below":
        "%(orphaned)s موعد بحاجة إلى انتباه — غير معروضة في الجدول أدناه",

    # ---- audits ----
    "Performed by %(sess)s ·": "نُفِّذ بواسطة %(sess)s ·",

    # ---- boarding ----
    "Price per Day (%(currency_label)s)": "السعر اليومي (%(currency_label)s)",
    "Discount (max %(discount_cap)s%%)": "الخصم (بحد أقصى %(discount_cap)s٪)",
    "Clean Up (max %(CLEANUP_CAP)s %(currency_label)s)":
        "الإعفاء عن الفئات القليلة (بحد أقصى %(CLEANUP_CAP)s %(currency_label)s)",

    # ---- cash register ----
    "No money-in/money-out activity recorded on %(day)s.":
        "لا توجد حركة دخول أو خروج أموال مسجلة في %(day)s.",
    "Totals for %(day)s": "إجماليات %(day)s",
    "Perform Audit — %(day)s": "تنفيذ جرد — %(day)s",
    "Cash Counted From the Register (%(currency_label)s)":
        "النقد المعدود من الصندوق (%(currency_label)s)",

    # ---- consignment ----
    "Cost Price (%(currency_label)s)": "سعر التكلفة (%(currency_label)s)",
    "Shelf Value (%(currency_label)s)": "قيمة الرف (%(currency_label)s)",
    "Amount Owed (%(currency_label)s)": "المبلغ المستحق (%(currency_label)s)",
    "Stock a distributor drops off. %(total_count)s receipt(s) on file.":
        "مخزون يورّده المورد. %(total_count)s عملية استلام مسجلة.",
    "Unit Cost (%(currency_label)s)": "تكلفة الوحدة (%(currency_label)s)",
    "Owed to Distributor (%(currency_label)s)": "المستحق للمورد (%(currency_label)s)",
    "Your Markup (%(currency_label)s)": "هامش ربحك (%(currency_label)s)",
    "Settle with %(distributor)s": "التسوية مع %(distributor)s",
    "Amount Paid (%(currency_label)s)": "المبلغ المدفوع (%(currency_label)s)",

    # ---- dashboard ----
    "%(backup_alert)s Open Settings →": "%(backup_alert)s فتح الإعدادات →",
    "Visit set for %(f)s": "زيارة محددة في %(f)s",
    "%(i)s %(i2)s left (threshold %(i3)s)": "المتبقي %(i)s %(i2)s (الحد %(i3)s)",

    # ---- distributors ----
    "Total Amount (%(currency_label)s)": "المبلغ الإجمالي (%(currency_label)s)",
    "Total %(bill)s · Paid %(bill2)s · Balance %(bill3)s %(currency_label)s":
        "الإجمالي %(bill)s · المدفوع %(bill2)s · الرصيد %(bill3)s %(currency_label)s",
    "Suppliers you restock inventory from. %(distributors)s on file.":
        "الموردون الذين تعيد التخزين منهم. %(distributors)s مسجل.",
    "Total Outstanding (%(currency_label)s)": "إجمالي المستحق (%(currency_label)s)",

    # ---- inpatient ----
    "View Full Daily Log History (%(updates)s entries)":
        "عرض سجل التحديثات اليومية الكامل (%(updates)s سجل)",
    "View all %(contacts)s contact attempts": "عرض جميع محاولات التواصل (%(contacts)s)",
    "Discount %% (Max %(discount_cap)s%%)": "الخصم ٪ (بحد أقصى %(discount_cap)s٪)",
    "Record Payment (%(currency_label)s)": "تسجيل دفعة (%(currency_label)s)",

    # ---- insights ----
    "Management-level view over the last %(months_back)s months. Admin only.":
        "عرض إداري لآخر %(months_back)s شهرًا. للإدارة فقط.",
    "Revenue, Last %(months_back)s Months (%(currency_label)s)":
        "الإيرادات، آخر %(months_back)s شهرًا (%(currency_label)s)",
    "Avg. Lifetime Spend / Client (%(currency_label)s)":
        "متوسط إجمالي الإنفاق لكل عميل (%(currency_label)s)",
    "Net of refunds, per month, in %(currency_label)s.":
        "صافي بعد المرتجعات، شهريًا، بـ %(currency_label)s.",
    "Revenue by Category — Monthly Breakdown (%(currency_label)s)":
        "الإيرادات حسب الفئة — التفصيل الشهري (%(currency_label)s)",
    "Visit count & billings generated, last %(months_back)s months.":
        "عدد الزيارات والفواتير الناتجة، آخر %(months_back)s شهرًا.",
    "Total Paid (%(currency_label)s)": "إجمالي المدفوع (%(currency_label)s)",

    # ---- patient history ----
    "Inpatient Stays (%(cases)s)": "فترات التنويم (%(cases)s)",
    "Boarding Sessions (%(boarding_sessions)s)": "فترات الإيواء (%(boarding_sessions)s)",
    "Grooming Sessions (%(grooming_sessions)s)": "جلسات العناية والتصفيف (%(grooming_sessions)s)",
    "Visit History (%(visits)s)": "سجل الزيارات (%(visits)s)",
    "%(patient)s — Full History": "%(patient)s — السجل الكامل",
    "(%(files)s file(s) on record)": "(%(files)s ملف مسجل)",

    # ---- POS / price list / refunds ----
    "Cash Received (%(currency_label)s)": "النقد المستلم (%(currency_label)s)",
    "Sale Price (%(currency_label)s)": "سعر البيع (%(currency_label)s)",
    "Refund Amount (%(currency_label)s)": "مبلغ الاسترداد (%(currency_label)s)",
    "Showing refunds on %(date_filter)s only.":
        "عرض المرتجعات في %(date_filter)s فقط.",
    "Clean Up on original bill: %(r)s %(currency_label)s":
        "الإعفاء عن الفئات القليلة على الفاتورة الأصلية: %(r)s %(currency_label)s",

    # ---- reports ----
    "Revenue from billing & retail sales, COGS from measured usage. Admin only.":
        "الإيرادات من الفوترة ومبيعات التجزئة، وتكلفة البضاعة من الاستهلاك المقاس. للإدارة فقط.",
    "Salaries / Payroll (%(currency_label)s)": "الرواتب / الأجور (%(currency_label)s)",
    "Other OpEx (%(currency_label)s)": "مصاريف تشغيلية أخرى (%(currency_label)s)",

    # ---- footer ----
    "VetClinicSystem IQ v%(app_version)s": "VetClinicSystem IQ الإصدار %(app_version)s",
    "VetClinicSystem JO v%(app_version)s": "VetClinicSystem JO الإصدار %(app_version)s",
}
