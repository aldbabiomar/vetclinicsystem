"""
Messages written by code that runs outside a request, or shown later than
they are made: backups, restores, updates, automatic startup (audit F1).

A `Msg` IS a str -- the rendered English -- so the logs it is written to,
the rows it is stored in and every test that compares it keep working
unchanged. It also carries its msgid and arguments, so the page that finally
shows it can do so in the clinic's language: `core.shown(m)`. Translating at
write time would be wrong twice: there is often no request (so no language)
yet, and a stored message would be frozen in whatever language was active
when it was written. This is the pattern selfcheck findings already use
(COMPARISON.md §60.1), made reusable.

Write one as  Msg(N_("Backup saved to %(path)s."), path=dest)  -- N_ is what
pybabel extracts; the msgid's %(name)s placeholders are filled from the
keyword arguments.
"""


def N_(text):
    """Mark a string for extraction without translating it here."""
    return text


class Msg(str):
    """A message: its value the rendered English, plus msgid and args."""

    def __new__(cls, msgid, **args):
        obj = super().__new__(cls, msgid % args if args else msgid)
        obj.msgid = msgid
        obj.args = args
        return obj

    def __reduce__(self):
        # Pickled or copied as what it is, not as a bare str.
        return (_rebuild, (self.msgid, self.args))


def _rebuild(msgid, args):
    return Msg(msgid, **args)
