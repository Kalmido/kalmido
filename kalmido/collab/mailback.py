"""(#6547): what comes back from a mail - the one check for automatic mails and the words of a returned one.

mail_auto is asked by every input that takes a mail as a reply (a task's comment, a letter's answer, the hub, the portal, a
data protection sheet; integrations/mail.py, taskmail.py, reqmail.py, docs/ingest.py, hub/hubmail.py, hub/mailbox.py,
office/privacy.py): an out-of-office answer or a delivery report is never a comment, a document or a signature.
The reading of a delivery report and its matching stand in integrations/mail.py (mail_bounce, mail_bounce_take); the areas that
keep the Message-ID of their mails mark them (office/mailstate.py oms_bounce, office/lettermail.py ltm_bounce,
hub/hubmail.py hbm_bounce, integrations/mail.py _inv_bounce) and tell the person who sent it (mail_bounce_tell: News + push,
collab/integfail.py integ_tell). Here so the areas need no import of the integrations layer."""
import email.utils

from ..core.i18n import N_, tr
from .integfail import integ_tell

_AUTO_PREC = ("bulk", "junk", "list", "auto_reply")
_AUTO_LOCAL = ("mailer-daemon", "postmaster")

MAIL_BOUNCE_WHY = {  # the kind of reason of a status code (RFC 3463, mail_bounce_kind) -> in words; the code itself follows in brackets
    "unknown": N_("the address does not exist"), "domain": N_("the domain of the address takes no e-mail"),
    "full": N_("the mailbox is full"), "refused": N_("the receiving server refused the e-mail (sender check or spam filter)"),
    "": N_("the receiving server returned it"),
}


def mail_auto(msg, sender=None):
    """'' for a mail a person wrote, else what kind of automatic mail it is (RFC 3834 and the common headers):
    'report' = a delivery report (multipart/report, mailer-daemon / postmaster), 'reply' = an automatic answer (Auto-Submitted
    auto-replied, X-Autoreply / X-Autorespond, Precedence auto_reply: an out-of-office note), 'auto' = otherwise generated
    (Auto-Submitted other than "no", Precedence bulk / junk / list). sender = the From address (read from msg when None)."""
    if sender is None:
        sender = email.utils.parseaddr(str(msg.get("From", "") or ""))[1].strip().lower()
    if msg.get_content_type() == "multipart/report" or (sender or "").partition("@")[0] in _AUTO_LOCAL:
        return "report"
    a = str(msg.get("Auto-Submitted", "") or "").strip().lower()
    prec = str(msg.get("Precedence", "") or "").strip().lower()
    if a.startswith("auto-replied") or prec == "auto_reply" or msg.get("X-Autoreply") or msg.get("X-Autorespond"):
        return "reply"
    if (a and a != "no") or prec in _AUTO_PREC:
        return "auto"
    return ""


def mail_mid(sent):
    """The Message-ID of a sent message (integrations/mail.py mail_send's answer; '' without one), as the areas keep it."""
    return str(sent.get("Message-ID", "") or "").strip()[:300] if sent is not None and hasattr(sent, "get") else ""


def mail_bounce_kind(code):
    """The kind of reason of a status code (a key of MAIL_BOUNCE_WHY)."""
    _c, s, d = (str(code or "").split(".") + ["", ""])[:3]
    if s == "1" and d in ("1", "0", "3", "6"):
        return "unknown"
    if (s == "1" and d == "2") or (s == "4" and d == "4"):
        return "domain"
    if s == "2" and d == "2":
        return "full"
    if s == "7":
        return "refused"
    return ""


def mail_bounce_why(code, lg=None):
    """The reason of a returned mail in words (language lg, else the request's), its status code in brackets. code '?' = a
    report without a status (stored so: the column's '' means "not returned")."""
    code = "" if code == "?" else (code or "")
    return tr(MAIL_BOUNCE_WHY[mail_bounce_kind(code)], lg=lg) + (f" ({code})" if code else "")


def mail_bounce_tell(c, uids, what, name, code, **data):
    """The News (+ push, collab/integfail.py integ_tell) to the person who sent a mail that came back: what = mail_bounced_*,
    name = the thing it carried (a text or f(language)); the reason in their language. The caller commits."""
    code = "" if code == "?" else (code or "")
    integ_tell(c, uids, what, name, MAIL_BOUNCE_WHY[mail_bounce_kind(code)], more=(f" ({code})" if code else "",), **data)
