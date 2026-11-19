"""(#6820): the delivery state of a document's e-mail -- office_docs.mail_state / mail_at (migrations.d/6820.py).

  none     never mailed by Kalmido (or before 2.1435.0)
  sent     the mail server took the mail (invoices.inv_send_mail, the one place: also through a person's own mailbox)
  failed   the mail server refused it or could not be reached (the same place; the document stays unsent)
  bounced  a person of the office marked it "Delivery failed" (a bounce lies in the mailbox; POST .../mail-bounced, office
           write right), or (#6547) Kalmido read the delivery report of the mail (integrations/mail.py mail_bounce_take): matched
           by office_docs.mail_msg_id (the Message-ID of the last mail, oms_sent_id), the status code in mail_why, the person
           who sent it hears it (News + push, mail_bounce_tell)

Every change is an entry of the core's history (obj_history, kind office_doc: before / after of mail_state; actor the person,
or the system for sent / failed: user None, via 'system') and, for failed / bounced, a line of the document's office log (its
"History"; a sent mail has its line "send" already). The route POST .../mail-bounced stands in office/docs.py
(odoc_mail_bounced, next to the status). Any document kind (quotations, invoices, reminders, ...). The list
filters on it through its status select (?status=mail_failed: failed or bounced). The issuer's read routes show
{state, at} without address and error text (issdocs.isd_public). No table of its own."""
from ..core.config import app
from ..core.db import DbError, iso_ms, now_utc
from ..core.i18n import N_, tr
from ..core.writes import obj_history_add
from ..collab.mailback import mail_bounce_tell, mail_bounce_why, mail_mid  # (#6547)
from .ledger import ofx_log

OMS_STATES = ("none", "sent", "failed", "bounced")
OMS_BAD = ("failed", "bounced")  # the list's filter "Delivery failed"
OMS_FILTER = "mail_failed"       # its value in the status select (?status=)
OMS_LABEL = {"offer": N_("Quotation"), "invoice": N_("Invoice"), "credit": N_("Credit note"), "reminder": N_("Reminder"),
             "delivery": N_("Delivery note")}  # (#6547): what the News item of a returned mail names (like docref.OFD_LABEL: a cycle)
OMS_KIND = "office_doc"          # the tracked kind of office_docs (office/undo.py ow_kind)


def oms_public(r, why=False):
    """{state, at} of document row r (at: ISO text or None). why (#6547, the office's own routes, not the issuer's): + why = the
    reason of a mail Kalmido saw come back, in words (only then)."""
    k = r.keys() if hasattr(r, "keys") else ()
    st = (r["mail_state"] if "mail_state" in k else None) or "none"
    at = r["mail_at"] if "mail_at" in k else None
    out = {"state": st if st in OMS_STATES else "none", "at": at.isoformat() if hasattr(at, "isoformat") else (at or None)}
    if why:
        code = (r["mail_why"] if "mail_why" in k else "") or ""
        if out["state"] == "bounced" and code:  # (only then: a mail never returned keeps the answer {state, at})
            out["why"] = mail_bounce_why(code)
    return out


def oms_set(c, oid, did, state, uid=None, log=True):
    """Sets the delivery state of document did to state (sent / failed / bounced, or back to sent from bounced): the columns,
    updated_at (the issuer's changed_since sees it), the history entry and for failed / bounced the office log line.
    uid None = Kalmido itself (system). The caller commits; nothing when the state is already that one (mail_at moves on)."""
    if state not in OMS_STATES:
        raise ValueError(state)
    r = c.execute("SELECT mail_state FROM office_docs WHERE id=? AND org_id=?", (int(did), int(oid))).fetchone()
    if r is None:
        return
    before = r["mail_state"] or "none"
    ts = now_utc()
    c.execute("UPDATE office_docs SET mail_state=?, mail_at=?, updated_at=? WHERE id=? AND org_id=?", (state, iso_ms(ts), iso_ms(ts), int(did), int(oid)))
    if state != "bounced" or uid:  # (#6547): the reason of a returned mail goes with any other change of the state
        c.execute("UPDATE office_docs SET mail_why='' WHERE id=? AND org_id=? AND mail_why<>''", (int(did), int(oid)))
    if before == state:
        return
    obj_history_add(c, uid, OMS_KIND, did, {"mail_state": before}, {"mail_state": state}, action="mail", org_id=oid,
                    agent=False, via=None if uid else "system")
    if log and state in OMS_BAD:
        ofx_log(c, oid, "mail_" + state, doc_id=did, detail={"before": {"mail_state": before}, "after": {"mail_state": state}})


def oms_failed_after(c, oid, did):
    """The mail of document did was refused after its marks were rolled back (invoices.inv_send_mail): state failed in a
    transaction of its own, committed, so the refusal stays visible. Never raises (the caller raises the refusal)."""
    try:
        oms_set(c, oid, did, "failed")
        c.commit()
    except DbError as e:  # the refusal itself is what the person must see
        c.rollback()
        app.logger.warning("office mail state: %s", type(e).__name__)


def oms_was_mailed(c, oid, r):
    """True when document row r went out by e-mail: state sent, or (before 2.1435.0) a log line "send"."""
    st = oms_public(r)["state"]
    if st != "none":
        return st in ("sent", "bounced")
    return c.execute("SELECT 1 FROM office_doc_log WHERE org_id=? AND doc_id=? AND action='send' LIMIT 1", (oid, r["id"])).fetchone() is not None


def oms_sent_id(c, oid, did, sent):
    """(#6547): the Message-ID of the mail of document did that just went out (sent = the message, integrations/mail.py
    mail_send), so its delivery report finds it. The caller commits."""
    mid = mail_mid(sent)
    if mid:
        c.execute("UPDATE office_docs SET mail_msg_id=? WHERE id=? AND org_id=?", (mid, int(did), int(oid)))


def oms_in_scope(c, oid, scope):
    """(#6547, reader F3 of job/5778): does office oid belong to the mailbox a delivery report came in through? scope None = the
    instance mailbox (any office: the Message-ID is known only to the sender and the recipient); (org, ws) = a workspace's own
    mailbox: an organisation's -> only its office, a person's ("u<id>") -> only that person's personal office."""
    if scope is None:
        return True
    org, ws = scope
    if org:
        return int(oid) == int(org)
    ws = str(ws or "")
    if not ws.startswith("u") or not ws[1:].isdigit():
        return False
    r = c.execute("SELECT personal_of FROM orgs WHERE id=?", (int(oid),)).fetchone()
    return bool(r) and r[0] is not None and int(r[0]) == int(ws[1:])


def oms_bounce(c, mid, code, scope):
    """(#6547, integrations/mail.py mail_bounce_hooks): the documents whose last mail had Message-ID mid came back: state
    bounced (by Kalmido, the reason's code in mail_why) and the person who sent it hears it. The instance mailbox: the Message-ID
    is known only to the sender and the recipient; a workspace's own mailbox only marks its own office's (oms_in_scope).
    True when one was found."""
    rows = [r for r in c.execute("SELECT id, org_id, kind, number, mail_state FROM office_docs WHERE mail_msg_id=?", (mid,)).fetchall()
            if oms_in_scope(c, r["org_id"], scope)]
    for r in rows:
        oid, did = r["org_id"], r["id"]
        oms_set(c, oid, did, "bounced")
        c.execute("UPDATE office_docs SET mail_why=? WHERE id=? AND org_id=?", (code or "?", did, oid))
        who = c.execute("SELECT user_id FROM office_doc_log WHERE org_id=? AND doc_id=? AND action='send' AND user_id IS NOT NULL "
                        "ORDER BY id DESC LIMIT 1", (oid, did)).fetchone()
        if who and r["mail_state"] != "bounced":
            tab = "offers" if r["kind"] == "offer" else "invoices"
            label = OMS_LABEL.get(r["kind"]) or "Document"
            mail_bounce_tell(c, [who[0]], "mail_bounced_doc", lambda lg, n=r["number"] or "", x=label: (tr(x, lg=lg) + " " + n).strip(),
                             code, click=f"office/{tab}/{int(did)}", go=f"office/{tab}/{int(did)}")
    return bool(rows)

