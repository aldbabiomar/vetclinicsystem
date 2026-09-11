# -*- coding: utf-8 -*-
"""Arabic translations, batch 1 — system, auth, and generic CRUD messages.

Everything here is ARABIC_LOCALIZATION_PLAN §3's "plain, unambiguous,
high-frequency software vocabulary with one obvious correct Arabic rendering".
Modern Standard Arabic, formal register, hamza forms throughout (§2 and the
translator's 2026-09-11 instruction).

Domain vocabulary already agreed in Batch 1 of the question process is reused
verbatim so the app stays internally consistent:
    Clean Up -> الإعفاء عن الفئات القليلة        Discount -> الخصم
    Owners   -> الملاك                            Patients -> المرضى
"""

BATCH = {
    # ---- uploads, numbers, generic input validation ----
    "That file is too large — the limit is %(MAX_UPLOAD_MB)s MB per upload.":
        "الملف كبير جدًا — الحد الأقصى %(MAX_UPLOAD_MB)s ميجابايت لكل رفع.",
    "That number is too large to be a valid value here.":
        "هذا الرقم كبير جدًا ليكون قيمة صالحة هنا.",
    "That phone number doesn't look valid. Please check it and try again.":
        "رقم الهاتف لا يبدو صحيحًا. يرجى التحقق منه والمحاولة مرة أخرى.",
    "That form was missing something the server needed.":
        "النموذج ينقصه شيء يحتاجه الخادم.",

    # ---- authentication ----
    "Incorrect username or password, or account is disabled.":
        "اسم المستخدم أو كلمة المرور غير صحيحة، أو أن الحساب معطّل.",
    "Current password is incorrect.": "كلمة المرور الحالية غير صحيحة.",
    "New password and confirmation don't match.":
        "كلمة المرور الجديدة والتأكيد غير متطابقين.",
    "Password updated.": "تم تحديث كلمة المرور.",
    "Password reset. The user will be asked to set a new one on next login.":
        "تمت إعادة تعيين كلمة المرور. سيُطلب من المستخدم تعيين كلمة جديدة عند تسجيل الدخول التالي.",

    # ---- users and roles ----
    "Fill in a username, full name, and role.":
        "أدخل اسم المستخدم والاسم الكامل والدور.",
    "That username is already taken.": "اسم المستخدم هذا مستخدم بالفعل.",
    "You can't disable your own account.": "لا يمكنك تعطيل حسابك الخاص.",
    "User not found.": "المستخدم غير موجود.",
    "Can't disable the last active Admin.":
        "لا يمكن تعطيل آخر مدير نشط.",
    "User updated.": "تم تحديث المستخدم.",
    "Not a valid role.": "الدور غير صالح.",
    "Can't move the last active Admin out of the Admin role.":
        "لا يمكن نقل آخر مدير نشط خارج دور المدير.",
    "Role updated.": "تم تحديث الدور.",
    "Give the new role a name.": "أعطِ الدور الجديد اسمًا.",
    "A role needs a name.": "الدور يحتاج إلى اسم.",
    "Role not found.": "الدور غير موجود.",
    "Role deleted.": "تم حذف الدور.",
    "That role name is already in use.": "اسم الدور هذا مستخدم بالفعل.",

    # ---- owners / patients: generic CRUD, not clinical judgement ----
    "Owner %(oid)s added.": "تمت إضافة المالك %(oid)s.",
    "Owner not found.": "المالك غير موجود.",
    "Owner updated.": "تم تحديث المالك.",
    "Patient not found.": "المريض غير موجود.",
    "Patient updated.": "تم تحديث المريض.",
    "Visit not found.": "الزيارة غير موجودة.",
    "Distributor not found.": "المورد غير موجود.",
    "Item not found.": "الصنف غير موجود.",

    # ---- months / dates / periods ----
    "Pick a month first.": "اختر الشهر أولًا.",
    "That's not a valid month.": "هذا ليس شهرًا صالحًا.",
    "That date wasn't valid, showing today instead.":
        "التاريخ غير صالح، يتم عرض تاريخ اليوم بدلًا منه.",
    "That date wasn't valid — showing today instead.":
        "التاريخ غير صالح — يتم عرض تاريخ اليوم بدلًا منه.",
    "That date wasn't valid — showing all dates instead.":
        "التاريخ غير صالح — يتم عرض جميع التواريخ بدلًا منه.",
    "That week link wasn't valid, showing the current week instead.":
        "رابط الأسبوع غير صالح، يتم عرض الأسبوع الحالي بدلًا منه.",

    # ---- common buttons and actions ----
    "Save": "حفظ",
    "Cancel": "إلغاء",
    "Delete": "حذف",
    "Edit": "تعديل",
    "Add": "إضافة",
    "Search": "بحث",
    "Close": "إغلاق",
    "Back": "رجوع",
    "Next": "التالي",
    "Print": "طباعة",
    "Export": "تصدير",
    "Confirm": "تأكيد",
    "Update": "تحديث",
    "Remove": "إزالة",
    "Apply": "تطبيق",
    "Clear": "مسح",
    "Reset": "إعادة تعيين",
    "Actions": "الإجراءات",
    "Filter": "تصفية",
    "View": "عرض",
    "Open": "فتح",
    "Done": "تم",
    "Yes": "نعم",
    "No": "لا",
    "All": "الكل",
    "None": "لا شيء",
    "Optional": "اختياري",
    "Required": "مطلوب",

    # ---- common field labels ----
    "Name": "الاسم",
    "Full Name": "الاسم الكامل",
    "Username": "اسم المستخدم",
    "Password": "كلمة المرور",
    "Phone": "الهاتف",
    "Email": "البريد الإلكتروني",
    "Address": "العنوان",
    "Notes": "ملاحظات",
    "Date": "التاريخ",
    "Time": "الوقت",
    "Status": "الحالة",
    "Type": "النوع",
    "Category": "الفئة",
    "Quantity": "الكمية",
    "Unit": "الوحدة",
    "Total": "الإجمالي",
    "Subtotal": "المجموع الفرعي",
    "Amount": "المبلغ",
    "Reason": "السبب",
    "Description": "الوصف",
    "Role": "الدور",
    "Created": "تاريخ الإنشاء",
    "Updated": "تاريخ التحديث",
    "Details": "التفاصيل",
    "Summary": "الملخص",
    "Reference": "المرجع",
    "Method": "الطريقة",
    "Contact Person": "الشخص المسؤول",
}
