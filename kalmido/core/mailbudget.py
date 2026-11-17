"""2.24.0 (#899, part): daily e-mail limits. Mails a person makes the server send (invitations, new links) count per sender
and per receiving address and day; over the limit the mail is not sent (the link still works and can be copied).
2.1297.0 (#6548): moved here from admin/hosting.py (which re-exports the names) so that every area - also the event
invitations - counts without an upward import; the receiving address counts in one form (mail_rcpt_key)."""
import re
from email.utils import getaddresses

from .config import mail_norm
from .db import gsetting, now_utc

MAIL_DAY_SENDER = 30   # per account and day (admin setting mail_day_limit)
MAIL_DAY_RCPT = 5      # per receiving address and day
MAIL_DAY_MAX = 10_000_000  # the admin setting's upper bound (was the storage quota bound of admin/hosting.py _mb)


def mail_day_limit(c):
    try:
        v = int(str(gsetting(c, "mail_day_limit")).strip())
    except (TypeError, ValueError):
        return MAIL_DAY_SENDER
    return v if 0 < v <= MAIL_DAY_MAX else MAIL_DAY_SENDER


def mail_rcpt_key(rcpt):
    """2.1297.0 (#6548): the one address a mail to rcpt reaches (lower case, no display name or brackets) - None when rcpt
    names no address or more than one ('<a@x.de>' and ' A@x.de' are a@x.de; 'a@x.de,b.c' is no single receiver)."""
    if not isinstance(rcpt, str) or not rcpt.strip():
        return None
    got = [a for _, a in getaddresses([rcpt.replace(";", ",")]) if a]
    if len(got) != 1 or rcpt.count("@") != 1:
        return None
    return mail_norm(re.sub(r"\s+", "", got[0]))


def mail_budget(c, sender, rcpt):
    """True and counted if one more mail from sender to rcpt fits today; False otherwise (caller commits).
    2.1297.0 (#6548): a receiver that is no single address never fits."""
    day = now_utc().strftime("%Y-%m-%d")
    c.execute("DELETE FROM mail_counts WHERE day<?", (day,))
    rk = mail_rcpt_key(rcpt)
    if not rk:
        return False
    keys = [(f"r:{rk}", MAIL_DAY_RCPT)]
    if sender:
        keys.append((f"s:{sender}", mail_day_limit(c)))
    for k, lim in keys:
        r = c.execute("SELECT n FROM mail_counts WHERE k=? AND day=?", (k, day)).fetchone()
        if r and r[0] >= lim:
            return False
    for k, _ in keys:
        c.execute("""INSERT INTO mail_counts(k,day,n) VALUES(?,?,1) ON CONFLICT(k) DO UPDATE SET
                     n=CASE WHEN mail_counts.day=excluded.day THEN mail_counts.n+1 ELSE 1 END, day=excluded.day""", (k, day))
    return True
