# -*- coding: utf-8 -*-
"""Arabic translations, batch 14 — stored enum values (enum_labels.py).

These are values written to the database in English. Only the DISPLAY is
translated, through app.py's |tr filter; the stored constant is untouched, so
every route validator and CHECK constraint keeps working against the English.
"""

BATCH = {
    # visits.case_status
    "Needs Filling": "بحاجة إلى استكمال",
    "Ongoing": "جارية",
    "Admitted to Inpatient": "محوّل إلى التنويم",
    "Deceased/Euthanized": "نافق / تم إنهاء حياته رحمةً",
    "Lost to Follow Up": "انقطع عن المتابعة",
    "Resolved": "منتهية",
    "Referred": "محوّل",

    # payment status
    "Unpaid": "غير مدفوع",
    "Partially Paid": "مدفوع جزئيًا",
    "Fully Paid": "مدفوع بالكامل",
    "N/A": "غير منطبق",

    # visit type
    "Outpatient": "عيادات خارجية",

    # follow-up
    "Physical Visit": "زيارة حضورية",
    "Pending": "معلّق",
    "Completed": "مكتمل",
    "Cancelled": "ملغى",
    "Surgery Follow Up": "متابعة بعد جراحة",
    "Medical Follow Up": "متابعة طبية",
    "Vaccine": "لقاح",
    "Deworming": "علاج الديدان",
    "Spot On": "قطرة موضعية",

    # wellness
    "Annual Vaccine": "اللقاح السنوي",
    "First Vaccine": "اللقاح الأول",
    "Rabies Vaccine": "لقاح السعار",
    "Spot On/Pill": "قطرة موضعية / حبة",
    "Finished": "منتهٍ",

    # patients
    "Dog": "كلب",
    "Cat": "قطة",
    "Bird": "طائر",
    "Rabbit": "أرنب",
    "Turtle": "سلحفاة",
    "Male": "ذكر",
    "Female": "أنثى",
    "Indoor/Outdoor": "داخل وخارج المنزل",

    # money / stock
    "Automatic": "تلقائي",
    "Manual": "يدوي",
    "Medicine": "دواء",
    "Owned": "مملوك",
    "Draft": "مسودة",
    "Confirmed": "مؤكد",
    "retail": "تجزئة",
    "service": "خدمة",
}
