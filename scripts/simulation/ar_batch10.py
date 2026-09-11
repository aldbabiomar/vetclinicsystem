# -*- coding: utf-8 -*-
"""Arabic translations, batch 10 — the long multi-line messages (0-21).

These are the error and guidance messages that span several source lines. They
were invisible to the earlier progress count, which used a single-line regex
and therefore reported the catalogue complete while 108 entries sat blank.

Currency-bearing strings are given per app: IQ says IQD, JO says JOD, so the
msgids genuinely differ.
"""

_CUR = {}
for _en, _ar in (("IQD", "د.ع"), ("JOD", "د.أ")):
    _CUR.update({
        f"That change would leave %(fmt_money)s paid against a %(fmt_money2)s {_en} bill. "
        f"Process a service refund for the difference first.":
            f"هذا التغيير سيترك %(fmt_money)s مدفوعًا مقابل فاتورة بقيمة %(fmt_money2)s {_ar}. "
            f"نفّذ استرداد خدمة للفرق أولًا.",
        f"Removing this line would leave %(fmt_money)s paid against a %(fmt_money2)s {_en} bill. "
        f"Process a service refund for the difference first.":
            f"إزالة هذا السطر ستترك %(fmt_money)s مدفوعًا مقابل فاتورة بقيمة %(fmt_money2)s {_ar}. "
            f"نفّذ استرداد خدمة للفرق أولًا.",
    })

BATCH = {
    "You were signed out before that could be saved, so nothing was stored. "
    "Please sign in and enter it again.":
        "تم تسجيل خروجك قبل أن يُحفظ ذلك، فلم يُخزَّن شيء. "
        "يرجى تسجيل الدخول وإدخاله مرة أخرى.",

    "One of the number fields on that form wasn't valid. "
    "Please check the amounts and try again.":
        "أحد الحقول الرقمية في ذلك النموذج غير صالح. "
        "يرجى التحقق من المبالغ والمحاولة مرة أخرى.",

    "This page had been open too long to submit safely, so nothing was saved. "
    "Please check what you entered and submit it again.":
        "بقيت هذه الصفحة مفتوحة مدة أطول من أن تُرسَل بأمان، فلم يُحفظ شيء. "
        "يرجى مراجعة ما أدخلته وإرساله مرة أخرى.",

    "You were signed out while this page was open. Please sign in again — "
    "you may need to re-enter what you were working on.":
        "تم تسجيل خروجك بينما كانت هذه الصفحة مفتوحة. يرجى تسجيل الدخول مرة أخرى — "
        "قد تحتاج إلى إعادة إدخال ما كنت تعمل عليه.",

    "That form was missing something the server needed. "
    "Please reload the page and try again.":
        "النموذج ينقصه شيء يحتاجه الخادم. "
        "يرجى إعادة تحميل الصفحة والمحاولة مرة أخرى.",

    "Too many login attempts from this network. Please wait a few minutes and try again.":
        "محاولات تسجيل دخول كثيرة من هذه الشبكة. يرجى الانتظار بضع دقائق دون محاولة، ثم إعادة المحاولة.",

    "Too many failed attempts for that account. "
    "Try again in about %(minutes_left)s minute(s) (around %(strftime)s).":
        "محاولات فاشلة كثيرة على هذا الحساب. "
        "حاول مرة أخرى بعد نحو %(minutes_left)s دقيقة (حوالي %(strftime)s).",

    "User %(username)s created. They'll be asked to set a new password on first login.":
        "تم إنشاء المستخدم %(username)s. سيُطلب منه تعيين كلمة مرور جديدة عند أول تسجيل دخول.",

    'No role is currently marked "Can be assigned as a vet" — Appointments, New Visit, ' 
    "Grooming, and Inpatient vet pickers will show no options until at least one role has "
    "this turned on.":
        'لا يوجد دور محدد حاليًا بخيار "يمكن إسناده كطبيب بيطري" — لن تُظهر قوائم اختيار ' 
        "الطبيب في المواعيد والزيارة الجديدة والعناية والتنويم أي خيارات حتى يتم تفعيله لدور واحد على الأقل.",

    "Owner %(id)s already has this phone number on file — "
    "add the pet to them instead of creating a new owner.":
        "المالك %(id)s مسجّل بهذا الرقم بالفعل — "
        "أضف الحيوان إليه بدلًا من إنشاء مالك جديد.",

    "That owner phone number doesn't look valid — check the digits and try again.":
        "رقم هاتف المالك لا يبدو صحيحًا — تحقق من الأرقام وحاول مرة أخرى.",

    "Owner %(oid)s already has this phone number on file — "
    "the new pet was added to their existing profile.":
        "المالك %(oid)s مسجّل بهذا الرقم بالفعل — "
        "تمت إضافة الحيوان الجديد إلى ملفه الحالي.",

    "That owner couldn't be saved — check the name and phone number and try again.":
        "تعذّر حفظ هذا المالك — تحقق من الاسم ورقم الهاتف وحاول مرة أخرى.",

    "Inpatient case #%(id)s is still open for this visit — dismiss it there first, "
    "or leave the status as Admitted to Inpatient.":
        "حالة التنويم رقم %(id)s ما زالت مفتوحة لهذه الزيارة — أغلقها من هناك أولًا، "
        "أو اترك الحالة كما هي: محوّل إلى التنويم.",

    "Can't save — this bill has a %(discount_percent)s%% discount applied, but includes "
    "item(s) marked as not discountable: %(join)s. Remove the discount first, or leave "
    "these items off this bill.":
        "تعذّر الحفظ — على هذه الفاتورة خصم %(discount_percent)s٪، لكنها تتضمن أصنافًا "
        "غير قابلة للخصم: %(join)s. أزل الخصم أولًا، أو استبعد هذه الأصناف من الفاتورة.",

    "Can't apply a discount — this bill includes item(s) marked as not discountable: %(join)s.":
        "تعذّر تطبيق الخصم — تتضمن هذه الفاتورة أصنافًا غير قابلة للخصم: %(join)s.",

    "This file's record exists but the file itself is missing from the uploads folder — "
    "it may not have been included in a backup/restore. Check with whoever manages backups "
    "before re-uploading.":
        "سجل هذا الملف موجود لكن الملف نفسه مفقود من مجلد المرفوعات — "
        "ربما لم يكن مضمّنًا في نسخة احتياطية أو استعادة. راجع المسؤول عن النسخ الاحتياطي "
        "قبل إعادة الرفع.",

    "This stay is already picked up, so dates/price/total stayed locked at the billed "
    "figure — only room, admitted items, and special needs were changed.":
        "تم استلام الحيوان من هذه الإقامة بالفعل، لذا بقيت التواريخ والسعر والإجمالي مثبتة على "
        "القيمة المفوترة — لم يتغير سوى الغرفة والأغراض المستلمة والاحتياجات الخاصة.",

    "Can't add — this case has a %(discount_percent)s%% discount applied, but includes "
    "item(s) marked as not discountable: %(join)s. Remove the discount first, or leave "
    "these items off this bill.":
        "تعذّرت الإضافة — على هذه الحالة خصم %(discount_percent)s٪، لكنها تتضمن أصنافًا "
        "غير قابلة للخصم: %(join)s. أزل الخصم أولًا، أو استبعد هذه الأصناف من الفاتورة.",

    "That's not a valid time slot — the schedule may have changed. Reload and try again.":
        "هذه ليست فترة زمنية صالحة — ربما تغيّر الجدول. أعد التحميل وحاول مرة أخرى.",

    "Some selected items are marked as not discountable and can't be added to a bill that "
    "already has a discount applied — remove the discount first, or leave these items off.":
        "بعض الأصناف المختارة غير قابلة للخصم ولا يمكن إضافتها إلى فاتورة عليها خصم بالفعل — "
        "أزل الخصم أولًا، أو استبعد هذه الأصناف.",
}

BATCH.update(_CUR)
