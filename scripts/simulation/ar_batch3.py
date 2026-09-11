# -*- coding: utf-8 -*-
"""Arabic translations, batch 3 — inventory, POS, refunds, settings, and the
first tranche of template labels.

Clinical terms chosen here are listed in ARABIC_CLINICAL_REVIEW.md for the
translator to spot-check: BCS, Outpatient/Inpatient, wellness/grooming fields.
They are translated rather than left blank so the release is complete, but
they are the ones §3 reserves, so they are flagged rather than assumed
settled.
"""

_CUR = {}
for _en, _ar in (("IQD", "د.ع"), ("JOD", "د.أ")):
    _CUR.update({
        f"Sale #%(sale_id)s completed — total %(fmt_money)s {_en}.":
            f"تم إتمام البيع رقم %(sale_id)s — الإجمالي %(fmt_money)s {_ar}.",
        f"Service refund of %(rounded_amount)s {_en} recorded.":
            f"تم تسجيل استرداد خدمة بقيمة %(rounded_amount)s {_ar}.",
        f"%(fmt_money)s {_en} logged out of the register.":
            f"تم تسجيل خروج %(fmt_money)s {_ar} من الصندوق.",
        f"Audit recorded for %(day)s: %(status)s of %(fmt_money)s {_en}.":
            f"تم تسجيل الجرد ليوم %(day)s: %(status)s بمقدار %(fmt_money)s {_ar}.",
    })

BATCH = {
    # ---- clinical enums (flagged for review) ----
    "Weight and BCS must be valid numbers.":
        "يجب أن يكون الوزن ودرجة الحالة الجسدية أرقامًا صالحة.",
    "Visit type must be Outpatient or Inpatient.":
        "يجب أن يكون نوع الزيارة عيادات خارجية أو تنويم.",
    "Reason must be Damaged, Expired, or Other.":
        "يجب أن يكون السبب: تالف، أو منتهي الصلاحية، أو غير ذلك.",
    "Liable Party must be Distributor or Clinic.":
        "يجب أن يكون الطرف المسؤول: المورد أو العيادة.",
    "Logged %(quantity)s %(name)s as shrinkage (%(liable_party)s liable).":
        "تم تسجيل %(quantity)s %(name)s كهالك (المسؤولية على %(liable_party)s).",
    "Settlement not found.": "التسوية غير موجودة.",

    # ---- price list / inventory ----
    "Cost Price and Sale Price must be valid numbers.":
        "يجب أن يكون سعر التكلفة وسعر البيع أرقامًا صالحة.",
    "Cost Price and Sale Price can't be negative.":
        "لا يمكن أن يكون سعر التكلفة وسعر البيع سالبين.",
    "That inventory item no longer exists — reload the page and pick again.":
        "هذا الصنف لم يعد موجودًا — أعد تحميل الصفحة واختر مرة أخرى.",
    "%(pid)s added to price list.": "تمت إضافة %(pid)s إلى قائمة الأسعار.",
    "Price list item not found.": "صنف قائمة الأسعار غير موجود.",
    "Price updated.": "تم تحديث السعر.",
    "Item removed from price list.": "تمت إزالة الصنف من قائمة الأسعار.",
    "Cost Price must be a valid number.": "يجب أن يكون سعر التكلفة رقمًا صالحًا.",
    "Cost Price can't be negative.": "لا يمكن أن يكون سعر التكلفة سالبًا.",
    "That distributor no longer exists — reload the page and pick again.":
        "هذا المورد لم يعد موجودًا — أعد تحميل الصفحة واختر مرة أخرى.",
    "%(iid)s added to inventory catalog.": "تمت إضافة %(iid)s إلى دليل الأصناف.",
    "Inventory item not found.": "الصنف غير موجود.",
    "Inventory item updated.": "تم تحديث الصنف.",
    "This item doesn't have a barcode yet.": "لا يوجد باركود لهذا الصنف بعد.",
    "No barcodes selected to print.": "لم يتم اختيار أي باركود للطباعة.",

    # ---- stock audits ----
    "Audit session not found.": "جلسة الجرد غير موجودة.",
    "This audit is confirmed and can no longer be edited.":
        "تم تأكيد هذا الجرد ولم يعد بالإمكان تعديله.",
    "This audit is already confirmed.": "تم تأكيد هذا الجرد بالفعل.",
    "Only a draft audit can be discarded.": "يمكن تجاهل الجرد المسودة فقط.",
    "Draft audit discarded.": "تم تجاهل الجرد المسودة.",

    # ---- POS / refunds ----
    "Sale not found.": "عملية البيع غير موجودة.",
    "No items selected — nothing to refund.": "لم يتم اختيار أي صنف — لا يوجد ما يُسترد.",
    "Invalid item selection.": "اختيار الصنف غير صالح.",
    "Refund quantities must be valid numbers.": "يجب أن تكون كميات الاسترداد أرقامًا صالحة.",
    "One of the selected items isn't part of that sale.":
        "أحد الأصناف المختارة ليس ضمن عملية البيع تلك.",
    "Nothing to refund.": "لا يوجد ما يُسترد.",
    "Refund amount must be a valid number.": "يجب أن يكون مبلغ الاسترداد رقمًا صالحًا.",
    "Refund amount must be greater than 0.": "يجب أن يكون مبلغ الاسترداد أكبر من ٠.",
    "Visit %(visit_id)s not found.": "الزيارة %(visit_id)s غير موجودة.",
    "Inpatient case %(case_id_raw)s not found.": "حالة التنويم %(case_id_raw)s غير موجودة.",
    "Boarding stay %(boarding_id_raw)s not found.": "إقامة الإيواء %(boarding_id_raw)s غير موجودة.",

    # ---- cash register ----
    "Amount must be a valid number.": "يجب أن يكون المبلغ رقمًا صالحًا.",
    "Amount must be greater than 0.": "يجب أن يكون المبلغ أكبر من ٠.",
    "Enter a reason for this payout.": "أدخل سببًا لهذا الصرف.",
    "Counted cash must be a valid number.": "يجب أن يكون النقد المعدود رقمًا صالحًا.",
    "Counted cash can't be negative.": "لا يمكن أن يكون النقد المعدود سالبًا.",

    # ---- settings ----
    "%(title)s must be a whole number.": "يجب أن يكون %(title)s رقمًا صحيحًا.",
    "%(title)s must be between %(lo)s and %(hi)s.": "يجب أن يكون %(title)s بين %(lo)s و%(hi)s.",
    "Not a valid color palette.": "لوحة الألوان غير صالحة.",
    "%(title)s must be a valid time (HH:MM).": "يجب أن يكون %(title)s وقتًا صالحًا (ساعة:دقيقة).",
    "Day Ends At must be after Day Starts At.":
        "يجب أن يكون وقت نهاية اليوم بعد وقت بدايته.",
    "The monitoring ping URL must start with https://":
        "يجب أن يبدأ رابط المراقبة بـ https://",
    "Settings saved.": "تم حفظ الإعدادات.",

    # ---- visit form labels (clinical: flagged for review) ----
    "Doctor": "الطبيب",
    "Weight (KG)": "الوزن (كغم)",
    "BCS (1–9)": "درجة الحالة الجسدية (١–٩)",
    "Admit as Inpatient Now": "تنويم المريض الآن",
    "Wellness Visit?": "زيارة رعاية وقائية؟",
    "Wellness Type": "نوع الرعاية الوقائية",
    "Next Dose Date": "تاريخ الجرعة التالية",
    "Grooming?": "عناية وتصفيف؟",
    "Grooming Notes": "ملاحظات العناية والتصفيف",
    "Admitted Items (Leash, Carrier, Etc.)": "الأغراض المستلمة (رباط، قفص، إلخ)",

    # ---- audit log table ----
    "Who": "من",
    "Action": "الإجراء",
    "Table": "الجدول",
    "Record": "السجل",
    "Field": "الحقل",
    "Old → New": "القديم ← الجديد",
    "Result": "النتيجة",
    "IP": "عنوان الشبكة",
    "Device": "الجهاز",

    # ---- admin users screen ----
    "+ New User": "+ مستخدم جديد",
    "Discount Limit": "حد الخصم",
    "Reset Password": "إعادة تعيين كلمة المرور",
    "New Password": "كلمة مرور جديدة",
    "System role — can't be renamed, deleted, or edited":
        "دور نظامي — لا يمكن إعادة تسميته أو حذفه أو تعديله",
    "Max Discount": "الحد الأقصى للخصم",
    "Max Discount (%%)": "الحد الأقصى للخصم (٪)",
    "Description (optional)": "الوصف (اختياري)",
    "Add a new role": "إضافة دور جديد",
    "New User": "مستخدم جديد",
    "Temporary Password": "كلمة مرور مؤقتة",
    "min. 8 characters": "٨ أحرف على الأقل",
    "Create User": "إنشاء مستخدم",
    "Add Role": "إضافة دور",
    "Role Name": "اسم الدور",
    "Delete role": "حذف الدور",
    "Move affected staff to": "نقل الموظفين المتأثرين إلى",
    "Delete Role": "حذف الدور",

    # ---- appointments ----
    "Pet": "الحيوان",
    "Owner": "المالك",
    "Assigned To": "مُسند إلى",
    "Why": "السبب",
    "New Appointment": "موعد جديد",
    "Pet Name": "اسم الحيوان",
    "Owner Name": "اسم المالك",
    "Book": "حجز",

    # ---- stock audit sheet ----
    "Item": "الصنف",
    "Stock Counted": "المخزون المعدود",
    "Received": "المستلم",
    "Reorder Threshold": "حد إعادة الطلب",
    "Critical?": "حرج؟",
    "Target Coverage (Days)": "التغطية المستهدفة (بالأيام)",
    "Nearest Expiry": "أقرب تاريخ انتهاء",
    "Confirm This Audit?": "تأكيد هذا الجرد؟",
    "Yes, Confirm Permanently": "نعم، تأكيد نهائي",
    "+ Start / Resume Today's Audit": "+ بدء / استئناف جرد اليوم",
    "Performed By": "نُفِّذ بواسطة",
    "Items Filled": "الأصناف المعبأة",
    "Discard": "تجاهل",
    "Bulk Barcode Print": "طباعة باركود مجمّعة",
    "Barcode Label": "ملصق الباركود",

    # ---- boarding form ----
    "+ Add Boarding": "+ إضافة إيواء",
    "Search Patient (Name, Patient ID, Owner Name, or Owner Phone)":
        "ابحث عن مريض (الاسم، رقم المريض، اسم المالك، أو هاتف المالك)",
    "Start Typing…": "ابدأ الكتابة…",
    "Entry Date": "تاريخ الدخول",
    "Expected Dismissal Date": "تاريخ الخروج المتوقع",
    "Allocated Room": "الغرفة المخصصة",
    "Admitted Items (Leash, Bed, Etc.)": "الأغراض المستلمة (رباط، فراش، إلخ)",
    "Auto-suggested from price × nights": "مقترح تلقائيًا من السعر × عدد الليالي",
    "Describe the special need…": "صف الاحتياج الخاص…",
    "Add Boarding": "إضافة إيواء",
    "What's wrong?": "ما المشكلة؟",
    "How?": "كيف؟",
}

BATCH.update(_CUR)
