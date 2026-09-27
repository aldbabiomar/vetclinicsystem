# -*- coding: utf-8 -*-
"""Arabic translations, batch 20 — weekdays, backup triggers, and the seeded roles.

The weekday names come from `logic.WEEKDAY_LABELS` and are rendered as data on
the Insights weekday-load table; the appointments grid uses Babel's own date
formatting instead (see the `weekdate` filter), so its day names were already
Arabic once `strftime` was replaced.

The three role names and descriptions are seeded into the database by
`auth.py`. A clinic that renames a role or rewrites its description simply has
no catalogue entry for the new wording, so its own text passes through `|tr`
unchanged — which is the behaviour you want in both directions.
"""

BATCH = {
    # logic.WEEKDAY_LABELS
    "Sunday": "الأحد",
    "Monday": "الاثنين",
    "Tuesday": "الثلاثاء",
    "Wednesday": "الأربعاء",
    "Thursday": "الخميس",
    "Friday": "الجمعة",
    "Saturday": "السبت",

    # backup_log.triggered_by, title-cased before display
    "Manual": "يدوي",
    "Nightly": "ليلي",
    "Shutdown": "عند الإغلاق",

    # auth.py seeded roles ("Admin" and "Vet" are already in the catalogue)
    "Reception": "الاستقبال",
    "Full access to every area of the app, always. There must be at least one "
    "active Admin.":
        "صلاحية كاملة على كل أجزاء التطبيق، دائمًا. يجب أن يبقى مدير واحد نشط على الأقل.",
    "Clinical staff — patient care, visits, and inpatient cases.":
        "الطاقم السريري — رعاية الحيوانات والزيارات وحالات التنويم.",
    "Front desk — scheduling, checkout, and client-facing tasks.":
        "مكتب الاستقبال — الحجز والدفع والمهام المتعلقة بالعملاء.",
}
