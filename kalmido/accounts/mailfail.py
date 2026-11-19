"""(#6385): a failed mail. A passing failure of the mail server (no connection, a time-out, a 4xx answer) is tried again
by bgjobs (mail:* kinds: BGJ_PREFIX runs with a growing gap); a lasting refusal (5xx, a refused recipient, a message that
cannot be built) is not. Only after the last run does the person who started the mail hear it (the caller's `final`).
integrations/mail.py mail_deliver counts the failures of the instance's server for the admin alert (smtp_down, smtp_err).
Below integrations on purpose: the mail:* kinds of every area (accounts, calendars, events, team) call it at module level."""
import smtplib
from datetime import timedelta

from ..core.db import DbError, iso, now_utc
from ..core.pg import system_ctx
from .bgjobs import bgj_last


# (#6385): runs of a mail:* kind that reports through mail_bg_failed / mail_bg_list: it raises only when nothing of the row
# went out (a list puts its rest into a new row), so a raising run never sent half - the reason the queue keeps the other
# mail:* kinds at one run (#7181); each such kind says retry=MAIL_RETRY at its bgj_fn.
MAIL_RETRY = 3


class SmtpTemporary(Exception):
    """(#6385): the mail server failed in passing; the row of the queue raises it to be tried again (its error column names
    it: mail_disturbed counts these rows)."""


class SmtpRcptTemporary(SmtpTemporary):
    """(#6385): a passing refusal of the recipient (450 / 451 to RCPT): tried again like SmtpTemporary, but the server works -
    mail_disturbed does not count it (an address anyone can name must not switch on the notice of every organisation admin)."""


def _smtp_code(e):
    if isinstance(e, smtplib.SMTPRecipientsRefused):
        codes = [v[0] for v in (e.recipients or {}).values() if isinstance(v, tuple) and v and isinstance(v[0], int)]
        return max(codes) if codes else 550
    return getattr(e, "smtp_code", None) if isinstance(e, smtplib.SMTPResponseException) else None


def smtp_temp(e):
    """(#6385): a later try may succeed: no connection / a time-out / a dropped connection, or an answer 4xx. Not: 5xx, a
    refused sign-in, a message that cannot be built (no OSError)."""
    if isinstance(e, SmtpTemporary):
        return True
    if not isinstance(e, OSError):  # smtplib's errors are OSErrors; a ValueError of the message is no server failure
        return False
    code = _smtp_code(e)
    return code is None or 400 <= int(code) < 500


def smtp_down(e):
    """(#6385): counts as a failure of the mail server for the admin alert: every failure of the connection or the session
    except a refusal of the recipients (the server works, the address does not)."""
    return isinstance(e, OSError) and not isinstance(e, smtplib.SMTPRecipientsRefused)


def smtp_err(e):
    """The error class for the alert, with the server's code (never its text: it can quote the address)."""
    code = _smtp_code(e)
    return f"{type(e).__name__} {code}" if code else type(e).__name__ + (f"/{type(e.reason).__name__}" if isinstance(getattr(e, "reason", None), BaseException) else "")


def mail_bg_failed(what, e, final=None):
    """(#6385): the except branch of a queued mail (a mail:* kind): logs (no address); a passing failure of the mail server
    raises SmtpTemporary while the row has runs left (bgjobs tries it again); after that, or on a lasting refusal, final()
    tells the person who started the mail (never fails the caller) and a passing failure still raises (the row ends
    'failed', the admins' queue alert counts it)."""
    print(what, "mail failed:", smtp_err(e), flush=True)
    temp = smtp_temp(e)
    kind = SmtpRcptTemporary if isinstance(e, smtplib.SMTPRecipientsRefused) else SmtpTemporary
    if temp and not bgj_last():
        raise kind(smtp_err(e)) from e
    if final:
        try:
            final()
        except Exception as x:  # noqa: BLE001 -- the notice is extra; the row ends either way
            print(what, "mail: notice failed:", type(x).__name__, flush=True)
    if temp:
        raise kind(smtp_err(e)) from e


def mail_bg_list(what, items, send, again):
    """(#6385): the mails of one queued row one after the other (send(item) per mail). The server fails before the first:
    mail_bg_failed (the row is tried again as a whole). It fails after some went out: the rest goes into a new row
    (again(rest) -> bgj_again), so no one gets a mail twice; on the row's last run the rest is tried one by one."""
    temp, out = None, 0
    for i, item in enumerate(items):
        try:
            send(item)
            out += 1
        except Exception as e:  # noqa: BLE001 -- one address's failure of any kind must not stop the mails to the rest
            if i and smtp_temp(e) and not bgj_last():
                try:  # some went out: the row must not raise from here (the queue would send them again)
                    moved = again(items[i:])
                except DbError as x:
                    print(what, "mail: the rest's new row failed:", type(x).__name__, "- tried one by one now", flush=True)
                    moved = False
                if moved:
                    print(what, "mail failed:", smtp_err(e), "- the rest waits for a new try", flush=True)
                    return
            try:
                mail_bg_failed(what, e)
            except SmtpTemporary as x:
                if not i and not bgj_last():
                    raise
                temp = x
            # a lasting refusal of this address, or the last run: the next one
    if temp and out and not bgj_last():  # some went out and the rest's own row failed: never the whole row again
        print(what, "mail: the rest failed in this run, not tried again (some went out)", flush=True)
    elif temp:
        raise temp  # the row ends 'failed' (the admins' queue alert, mail_disturbed)


def mail_disturbed(c):
    """(#6385): the instance's outgoing mail fails at the moment - a mail of the queue waits for its next try after a passing
    failure of the server, or ended on one within the hour (the queue's rows: the same answer in every process). The same
    answer for every address (an organisation admin's general notice, #3570: it never tells which address has an account)."""
    with system_ctx(c):  # a state of the queue, no content
        return bool(c.execute("""SELECT 1 FROM bg_jobs WHERE kind ILIKE ? AND error = ? AND
                                 (state='wait' OR (state='failed' AND finished_at >= ?)) LIMIT 1""",
                              ("mail:%", "SmtpTemporary", iso(now_utc() - timedelta(hours=1)))).fetchone())
