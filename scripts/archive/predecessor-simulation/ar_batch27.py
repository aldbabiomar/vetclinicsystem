# -*- coding: utf-8 -*-
"""Arabic translations, batch 27 — the self-check findings.

These are the sentences on the "this install needs attention" banner: the ones
that tell a clinic its backups are failing or its backup folder has vanished.
They were the last English left on an otherwise Arabic dashboard, and they are
the messages that matter most when they appear.

They are STORED in `self_check_log` when the scheduler runs and read back at
render time, so `selfcheck.py` keeps the English text and a msgid, and the
dashboard's `|finding` filter translates. `%(name)s` values are filled after
translation, so Arabic can place them where Arabic places them.
"""

BATCH = {
    # --- backups
    "No database backup has ever run on this install.":
        "لم تُشغَّل أي نسخة احتياطية لقاعدة البيانات على هذا التثبيت قط.",
    "No backup has ever completed successfully.":
        "لم تكتمل أي نسخة احتياطية بنجاح قط.",
    "The last successful backup has an unreadable timestamp, so its age cannot be judged.":
        "آخر نسخة احتياطية ناجحة تحمل ختمًا زمنيًا غير مقروء، لذا لا يمكن تحديد عمرها.",
    "No successful backup for 1 day.": "لا توجد نسخة احتياطية ناجحة منذ يوم واحد.",
    "No successful backup for %(days)s days.":
        "لا توجد نسخة احتياطية ناجحة منذ %(days)s يومًا.",
    "The last 3 backup attempts all failed: %(error)s":
        "فشلت محاولات النسخ الاحتياطي الثلاث الأخيرة جميعها: %(error)s",
    "A backup started but never finished — it has been running for over %(hours)s hours.":
        "بدأت نسخة احتياطية ولم تكتمل — وهي قيد التشغيل منذ أكثر من %(hours)s ساعة.",
    "The most recent backup is recorded as successful but its file is no longer on "
    "disk. Something removed it, or the folder it was written to is no longer the "
    "same folder.":
        "آخر نسخة احتياطية مسجلة على أنها ناجحة لكن ملفها لم يعد موجودًا على القرص. "
        "إما أن شيئًا ما حذفه، أو أن المجلد الذي كُتبت فيه لم يعد المجلد نفسه.",

    # --- the backup folder
    "No backup folder is configured — set one on the Settings page.":
        "لم يُحدَّد مجلد للنسخ الاحتياطي — عيّن واحدًا من صفحة الإعدادات.",
    "The backup folder is gone. Backups were being written there, so this is a folder "
    "that disappeared rather than one not set up yet — check whether the drive or "
    "synced folder is still connected before anything writes a new one.":
        "اختفى مجلد النسخ الاحتياطي. كانت النسخ تُكتب فيه، أي أنه مجلد اختفى وليس مجلدًا "
        "لم يُهيَّأ بعد — تحقق من أن القرص أو المجلد المزامَن ما زال متصلًا قبل أن يكتب "
        "أي شيء مجلدًا جديدًا.",
    "The backup folder does not exist and could not be created: %(error)s":
        "مجلد النسخ الاحتياطي غير موجود وتعذّر إنشاؤه: %(error)s",
    "The backup folder exists but cannot be written to: %(error)s":
        "مجلد النسخ الاحتياطي موجود لكن لا يمكن الكتابة فيه: %(error)s",

    # --- disk
    "Free disk space could not be read: %(error)s":
        "تعذّرت قراءة المساحة الحرة على القرص: %(error)s",
    "Only %(gb)s GB free on the backup volume.":
        "لم يتبقَّ سوى %(gb)s غيغابايت على قرص النسخ الاحتياطي.",
    "%(gb)s GB free on the backup volume.":
        "%(gb)s غيغابايت متاحة على قرص النسخ الاحتياطي.",

    # --- updates and schema
    "Some schema updates could not be applied on the last launch: %(failures)s":
        "تعذّر تطبيق بعض تحديثات قاعدة البيانات عند آخر تشغيل: %(failures)s",
    "The update log exists but could not be read: %(error)s":
        "سجل التحديثات موجود لكن تعذّرت قراءته: %(error)s",
    "The most recent update was rolled back — this install is not running the version "
    "it tried to install.":
        "تم التراجع عن آخر تحديث — هذا التثبيت لا يعمل بالإصدار الذي حاول تثبيته.",

    # --- restore verification
    "No backup has ever been verified as restorable on this install.":
        "لم يتم التحقق من قابلية استعادة أي نسخة احتياطية على هذا التثبيت قط.",
    "The last restore-verification result could not be read.":
        "تعذّرت قراءة نتيجة آخر تحقق من الاستعادة.",
    "The last restore-verification result has no readable date.":
        "نتيجة آخر تحقق من الاستعادة لا تحمل تاريخًا مقروءًا.",
    "The most recent restore verification did not pass: %(detail)s":
        "لم يجتز آخر تحقق من الاستعادة: %(detail)s",
    "No backup has been verified as restorable for %(days)s days.":
        "لم يتم التحقق من قابلية استعادة أي نسخة احتياطية منذ %(days)s يومًا.",

    # --- the database, and the catch-all
    "The database could not be queried: %(error)s":
        "تعذّر الاستعلام من قاعدة البيانات: %(error)s",
    "The database could not be read: %(error)s":
        "تعذّرت قراءة قاعدة البيانات: %(error)s",
    "This check could not complete: %(error)s":
        "تعذّر إكمال هذا الفحص: %(error)s",
}
