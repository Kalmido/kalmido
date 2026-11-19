"""#6531: a file of a mail or a public form that is not filed never goes silently.

core/pages.py save_attachment_bytes says why it left a file out (the storage is full, the virus scanner, a list encrypted in
the browser, a refusal). mail_files_save is the one loop over a mail's files (the mail import, the replies by mail, the
request address); att_skip_note / att_skip_task write the note on the task and the News item "attskip" for the owner. The
mail of a file left out stays in the mailbox (integrations/mail.py MailKept), like one that could not be written."""
from ..core.config import MAX_FILE_MB
from ..core.db import usettings
from ..core.i18n import N_, lang, tr
from ..core.pages import save_attachment_bytes
from .news import news_add

# #6531: why a file was left out, in the words of the note on the task (core/pages.py save_attachment_bytes)
ATT_SKIP_WHY = {"quota": N_("the storage is full"), "virus": N_("the virus scanner refused it"),
                "lock": N_("the list is encrypted in the browser"), "denied": N_("it was refused"),
                "large": N_("the file is too large")}


def mail_files_save(c, tid, files, cap, owner=None, rename=None):
    """#6531: the files of a mail (or a form) as files of task tid -> (whole, skipped, top). whole = every file was filed
    (False: more than cap files, one too large, one not written, or one left out: the mail stays in the mailbox, MailKept);
    skipped = [(name, why)] of the files left out: save_attachment_bytes' reason or "large" (over the size limit; att_skip_note
    writes them on the task);
    top = the highest file id of the task before (a reply's caller hangs the new files on its comment: id > top)."""
    top = c.execute("SELECT COALESCE(MAX(id),0) FROM attachments WHERE task_id=?", (tid,)).fetchone()[0]
    whole, skipped = len(files) <= cap, []
    for name, mime, data in files[:cap]:
        if 0 < len(data) <= MAX_FILE_MB * 1024 * 1024:
            try:
                why = save_attachment_bytes(c, tid, rename(name) if rename else name, mime, data, owner=owner, anon=True)  # (#6651): from outside
            except OSError:
                whole = False
                break
            if why:
                skipped.append((name, why))
                whole = False
        elif data:
            skipped.append((name, "large"))  # (over TASKS_MAX_FILE_MB)
            whole = False
    return whole, skipped, top


def att_skip_note(c, tid, skipped, owner=None, lg=None):
    """#6531: the files left out of task tid as a visible note -> the text ("" when none); the owner (whose storage the
    files count against: owner, else the task's creator) gets a News item "attskip" (row "limits", on by default). The
    caller puts the text into the task's description or the reply's comment and commits."""
    if not skipped:
        return ""
    who = owner
    if who is None:
        r = c.execute("SELECT created_by FROM tasks WHERE id=?", (tid,)).fetchone()
        who = r[0] if r else None
    lg = lg or (lang(c, who) if who else "en")
    text = "\n".join("— " + tr("File not filed: {0} ({1})", n, tr(ATT_SKIP_WHY.get(w, ATT_SKIP_WHY["denied"]), lg=lg), lg=lg)
                     for n, w in skipped)
    if who:  # (s given: about the person's own storage, also without the collaboration module, like "ptlimit")
        news_add(c, who, "attskip", task_id=tid, actor=0, s=usettings(c, who),
                 data={"names": [n[:120] for n, _w in skipped[:5]], "n": len(skipped), "why": skipped[0][1]})
    return text


def att_skip_task(c, tid, skipped, owner=None):
    """#6531: att_skip_note's text appended to the description of task tid (a task made from a mail / a form)."""
    text = att_skip_note(c, tid, skipped, owner)
    if text:
        r = c.execute("SELECT content FROM tasks WHERE id=?", (tid,)).fetchone()
        c.execute("UPDATE tasks SET content=? WHERE id=?", (((r[0] if r else "") or "").rstrip() + "\n\n" + text, tid))
