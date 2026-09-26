"""
Every sentence the static JavaScript files show (audit F2).

static/*.js cannot call gettext, so these reach them translated through
base.html: `window.VZ_I18N` maps each msgid below to the clinic's language,
and `vzT(msgid, {name: value})` looks one up and fills its %(name)s
placeholders (falling back to the English). N_ marks them for pybabel.

Add a sentence here when a static script needs one, and call it through
vzT() with EXACTLY this text: tests/test_js_strings.py fails on a vzT() msgid
that is not listed here, and on English prose in a static script outside
vzT().
"""
from messages import N_

JS_STRINGS = [
    # phone-validate.js
    N_("That phone number doesn't look valid — check the digits and try again."),
    # progress.js
    N_("Something went wrong."),
    N_("Failed"),
    N_("Done"),
    N_("Working"),
    N_("Lost track of this job — the server may have restarted. Try again."),
    N_("Could not reach the server."),
    # toast.js
    N_("Dismiss"),
    # ui.js
    N_("Cancel"),
    N_("Confirm"),
    N_("Saving…"),
    N_("Couldn't reach the server — please check your connection and try again."),
    # unsaved-changes-form.js and unsaved-changes.js
    N_("Unsaved Changes"),
    N_("You have unsaved changes on this page. Leave without saving?"),
    N_("Keep Editing"),
    N_("Discard Changes"),
    N_("Save & Continue"),
    N_("Save Changes"),
    N_("Save Changes (%(n)s)"),
    N_("Some changes couldn't be saved — please check your connection and try again. "
       "The items that failed are still highlighted."),
    N_("Some changes couldn't be saved — please check your connection and try again. "
       "You're still on this page and nothing else has been lost."),
    N_("You have unsaved changes on 1 item (%(names)s). Save them before leaving, or discard them?"),
    N_("You have unsaved changes on %(n)s items (%(names)s). Save them before leaving, or discard them?"),
    N_("%(names)s, and %(n)s more"),
    # upload-progress.js
    N_("Max file size: %(max)s MB."),
    N_("%(file)s is %(size)s — that's over the %(max)s MB limit. Please choose a smaller file."),
    N_("Selected: %(file)s (%(size)s). Max %(max)s MB."),
    N_("Uploading %(file)s…"),
    N_("Upload failed (server returned %(status)s). Please try again."),
    N_("Upload failed — check your connection and try again."),
]
