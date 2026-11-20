"""2.522.0 (#4433): the office and the private file store apart -- receipts only in the office, the private documents in the
file store, ONE general input sorts.

The office (decision 04.11.2026) = the documents space of the office a person works in (office/model.py office_where): an
organisation's office -> that organisation's documents space; the personal office of a person without one (pb_personal)
keeps its documents in the person's own space (office/books.py bk_ws), so there doc_meta.area tells the two apart
('office' | 'private' | '' = never sorted: a receipt row counts as office, everything else as private). Whoever has no office
(no feature "office", an agent, a kid, several organisations without a chosen one) keeps everything as before: no sorting,
no "Move to office", no filter.

The general input (an upload without a target in the own space, the share target, a mail to the person's own document
address) marks a new document area_sort = 'pending' and keeps the office it is brought in for (doc_meta.area_to, #7325: the
request's office, ar_to_req; without a request only the one office on, ar_only; '' = none clear); after its first recognition
(docs/ingest.py doc_after, outside the recognition's transaction) ar_sort_queued puts it: a surely recognised invoice /
receipt (ar_kind: an e-invoice, an invoice number with a net amount or a VAT rate) into that office, anything else and every
doubt (a stack waiting to be split) into the private space; an invoice without a clear office stays there as 'ask' ("New in
the office" offers it to the person). It never becomes a receipt by that (a person
records it, #2865). area_sort = 'auto' then offers "Wrong area" (one click, undo) in both areas; a person's choice is
'person'. A bound input (a scan inbox with place / folder docs/scankeys.py, the receipt fetcher docs/fetcher.py, an
organisation's document address, an upload into a chosen workspace, the office's own uploads) lands exactly where it
was sent and is never sorted.

Tenant boundary: the server sorts, only into the office of the person who brought the document in (created_by), with that
person's rights (files/fsmove.py fsm_plan in a request context of their own: write on the document, the right to add to the
office's documents folder); an agent never sorts and never moves (403), so nothing lands in a foreign workspace.

POST /api/docs/<id>/area {to: office | private, undo?: true} -- a person moves a document into the office / back into the
private space ("Move to office" of the private sheet, "Wrong area" of a sorted one; undo = the same call back)."""

import re

from flask import g, jsonify

from ..core.config import app
from ..core.db import body, bump, db, err, usettings
from ..core.i18n import N_, tr
from ..core.access import Denied
from ..core.pg import system_ctx
from ..accounts.session import me
from ..accounts.orgs import is_org_admin, user_orgs
from ..accounts.orgroles import org_role_key
from ..accounts.spacemove import smv_refuse_agent
from ..accounts.wsplace import wsp_on
from ..files.store import fs_log_add, need_node
from ..files.fsmove import _rm, fsm_apply, fsm_plan
from ..office.model import OfficeNoArea, office_pick, office_pick_req  # (#7313); (#7325); (#7321)
from ..core.errors import BadInput  # 2.654.0 (#4823)
from ..office.rights import ofr_allows  # review 2.522 (4)
from . import store as S
from .ingest import doc_after
from .split import sp_view

AR_AREAS = ("office", "private")
AR_NO_WRITE = ("guest", "readonly")  # roles that add nothing to an organisation's documents folder (docs/store.py root_add_ok)
AR_OTHER_OFFICE = N_("This upload is meant for another office than the one open. Reload the page and try again.")  # (#7321)
AR_OFFICE_OFF = N_("The office is switched off for you in this workspace.")  # (#7321)
_AR_ORG = re.compile(r"org:([1-9][0-9]{0,11})")


def ar_ws(oid):
    """(#7325): an office area of office_pick (None = the own office, 0 = none to tell, an organisation's id) as the value of
    doc_meta.area_to: 'private' | 'org:<id>' | ''."""
    return "private" if oid is None else ("org:%d" % oid if oid else "")


def ar_office(c, uid, to):
    """(#7325): the office area to ('private' | 'org:<id>' -- named by the caller: the request's office, ar_here, or the
    document's own target, doc_meta.area_to) of person uid as ('own', 'u<uid>', None) | ('org', 'o<oid>', oid), or None when it
    is no office of theirs that is on and writable for them. "On" is ONE question (accounts/wsplace.py wsp_on, the shared place
    of #7309: the main switch, "Also private", the organisation's areas, my module switches, the card); writable = a role
    that adds to the organisation's documents (accounting uploads receipts too) and the office groups' right on receipts. Never reads a setting or a request: what is meant is the caller's (#7325, before: _ar_named)."""
    if not uid or not to:
        return None
    with system_ctx(c):  # the person's own account row (kind, kid): the queue has no request
        u = c.execute("SELECT kind, kid, disabled FROM users WHERE id=?", (int(uid),)).fetchone()
    if not u or (u["kind"] or "user") == "agent" or u["kid"] or u["disabled"]:
        return None
    if to == "private":
        oid = None
    else:
        m = _AR_ORG.fullmatch(to)
        if not m or int(m.group(1)) not in user_orgs(c, uid):
            return None
        oid = int(m.group(1))
    if not wsp_on(c, uid, "office", oid):
        return None
    if oid is None:
        return ("own", S.doc_ws(None, uid), None)
    if org_role_key(c, uid, oid) in (None, *AR_NO_WRITE):
        return None
    with system_ctx(c):  # review 2.522 (4): the office groups must let the person work on receipts (office_org would say 403)
        if not ofr_allows(c, uid, oid, "receipts", "edit"):
            return None
    return ("org", S.doc_ws(oid, None), oid)


def ar_here(c, uid):
    """(#7325): the office uid's request works in (office/model.py office_pick_req: the area the request names, else the
    setting, else the only office on) as ar_office, None = none (several, none named; off). Requests only."""
    orgs = user_orgs(c, uid)
    try:
        oid = office_pick_req(c, uid, orgs)
    except BadInput:  # (#4823) a foreign area named (400 on the office routes): counts as none named, never that area
        oid = office_pick(c, uid, orgs, (usettings(c, uid).get("workspace") or "").strip(), "")
    return ar_office(c, uid, ar_ws(oid))


def ar_only(c, uid):
    """(#7325): the target of a new document of the general input WITHOUT a request (a mail to the person's own address, a
    mailbox rule): only the one office that is on for uid (office_pick without a name and without the setting: what the person
    had open then is unknown, the setting of the moment is no answer), else ''."""
    return ar_to(c, uid, office_pick(c, uid, user_orgs(c, uid), "", ""))


def ar_to(c, uid, oid):
    """(#7325): doc_meta.area_to for the office area oid of office_pick: '' when it is not on and writable for uid."""
    to = ar_ws(oid)
    return to if ar_office(c, uid, to) else ""


def ar_to_req(c, uid):
    """(#7325): doc_meta.area_to of a document the person's request brings in (docs/web.py the upload): ar_here."""
    off = ar_here(c, uid)
    return "" if not off else ("private" if off[0] == "own" else "org:%d" % off[2])


def ar_upload_need(c, uid, org):
    """(#7321 point 3): the office's own upload (POST /api/docs area=office: Office > Receipts, the bank's receipts) goes into
    the workspace org (None = Private) only when that is the office this request works in (office_pick_req: the area the app
    names with it, else the setting) -- a page left open in another office never puts a receipt into the wrong books.
    A foreign area named: 400 like the office routes; none clear: 400 office_no_area; another one: 409."""
    want = office_pick_req(c, uid, user_orgs(c, uid))
    if want == 0:
        raise OfficeNoArea()
    if (want or None) != (org or None):
        raise Denied(409, tr(AR_OTHER_OFFICE))


def ar_cands(c, uid):
    """(#7325): the office areas that are on and writable for uid (ar_office), Private first."""
    return [w for w in ("private", *("org:%d" % o for o in user_orgs(c, uid))) if ar_office(c, uid, w)]


def ar_is_receipt(c, nid):
    return bool(c.execute("SELECT 1 FROM rc_receipts WHERE node_id=?", (nid,)).fetchone())


def ar_of(c, m, off, uid):
    """The area of document meta m for person uid with the office off (ar_office): 'office' | 'private' | None (another
    workspace: an organisation that is not the office, somebody else's private space)."""
    if not off or not m:
        return None
    if m["ws"] == off[1]:
        if off[0] == "org" and m["area"] != "office" and not ar_is_receipt(c, m["node_id"]):
            return None  # 2.576.0 (#4487): the organisation's other documents (a contract): its file store, not the office
        return "office" if m["area"] == "office" or ar_is_receipt(c, m["node_id"]) else "private"
    if off[0] == "org" and m["ws"] == S.doc_ws(None, uid):
        return "office" if ar_is_receipt(c, m["node_id"]) else "private"  # an old receipt of the personal office (#4434 moves them)
    return None


def ar_kind(c, m, rc=False):
    """(#7325): the ONE recogniser of an invoice / receipt (before: ar_guess here and amv_kind in docs/areamove.py with two
    thresholds) -> ('receipt' | 'einvoice' | 'invoice', sure) of document meta m, or None (no receipt: a letter, a stack, not
    read). rc = it is a receipt already. Sure: a receipt, an e-invoice, an invoice number with one more sign (net amount, VAT
    rate); one sign alone (an amount, a rate, a number) is a doubt."""
    if rc:
        return "receipt", True
    if not m or m["state"] != "done" or (sp_view(m) or {}).get("stack"):
        return None  # not read (failed) or a stack waiting to be split (#4468)
    det = S.meta_json(c, m, "extracted", {})
    if not isinstance(det, dict):
        return None
    if isinstance(det.get("_einv"), dict):
        return "einvoice", True
    signs = sum(1 for k in ("invoice_no", "net", "vat_pct") if det.get(k))
    if not signs:
        return None
    return "invoice", bool(det.get("invoice_no")) and signs >= 2


def ar_invoice(c, nid, sure=True):
    """(#7325): is document nid an invoice / receipt (ar_kind)? sure: only a sure one (what the general input sorts into the
    office); sure=False: every sign counts (docs/pdfoptq.py: in doubt a document is kept as it is)."""
    k = ar_kind(c, S.meta_row(c, nid), ar_is_receipt(c, nid))
    return bool(k and (k[1] or not sure))


def ar_view(c, node, m, uid):
    """What the document sheet needs (GET /api/docs/<id> "area", docs/web.py doc_json), None without an office or in another workspace:
    {area, office: own | org, wrong: "Wrong area" offered, can_move, ask: no office was clear at the input (#7325)}."""
    off = ar_here(c, uid)
    a = ar_of(c, m, off, uid)
    if not a:
        return None
    rc = ar_is_receipt(c, m["node_id"])
    return {"area": a, "office": off[0], "wrong": m["area_sort"] == "auto" and not rc,
            "can_move": node["role"] in ("owner", "edit") and not rc,
            "ask": m["area_sort"] == "ask" and not rc}


def ar_sql(c, uid, want):
    """(SQL condition on d = doc_meta, params) of the documents list ?area=office | private; None = no filter (no office).
    Only ever ANDed to the list's visibility (docs/web.py doc_query: doc_visible), so it narrows a list and never shows more.
    2.576.0 (#4487, decision 04.11.2026: the office's receipts and the file store apart): an organisation's office takes
    only its office documents (area 'office': the office's own uploads, a sorted / moved invoice) and receipts out of the
    file store; the organisation's other documents (contracts, letters) stay there."""
    off = ar_here(c, uid) if want in AR_AREAS else None
    if not off:
        return None
    rc = "EXISTS (SELECT 1 FROM rc_receipts r WHERE r.node_id=d.node_id)"
    if off[0] == "org":  # 2.576.0 (#4487): only the organisation's office documents / receipts, its contracts stay in the file store
        office = f"((d.ws=? AND (d.area='office' OR {rc})) OR (d.ws=? AND {rc}))"
        params = [off[1], S.doc_ws(None, uid)]
    else:
        office = f"(d.ws=? AND (d.area='office' OR {rc}))"
        params = [off[1]]
    return (office, params) if want == "office" else (f"NOT {office}", params)


def _set(c, nid, area, how):
    c.execute("UPDATE doc_meta SET area=?, area_sort=? WHERE node_id=?", (area, how, nid))


def ar_move(c, uid, nid, to, how, off):
    """Document nid of person uid into the area to ('office' | 'private') of uid's office off (ar_office: the request's,
    ar_here, or the document's own target in the queue); how = the new area_sort. Returns the old sealed files to remove
    after the commit. Raises Denied (no office, not the person's, no right)."""
    m = S.meta_row(c, nid)
    cur = ar_of(c, m, off, uid)
    if not cur:
        raise Denied(409, tr("This document is not in your office or your own documents"))
    if ar_is_receipt(c, nid):
        raise Denied(409, tr("This document is a receipt already"))
    if cur == to:
        _set(c, nid, to, how)
        return []
    if off[0] == "own":
        _set(c, nid, to, how)
        return []
    target = off[2] if to == "office" else None
    plan = fsm_plan(c, uid, {"ids": [nid], "parent": "docs"}, target, False)
    if plan["block"]:
        raise Denied(plan["code"], plan["block"])
    new_paths, old_paths = [], []
    try:
        fsm_apply(c, uid, plan, target, new_paths, old_paths)
    except BaseException:
        _rm(new_paths)
        raise
    _set(c, nid, to, how)
    return old_paths


# ---- the general input, after the first recognition (docs/ingest.py doc_after) ------------------------------------------
def ar_sort_queued(c, nid):
    """A document of the general input (area_sort 'pending') goes to the office it was brought in for (doc_meta.area_to, set
    once by docs/ingest.py docs_ingest) or stays private (commits itself). (#7325): the queue only READS the target and checks
    that this office is still on and writable for the person; it never works one out (no request, no setting). A recognised
    invoice without such an office stays visible in the person's own documents with area_sort 'ask': "New in the office" of
    every office that is on for that person offers it to them alone (docs/web.py doc_query, office/oftree.py); taking it over
    is POST /api/docs/<id>/area in that office's request. Never area 'office' without an office."""
    with system_ctx(c):  # docs queue: the sorting of a document, decided for the person who brought it in
        m = c.execute("SELECT node_id, ws, area, area_sort, area_to, created_by FROM doc_meta WHERE node_id=?", (nid,)).fetchone()
    if not m or m["area_sort"] != "pending":
        return
    with system_ctx(c):  # review 2.522 (3): claim it -- a person's click in between wins, the queue then does nothing
        claimed = c.execute("UPDATE doc_meta SET area_sort='sorting' WHERE node_id=? AND area_sort='pending'", (nid,)).rowcount
    c.commit()
    if not claimed:
        return
    uid = m["created_by"]
    with system_ctx(c):  # the person's office (their memberships and switches) and what the recognition read
        off = ar_office(c, uid, m["area_to"] or "")
        inv = ar_invoice(c, nid)
        any_off = bool(off) or (inv and bool(ar_cands(c, uid)))

    def put(area, how):
        with system_ctx(c):
            _set(c, nid, area, how)
        c.commit()

    if m["ws"] != S.doc_ws(None, uid or 0):
        return put(m["area"] or "", "")  # moved out of the own space meanwhile (by the person): where it is now
    if not inv:
        return put("private" if off else "", "auto" if off else "")  # no invoice: the own documents ("Wrong area" with an office)
    if not off:
        return put("", "ask" if any_off else "")  # no clear office (several, none named, off now): visible, offered
    if off[0] == "own":
        return put("office", "auto")
    with system_ctx(c):  # docs queue (no request): the sorting state of the person's own document / their office role
        back = is_org_admin(c, uid, off[2])
    if not back:
        # review 2.522 (1, 2): out of an organisation only its admin moves a file (accounts/orgout.py org_out_ok), so for a
        # member "Wrong area" could not bring it back, and a stranger's mail to the person's address would decide the tenant:
        # it stays in the own documents, offered in "New in the office" (#7325) -- taking it over is the person's own click
        return put("", "ask")
    old = []
    prev = c.ctx
    try:
        with app.test_request_context("/api/docs/area-sort"):
            g.db = c
            g.user = c.execute("SELECT * FROM users WHERE id=?", (int(uid),)).fetchone()
            try:
                old = ar_move(c, uid, nid, "office", "auto", off)
                fs_log_add(c, nid, "area", "auto:office")  # review 2.522 (5): the server sorted, not the person
                bump(c)
                c.commit()
            except Exception as e:  # noqa: BLE001 -- a refused move leaves it in the own documents, offered
                c.rollback()
                print("docs: area sort", nid, type(e).__name__, flush=True)
                with system_ctx(c):
                    _set(c, nid, "", "ask")
                c.commit()
            finally:
                g.pop("db", None)  # the queue's connection: closed by the queue
    finally:
        c.set_ctx(*prev)  # the queue's own context again (the request context followed the person)
    _rm(old)


if ar_sort_queued not in doc_after:
    doc_after.append(ar_sort_queued)


# ---- people ---------------------------------------------------------------------------------------------------------
@app.post("/api/docs/<int:nid>/area")
def ar_post(nid):
    """{to: office | private, undo?: bool}: a person moves the document into the office / the private space."""
    smv_refuse_agent()  # agents never move a document between the areas (nor sort one)
    c = db()
    uid = me()
    b = body()
    to = b.get("to")
    if to not in AR_AREAS:
        return err(tr("Invalid value: {0}", "to"))
    need_node(c, nid, write=True)
    m = S.meta_row(c, nid)
    if not m:
        raise Denied(404)
    was = m["area_sort"]
    how = "auto" if b.get("undo") is True and was == "person" else ("person" if was in ("auto", "person", "ask") else "")
    try:
        old = ar_move(c, uid, nid, to, how, ar_here(c, uid))  # (#7325): the office of this request ("New in the office" of it)
        fs_log_add(c, nid, "area", to)
        bump(c)
        c.commit()
    except BaseException:
        c.rollback()
        raise
    _rm(old)
    n = c.execute("SELECT org_id FROM fs_nodes WHERE id=?", (nid,)).fetchone()
    return jsonify(id=nid, area=to, area_sort=how, ws=S.meta_row(c, nid)["ws"], org_id=n["org_id"] if n else None)
