# -*- coding: utf-8 -*-
"""Arabic translations, batch 15 — the grooming services, the grooming status
the first enum_labels.py got wrong, and the one-letter sex codes.

These only appeared once enum_labels.py was rebuilt from the constants the
code actually uses instead of from memory. "Waiting" is the clearest case:
the stored grooming status has always been Waiting/Ongoing/Finished, and the
first version of that file declared Pending/In Progress/Finished, so the real
value had no msgid at all.

"Zoning" is flagged in ARABIC_TRANSLATION_QUESTIONS.md — it is not a standard
grooming term in English either, so the Arabic below is a best reading of a
sanitary trim and wants the clinic's own word.
"""

BATCH = {
    # logic.GROOMING_SERVICES
    "Bath": "استحمام",
    "Haircut": "قص الشعر",
    "De-shedding": "إزالة الوبر المتساقط",
    "Nail Trim": "تقليم الأظافر",
    "Ear Cleaning": "تنظيف الأذن",
    "Ear Mites Cleaning": "تنظيف سوس الأذن",
    "Paw Clipping": "قص شعر الكفوف",
    "Nail Caps": "أغطية الأظافر",
    "Anal Gland Emptying": "تفريغ الغدد الشرجية",
    "Zoning": "تهذيب المنطقة الحساسة",

    # visits.grooming_status
    "Waiting": "قيد الانتظار",

    # patients.sex — stored as single letters, displayed as words
    "M": "ذكر",
    "F": "أنثى",
}
