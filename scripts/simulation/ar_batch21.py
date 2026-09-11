# -*- coding: utf-8 -*-
"""Arabic translations, batch 21 — the inventory badges and the ordering sheet's
usage trend.

Both are computed in `logic.py` and reach the page as row values, so they are
declared in `enum_labels.py` and rendered through `|tr` like every other
stored value. The trend note is the `title=` tooltip on the trend cell, which
is why it is a sentence rather than a label.
"""

BATCH = {
    # logic.inventory_status() stock_status
    "LOW STOCK": "مخزون منخفض",
    "No audits yet": "لا جرد بعد",

    # ordering sheet usage trend
    "Not enough data": "بيانات غير كافية",
    "Increasing": "في ازدياد",
    "Decreasing": "في انخفاض",
    "Steady": "مستقر",

    # the trend cell's tooltip
    "Not enough audit history yet (need 2+ confirmed audits)":
        "سجل الجرد غير كافٍ بعد (يلزم عمليتا جرد مؤكدتان أو أكثر)",
    "Usage rising - consider more coverage days":
        "الاستهلاك في ارتفاع — فكّر بزيادة أيام التغطية",
    "Usage falling - consider fewer coverage days":
        "الاستهلاك في انخفاض — فكّر بتقليل أيام التغطية",
    "Usage steady - keep current target":
        "الاستهلاك مستقر — أبقِ الهدف الحالي",
}
