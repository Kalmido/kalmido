"""#6945: the PO number of a project (lists.po_number) and the order reference of its documents (office_docs.order_ref).

There is no field of its own on the documents: the PO number IS order_ref (BT-13 in ZUGFeRD / XRechnung / Peppol).
- ppo_clean(v)                 the value of a PATCH (text, at most PPO_MAX characters, '' = none)
- ppo_doc_take(c, did)         a document bound to a project (offer / invoice / credit note, not finalised, no own
                               order_ref) takes the project's PO number -> the value taken or None
- ppo_from_doc(c, uid, did)    the way back: a document of a project that has no PO number yet gives it its order_ref;
                               a project with another PO keeps its own (the document keeps its own too) -> project id or None
- ppo_drafts(c, lid, old, new) the project's PO changed: drafts that still carried the old one (or none) follow; a finalised
                               document and a draft with its own different value stay -> the ids changed
- ppo_of(c, lid)               the project's PO number ('' = none), for the editor's hint "differs from the project's PO"
Only core imports at module level: lists/lists.py imports it before its own names exist (core.writes loads inside)."""
from ..core.access import MANAGE_ROLES, list_role, live_sql, me
from ..core.db import iso_ms, now_utc
from ..core.errors import BadInput
from ..core.i18n import tr

PPO_MAX = 80  # as office_docs.order_ref (office/docs.py clean_doc)
PPO_KINDS = ("offer", "invoice", "credit")  # the kinds that belong to a project (office/docproject.py DPJ_KINDS)
_KINDS_SQL = "('offer','invoice','credit')"
_DRAFT = f"d.locked_at IS NULL AND d.status='draft' AND {live_sql('d')}"


def ppo_clean(v):
    """A PO number from a request: trimmed text, at most PPO_MAX characters; None / '' = none."""
    if v is None:
        return ""
    if not isinstance(v, (str, int)) or isinstance(v, bool):
        raise BadInput(tr("Invalid value: {0}", "po_number"))
    v = " ".join(str(v).split())
    if len(v) > PPO_MAX:
        raise BadInput(tr("Invalid value: {0}", "po_number"))
    return v


def ppo_of(c, lid):
    if not lid:
        return ""
    r = c.execute("SELECT po_number FROM lists WHERE id=?", (int(lid),)).fetchone()
    return (r["po_number"] or "") if r else ""


def ppo_doc_take(c, did):
    """A new / newly bound document takes its project's PO number when it has no order reference of its own (drafts only)."""
    r = c.execute(f"""UPDATE office_docs d SET order_ref=l.po_number, updated_at=? FROM lists l
                      WHERE d.id=? AND l.id=d.list_id AND COALESCE(l.po_number, '')<>'' AND COALESCE(d.order_ref, '')=''
                      AND d.kind IN {_KINDS_SQL} AND {_DRAFT} RETURNING d.order_ref""", (iso_ms(now_utc()), int(did))).fetchone()
    return r["order_ref"] if r else None


def ppo_from_doc(c, uid, did):
    """The way back: document did's order_ref becomes its project's PO number while the project has none.
    #7190 (F1 of the review of job/5545): only for a person who may change the project's settings (owner / project admins, as
    PATCH /api/lists po_number) -- an office member without that role leaves the project as it is."""
    lid = c.execute("SELECT list_id FROM office_docs WHERE id=?", (int(did),)).fetchone()
    if not lid or not lid["list_id"] or list_role(c, lid["list_id"], uid) not in MANAGE_ROLES:
        return None
    r = c.execute(f"""UPDATE lists l SET po_number=d.order_ref, updated_at=? FROM office_docs d
                      WHERE d.id=? AND l.id=d.list_id AND COALESCE(l.po_number, '')='' AND COALESCE(d.order_ref, '')<>''
                      AND d.kind IN {_KINDS_SQL} AND {live_sql('d')} RETURNING l.id, l.po_number""",
                  (iso_ms(now_utc()), int(did))).fetchone()
    if not r:
        return None
    from ..core.writes import obj_history_add  # core.writes comes later in kalmido/__init__.py ORDER (it loads lists.lists)
    obj_history_add(c, uid, "list", r["id"], {"po_number": ""}, {"po_number": r["po_number"]})  # the project's settings history
    return r["id"]


def ppo_drafts(c, lid, old, new, uid=None):
    """Project lid's PO number changed from old to new: its drafts without an own different value follow (finalised ones never).
    #7190 (F2 of the review of job/5545): only the drafts of office areas where the person (uid, default the signed-in one) has
    an office role -- another area's drafts keep their value --, each change in that area's office log like an edit."""
    if (old or "") == (new or ""):
        return []
    from ..office.ledger import ofx_log
    from ..office.model import office_role
    uid = uid or me()
    cand = c.execute(f"""SELECT d.id, d.org_id FROM office_docs d WHERE d.list_id=? AND d.kind IN {_KINDS_SQL} AND {_DRAFT}
                         AND COALESCE(d.order_ref, '') IN ('', ?)""", (int(lid), old or "")).fetchall()
    areas = {x["org_id"] for x in cand}
    mine = {oid for oid in areas if oid and office_role(c, uid, oid)}
    out = []
    for x in cand:
        if x["org_id"] not in mine:
            continue
        r = c.execute(f"""UPDATE office_docs d SET order_ref=?, updated_at=? WHERE d.id=? AND d.org_id=? AND {_DRAFT}
                          AND COALESCE(d.order_ref, '') IN ('', ?) RETURNING d.id, d.order_ref AS was""",
                      (new or "", iso_ms(now_utc()), x["id"], x["org_id"], old or "")).fetchone()
        if r:
            ofx_log(c, x["org_id"], "update", doc_id=r["id"], detail={"before": {"order_ref": old or ""}, "after": {"order_ref": new or ""}})
            out.append(r["id"])
    return out
