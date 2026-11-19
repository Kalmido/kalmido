"""(#7300): "Created by" of a quotation -- office_docs.author_id, a choice among the organisation's people.

Decided 19.11.2026: quotations get the field "Erstellt von", a choice of the organisation's members;
the name stands on the quotation's PDF as "Ihr Ansprechpartner" / "Your contact" (name only).
  * created_by stays the account that really made the document (log, rights); author_id is only the person named.
  * the default of a new quotation is the person making it (an agent or a guest names nobody: NULL); it can change while the
    quotation is a draft (office_docs edits refuse finalised ones), finalising freezes the name with the sender (ledger).
  * the choice: active members of the organisation (no agents, no guests, no disabled accounts); a personal office has no
    choice and no line (only one person works there).
  * the number token {initials} reads author_id (fallback created_by), so field and number agree; numbers given stay.
  * a duplicate and an invoice made from the quotation keep author_id (docs.DUP_SKIP lacks it, invoices.inv_new_row copies
    it); the invoice does not print it.
  * no FK (like contact_id): an account deleted later leaves the id, the name then falls back to none."""
from ..core.errors import BadInput
from ..core.i18n import tr
from ..core.pg import system_ctx
from .ledger import ofx_user_label
from .model import pb_owner


def oda_choices(c, oid):
    """[{id, name}] who can be named on a quotation of office area oid; [] for a personal office."""
    if pb_owner(c, oid) is not None:
        return []
    with system_ctx(c):  # names of the area's people (membership structure), like cards._members
        rows = c.execute("SELECT u.id, u.display_name, u.username FROM org_members m JOIN users u ON u.id=m.user_id "
                         "WHERE m.org_id=? AND NOT u.disabled AND COALESCE(u.kind, 'user')<>'agent' AND COALESCE(m.role, '')<>'guest' "
                         "ORDER BY lower(COALESCE(NULLIF(u.display_name, ''), u.username))", (oid,)).fetchall()
    return [{"id": r["id"], "name": (r["display_name"] or r["username"] or "").strip()} for r in rows]


def oda_default(c, oid, uid, kind):
    """author_id of a new document of kind made by uid: uid when uid can be named on a quotation, else None."""
    if kind != "offer" or not uid:
        return None
    return uid if any(p["id"] == uid for p in oda_choices(c, oid)) else None


def oda_clean(c, oid, b, cur, f):
    """author_id from body b into f (quotations only; None / "" / 0 = nobody); a person outside the choice: 400."""
    if "author_id" not in b or cur["kind"] != "offer":
        return
    v = b.get("author_id")
    if v in (None, "", 0, "0"):
        f["author_id"] = None
        return
    try:
        v = int(v)
    except (TypeError, ValueError):
        raise BadInput(tr("Invalid value: {0}", "author_id")) from None
    cur_v = cur["author_id"] if "author_id" in cur.keys() else None
    if v != cur_v and not any(p["id"] == v for p in oda_choices(c, oid)):
        raise BadInput(tr("Invalid value: {0}", "author_id"))
    f["author_id"] = v


def oda_name(c, oid, r):
    """The printed name of document r's author: '' without one, in a personal office or for another kind."""
    aid = r["author_id"] if "author_id" in r.keys() else None
    if not aid or r["kind"] != "offer" or pb_owner(c, oid) is not None:
        return ""
    return ofx_user_label(c, aid)
