"""2.367.3 (#2971): an integration stopped working -- the person who can repair it hears it once (News + push, event
"integration" of the notification settings), not only as a status line in the settings. One call per outage: the callers tell
when a channel / webhook turns off, an inbound webhook pauses, or a polled connection reaches INTEG_FAILS failures in a row
(a success counts anew). The text is stored in the person's language: it carries names of things they set up themselves, never
the content of a list. Agents get nothing (their events are for that)."""
import json

from ..accounts.bgjobs import BGJ_FNS, bgj_add
from ..core.config import APP_NAME, PUBLIC_URL
from ..core.db import iso_ms, now_utc, usettings
from ..core.i18n import LANGS, N_, tr
from ..core.mailframe import mail_html
from ..core.pg import system_ctx
from ..notify.alerts import _env_int
from ..notify.push import push_prio
from .comments import send_pushes
from .news import notif_ok

INTEG_FAILS = _env_int("KALMIDO_INTEG_FAILS", 5)  # failed polls in a row of a mailbox, a git connection -> told once
INTEG_BACKOFF_MAX = 6 * 3600  # 2.1302.0 (#6545): the longest wait between two fetches of a mailbox that keeps failing


def integ_backoff_s(interval, fails):
    """2.1302.0 (#6545): seconds until the next fetch of a polled connection (a mailbox) after fails failures in a row: the
    interval, doubled with every failure (like the calendar subscriptions), at most INTEG_BACKOFF_MAX -- a wrong password
    was tried every minute."""
    if not fails:
        return interval
    return min(interval * 2 ** min(int(fails), 16), max(interval, INTEG_BACKOFF_MAX))


INTEG_TEXT = {
    "channel": N_("Forwarding {0} was switched off after repeated failed sends."),
    "channel_admin": N_("Forwarding {0} was switched off: the person who set it up is no admin of the organisation any more."),
    "webhook": N_("Webhook {0} was switched off: its events could not be delivered."),
    "webhook_admin": N_("Webhook {0} was switched off: the person who set it up is no admin of the organisation any more."),
    "hookin": N_("Inbound webhook {0} is paused: {1}"),
    "mailbox": N_("Mailbox {0} cannot fetch e-mail, failing since {1}."),
    "git": N_("Git connection {0} cannot fetch, failing since {1}."),
    # 2.1302.0 (#6545): the server refused the login INTEG_FAILS times in a row: the mailbox is not fetched any more
    "mailbox_auth": N_("Mailbox {0}: fetching stopped, the server refused the sign-in several times in a row (failing since {1}). Save the access data again."),
    "maillost": N_("Mailbox {0}: e-mails could not be taken over ({1}); they are still in the mailbox."),  # 2.1269 (#6386)
    "docflow": N_("Document flow {0} keeps failing on a document, failing since {1}."),  # 2.1265.0 (#6389): a scheduled flow
    "backup": N_("Backup failed: {0}"),
    "payonline": N_("An online payment on invoice {0} could not be booked: {1}"),  # 2.469.0 (#3459)
}


def integ_org_admins(c, oid):
    with system_ctx(c):  # the admins of the organisation the integration belongs to (a background loop or an anonymous call)
        return [r[0] for r in c.execute("SELECT user_id FROM org_members WHERE org_id=? AND role='admin'", (oid,)).fetchall()]


def integ_tell(c, uids, what, name, detail="", click="", mail=False, **data):
    """What went wrong (a key of INTEG_TEXT) with the thing called name, for each of uids once. click = where to repair it:
    the page after # (a push); data = what the News item needs to open it. name: a text, or f(language) when it needs
    translating. detail: a date, or a text marked with N_. The caller commits; never fails its caller's work.
    mail (2.1302.0, #6545): an e-mail too (the background mail queue, only with outgoing mail and an address), for whoever
    has the event "integration" on in the News or as a push -- switching the event off stops the mail as well."""
    pushes, mails = [], []
    try:
        with c.savepoint(), system_ctx(c):  # the recipients' settings and News, whoever or whatever noticed it
            for uid in dict.fromkeys(x for x in uids if x):
                u = c.execute("SELECT disabled, kind FROM users WHERE id=?", (uid,)).fetchone()
                if not u or u["disabled"] or u["kind"] == "agent":
                    continue
                s = usettings(c, uid)
                lg = s.get("lang") if s.get("lang") in LANGS else "en"
                text = tr(INTEG_TEXT[what], name(lg) if callable(name) else name, tr(detail, lg=lg) if detail else "", lg=lg)
                news_on, push_on = notif_ok(c, uid, s, "integration", "news"), notif_ok(c, uid, s, "integration", "push")
                if news_on:
                    c.execute("INSERT INTO notifications(user_id,kind,task_id,list_id,actor_id,comment_id,data,created_at) VALUES(?,?,?,?,?,?,?,?)",
                              (uid, "integfail", None, None, None, None,
                               json.dumps({**data, "what": what, "text": text}, ensure_ascii=False), iso_ms(now_utc())))
                if push_on:
                    pushes.append((uid, tr("Integration problem", lg=lg), text, f"{PUBLIC_URL}/#{click or 'settings'}", push_prio(s)))
                if mail and (news_on or push_on):
                    to = (c.execute("SELECT email FROM users WHERE id=?", (uid,)).fetchone()["email"] or "").strip()
                    if to:
                        mails.append((uid, to, lg, text))
    except Exception as e:  # noqa: BLE001
        print("integration notice failed:", what, type(e).__name__, flush=True)
        return
    send_pushes(pushes)
    for uid, to, lg, text in mails:
        integ_mail(uid, to, lg, text, click)


def integ_mail(uid, to, lg, text, click=""):
    """2.1302.0 (#6545): one integration notice as an e-mail through the background mail queue (like a failed backup)."""
    if "mail:security" not in BGJ_FNS:  # registered only with outgoing mail (integrations/mail.py)
        return
    try:
        link = f"{PUBLIC_URL}/#{click or 'settings'}"
        subject = f"{APP_NAME}: {tr('Integration problem', lg=lg)}"
        foot = tr("You get this e-mail because Integrations is switched on in Settings > Notifications.", lg=lg)
        bgj_add("mail:security", to, subject, f"{text}\n\n{link}\n\n-- \n{foot}\n",
                mail_html(subject, [text], tr("Open settings", lg=lg), link, lang=lg, note=foot), user_id=uid)
    except Exception as e:  # noqa: BLE001 -- the News item and the push went out; the mail is a second way
        print("integration mail failed:", type(e).__name__, flush=True)
