# -*- coding: utf-8 -*-
"""Arabic translations, batch 5 — the remainder: barcodes, inventory status,
ordering sheet, patients, POS, refunds, reports, settings and visit forms.

Completes the catalogue. Clinical fields here (Species, Sex, Reproductive
Status, Case Status, Treatment Plan, Additional Tests / X-Rays) are listed in
ARABIC_CLINICAL_REVIEW.md for spot-checking — they are §3's reserved category,
translated so the release is complete rather than left blank, but flagged.
"""

BATCH = {
    "Password reset. The user will be asked to set a new one on next login.":
        "تمت إعادة تعيين كلمة المرور. سيُطلب من المستخدم تعيين كلمة جديدة عند تسجيل الدخول التالي.",

    # ---- barcodes ----
    "Manage Barcode": "إدارة الباركود",
    "Click to change distributor": "اضغط لتغيير المورد",
    "Scan or type a barcode…": "امسح أو اكتب باركود…",
    "Remove Barcode": "إزالة الباركود",
    "Create Now": "إنشاء الآن",
    "Search by Item Name…": "ابحث باسم الصنف…",

    # ---- inventory status / ordering sheet ----
    "Stock": "المخزون",
    "Threshold": "الحد",
    "Latest Audit": "آخر جرد",
    "Stock Status": "حالة المخزون",
    "Expiry Status": "حالة الانتهاء",
    "Audit Status": "حالة الجرد",
    "Days Left": "الأيام المتبقية",
    "Priority": "الأولوية",
    "Suggested Order Qty": "الكمية المقترحة للطلب",
    "Trend": "الاتجاه",
    "Note": "ملاحظة",

    # ---- auth ----
    "Log In": "تسجيل الدخول",

    # ---- patients (clinical: flagged for review) ----
    "Species": "النوع",
    "Sex": "الجنس",
    "Search Name or Phone…": "ابحث بالاسم أو الهاتف…",
    "Discharged": "تم الإخراج",
    "Open Boarding": "فتح إيواء",
    "Services": "الخدمات",
    "Follow-Up": "المتابعة",
    "Edit Patient Details": "تعديل بيانات المريض",
    "Animal Name": "اسم الحيوان",
    "Reproductive Status": "الحالة التناسلية",
    "Age / DOB Note": "ملاحظة العمر / تاريخ الميلاد",
    "Housing": "بيئة الإيواء",
    "Microchip Number (optional)": "رقم الشريحة (اختياري)",
    "Search ID, Animal, Microchip, Owner, or Phone…":
        "ابحث بالمعرّف أو الحيوان أو الشريحة أو المالك أو الهاتف…",

    # ---- POS ----
    "Scan Barcode or Search Item Name": "امسح الباركود أو ابحث باسم الصنف",
    "Scan Barcode or Type Item Name…": "امسح الباركود أو اكتب اسم الصنف…",
    "Complete Sale": "إتمام البيع",
    "Cashier": "أمين الصندوق",
    "Linked Inventory Item (Retail Only — for POS)":
        "الصنف المرتبط في المخزون (التجزئة فقط — لنقطة البيع)",
    "Checked = a discount can be applied to a bill including this item.":
        "محدد = يمكن تطبيق خصم على فاتورة تتضمن هذا الصنف.",

    # ---- refunds ----
    "Sale ID": "رقم عملية البيع",
    "Find Sale": "البحث عن عملية بيع",
    "Refund Date": "تاريخ الاسترداد",
    "Refund Method": "طريقة الاسترداد",
    "Reason (optional)": "السبب (اختياري)",
    "e.g. wrong item, customer changed mind":
        "مثال: صنف خاطئ، أو غيّر العميل رأيه",
    "Process Retail Refund": "تنفيذ استرداد تجزئة",
    "e.g. service not completed": "مثال: لم تُنفَّذ الخدمة",
    "Process Service Refund": "تنفيذ استرداد خدمة",
    "Processed By": "نُفِّذ بواسطة",

    # ---- reports ----
    "Revenue": "الإيرادات",
    "COGS": "تكلفة البضاعة المباعة",
    "Gross Profit": "إجمالي الربح",
    "OpEx": "المصاريف التشغيلية",
    "Net Profit": "صافي الربح",
    "Net Margin": "هامش الربح الصافي",
    "MoM Change": "التغير الشهري",
    "Save Operating Costs": "حفظ التكاليف التشغيلية",
    "Year": "السنة",
    "YoY Change": "التغير السنوي",
    "Cohort (First Visit)": "المجموعة (الزيارة الأولى)",
    "Size": "الحجم",

    # ---- settings ----
    "Clinic Settings": "إعدادات العيادة",
    "Clinic Name": "اسم العيادة",
    "Location": "الموقع",
    "Clinic Opening Date": "تاريخ افتتاح العيادة",
    "Color Palette": "لوحة الألوان",
    "Audit Overdue After (Days)": "يُعد الجرد متأخرًا بعد (أيام)",
    "Expiry Warning Window (Days)": "مدة التنبيه قبل الانتهاء (أيام)",
    "Day Starts At": "يبدأ اليوم عند",
    "Day Ends At": "ينتهي اليوم عند",
    "Slot Length (Minutes)": "مدة الفترة (بالدقائق)",
    "Backup Folder (on this computer)": "مجلد النسخ الاحتياطي (على هذا الجهاز)",
    "e.g. /Users/you/VetClinicSystemBackups or D:\\\\VetClinicSystemBackups":
        "مثال: /Users/you/VetClinicSystemBackups أو D:\\\\VetClinicSystemBackups",
    "Browse…": "تصفح…",
    "Nightly Backup Time": "وقت النسخ الاحتياطي الليلي",
    "Keep Last N Backups": "الاحتفاظ بآخر عدد من النسخ",
    "Keep Logs For (Days)": "الاحتفاظ بالسجلات لمدة (أيام)",
    "Warn If No Backup For (Days)": "التنبيه إذا لم توجد نسخة خلال (أيام)",
    "Monitoring Ping URL": "رابط المراقبة",
    "https://… (leave blank to disable)": "https://… (اتركه فارغًا للتعطيل)",
    "Save Settings": "حفظ الإعدادات",
    "Back Up Now": "نسخ احتياطي الآن",
    "Started": "بدأ",
    "Triggered By": "بدأه",
    "File": "الملف",
    "Backup File To Restore": "ملف النسخة المراد استعادتها",
    "Browse to a .dump backup file": "تصفح للوصول إلى ملف نسخة .dump",
    "Restore Now": "استعادة الآن",
    "Source File": "الملف المصدر",
    "Updates": "التحديثات",
    "Check for Updates": "التحقق من التحديثات",
    "Update Now": "تحديث الآن",
    "Not Now": "ليس الآن",
    "Rollback to Previous Version": "الرجوع إلى الإصدار السابق",
    "Choose Backup Folder": "اختيار مجلد النسخ الاحتياطي",
    "New folder name": "اسم المجلد الجديد",
    "+ New Folder": "+ مجلد جديد",
    "Select This Folder": "اختيار هذا المجلد",

    # ---- visit forms (clinical: flagged for review) ----
    "Additional Tests / X-Rays": "فحوصات إضافية / أشعة",
    "Add Billed Items": "إضافة أصناف للفاتورة",
    "Search by service, medicine, or item name…":
        "ابحث باسم الخدمة أو الدواء أو الصنف…",
    "Date Billed": "تاريخ الفوترة",
    "Save Billing": "حفظ الفاتورة",
    "Edit Visit": "تعديل الزيارة",
    "Case Status": "حالة الحالة",
    "Visit Type": "نوع الزيارة",
    "History": "التاريخ المرضي",
    "Treatment Plan": "خطة العلاج",
    "Updates Log": "سجل التحديثات",
    "Follow-Up Needed?": "هل المتابعة مطلوبة؟",
    "Follow-Up Status": "حالة المتابعة",
    "Follow-Up Method": "طريقة المتابعة",
    "Log Visit — Existing Patient": "تسجيل زيارة — مريض حالي",
    "Presenting Complaint / Reason for Visit": "الشكوى الحالية / سبب الزيارة",
    "Log Visit": "تسجيل زيارة",
    "Log Visit — New Patient": "تسجيل زيارة — مريض جديد",
    "Owner Phone": "هاتف المالك",
    "Owner Address": "عنوان المالك",
    "Log a Visit": "تسجيل زيارة",
    "Existing Patient": "مريض حالي",
    "New Patient": "مريض جديد",
    "Search by Animal or Owner name…": "ابحث باسم الحيوان أو المالك…",

    # ---- wellness ----
    "Wellness Reminders": "تذكيرات الرعاية الوقائية",
    "Remind From": "التذكير اعتبارًا من",
    "Method?": "الطريقة؟",
}
