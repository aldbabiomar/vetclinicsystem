# -*- coding: utf-8 -*-
"""Arabic translations, batch 6 — the last 12, including JO-only wording.

The backup-path example carries a single literal backslash (D:\\Vet...). In
the .po it appears escaped as `\\\\`, and batch 5 wrote two real backslashes,
so the msgid never matched. Written here with exactly one.

Several strings are JO-only: its refund and settlement messages are worded
differently from IQ's, and its currency is JOD. They are not a translation of
IQ's — they are their own msgids, which is why they need their own entries.
"""

BATCH = {
    # ---- IQ: the backup path example (one literal backslash) ----
    "e.g. /Users/you/VetClinicSystemBackups or D:\\VetClinicSystemBackups":
        "مثال: /Users/you/VetClinicSystemBackups أو D:\\VetClinicSystemBackups",
    "e.g. /Users/you/VetClinicSystemJOBackups or D:\\VetClinicSystemJOBackups":
        "مثال: /Users/you/VetClinicSystemJOBackups أو D:\\VetClinicSystemJOBackups",

    # ---- JO-only wording ----
    "Your password was changed — please log in again.":
        "تم تغيير كلمة المرور — يرجى تسجيل الدخول مرة أخرى.",
    "Report data rebuilt from current billing, sales, and cost data.":
        "تمت إعادة بناء بيانات التقارير من الفوترة والمبيعات والتكاليف الحالية.",
    "Clean Up can't exceed %(CLEANUP_CAP)s JOD total on this bill.":
        "لا يمكن الإعفاء عن الفئات القليلة أكثر من %(CLEANUP_CAP)s د.أ كمجموع لهذه الفاتورة.",
    "That's more than the %(fmt_money)s JOD owed this period.":
        "هذا أكثر من المبلغ المستحق لهذه الفترة البالغ %(fmt_money)s د.أ.",
    "That's more than what's left refundable on this visit (%(fmt_money)s JOD).":
        "هذا أكثر من المبلغ المتبقي القابل للاسترداد على هذه الزيارة (%(fmt_money)s د.أ).",
    "That's more than what's left refundable on this case (%(fmt_money)s JOD).":
        "هذا أكثر من المبلغ المتبقي القابل للاسترداد على هذه الحالة (%(fmt_money)s د.أ).",
    "That's more than what's left refundable on this stay (%(fmt_money)s JOD).":
        "هذا أكثر من المبلغ المتبقي القابل للاسترداد على هذه الإقامة (%(fmt_money)s د.أ).",
    "Service refund of %(amount)s JOD recorded.":
        "تم تسجيل استرداد خدمة بقيمة %(amount)s د.أ.",
    "e.g. counted twice, drawer was short a note":
        "مثال: تم العد مرتين، وينقص الصندوق ورقة نقدية",
    "Scan or type the barcode from the packaging":
        "امسح أو اكتب الباركود من العبوة",
}
