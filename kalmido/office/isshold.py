"""2.1384.0 (#6700): the hold mark at a client an invoice issuer's key set up or changed (clients.issuer_hold, office/issclients.py).

Every sending reads the recipient's address fresh from the client (contacts_cl.fk_send_rcpts, recurring.rin_client_mail) and a
series with auto_send finalises and mails without a dialog, so a note on a document is not enough: the mark sits at the client
and every way that finalises or sends a document of it asks here (ihd_check):

  - finalising (ledger.ofx_finalize) and sending (invoices.inv_send: a send, a send again, a reminder, a correction) in the
    dialog need the person's explicit confirmation: the body's client_hold_ok = the mark's "at" as the dialog showed it (a
    mark the key changed after the dialog opened asks again);
  - every way without a dialog (the series' auto_send and its catch-up of a mail, anything that calls without the confirmation)
    is refused: the document stays a draft or unsent (409 client_hold, stored reason);
  - the client portal takes no sign-in by the address of a client with a mark (portaldocs), and its invitation is refused.

Only a person takes the mark away (POST /api/clients/<id>/issuer-hold: "Client data from the invoice issuer checked"), with
the rights to change the client's invoicing fields; the key never does (it sets it again with every change of a held field).

The mark (JSON): {"at": ISO time of the last change, "issuer": id, "new": the key set the client up, "fields": {field: [old,
new]} (old of the first change since a person last checked, new of the last), "flags": ["client_lookalike", "text_suspicious"]}.
The fields are the client's own invoicing data (not sealed at rest, like the client's columns)."""
import json

from flask import g, has_request_context, jsonify

from ..core.config import app
from ..core.db import body, bump, db, iso, iso_ms, now_utc
from ..core.errors import Denied, DeniedKey
from ..core.i18n import N_, tr
from ..core.pg import system_ctx
from ..accounts.session import me
from ..team.clients import CLIENT_BILL_GATED, _gate, cl_bill_ok, need_client
from .issuers import iss_log
from .model import pb_cl_sql
from .owrite import ow_write

IHD_FIELDS = ("email_invoice", "name", "name_extra", "street", "address_extra", "zip", "city", "country", "vat_id", "buyer_reference")
IHD_HELD = N_("The client's data come from an invoice issuer and no person has checked them yet: confirm them in the dialog, or check them at the client first.")
IHD_NO_DIALOG = N_("The client's data come from an invoice issuer and no person has checked them yet: nothing is finalised or sent without a dialog. Check them at the client, then send it by hand.")


def ihd_load(raw):
    """The mark of a client's column value (None when there is none or it cannot be read: an unreadable mark still holds)."""
    if not raw:
        return None
    try:
        h = json.loads(raw)
    except (TypeError, ValueError):
        h = None
    return h if isinstance(h, dict) else {"at": str(raw)[:40], "fields": {}, "flags": [], "new": False}


IHD_FLAGS = ("client_lookalike", "text_suspicious")  # the flags a mark may carry (office/issclients.py sets them)
IHD_VALUE_MAX = 200  # a field's value in a mark: the longest client field a key sets (street, address extra, e-mail)


def _ihd_pair(v):
    """[old, new] of a mark's field as two texts ("" for anything else: a number, an object, a list of another length)."""
    if isinstance(v, (list, tuple)) and len(v) == 2 and all(isinstance(x, str) for x in v):
        return [v[0][:IHD_VALUE_MAX], v[1][:IHD_VALUE_MAX]]
    return None


def ihd_norm(raw):
    """#7113 (review F11): a mark built anew from what an import brought along (the importing admin's file): "at" as a text,
    "fields" only the known ones with two texts, "flags" from IHD_FLAGS, "new" a boolean, no issuer (another area's). A mark that
    says nothing (no at, field, flag, new) is None (NULL): an empty one held every finalising and send without being shown. An
    unreadable one still holds (ihd_load). -> JSON text or None."""
    h = ihd_load(raw)
    if h is None:
        return None
    at = h.get("at") if isinstance(h.get("at"), str) else ""
    f = h.get("fields") if isinstance(h.get("fields"), dict) else {}
    fields = {k: p for k, p in ((k, _ihd_pair(f.get(k))) for k in IHD_FIELDS if k in f) if p is not None}
    fl = h.get("flags") if isinstance(h.get("flags"), list) else []
    flags = sorted({x for x in fl if isinstance(x, str) and x in IHD_FLAGS})
    new = h.get("new") is True
    if not (at.strip() or fields or flags or new):
        return None
    out = {"at": at.strip()[:40] or iso_ms(now_utc()), "new": new, "fields": fields, "flags": flags}
    return json.dumps(out, ensure_ascii=False)


def ihd_issuer(c, h, cid):
    """The issuer of mark h (row id, org_id, name) only when it belongs to the area of client cid; None: no issuer, an unknown
    one or another area's (review F1: a mark that came along with an organisation import or was set by hand names no issuer
    of another area - its name is not shown and its office log gets no line)."""
    try:
        iid = int((h or {}).get("issuer") or 0)
    except (TypeError, ValueError):
        return None
    if not iid or not cid:
        return None
    with system_ctx(c):  # the issuer and whether the client lies in its area (both rows may be outside the reader's context)
        iss = c.execute("SELECT id, org_id, name FROM office_issuers WHERE id=?", (iid,)).fetchone()
        if iss is None or not c.execute(f"SELECT 1 FROM clients WHERE id=? AND {pb_cl_sql(c, iss['org_id'])}", (int(cid),)).fetchone():
            return None
    return iss


def _viewer():
    """The signed-in person of the request (None: none, e.g. a series' run in the background)."""
    u = g.get("user") if has_request_context() else None
    return u["id"] if u else None


def ihd_public(c, h, cid=None, uid=None):
    """The mark as the office shows it: {at, new, issuer: name, fields: [{field, old, new}], flags, client_id}.
    review F4: the old / new values of an invoicing field a person may not see (team/clients.py CLIENT_BILL_GATED,
    cl_bill_ok) stay empty - the field's name shows that it changed (uid: the person, default the request's)."""
    if h is None:  # #7113 (review F11): an empty mark {} still holds, so it shows too (a person can take it away)
        return None
    iss = ihd_issuer(c, h, cid)
    uid = uid if uid is not None else _viewer()
    see = True
    f = h.get("fields") if isinstance(h.get("fields"), dict) else {}
    if any(k in CLIENT_BILL_GATED for k in f):
        oid = None
        if cid:
            with system_ctx(c):  # the client's area only (the rights of uid in it decide)
                r = c.execute("SELECT org_id FROM clients WHERE id=?", (int(cid),)).fetchone()
            oid = r[0] if r else None
        see = bool(uid) and cl_bill_ok(c, uid, oid)

    def val(k, v, i):
        if k in CLIENT_BILL_GATED and not see:
            return ""
        return (_ihd_pair(v) or ["", ""])[i]  # #7113 (review F11): a broken value (number, object) shows empty, no 500
    return {"at": str(h.get("at") or ""), "new": bool(h.get("new")), "issuer": iss["name"] if iss else "", "client_id": cid,
            "fields": [{"field": k, "old": val(k, v, 0), "new": val(k, v, -1), **({} if see or k not in CLIENT_BILL_GATED else {"hidden": True})}
                       for k, v in f.items() if k in IHD_FIELDS],
            "flags": [x for x in (h.get("flags") if isinstance(h.get("flags"), list) else []) if isinstance(x, str)][:5]}


def ihd_of(c, cid):
    """The mark of client cid (None: none). Read as "system": the check must never miss a mark because the reader's context
    does not see the row (a hidden row would be a send without the check)."""
    if not cid:
        return None
    with system_ctx(c):  # existence of the mark only; the rights to the document were checked by the caller
        r = c.execute("SELECT issuer_hold FROM clients WHERE id=?", (int(cid),)).fetchone()
    return ihd_load(r[0]) if r else None


def ihd_check(c, cid, ok=None):
    """Raises 409 client_hold (DeniedKey, data {client_hold: the mark}) while client cid has a mark and ok is not the mark's
    "at" (the dialog's explicit confirmation). ok None = a way without a dialog: always refused while the mark stands."""
    h = ihd_of(c, cid)
    if h is None:
        return
    if ok is not None and isinstance(ok, str) and ok and ok == str(h.get("at") or ""):
        return
    e = DeniedKey(409, IHD_HELD if ok is not None else IHD_NO_DIALOG)
    e.data = {"client_hold": ihd_public(c, h, int(cid))}
    e.v1_name = "client_hold"
    raise e


def ihd_ok(b):
    """The confirmation of a dialog's body b: its client_hold_ok (text) or "" (a dialog without one: asked, refused)."""
    v = b.get("client_hold_ok") if isinstance(b, dict) else None
    return v if isinstance(v, str) else ""


@app.post("/api/clients/<int:cid>/issuer-hold")
def ihd_clear(cid):
    """{at} -- a person checked the client data an invoice issuer set (the mark as shown: at; a newer one 409 with it): the mark
    goes. The rights of a change of the client's invoicing fields (need_client for a write, team/clients.cl_bill_ok edit); a
    line in the office log of the issuer and in the client's history."""
    c = db()
    uid = me()
    _gate(c)
    r = need_client(c, cid, uid)
    if not cl_bill_ok(c, uid, r["org_id"], "edit"):
        raise Denied(403)
    b = body()
    at = b.get("at") if isinstance(b, dict) else None
    h = ihd_load(r["issuer_hold"])
    if h is None:
        return jsonify(ok=True, client_hold=None)
    seen = {}

    def clean(c, b, cur):  # review F3: compared under the client's lock with the mark as it is now (a key's change waits for it)
        hc = ihd_load(cur.get("issuer_hold"))
        if hc is None:
            return {}
        if not isinstance(at, str) or at != str(hc.get("at") or ""):
            e = Denied(409, tr("The invoice issuer changed the client's data again meanwhile; check them again"))
            e.data = {"client_hold": ihd_public(c, hc, cid, uid)}
            raise e
        seen["h"] = hc
        return {"issuer_hold": None}
    ow_write(c, uid, "client", cid, {}, clean, where="id=?", args=(cid,), lock=f"clients-{cid}", version=False)
    h = seen.get("h")
    iss = ihd_issuer(c, h, cid) if h else None  # review F1: only an issuer of the client's own area gets the line
    if iss is not None:
        iss_log(c, iss["org_id"], iss["id"], "issuer_hold_checked", f"client:{cid}", {"client": cid, "at": h.get("at"), "checked_at": iso(now_utc())}, uid=uid)
    bump(c)
    c.commit()
    return jsonify(ok=True, client_hold=None)
