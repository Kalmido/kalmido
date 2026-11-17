"""2.367.3 (#2971): an integration stopped working -- the person who can repair it hears it once (News + push, event
"integration" of the notification settings), not only as a status line in the settings. One call per outage: the callers tell
when a channel / webhook turns off, an inbound webhook pauses, or a polled connection reaches INTEG_FAILS failures in a row
(a success counts anew). The text is stored in the person's language: it carries names of things they set up themselves, never
the content of a list. Agents get nothing (their events are for that)."""
import json

from ..core.config import PUBLIC_URL
from ..core.db import iso_ms, now_utc, usettings
from ..core.i18n import LANGS, N_, tr
from ..core.pg import system_ctx
from ..notify.alerts import _env_int
from ..notify.push import push_prio
from .comments import send_pushes
from .news import notif_ok

INTEG_FAILS = _env_int("KALMIDO_INTEG_FAILS", 5)  # failed polls in a row of a mailbox, a git connection -> told once
INTEG_TEXT = {
    "channel": N_("Forwarding {0} was switched off after repeated failed sends."),
    "channel_admin": N_("Forwarding {0} was switched off: the person who set it up is no admin of the organisation any more."),
    "webhook": N_("Webhook {0} was switched off: its events could not be delivered."),
    "webhook_admin": N_("Webhook {0} was switched off: the person who set it up is no admin of the organisation any more."),
    # 2.1322.0 (#6560 6): ... and how much was waiting: {1} events, the oldest of {2} (a day), dropped with the switch-off
    "webhook_lost": N_("Webhook {0} was switched off: its events could not be delivered. {1} waiting events since {2} were discarded."),
    "webhook_admin_lost": N_("Webhook {0} was switched off: the person who set it up is no admin of the organisation any more. {1} waiting events since {2} were discarded."),
    "hookin": N_("Inbound webhook {0} is paused: {1}"),
    "reqmail": N_("Requests by e-mail to project {0} reached the hourly limit: further e-mails wait in the mailbox and are taken in later."),  # 2.1322.0 (#6560 3)
    "errhook": N_("Error reports of project {0} are paused: {1}"),  # 2.1322.0 (#6560 4)
    "mailbox": N_("Mailbox {0} cannot fetch e-mail, failing since {1}."),
    "git": N_("Git connection {0} cannot fetch, failing since {1}."),
    "gitowner": N_("Git connection {0} is paused: the person whose access token it uses has no access to the project any more."),  # 2.1306.0 (#6554)
    "gitcap": N_("Git connection {0} reached its daily limit of new issues or comments ({1}); the rest goes out tomorrow."),  # 2.1306.0 (#6554)
    "maillost": N_("Mailbox {0}: e-mails could not be taken over ({1}); they are still in the mailbox."),  # 2.1269 (#6386)
    "docflow": N_("Document flow {0} keeps failing on a document, failing since {1}."),  # 2.1265.0 (#6389): a scheduled flow
    "docflow_hook": N_("The webhook of document flow {0} was switched off: its calls could not be delivered (last error: {1})."),  # 2.1321.0 (#6555)
    "docflow_admin": N_("Document flow {0} was paused: the person who set up its webhook is no admin of the workspace any more."),  # 2.1321.0 (#6555)
    "backup": N_("Backup failed: {0}"),
    "payonline": N_("An online payment on invoice {0} could not be booked: {1}"),  # 2.469.0 (#3459)
}


def integ_org_admins(c, oid):
    with system_ctx(c):  # the admins of the organisation the integration belongs to (a background loop or an anonymous call)
        return [r[0] for r in c.execute("SELECT user_id FROM org_members WHERE org_id=? AND role='admin'", (oid,)).fetchall()]


def integ_tell(c, uids, what, name, detail="", click="", more=(), **data):
    """What went wrong (a key of INTEG_TEXT) with the thing called name, for each of uids once. click = where to repair it:
    the page after # (a push); data = what the News item needs to open it. name: a text, or f(language) when it needs
    translating. detail: a date, or a text marked with N_; more = further values of the text ({2}, ...; 2.1322.0, #6560).
    The caller commits; never fails its caller's work."""
    pushes = []
    try:
        with c.savepoint(), system_ctx(c):  # the recipients' settings and News, whoever or whatever noticed it
            for uid in dict.fromkeys(x for x in uids if x):
                u = c.execute("SELECT disabled, kind FROM users WHERE id=?", (uid,)).fetchone()
                if not u or u["disabled"] or u["kind"] == "agent":
                    continue
                s = usettings(c, uid)
                lg = s.get("lang") if s.get("lang") in LANGS else "en"
                text = tr(INTEG_TEXT[what], name(lg) if callable(name) else name, tr(detail, lg=lg) if detail else "", *more, lg=lg)
                if notif_ok(c, uid, s, "integration", "news"):
                    c.execute("INSERT INTO notifications(user_id,kind,task_id,list_id,actor_id,comment_id,data,created_at) VALUES(?,?,?,?,?,?,?,?)",
                              (uid, "integfail", None, None, None, None,
                               json.dumps({**data, "what": what, "text": text}, ensure_ascii=False), iso_ms(now_utc())))
                if notif_ok(c, uid, s, "integration", "push"):
                    pushes.append((uid, tr("Integration problem", lg=lg), text, f"{PUBLIC_URL}/#{click or 'settings'}", push_prio(s)))
    except Exception as e:  # noqa: BLE001
        print("integration notice failed:", what, type(e).__name__, flush=True)
        return
    send_pushes(pushes)
