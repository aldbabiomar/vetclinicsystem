# -*- coding: utf-8 -*-
"""Arabic translations, batch 29 — the progress panels.

Every long job in the app reports through one shared progress component: an
update, a rollback, a backup, a restore, and the loading shells the heavy
reports use. Their step labels are sent to the browser as data and drawn in
the panel, so they are display text — and they were the last English a clinic
would see, at the moment it is watching the screen most closely.
"""

BATCH = {
    # --- the update / rollback job
    "Backing up database": "جارٍ أخذ نسخة احتياطية لقاعدة البيانات",
    "Downloading release": "جارٍ تنزيل الإصدار",
    "Validating release": "جارٍ التحقق من الإصدار",
    "Applying database changes": "جارٍ تطبيق تغييرات قاعدة البيانات",
    "Verifying the new version": "جارٍ التحقق من الإصدار الجديد",
    "Switching to the new version": "جارٍ التحويل إلى الإصدار الجديد",
    "Rolling back": "جارٍ التراجع",
    "Update": "تحديث",
    "Update failed.": "فشل التحديث.",
    "Rollback": "تراجع",
    "Rollback failed.": "فشل التراجع.",
    "%(job)s failed to start.": "تعذّر بدء %(job)s.",
    "Done — reloading.": "تم — جارٍ إعادة التحميل.",
    "Done": "تم",
    "Restarting VetClinicSystem JO": "جارٍ إعادة تشغيل VetClinicSystem JO",
    "The app is restarting — this page will reconnect automatically.":
        "التطبيق قيد إعادة التشغيل — ستُعاد هذه الصفحة تلقائيًا.",

    # --- the backup job
    "Checking backup folder": "جارٍ فحص مجلد النسخ الاحتياطي",
    "Dumping database": "جارٍ تفريغ قاعدة البيانات",
    "Applying retention policy": "جارٍ تطبيق سياسة الاحتفاظ",

    # --- the restore job
    "Checking backup file": "جارٍ فحص ملف النسخة الاحتياطية",
    "Restoring database": "جارٍ استعادة قاعدة البيانات",
    "Reconciling schema": "جارٍ مطابقة بنية قاعدة البيانات",
    "Recording result": "جارٍ تسجيل النتيجة",

    # --- the loading shells on the heavy reports
    "Revenue by category": "الإيرادات حسب الفئة",
    "Vet performance": "أداء الأطباء",
    "Client value": "قيمة العملاء",
    "Weekday appointment load": "حِمل المواعيد حسب أيام الأسبوع",
    "Inpatient/boarding occupancy": "إشغال الإقامة المرضية والفندقية",
    "Payment mix": "توزيع طرق الدفع",
    "Cash Register health": "سلامة صندوق النقد",
    "Computing cohort retention grid": "جارٍ حساب جدول الاحتفاظ بالعملاء",
    "Computing distributor balances": "جارٍ حساب أرصدة الموردين",
    "Rebuilding monthly summary": "جارٍ إعادة بناء الملخص الشهري",
}
