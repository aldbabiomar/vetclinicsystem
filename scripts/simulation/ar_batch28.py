# -*- coding: utf-8 -*-
"""Arabic translations, batch 28 — the dashboard's backup banner.

The four sentences from `logic.backup_alert_message()`. This predates the
self-check by some margin and reported the same conditions through its own
mechanism — a bare f-string, which meant the one banner a clinic sees when its
backups are failing could never be translated at all: the interpolated error
made every message unique, so no catalogue entry could ever match it.

It now returns the same shape a self-check finding does, and both render
through the one `|finding` filter.
"""

BATCH = {
    "No database backup has ever run yet — set a backup folder on the Settings page.":
        "لم تُشغَّل أي نسخة احتياطية لقاعدة البيانات بعد — عيّن مجلدًا للنسخ الاحتياطي "
        "من صفحة الإعدادات.",
    "The last database backup failed: %(error)s.":
        "فشلت آخر نسخة احتياطية لقاعدة البيانات: %(error)s.",
    "The last backup started but never finished — check the Settings page.":
        "بدأت آخر نسخة احتياطية ولم تكتمل — راجع صفحة الإعدادات.",
    "The database hasn't been backed up in 2+ days — check the Settings page.":
        "لم تُنسخ قاعدة البيانات احتياطيًا منذ يومين أو أكثر — راجع صفحة الإعدادات.",
}
