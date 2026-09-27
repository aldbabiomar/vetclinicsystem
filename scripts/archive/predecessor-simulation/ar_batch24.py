# -*- coding: utf-8 -*-
"""Arabic translations, batch 24 — the clinic's terminology for three features.

Renamed by the clinic on 2026-09-11:

    Inpatient   التنويم    ->  الإقامة المرضية
    Boarding    الإيواء    ->  الإقامة الفندقية
    Refunds     المرتجعات  ->  المرتجعات النقدية

Three things a find-and-replace would have got wrong, which is why every one
of these 60-odd entries is written out rather than substituted:

1. **"تنويم" is both a noun and a verb.** As a noun it is the ward — that is
   the one being renamed. As a masdar it is the ACT of admitting: "تنويم
   المريض" is "admit the patient", and swapping a noun phrase into it gives
   "الإقامة المرضية المريض", which is not Arabic. Every verbal use becomes
   **إدخال** (admit / admission), which the catalogue already used in places
   ("الحيوانات المُدخلة حاليًا"). So "Admit Patient" is إدخال المريض and
   "Admission Date" is تاريخ الإدخال, while "Inpatient Cases" is حالات
   الإقامة المرضية.

2. **"المرتجعات" means two different things in this app.** Refunds return
   MONEY to a client; consignment returns send STOCK back to a distributor.
   Only the first becomes المرتجعات النقدية. The consignment side was already
   disambiguated (`Returns` → المرتجعات إلى المورد, `Consignment Returns` →
   مرتجعات الأمانة) and is deliberately left alone — calling a distributor's
   stock return "cash returns" would be worse than the ambiguity.

3. **`Housing` is بيئة الإيواء and does NOT change.** It is the patient's
   living environment — Indoor / Outdoor / Stray — and has nothing to do with
   the boarding service that happens to share the word.

The hamza form is used throughout (الإقامة, not الاقامة), per the standing
decision recorded in ARABIC_TRANSLATION_QUESTIONS.md batch 1.
"""

BATCH = {
    # ---- Inpatient: the feature, as a noun
    "Inpatient": "الإقامة المرضية",
    "Inpatient Cases": "حالات الإقامة المرضية",
    "Manage Inpatient Cases": "إدارة حالات الإقامة المرضية",
    "Admitted to Inpatient": "محوّل إلى الإقامة المرضية",
    "Inpatient Payment": "دفعة إقامة مرضية",
    "Inpatient Case ID": "رقم حالة الإقامة المرضية",
    "Inpatient Case %(case_id)s": "حالة إقامة مرضية %(case_id)s",
    "Inpatient case not found.": "حالة الإقامة المرضية غير موجودة.",
    "Inpatient case %(case_id_raw)s not found.":
        "حالة الإقامة المرضية %(case_id_raw)s غير موجودة.",
    "An inpatient case was opened for this visit.":
        "تم فتح حالة إقامة مرضية لهذه الزيارة.",
    "No inpatient cases.": "لا توجد حالات إقامة مرضية.",
    "Active Inpatient Cases": "حالات الإقامة المرضية النشطة",
    "Avg. Inpatient Stay (Days)": "متوسط مدة الإقامة المرضية (بالأيام)",
    "Inpatient Stays (%(cases)s)": "فترات الإقامة المرضية (%(cases)s)",
    "Export Inpatient (PDF)": "تصدير الإقامة المرضية (PDF)",
    "Inpatient & Boarding Load": "حِمل الإقامة المرضية والفندقية",
    "Visit type must be Outpatient or Inpatient.":
        "يجب أن يكون نوع الزيارة عيادات خارجية أو إقامة مرضية.",
    "Clinical staff — patient care, visits, and inpatient cases.":
        "الطاقم السريري — رعاية الحيوانات والزيارات وحالات الإقامة المرضية.",
    "Inpatient case #%(id)s is still open for this visit — dismiss it there first, "
    "or leave the status as Admitted to Inpatient.":
        "حالة الإقامة المرضية رقم %(id)s ما زالت مفتوحة لهذه الزيارة — أغلقها من هناك "
        "أولًا، أو اترك الحالة كما هي: محوّل إلى الإقامة المرضية.",

    # ---- Inpatient: the ACT of admitting — a verb, so إدخال, not the noun
    "Admit": "إدخال",
    "Admit Patient": "إدخال المريض",
    "+ Admit Patient": "+ إدخال مريض",
    "Admit as Inpatient Now": "إدخال المريض للإقامة المرضية الآن",
    "Admitted": "تم الإدخال",
    "Patient admitted.": "تم إدخال المريض.",
    "Admission Date": "تاريخ الإدخال",
    "Admitted %(admission_date)s": "أُدخل في %(admission_date)s",
    "A case can't be discharged before it was admitted — check the dates.":
        "لا يمكن إخراج الحالة قبل تاريخ إدخالها — تحقق من التواريخ.",

    # ---- Boarding
    "Boarding": "الإقامة الفندقية",
    "Manage Boarding": "إدارة الإقامة الفندقية",
    "Boarding Payment": "دفعة إقامة فندقية",
    "Boarding ID": "رقم الإقامة الفندقية",
    "Boarding %(boarding_id)s": "إقامة فندقية %(boarding_id)s",
    "Add Boarding": "إضافة إقامة فندقية",
    "+ Add Boarding": "+ إضافة إقامة فندقية",
    "Open Boarding": "فتح إقامة فندقية",
    "Currently Boarding": "في الإقامة الفندقية حاليًا",
    "Boarding session added.": "تمت إضافة فترة الإقامة الفندقية.",
    "Boarding session not found.": "فترة الإقامة الفندقية غير موجودة.",
    "Boarding session updated.": "تم تحديث فترة الإقامة الفندقية.",
    "No boarding sessions on record.": "لا توجد فترات إقامة فندقية مسجلة.",
    "Boarding stay %(boarding_id_raw)s not found.":
        "الإقامة الفندقية %(boarding_id_raw)s غير موجودة.",
    "Active Boarding Stays": "الإقامات الفندقية النشطة",
    "Avg. Boarding Stay (Days)": "متوسط مدة الإقامة الفندقية (بالأيام)",
    "Boarding Sessions (%(boarding_sessions)s)":
        "فترات الإقامة الفندقية (%(boarding_sessions)s)",
    "View boarding record →": "عرض سجل الإقامة الفندقية →",
    "Same-day boarding is billed as 1 night.":
        "الإقامة الفندقية في اليوم نفسه تُفوتر ليلة واحدة.",
    "%(total_count)s boarding session(s).": "%(total_count)s فترة إقامة فندقية.",
    "%(total_count)s boarding session(s) currently boarding.":
        "%(total_count)s فترة إقامة فندقية جارية حاليًا.",

    # ---- Refunds: money back to a client. NOT the consignment returns.
    "Refunds": "المرتجعات النقدية",
    "Manage Refunds": "إدارة المرتجعات النقدية",
    "Recent Refunds": "المرتجعات النقدية الأخيرة",
    "Showing refunds on %(date_filter)s only.":
        "عرض المرتجعات النقدية في %(date_filter)s فقط.",
    "No refunds recorded on %(day)s.": "لا توجد مرتجعات نقدية مسجلة في %(day)s.",
    "No refunds recorded yet.": "لا توجد مرتجعات نقدية مسجلة بعد.",
    "Net of refunds, per month, in %(currency_label)s.":
        "صافي بعد المرتجعات النقدية، شهريًا، بـ %(currency_label)s.",

    # ---- sentences carrying two or three of the renamed terms at once
    "A service refund must be linked to exactly one visit, inpatient case, or "
    "boarding stay.":
        "يجب ربط استرداد الخدمة بزيارة واحدة فقط، أو حالة إقامة مرضية واحدة، أو "
        "إقامة فندقية واحدة.",
    "Every POS sale, Visit/Inpatient/Boarding payment, and refund on %(day)s — for "
    "end-of-day cash-up against what's physically in the till.":
        "كل عملية بيع في نقطة البيع، ودفعات الزيارات والإقامة المرضية والإقامة "
        "الفندقية، والمرتجعات النقدية في %(day)s — لجرد نهاية اليوم مقابل الموجود "
        "فعليًا في الصندوق.",
    "From visit, inpatient & boarding payments (walk-in POS retail sales aren't "
    "linked to a client in this system).":
        "من دفعات الزيارات والإقامة المرضية والإقامة الفندقية (مبيعات التجزئة "
        "المباشرة في نقطة البيع غير مرتبطة بعميل في هذا النظام).",
    "Patients currently admitted for boarding or ongoing treatment. Use \"All Cases\" "
    "to include discharged patients, or \"Balance Due\" for discharged cases still "
    "owing money (e.g. a procedure billed after the patient already left). "
    "%(total_count)s shown.":
        "الحيوانات المُدخلة حاليًا للإقامة الفندقية أو لعلاج مستمر. استخدم \"كل "
        "الحالات\" لتضمين الحيوانات المخرَجة، أو \"رصيد مستحق\" للحالات المخرَجة التي "
        "ما زال عليها مبلغ (مثل إجراء فُوتر بعد خروج الحيوان). المعروض %(total_count)s.",
    "Removes a revenue amount only — no stock is touched. Enter %(exactly_one)s of "
    "Visit ID, Inpatient Case ID or Boarding ID: the refund reverses that specific "
    "record, and the amount is capped at what is still refundable against it. A "
    "goodwill refund with no record behind it belongs in Cash Register instead.":
        "يزيل مبلغ إيراد فقط — دون المساس بالمخزون. أدخل %(exactly_one)s من رقم "
        "الزيارة أو رقم حالة الإقامة المرضية أو رقم الإقامة الفندقية: يعكس الاسترداد "
        "ذلك السجل تحديدًا، والمبلغ محدود بما تبقّى قابلًا للاسترداد عليه. أما "
        "الاسترداد كبادرة حسن نية دون سجل خلفه فمكانه صندوق النقد.",
    "This sale had a {cleanup} %(currency_label)s Clean Up applied — total refunds "
    "against it can't exceed what was actually collected ({total} %(currency_label)s).":
        "طُبِّق على عملية البيع هذه إعفاء عن الفئات القليلة بمقدار {cleanup} "
        "%(currency_label)s — لا يمكن أن تتجاوز المرتجعات النقدية عليها ما حُصِّل "
        "فعليًا ({total} %(currency_label)s).",
    "No role is currently marked \"Can be assigned as a vet\" — Appointments, New "
    "Visit, Grooming, and Inpatient vet pickers will show no options until at least "
    "one role has this turned on.":
        "لا يوجد دور محدد حاليًا بخيار \"يمكن إسناده كطبيب بيطري\" — لن تُظهر قوائم "
        "اختيار الطبيب في المواعيد والزيارة الجديدة والعناية والإقامة المرضية أي "
        "خيارات حتى يتم تفعيله لدور واحد على الأقل.",
    "Whether staff with this role show up as a vet to assign in Appointments, "
    "Visits, Grooming, and Inpatient":
        "ما إذا كان الموظفون بهذا الدور يظهرون كأطباء يمكن إسنادهم في المواعيد "
        "والزيارات والعناية والإقامة المرضية",
}
