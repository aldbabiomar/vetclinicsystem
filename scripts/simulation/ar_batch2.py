# -*- coding: utf-8 -*-
"""Arabic translations, batch 2 — validation and CRUD messages across the
clinical, consignment and admin blueprints.

MSA, formal register, hamza forms. Domain terms reuse the vocabulary already
agreed with the translator so the app stays internally consistent:
    Clean Up   -> الإعفاء عن الفئات القليلة       Discount -> الخصم
    Shrinkage  -> الهالك                          Settlements -> التسويات
    Boarding   -> الإيواء                          Inpatient -> التنويم

Currency-bearing strings appear twice, once per app: IQ renders IQD and JO
renders JOD, so the msgids genuinely differ and each needs its own entry.
"""

_CUR = {}
for _cur_en, _cur_ar in (("IQD", "د.ع"), ("JOD", "د.أ")):
    _CUR.update({
        f"That's more than the remaining balance of %(fmt_money)s {_cur_en} on this visit.":
            f"هذا أكثر من الرصيد المتبقي البالغ %(fmt_money)s {_cur_ar} على هذه الزيارة.",
        f"That's more than the remaining balance of %(fmt_money)s {_cur_en} on this stay.":
            f"هذا أكثر من الرصيد المتبقي البالغ %(fmt_money)s {_cur_ar} على هذه الإقامة.",
        f"That's more than the remaining balance of %(fmt_money)s {_cur_en} on this case.":
            f"هذا أكثر من الرصيد المتبقي البالغ %(fmt_money)s {_cur_ar} على هذه الحالة.",
        f"That's more than the remaining balance of %(fmt_money)s {_cur_en} on this bill.":
            f"هذا أكثر من الرصيد المتبقي البالغ %(fmt_money)s {_cur_ar} على هذه الفاتورة.",
        f"That's more than the %(fmt_money)s {_cur_en} owed for this period.":
            f"هذا أكثر من المبلغ المستحق لهذه الفترة البالغ %(fmt_money)s {_cur_ar}.",
        f"Settlement recorded: %(fmt_money)s {_cur_en} paid, settled in full.":
            f"تم تسجيل التسوية: دُفع %(fmt_money)s {_cur_ar}، وتمت التسوية بالكامل.",
    })

BATCH = {
    # ---- reports / operating costs ----
    "Operating costs must be valid numbers.": "يجب أن تكون التكاليف التشغيلية أرقامًا صالحة.",
    "Operating costs can't be negative.": "لا يمكن أن تكون التكاليف التشغيلية سالبة.",
    "Operating costs saved for %(month)s.": "تم حفظ التكاليف التشغيلية لشهر %(month)s.",

    # ---- discount caps / roles ----
    "Custom discount override must be a whole number.":
        "يجب أن يكون تجاوز الخصم المخصص رقمًا صحيحًا.",
    "Custom discount override must be between 0 and 100.":
        "يجب أن يكون تجاوز الخصم المخصص بين ٠ و١٠٠.",
    "Max Discount must be a whole number.": "يجب أن يكون الحد الأقصى للخصم رقمًا صحيحًا.",
    "Max Discount must be between 0 and 100.": "يجب أن يكون الحد الأقصى للخصم بين ٠ و١٠٠.",
    "The Admin role can't be edited.": "لا يمكن تعديل دور المدير.",
    "The Admin role can't be deleted.": "لا يمكن حذف دور المدير.",
    "Pick a role to move the affected staff to before deleting this one.":
        "اختر دورًا لنقل الموظفين المتأثرين إليه قبل حذف هذا الدور.",

    # ---- owners / patients ----
    "That phone number doesn't look valid — check the digits and try again.":
        "رقم الهاتف لا يبدو صحيحًا — تحقق من الأرقام وحاول مرة أخرى.",
    "That phone number is already on file for another owner.":
        "رقم الهاتف هذا مسجّل بالفعل لمالك آخر.",
    "That microchip number doesn't look valid — check the digits and try again.":
        "رقم الشريحة لا يبدو صحيحًا — تحقق من الأرقام وحاول مرة أخرى.",
    "That microchip number is already on another patient's record.":
        "رقم الشريحة هذا مسجّل بالفعل في سجل مريض آخر.",

    # ---- visits ----
    "Pick a patient from the search results before logging a visit.":
        "اختر مريضًا من نتائج البحث قبل تسجيل الزيارة.",
    "Weight can't be negative.": "لا يمكن أن يكون الوزن سالبًا.",
    "An inpatient case was opened for this visit.": "تم فتح حالة تنويم لهذه الزيارة.",
    "Visit updated.": "تم تحديث الزيارة.",

    # ---- billing ----
    "Add at least one billed item.": "أضف صنفًا واحدًا على الأقل إلى الفاتورة.",
    "Manual amount must be a valid number.": "يجب أن يكون المبلغ اليدوي رقمًا صالحًا.",
    "Manual Entry requires a Billed Amount greater than 0.":
        "الإدخال اليدوي يتطلب مبلغًا مفوترًا أكبر من ٠.",
    "Some quantities weren't valid numbers and were skipped.":
        "بعض الكميات لم تكن أرقامًا صالحة وتم تجاهلها.",
    "Some selected items no longer exist in the Price List and were skipped.":
        "بعض الأصناف المختارة لم تعد موجودة في قائمة الأسعار وتم تجاهلها.",
    "Billing saved.": "تم حفظ الفاتورة.",
    "Discount must be a valid number.": "يجب أن يكون الخصم رقمًا صالحًا.",
    "Save the bill first — a discount needs something to apply to.":
        "احفظ الفاتورة أولًا — الخصم يحتاج إلى ما يُطبَّق عليه.",
    "%(percent)s%% discount applied.": "تم تطبيق خصم %(percent)s٪.",
    "Payment amount must be a valid number.": "يجب أن يكون مبلغ الدفعة رقمًا صالحًا.",
    "Payment amount must be greater than 0.": "يجب أن يكون مبلغ الدفعة أكبر من ٠.",
    "Payment amount must be greater than zero.": "يجب أن يكون مبلغ الدفعة أكبر من صفر.",
    "Clean Up amount must be a valid number.":
        "يجب أن تكون قيمة الإعفاء عن الفئات القليلة رقمًا صالحًا.",
    "Payment recorded.": "تم تسجيل الدفعة.",

    # ---- attachments ----
    "No file selected.": "لم يتم اختيار أي ملف.",
    "File not found.": "الملف غير موجود.",
    "File not found — it may have already been deleted.":
        "الملف غير موجود — ربما تم حذفه بالفعل.",
    "Deleted %(original_name)s.": "تم حذف %(original_name)s.",

    # ---- worklists ----
    "Follow-up status updated.": "تم تحديث حالة المتابعة.",
    "Wellness reminder updated.": "تم تحديث تذكير الرعاية الوقائية.",
    "Grooming entry updated.": "تم تحديث سجل العناية و تصفيف الحيوان.",

    # ---- boarding ----
    "Pick a patient first.": "اختر مريضًا أولًا.",
    "Pick a patient from the search results first.": "اختر مريضًا من نتائج البحث أولًا.",
    "Price per Day and Total must be valid numbers.":
        "يجب أن يكون السعر اليومي والإجمالي أرقامًا صالحة.",
    "Price per Day and Total can't be negative.":
        "لا يمكن أن يكون السعر اليومي والإجمالي سالبين.",
    "Boarding session added.": "تمت إضافة فترة الإيواء.",
    "Boarding session not found.": "فترة الإيواء غير موجودة.",
    "A stay can't end before it starts — check the dates.":
        "لا يمكن أن تنتهي الإقامة قبل أن تبدأ — تحقق من التواريخ.",
    "Boarding session updated.": "تم تحديث فترة الإيواء.",
    "Marked as picked up.": "تم وضع علامة الاستلام.",
    "Describe what's wrong before submitting.": "صف المشكلة قبل الإرسال.",
    "Incident logged.": "تم تسجيل الحادثة.",

    # ---- inpatient ----
    "Patient admitted.": "تم تنويم المريض.",
    "Inpatient case not found.": "حالة التنويم غير موجودة.",
    "A case can't be discharged before it was admitted — check the dates.":
        "لا يمكن إخراج الحالة قبل تاريخ تنويمها — تحقق من التواريخ.",
    "Case updated.": "تم تحديث الحالة.",
    "Update logged.": "تم تسجيل التحديث.",
    "Update edited.": "تم تعديل التحديث.",
    "Contact attempt logged.": "تم تسجيل محاولة التواصل.",
    "%(added)s procedure(s) added to the bill.": "تمت إضافة %(added)s إجراء إلى الفاتورة.",
    "That billing line was already removed.": "سطر الفاتورة هذا تمت إزالته بالفعل.",
    "Line removed.": "تمت إزالة السطر.",

    # ---- appointments ----
    "Appointment date is required.": "تاريخ الموعد مطلوب.",
    "Pick a valid, active vet for this appointment.":
        "اختر طبيبًا بيطريًا نشطًا وصالحًا لهذا الموعد.",
    "That slot is already booked for this vet/groomer.":
        "هذه الفترة محجوزة بالفعل لهذا الطبيب أو مقدّم العناية.",
    "Appointment booked.": "تم حجز الموعد.",
    "Appointment not found.": "الموعد غير موجود.",
    "Appointment cancelled.": "تم إلغاء الموعد.",

    # ---- distributors ----
    "Lead Time (Days) must be a whole number.": "يجب أن تكون مدة التوريد (بالأيام) رقمًا صحيحًا.",
    "Lead Time (Days) can't be negative.": "لا يمكن أن تكون مدة التوريد (بالأيام) سالبة.",
    "%(did)s added.": "تمت إضافة %(did)s.",
    "Distributor updated.": "تم تحديث المورد.",
    "Distributor deleted.": "تم حذف المورد.",

    # ---- distributor bills ----
    "Total amount must be a valid number.": "يجب أن يكون المبلغ الإجمالي رقمًا صالحًا.",
    "Total amount must be greater than zero.": "يجب أن يكون المبلغ الإجمالي أكبر من صفر.",
    "Bill %(bid)s logged.": "تم تسجيل الفاتورة %(bid)s.",
    "Bill not found.": "الفاتورة غير موجودة.",
    "Delete the payments on this bill first.": "احذف الدفعات على هذه الفاتورة أولًا.",
    "Bill deleted.": "تم حذف الفاتورة.",
    "Payment not found.": "الدفعة غير موجودة.",
    "Payment deleted.": "تم حذف الدفعة.",

    # ---- consignment ----
    "Pick a Consignment item first.": "اختر صنفًا بنظام الأمانة أولًا.",
    "Quantity and Unit Cost must be valid numbers.":
        "يجب أن تكون الكمية وتكلفة الوحدة أرقامًا صالحة.",
    "Quantity must be greater than 0.": "يجب أن تكون الكمية أكبر من ٠.",
    "Unit Cost can't be negative.": "لا يمكن أن تكون تكلفة الوحدة سالبة.",
    "Received %(quantity)s %(name)s.": "تم استلام %(quantity)s %(name)s.",
    "Quantity must be a valid number.": "يجب أن تكون الكمية رقمًا صالحًا.",
    "Returned %(quantity)s %(name)s to %(distributor_id)s.":
        "تمت إعادة %(quantity)s %(name)s إلى %(distributor_id)s.",
    "Amount Paid must be a valid number.": "يجب أن يكون المبلغ المدفوع رقمًا صالحًا.",
    "Amount Paid can't be negative.": "لا يمكن أن يكون المبلغ المدفوع سالبًا.",
    "There's nothing to settle for this distributor yet.":
        "لا يوجد ما يستوجب التسوية مع هذا المورد حتى الآن.",
}

BATCH.update(_CUR)
