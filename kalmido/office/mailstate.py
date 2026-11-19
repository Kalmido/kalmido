"""(#6820): the delivery state of a document's e-mail -- office_docs.mail_state / mail_at (migrations.d/6820.py).

  none     never mailed by Kalmido (or before 2.1435.0)
  sent     the mail server took the mail (invoices.inv_send_mail, the one place: also through a person's own mailbox)
  failed   the mail server refused it or could not be reached (the same place; the document stays unsent)
  bounced  a person of the office marked it "Delivery failed" (a bounce lies in the mailbox; POST .../mail-bounced, office
           write right) -- reading bounces automatically is a task of its own

Every change is an entry of the core's history (obj_history, kind office_doc: before / after of mail_state; actor the person,
or the system for sent / failed: user None, via 'system') and, for failed / bounced, a line of the document's office log (its
"History"; a sent mail has its line "send" already). The route POST .../mail-bounced stands in office/docs.py
(odoc_mail_bounced, next to the status). Any document kind (quotations, invoices, reminders, ...). The list
filters on it through its status select (?status=mail_failed: failed or bounced). The issuer's read routes show
{state, at} without address and error text (issdocs.isd_public). No table of its own."""
from ..core.config import app
from ..core.db import DbError, iso_ms, now_utc
from ..core.writes import obj_history_add
from .ledger import ofx_log

OMS_STATES = ("none", "sent", "failed", "bounced")
OMS_BAD = ("failed", "bounced")  # the list's filter "Delivery failed"
OMS_FILTER = "mail_failed"       # its value in the status select (?status=)
OMS_KIND = "office_doc"          # the tracked kind of office_docs (office/undo.py ow_kind)


def oms_public(r):
    """{state, at} of document row r (at: ISO text or None)."""
    k = r.keys() if hasattr(r, "keys") else ()
    st = (r["mail_state"] if "mail_state" in k else None) or "none"
    at = r["mail_at"] if "mail_at" in k else None
    return {"state": st if st in OMS_STATES else "none", "at": at.isoformat() if hasattr(at, "isoformat") else (at or None)}


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
