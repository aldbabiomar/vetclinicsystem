# -*- coding: utf-8 -*-
"""Arabic translations, batch 19 — the roles matrix and the cash-register ledger.

Both are lists that live in Python (`auth.PERMISSIONS`, and the CASE arms
inside `logic.cash_register_ledger`'s SQL) and reach the page as data, so no
template literal ever contained them. They are declared in `enum_labels.py`
and rendered through `|tr`; `tests/test_enum_labels.py` compares the
declarations against those two sources, and caught a fallback event type
("Payment", for a payment row tied to no visit, case or stay) that this batch
would otherwise have left out.
"""

BATCH = {
    # logic.cash_register_ledger() event types
    "POS Sale": "بيع في نقطة البيع",
    "Visit Payment": "دفعة زيارة",
    "Inpatient Payment": "دفعة تنويم",
    "Boarding Payment": "دفعة إيواء",
    "Payment": "دفعة",

    # auth.PERMISSIONS labels — the roles & permissions matrix
    "Manage Owners": "إدارة المالكين",
    "Manage Patients": "إدارة الحيوانات",
    "Manage Visits": "إدارة الزيارات",
    "Manage Follow-Ups": "إدارة المتابعات",
    "Manage Wellness Plans": "إدارة خطط الوقاية",
    "Manage Grooming": "إدارة العناية والتصفيف",
    "Manage Boarding": "إدارة الإيواء",
    "Manage Appointments": "إدارة المواعيد",
    "Manage Inpatient Cases": "إدارة حالات التنويم",
    "View Inventory Status": "عرض حالة المخزون",
    "Manage Ordering Sheet": "إدارة كشف الطلبات",
    "Manage Audit History": "إدارة سجل الجرد",
    "Manage Inventory Catalog": "إدارة كتالوج المخزون",
    "Manage Distributors": "إدارة الموردين",
    "Process POS Sales": "تنفيذ مبيعات نقطة البيع",
    "View Sales History": "عرض سجل المبيعات",
    "Manage Price List": "إدارة قائمة الأسعار",
    "Manage Refunds": "إدارة المرتجعات",
    "Manage Cash Register": "إدارة صندوق النقد",
    "View Financial Reports": "عرض التقارير المالية",
    "View Insights & Retention": "عرض التحليلات والاحتفاظ بالعملاء",
    "Manage Users & Roles": "إدارة المستخدمين والأدوار",
    "Manage Settings": "إدارة الإعدادات",
    "Manage Backups, Updates & Startup": "إدارة النسخ الاحتياطي والتحديثات والتشغيل",
    "View Logins & Change Log": "عرض تسجيلات الدخول وسجل التغييرات",
    "View Consignment": "عرض الأمانة",
    "Manage Consignment Items": "إدارة أصناف الأمانة",
    "Log Receiving, Returns & Shrinkage": "تسجيل الاستلام والمرتجعات والهالك",
    "Manage Settlements": "إدارة التسويات",
}
