# -*- coding: utf-8 -*-
"""Arabic translations, batch 11 — settlements, inventory, audits, refunds,
cash register, and the admin/appointments help text."""

_CUR = {}
for _en, _ar, _note in (("IQD", "د.ع", "250"), ("JOD", "د.أ", None)):
    _CUR.update({
        f"Settlement recorded: %(fmt_money)s {_en} paid of %(fmt_money2)s {_en} owed — "
        f"%(fmt_money3)s {_en} carries forward.":
            f"تم تسجيل التسوية: دُفع %(fmt_money)s {_ar} من أصل %(fmt_money2)s {_ar} مستحقة — "
            f"يُرحَّل %(fmt_money3)s {_ar}.",
        f"This sale has no refundable value left to pay out — the smallest note is "
        f"%(SMALLEST_NOTE)s {_en} and only %(fmt_money)s {_en} of this sale is still refundable.":
            f"لم تعد لهذه العملية قيمة قابلة للاسترداد — أصغر فئة نقدية هي %(SMALLEST_NOTE)s {_ar} "
            f"ولم يتبقَّ سوى %(fmt_money)s {_ar} قابلة للاسترداد من هذه العملية.",
        f"That's more than this sale actually collected (%(fmt_money)s {_en}, after any "
        f"Clean Up applied at sale time) minus what's already been refunded.":
            f"هذا أكثر مما حصّلته هذه العملية فعليًا (%(fmt_money)s {_ar}، بعد أي إعفاء عن الفئات "
            f"القليلة طُبِّق وقت البيع) مطروحًا منه ما تم استرداده بالفعل.",
        f"That's more than the %(fmt_money)s {_en} still refundable against this record.":
            f"هذا أكثر من %(fmt_money)s {_ar} المتبقية القابلة للاسترداد على هذا السجل.",
        f"That's more than the %(fmt_money)s {_en} actually in the register for %(day)s.":
            f"هذا أكثر من %(fmt_money)s {_ar} الموجودة فعليًا في الصندوق ليوم %(day)s.",
    })
_CUR["Heads up: this price isn't a multiple of 250 IQD — totals including this item may "
     "need rounding at checkout (this is handled automatically)."] = (
    "تنبيه: هذا السعر ليس من مضاعفات ٢٥٠ د.ع — قد تحتاج الإجماليات التي تتضمن هذا الصنف "
    "إلى تقريب عند الدفع (يتم ذلك تلقائيًا).")

BATCH = {
    "That inventory item is already linked to %(id)s (%(name)s) — an item can only be "
    "linked from one active Price List row at a time.":
        "هذا الصنف مرتبط بالفعل بـ %(id)s (%(name)s) — لا يمكن ربط الصنف إلا من سطر واحد "
        "نشط في قائمة الأسعار في كل مرة.",

    "Set this item back to Owned on the Consignment Items page before changing its category.":
        "أعد هذا الصنف إلى \"مملوك\" من صفحة أصناف الأمانة قبل تغيير فئته.",

    "This item has consignment activity against it — its distributor can't be changed here. "
    "Create a new inventory item for the new supply source.":
        "على هذا الصنف حركة أمانة — لا يمكن تغيير مورده من هنا. "
        "أنشئ صنفًا جديدًا لمصدر التوريد الجديد.",

    "Audit counts must be valid numbers. The draft was not saved — please correct the "
    "highlighted value(s).":
        "يجب أن تكون أعداد الجرد أرقامًا صالحة. لم تُحفظ المسودة — يرجى تصحيح القيم المميزة.",

    "Audit saved. You can come back and finish it later, or confirm it once it's complete.":
        "تم حفظ الجرد. يمكنك العودة لإكماله لاحقًا، أو تأكيده عند اكتماله.",

    "Audit counts must be valid numbers. Nothing was confirmed — please correct the "
    "highlighted value(s).":
        "يجب أن تكون أعداد الجرد أرقامًا صالحة. لم يتم تأكيد شيء — يرجى تصحيح القيم المميزة.",

    "Nothing has been counted in this audit yet — fill in at least one item before confirming.":
        "لم يتم عدّ أي شيء في هذا الجرد بعد — أدخل صنفًا واحدًا على الأقل قبل التأكيد.",

    "Audit confirmed and locked. Inventory Status and Ordering Sheet now reflect these counts.":
        "تم تأكيد الجرد وقفله. تعكس الآن حالة المخزون وكشف الطلبات هذه الأعداد.",

    "Look up a sale first — a retail refund must be linked to the sale it's refunding.":
        "ابحث عن عملية البيع أولًا — يجب ربط استرداد التجزئة بعملية البيع التي يستردها.",

    "Can't refund %(qty)s %(name)s — only %(remaining)s left refundable from this sale.":
        "تعذّر استرداد %(qty)s %(name)s — لم يتبقَّ سوى %(remaining)s قابلة للاسترداد من هذه العملية.",

    "A service refund must be linked to exactly one visit, inpatient case, or boarding stay.":
        "يجب ربط استرداد الخدمة بزيارة واحدة فقط، أو حالة تنويم واحدة، أو إقامة إيواء واحدة.",

    "Audit recorded for %(day)s: Perfect — counted cash matches the system exactly.":
        "تم تسجيل الجرد ليوم %(day)s: مطابق — النقد المعدود يطابق النظام تمامًا.",

    "Add staff, and add or edit the roles they can be assigned — including what each role "
    "can access and its discount limit.":
        "أضف الموظفين، وأضف أو عدّل الأدوار التي يمكن إسنادها إليهم — بما في ذلك ما يمكن لكل "
        "دور الوصول إليه وحد الخصم الخاص به.",

    'The Role dropdown always reflects whatever roles exist in the Roles & Permissions tab. '
    'A per-user discount override (set at creation, in the New User form) shows here as '
    '"Custom" — most staff just inherit their role\'s limit.':
        'تعكس قائمة الأدوار دائمًا الأدوار الموجودة في تبويب الأدوار والصلاحيات. '
        'يظهر تجاوز الخصم الخاص بمستخدم (يُحدَّد عند الإنشاء في نموذج المستخدم الجديد) هنا '
        'بوصفه "مخصص" — ومعظم الموظفين يرثون حد دورهم.',

    "Whether staff with this role show up as a vet to assign in Appointments, Visits, "
    "Grooming, and Inpatient":
        "ما إذا كان الموظفون بهذا الدور يظهرون كأطباء يمكن إسنادهم في المواعيد والزيارات "
        "والعناية والتنويم",

    "New roles start with everything below unchecked — turn on only what this role needs.":
        "تبدأ الأدوار الجديدة بكل ما يلي غير محدد — فعّل ما يحتاجه هذا الدور فقط.",

    "Pick a role to move them to before this role can be deleted. Nobody is left without a role.":
        "اختر دورًا لنقلهم إليه قبل إمكانية حذف هذا الدور. لا يُترك أحد دون دور.",

    "Weekly schedule of booked appointments. Slot length and hours are set in Settings.":
        "الجدول الأسبوعي للمواعيد المحجوزة. تُضبط مدة الفترة وساعات العمل من الإعدادات.",

    'No role is currently marked "Can be assigned as a vet," so there\'s nothing to '
    'schedule against below. Turn it on for at least one role in Users & Roles →':
        'لا يوجد دور محدد حاليًا بخيار "يمكن إسناده كطبيب بيطري"، لذا لا يوجد ما يُجدوَل عليه '
        'أدناه. فعّله لدور واحد على الأقل من المستخدمون والصلاحيات ←',

    "Still booked, but either the vet assigned is no longer active, or the appointment's "
    "time no longer matches the clinic's current scheduling hours/slot length (Settings). "
    "Cancel and rebook to fix.":
        "ما زال محجوزًا، لكن إما أن الطبيب المُسنَد لم يعد نشطًا، أو أن وقت الموعد لم يعد "
        "يطابق ساعات العمل أو مدة الفترة الحالية للعيادة (الإعدادات). ألغِ الحجز وأعد الحجز للتصحيح.",
}

BATCH.update(_CUR)
