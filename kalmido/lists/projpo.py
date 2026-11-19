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
Only core imports: lists/lists.py and office/docs.py both call it at module level."""
from ..core.access import live_sql
from ..core.db import iso_ms, now_utc
from ..core.errors import BadInput
from ..core.i18n import tr
from ..core.writes import obj_history_add

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
    """The way back: document did's order_ref becomes its project's PO number while the project has none."""
    r = c.execute(f"""UPDATE lists l SET po_number=d.order_ref, updated_at=? FROM office_docs d
                      WHERE d.id=? AND l.id=d.list_id AND COALESCE(l.po_number, '')='' AND COALESCE(d.order_ref, '')<>''
                      AND d.kind IN {_KINDS_SQL} AND {live_sql('d')} RETURNING l.id, l.po_number""",
                  (iso_ms(now_utc()), int(did))).fetchone()
    if not r:
        return None
    obj_history_add(c, uid, "list", r["id"], {"po_number": ""}, {"po_number": r["po_number"]})  # the project's settings history
    return r["id"]


def ppo_drafts(c, lid, old, new):
    """Project lid's PO number changed from old to new: its drafts without an own different value follow (finalised ones never)."""
    if (old or "") == (new or ""):
        return []
    rows = c.execute(f"""UPDATE office_docs d SET order_ref=?, updated_at=? WHERE d.list_id=? AND d.kind IN {_KINDS_SQL} AND {_DRAFT}
                         AND COALESCE(d.order_ref, '') IN ('', ?) RETURNING d.id""",
                     (new or "", iso_ms(now_utc()), int(lid), old or "")).fetchall()
    return [x["id"] for x in rows]
