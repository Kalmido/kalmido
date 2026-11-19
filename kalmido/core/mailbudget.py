"""2.24.0 (#899, part): daily e-mail limits. Mails a person makes the server send (invitations, new links) count per sender
and per receiving address and day; over the limit the mail is not sent (the link still works and can be copied).
2.1297.0 (#6548): moved here from admin/hosting.py (which re-exports the names) so that every area - also the event
invitations - counts without an upward import; the receiving address counts in one form (mail_rcpt_key).
2.1312.0 (#6540): also the limits of a workspace's own SMTP (mail_own_budget) and its rules (login, ports: smtp_own_refused),
shared by hub/mailbox.py and integrations/mail.py smtp_open."""
import re
from email.utils import getaddresses

from .config import mail_norm
from .db import gsetting, now_utc

# (#6546): f(smtp access, error or None) after every send through a workspace's own SMTP (integrations/mail.py mail_deliver
# calls them; hub/mailbox.py counts the mailbox's failed sends and tells its admins) - here, below both
SMTP_OWN_DONE = []

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


MAIL_DAY_OWN_RCPT = 20  # 2.1312.0 (#6540): per person and receiving address and day through a workspace's own SMTP


def mail_own_budget(c, sender, rcpts):
    """2.1312.0 (#6540): True and counted if one more mail from sender to every one of rcpts fits today through a workspace's
    own SMTP (at most MAIL_DAY_OWN_RCPT per person and receiving address); False otherwise, nothing counted (caller commits).
    The server's own limits (mail_budget) stay with the server's SMTP: a company answering its customer a sixth time is fine.
    Per person, not per address alone: another workspace's mails never use up this one's."""
    day = now_utc().strftime("%Y-%m-%d")
    c.execute("DELETE FROM mail_counts WHERE day<?", (day,))
    keys = set()
    for a in rcpts:
        rk = mail_rcpt_key(a)
        if not rk:
            return False
        keys.add(f"o:{sender}:{rk}")
    for k in keys:
        r = c.execute("SELECT n FROM mail_counts WHERE k=? AND day=?", (k, day)).fetchone()
        if r and r[0] >= MAIL_DAY_OWN_RCPT:
            return False
    for k in keys:
        c.execute("""INSERT INTO mail_counts(k,day,n) VALUES(?,?,1) ON CONFLICT(k) DO UPDATE SET
                     n=CASE WHEN mail_counts.day=excluded.day THEN mail_counts.n+1 ELSE 1 END, day=excluded.day""", (k, day))
    return True


class SmtpNoLogin(Exception):
    """2.1312.0 (#6540): a workspace's SMTP without user name or password: never used (no mail without a login)."""


class SmtpPortRefused(Exception):
    """2.1312.0 (#6540): a workspace's SMTP on a port other than 465 / 587 that the admin did not allow for that host."""


SMTP_OWN_PORTS = (465, 587)  # 2.1312.0 (#6540): a workspace's own SMTP (25 / another port: only a host:port of the admin's list)
SMTP_OWN_S = 60  # 2.1312.0 (#6540): the whole time of one delivery through a workspace's SMTP (connect, login, the mail)


def smtp_port(cfg):
    return cfg["port"] or (465 if cfg["tls"] == "ssl" else 587 if cfg["tls"] == "starttls" else 25)


def smtp_own_refused(cfg):
    """2.1312.0 (#6540): why a workspace's SMTP access cfg is never connected to: SmtpNoLogin / SmtpPortRefused, else None."""
    if not cfg.get("user") or not cfg.get("password"):
        return SmtpNoLogin()
    port = smtp_port(cfg)
    h = str(cfg.get("host") or "").lower().strip("[]").rstrip(".")
    allow = cfg.get("allow") or frozenset()
    if port not in SMTP_OWN_PORTS and (h, port) not in allow and (h, None) not in allow:  # calendars cal_host_allowed
        return SmtpPortRefused()
    return None
