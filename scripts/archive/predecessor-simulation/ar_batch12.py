# -*- coding: utf-8 -*-
"""Arabic translations, batch 12 — audit help text, consignment explanations,
error pages and insights commentary."""

BATCH = {
    "— stock level at or below which this item is flagged LOW STOCK; leave blank to keep "
    "the last value set for this item.":
        "— مستوى المخزون الذي يُعلَّم عنده الصنف كمخزون منخفض أو أقل منه؛ اتركه فارغًا "
        "للإبقاء على آخر قيمة مضبوطة لهذا الصنف.",

    "— how many days of stock you want on hand when reordering; leave blank to keep the "
    "last value set (defaults to 30 if never set).":
        "— كم يومًا من المخزون تريد توفره عند إعادة الطلب؛ اتركه فارغًا للإبقاء على آخر قيمة "
        "مضبوطة (الافتراضي ٣٠ إن لم تُضبط من قبل).",

    "Continuing will confirm the audit and it can't be edited after. If you intend to save "
    "it for later, click Cancel and use Save instead.":
        "المتابعة ستؤكد الجرد ولن يمكن تعديله بعدها. إن كنت تنوي حفظه لوقت لاحق، اضغط إلغاء "
        "واستخدم حفظ بدلًا من ذلك.",

    "One session per shelf-walk. Only Confirmed audits count toward Inventory Status and "
    "the Ordering Sheet. %(total_count)s shown.":
        "جلسة واحدة لكل جولة على الرفوف. تُحتسب عمليات الجرد المؤكدة فقط في حالة المخزون "
        "وكشف النواقص. المعروض %(total_count)s.",

    "One or more barcodes could not be rendered — check the flagged item(s) below before printing.":
        "تعذّر عرض باركود واحد أو أكثر — تحقق من الأصناف المميزة أدناه قبل الطباعة.",

    "Check this to report any chronic diseases or custom requirements for the stay "
    "(medication schedule, dietary restrictions, mobility issues, etc.).":
        "حدد هذا للإبلاغ عن أي أمراض مزمنة أو متطلبات خاصة بالإقامة "
        "(جدول الأدوية، قيود غذائية، صعوبات في الحركة، وغيرها).",

    "Notes on file but Special Needs is unchecked — they won't be saved unless you check the box.":
        "توجد ملاحظات مسجلة لكن خانة الاحتياجات الخاصة غير محددة — لن تُحفظ ما لم تحدد الخانة.",

    "Only Cash is audited here — Card and Transfer settle electronically and can't be "
    "counted out of a drawer.":
        "يُجرد النقد فقط هنا — تُسوّى البطاقة والحوالة إلكترونيًا ولا يمكن عدّها من الصندوق.",

    'Retail inventory items. Check "Consignment?" and pick a distributor to attach one and '
    'start logging receiving/shrinkage/returns against it — check the box for as many items '
    'as you need, then save them all at once.':
        'أصناف مخزون التجزئة. حدد "أمانة؟" واختر موردًا لربط الصنف والبدء بتسجيل الاستلام '
        'والهالك والمرتجعات عليه — حدد الخانة لأي عدد تحتاجه من الأصناف، ثم احفظها جميعًا دفعة واحدة.',

    "Distributor-owned stock on your shelves. %(rows)s distributor(s) with Consignment items.":
        "مخزون مملوك للمورد على رفوفك. %(rows)s مورد لديهم أصناف أمانة.",

    "Unsold stock handed back to the distributor. %(total_count)s return(s) on file. "
    "No revenue, COGS, or settlement impact — nothing sold, so nothing owed either way.":
        "مخزون غير مباع أُعيد إلى المورد. %(total_count)s مرتجع مسجل. "
        "لا أثر على الإيرادات أو تكلفة البضاعة أو التسوية — لم يُبع شيء، فلا مستحقات في أي اتجاه.",

    "What sold, what's owed the distributor, and your markup — priced at what each sale "
    "actually charged and cost at the time, not today's Price List.":
        "ما بيع، وما هو مستحق للمورد، وهامش ربحك — مسعّرة بما حصّلته كل عملية بيع وبتكلفتها "
        "وقتها، لا بقائمة أسعار اليوم.",

    "A partial payment carries the remainder forward as the starting balance for the next settlement.":
        "الدفعة الجزئية تُرحّل المتبقي ليكون الرصيد الافتتاحي للتسوية التالية.",

    "Clinic-liable shrinkage adds to what's owed the distributor at settlement — they're "
    "still owed for stock lost on your side. Distributor-liable shrinkage adds nothing — "
    "they absorb that loss directly.":
        "الهالك الذي تتحمله العيادة يُضاف إلى المستحق للمورد عند التسوية — يبقى له حق في "
        "المخزون المفقود لديك. أما الهالك الذي يتحمله المورد فلا يُضاف شيئًا — فهو يتحمل تلك "
        "الخسارة مباشرة.",

    "This month's operating costs haven't been entered yet — add them on the Monthly P&L "
    "page before the month closes.":
        "لم تُدخل التكاليف التشغيلية لهذا الشهر بعد — أضفها في صفحة الأرباح والخسائر الشهرية "
        "قبل إغلاق الشهر.",

    "You're seeing this because you can change Settings. It will come back next time you "
    "sign in, until the problem below is fixed.":
        "تظهر لك هذه الرسالة لأن بإمكانك تغيير الإعدادات. ستعود في المرة القادمة التي تسجل "
        "فيها الدخول، حتى تُحل المشكلة أدناه.",

    "Your role doesn't have access to this page. If that seems wrong, check with an Admin.":
        "دورك لا يملك صلاحية الوصول إلى هذه الصفحة. إن بدا ذلك غير صحيح، راجع أحد المديرين.",

    "The page you're looking for doesn't exist, or may have been moved or deleted.":
        "الصفحة التي تبحث عنها غير موجودة، أو ربما نُقلت أو حُذفت.",

    "This wasn't your fault — an unexpected error happened while handling that page. "
    "Copy the box below and send it along and it can be looked into.":
        "لم يكن هذا خطأك — حدث خطأ غير متوقع أثناء معالجة تلك الصفحة. "
        "انسخ المربع أدناه وأرسله ليتم فحص المشكلة.",

    "Error ID: %(error_id)s Time: %(error_time)s Page: %(request_line)s Type: %(exc_type)s "
    "Message: %(exc_message)s %(traceback_text)s":
        "معرّف الخطأ: %(error_id)s الوقت: %(error_time)s الصفحة: %(request_line)s "
        "النوع: %(exc_type)s الرسالة: %(exc_message)s %(traceback_text)s",

    "Ongoing grooming requests logged as part of a visit. %(total_count)s shown.":
        "طلبات العناية والتصفيف الجارية المسجلة ضمن زيارة. المعروض %(total_count)s.",

    "Cash vs. card, last %(months_back)s months — a useful trust/adoption signal for a new clinic.":
        "النقد مقابل البطاقة، آخر %(months_back)s شهرًا — مؤشر مفيد على الثقة والإقبال لعيادة جديدة.",

    "From visit, inpatient & boarding payments (walk-in POS retail sales aren't linked to "
    "a client in this system).":
        "من دفعات الزيارات والتنويم والإيواء (مبيعات التجزئة المباشرة في نقطة البيع غير "
        "مرتبطة بعميل في هذا النظام).",

    'Baghdad work week (Sunday–Thursday) shown first; Friday/Saturday is the weekend. '
    '"Fulfillment" compares appointments booked that weekday against visits logged on the '
    'same weekday system-wide — an approximation, since appointments aren\'t linked to a '
    'specific visit record in this system.':
        'يُعرض أسبوع العمل في بغداد (الأحد–الخميس) أولًا؛ والجمعة والسبت عطلة نهاية الأسبوع. '
        'تقارن "نسبة الإنجاز" المواعيد المحجوزة في ذلك اليوم بالزيارات المسجلة في اليوم نفسه '
        'على مستوى النظام — وهي تقديرية، لأن المواعيد غير مرتبطة بسجل زيارة محدد في هذا النظام.',

    'Amman work week (Sunday–Thursday) shown first; Friday/Saturday is the weekend. '
    '"Fulfillment" compares appointments booked that weekday against visits logged on the '
    'same weekday system-wide — an approximation, since appointments aren\'t linked to a '
    'specific visit record in this system.':
        'يُعرض أسبوع العمل في عمّان (الأحد–الخميس) أولًا؛ والجمعة والسبت عطلة نهاية الأسبوع. '
        'تقارن "نسبة الإنجاز" المواعيد المحجوزة في ذلك اليوم بالزيارات المسجلة في اليوم نفسه '
        'على مستوى النظام — وهي تقديرية، لأن المواعيد غير مرتبطة بسجل زيارة محدد في هذا النظام.',
}
