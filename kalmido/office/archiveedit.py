"""2.81.0 B (#1834): correct an archived document of the office (office_archive, legacyimport.py) afterwards: its client,
its amount as net + tax lines (19 %, 7 %, 0 %, reverse charge; Kalmido adds the gross) and paid (invoices only). The PDF
and its number never change. Everybody who reads the office archive of the organisation may assign its client (members
and admins; agents never reach the office routes, office_gate); amount, tax lines and paid only an office admin
(audit 2.86 B3, #1968: the bookkeeping sums hang on them) and never below zero. Every change goes into the entry's history
(office_archive_log: when, who, in which role, old and new value as JSON text), shown in the edit dialog.
office_archive.amount stays the gross sum (2.80.0 reads it unchanged); tax_lines NULL = only the gross is known."""
import json
import os
import re
from decimal import Decimal, ROUND_HALF_UP

from flask import jsonify

from ..core.config import app
from ..core.access import Denied, live_sql
from ..core.i18n import N_, tr
from ..core.db import bump, iso, iso_ms, local_now, now_utc
from ..core.pg import system_ctx
from ..core.retention import ret_keep_years
from ..core.writes import obj_on_purge
from ..core.conflict import ccf_check  # 2.570.0 (#4770)
from ..core.pg import write_lock
from ..core.errors import BadInput
from .model import OFFICE_ADMIN_ONLY, office_ctx_admin, office_role, pb_cl_sql
from .rights import ofr_admin_or
from .okern import ofk_register, ofk_restore, ofk_trash  # 2.1315.0 (#6590 c)
from .periodlock import period_need_open  # 2.1315.0 (#6590 c)
from .ledger import ofx_log  # 2.1315.0 (#6590 c)
from .legacyimport import _number_used, _run_count, fi_archive_path  # 2.1315.0 (#6590 c)
from .legacyimport import _amount, _archive_fields, _archive_public  # 2.369.5 (#2517): pulled up from functions

R81B_RATES = {"19": 19, "7": 7, "0": 0, "rc": 0}  # rc = reverse charge: the client pays the tax, none on the document
R81B_LINES_MAX = 10
R81B_ADMIN_FIELDS = ("amount", "tax_lines", "paid")  # #1968: members only assign the client
CENT = Decimal("0.01")


def r81b_tax_lines(v):
    """The checked tax lines [{net, tax}] -> ([{net, tax, amount}] with texts, gross Decimal); 400 for anything else."""
    if not isinstance(v, list) or not 1 <= len(v) <= R81B_LINES_MAX:
        raise BadInput(tr("Invalid value: {0}", "tax_lines"))
    out, gross = [], Decimal(0)
    for ln in v:
        net = _amount(ln.get("net")) if isinstance(ln, dict) else None
        tax = str(ln.get("tax")) if isinstance(ln, dict) else ""
        if net is None or net < 0 or tax not in R81B_RATES:  # #1968: no negative net
            raise BadInput(tr("Invalid value: {0}", "tax_lines"))
        net = net.quantize(CENT, ROUND_HALF_UP)
        amt = (net * R81B_RATES[tax] / 100).quantize(CENT, ROUND_HALF_UP)
        out.append({"net": str(net), "tax": tax, "amount": str(amt)})
        gross += net + amt
    return out, gross


def r81b_lines(r):
    try:
        v = json.loads(r["tax_lines"]) if r["tax_lines"] else None
    except (ValueError, TypeError):
        v = None
    return v if isinstance(v, list) else None


def r81b_ver(r):
    """2.570.0 (#4770): the version of an entry: its last correction (fragment 4770_a), never corrected = its created_at."""
    return str((r["updated_at"] if "updated_at" in r.keys() else "") or r["created_at"] or "")


def r81b_public(d, r):
    """The tax lines + net / tax sums into the public dict of an entry (_archive_public); None = only the gross known.
    2.570.0 (#4770): + updated_at, the version a correction / its undo sends back as expect_updated_at."""
    d["updated_at"] = r81b_ver(r)
    lines = r81b_lines(r) if "tax_lines" in r.keys() else None
    if lines:  # review: the gross changed without them (an older version) -> they no longer fit, tax unknown again
        try:
            if sum(Decimal(x["net"]) + Decimal(x["amount"]) for x in lines) != Decimal(str(r["amount"])):
                lines = None
        except Exception:  # noqa: BLE001 -- no readable gross
            lines = None
    d["tax_lines"] = lines
    d["net"] = float(sum(Decimal(x["net"]) for x in lines)) if lines else None
    d["tax"] = float(sum(Decimal(x["amount"]) for x in lines)) if lines else None
    return d


def _client(c, oid, cid):
    if not cid:
        return None
    r = c.execute(f"SELECT name FROM clients WHERE id=? AND {pb_cl_sql(c, oid)}", (cid,)).fetchone()
    return {"id": cid, "name": r["name"] if r else ""}


def _amount_val(gross, lines):
    return {"gross": float(gross) if gross is not None else None, "lines": lines}


def r81b_archive_patch(c, oid, uid, aid, b):
    """Apply {client_id?, tax_lines? | amount?, paid?} to entry aid of office area oid; one history row per changed field.
    Returns the names of the changed fields. tax_lines win over amount; amount alone = gross only (tax unknown).
    #1968: amount / tax_lines / paid only an office admin (403), a negative amount 400.
    2.570.0 (#4770): expect_updated_at set and the entry corrected since -> 409 with the entry under "current"; missing -> as
    before. A change stamps updated_at."""
    write_lock(c, f"office_archive-{int(aid)}")
    r = c.execute(f"SELECT * FROM office_archive WHERE id=? AND org_id=? AND {live_sql()}", (aid, oid)).fetchone()  # 2.1315.0 (#6590 c): not the trash
    if not r:
        raise Denied(404)
    ccf_check(b, r81b_ver(r), "current", lambda: _archive_public(r))
    if "copy_of" in r.keys() and r["copy_of"]:  # 2.97.0 C (#2049): a copy taken along by a move is view / PDF only
        from .officemove import OFM_RO
        raise Denied(409, tr(OFM_RO))
    role = office_role(c, uid, oid)
    if any(k in b for k in R81B_ADMIN_FIELDS) and not ofr_admin_or(c, uid, oid, "settings", "manage"):  # 2.187.0 B (#2476): groups by level
        raise Denied(403, tr(OFFICE_ADMIN_ONLY))
    keep = ("client_id", "amount") + (("paid",) if r["kind"] == "invoice" else ())  # paid: invoices only (an offer ignores it)
    f = _archive_fields(c, oid, {k: v for k, v in b.items() if k in keep}, partial=True)
    if b.get("tax_lines") not in (None, []):
        lines, gross = r81b_tax_lines(b["tax_lines"])
        f["amount"], f["tax_lines"] = str(gross), json.dumps(lines)
    elif "amount" in f:
        if f["amount"] is not None and Decimal(f["amount"]) < 0:
            raise BadInput(tr("Invalid value: {0}", "amount"))
        f["tax_lines"] = None
    log, ts = [], iso(now_utc())
    if "client_id" in f and (f["client_id"] or None) != (r["client_id"] or None):
        log.append(("client", _client(c, oid, r["client_id"]), _client(c, oid, f["client_id"])))
    if "amount" in f:
        old_g = Decimal(str(r["amount"])) if r["amount"] is not None else None
        new_g = Decimal(f["amount"]) if f["amount"] is not None else None
        old_l, new_l = r81b_lines(r), (json.loads(f["tax_lines"]) if f["tax_lines"] else None)
        if old_g != new_g or old_l != new_l:
            log.append(("amount", _amount_val(old_g, old_l), _amount_val(new_g, new_l)))
    if "paid" in f and int(f["paid"]) != int(r["paid"] or 0):
        log.append(("paid", int(r["paid"] or 0), int(f["paid"])))
    if not log:
        return []
    f["updated_at"] = iso_ms(now_utc())  # 2.570.0 (#4770): the new version
    c.execute(f"UPDATE office_archive SET {', '.join(k + '=?' for k in f)} WHERE id=? AND org_id=?", [*f.values(), aid, oid])
    for field, old, new in log:
        c.execute("INSERT INTO office_archive_log(org_id, archive_id, at, user_id, field, old, new, role) VALUES(?,?,?,?,?,?,?,?)",
                  (oid, aid, ts, uid, field, json.dumps(old, ensure_ascii=False), json.dumps(new, ensure_ascii=False),
                   "" if role == "admin" else "member"))
    return [x[0] for x in log]


def r81b_history(c, oid, aid):
    users, out = {}, []
    for r in c.execute("SELECT * FROM office_archive_log WHERE org_id=? AND archive_id=? ORDER BY id DESC LIMIT 200", (oid, aid)):
        if r["user_id"] and r["user_id"] not in users:
            u = c.execute("SELECT display_name, username FROM users WHERE id=?", (r["user_id"],)).fetchone()
            users[r["user_id"]] = (u["display_name"] or u["username"]) if u else ""
        try:
            old, new = json.loads(r["old"] or "null"), json.loads(r["new"] or "null")
        except ValueError:
            old = new = None
        out.append({"id": r["id"], "at": r["at"], "user_name": users.get(r["user_id"], ""), "field": r["field"], "old": old, "new": new,
                    "by_member": r["role"] == "member"})
    return out


@app.get("/api/office/legacy/archive/<int:aid>")
def r81b_archive_get(aid):
    """Members: one archived document with its history (newest first) -- the edit dialog."""
    from .legacyimport import _archive_public, _ctx
    c, uid, oid = _ctx(admin=False)
    r = c.execute(f"SELECT * FROM office_archive WHERE id=? AND org_id=? AND {live_sql()}", (aid, oid)).fetchone()  # 2.1315.0 (#6590 c)
    if not r:
        raise Denied(404)
    cl = _client(c, oid, r["client_id"])
    d = _archive_public(r, {r["client_id"]: cl["name"]} if cl else {})
    d["history"] = r81b_history(c, oid, aid)
    d["admin"] = office_role(c, uid, oid) == "admin"  # #1968: only an admin edits amount / tax lines / paid
    return jsonify(d)


# ---------------------------------------------------------------- 2.1315.0 (#6590 c): one old document into the trash
# A single imported PDF (the run's undo only goes within 24 h and while untouched) goes into the core's trash (kind
# oarchive, office/okern.py ofk_register): an office admin, while it is bound nowhere -- its month is not locked (the
# period lock is what the books know as written down; old documents count in no other evaluation) and it is no read-only
# copy of a move. Its number is freed while it lies there (trash_number), so a corrected PDF can carry it; the restore
# (its own route or the office trash) puts it back and refuses (409) while the number or the same file is live again.
# An old invoice stays in the trash while the law keeps it (books: ret_keep_years("book") from the end of its year);
# the retention run deletes it and its stored PDF after that.
OAR_KIND = "oarchive"
OAR_TRASH = "archive"  # the app's name of it in the office trash
OAR_NUMBER_BACK = N_("The number {0} is used again meanwhile: the old document cannot come back")
OAR_FILE_BACK = N_("This PDF is in the archive again meanwhile")
OAR_KEPT = N_("An old invoice is kept by law until {0}")


def oar_keep_sql(a):
    """obj_register trash_keep: an old invoice of a year still kept (the year from its date, else from its import)."""
    y = local_now().year - ret_keep_years("book")
    return (f"({a}.kind = 'invoice' AND substr(COALESCE(NULLIF({a}.date, ''), CAST({a}.created_at AS text)), 1, 4) >= ?)", (f"{y:04d}",))


def oar_kept_until(r):
    """The first day an old invoice may go for good ('' = not kept)."""
    if r["kind"] != "invoice":
        return ""
    d = (r["date"] or "") or str(r["created_at"] or "")
    y = int(d[:4]) if re.match(r"^\d{4}", d) else local_now().year
    k = f"{y + ret_keep_years('book') + 1}-01-01"
    return k if local_now().date().isoformat() < k else ""


def _oar_label(c, oid, row):
    return " · ".join(x for x in (row.get("trash_number") or row.get("number") or "", row.get("client_name") or "", row.get("date") or "",
                                  row.get("file_name") or "") if x)


def oar_back(c, oid, row):
    """ofk_register limit: after a restore the number comes back -- 409 (rolled back) while it or the same PDF is live."""
    r = c.execute("SELECT * FROM office_archive WHERE id=? AND org_id=?", (row["id"], oid)).fetchone()
    if r is None:
        return
    if r["sha256"] and c.execute(f"SELECT 1 FROM office_archive WHERE org_id=? AND sha256=? AND id<>? AND {live_sql()}",
                                 (oid, r["sha256"], r["id"])).fetchone():
        raise Denied(409, tr(OAR_FILE_BACK))
    num = r["trash_number"] or ""
    if num:
        write_lock(c, f"office_num_{int(oid)}")  # the same lock as an upload / a new document's number
        if _number_used(c, oid, num, r["id"]):
            raise Denied(409, tr(OAR_NUMBER_BACK, num))
        c.execute("UPDATE office_archive SET number=?, trash_number='' WHERE id=? AND org_id=?", (num, r["id"], oid))


def oar_purge(c, aid):
    """obj_on_purge: kept by law = Denied (the retention run counts it, the office trash's delete refuses); else the stored
    PDF goes after the commit (the row, its history and log go with the core / the cascade)."""
    with system_ctx(c):
        r = c.execute("SELECT * FROM office_archive WHERE id=?", (int(aid),)).fetchone()
    if r is None:
        return None
    k = oar_kept_until(r)
    if k:
        raise Denied(409, tr(OAR_KEPT, k))
    p = fi_archive_path(r["org_id"], r["file"])

    def rm():  # after the commit (core/serializers.py unlink_files): OFFICE_DIR is not below ATT_DIR
        try:
            os.remove(p)
        except FileNotFoundError:
            pass
    return [rm] if p else None


def oar_bound(c, oid, r):
    """409 while the old document is bound: a read-only copy of a move, or its month is locked (office/periodlock.py)."""
    if "copy_of" in r.keys() and r["copy_of"]:
        from .officemove import OFM_RO
        raise Denied(409, tr(OFM_RO))
    period_need_open(c, oid, r["date"] or None)


def _oar_ctx():
    return office_ctx_admin()


ofk_register(OAR_KIND, "office_archive", N_("Old document (PDF)"), "settings", need="manage",
             view={"kind": OAR_TRASH, "label": _oar_label, "ctx": _oar_ctx}, step=False, trash_keep=oar_keep_sql, limit=oar_back)
obj_on_purge(OAR_KIND, oar_purge)


@app.delete("/api/office/legacy/archive/<int:aid>")
def oar_trash_route(aid):
    """Office admin: one old document into the trash (see above) -> {ok, id}; 409 while bound, 404 unknown / in the trash."""
    c, uid, oid = _oar_ctx()
    write_lock(c, f"office_archive-{int(aid)}")
    r = c.execute(f"SELECT * FROM office_archive WHERE id=? AND org_id=? AND {live_sql()}", (aid, oid)).fetchone()
    if not r:
        raise Denied(404)
    oar_bound(c, oid, r)
    c.execute("UPDATE office_archive SET trash_number=number, number='' WHERE id=? AND org_id=?", (aid, oid))
    ofk_trash(c, uid, OAR_KIND, aid)
    if r["run_id"]:
        _run_count(c, oid, r["run_id"])
    ofx_log(c, oid, "delete", target="archive", detail={"archive_id": aid, "number": r["number"] or ""})
    bump(c)
    c.commit()
    return jsonify(ok=True, id=aid)


@app.post("/api/office/legacy/archive/<int:aid>/restore")
def oar_restore_route(aid):
    """Office admin: the old document back out of the trash (the toast's undo) -> the entry; 409 number / file live again."""
    c, uid, oid = _oar_ctx()
    write_lock(c, f"office_archive-{int(aid)}")
    r = c.execute("SELECT * FROM office_archive WHERE id=? AND org_id=?", (aid, oid)).fetchone()
    if not r:
        raise Denied(404)
    if r["deleted_at"]:
        ofk_restore(c, uid, OAR_KIND, aid)
        if r["run_id"]:
            _run_count(c, oid, r["run_id"])
        ofx_log(c, oid, "restore", target="archive", detail={"archive_id": aid})
    bump(c)
    c.commit()
    return jsonify(_archive_public(c.execute("SELECT * FROM office_archive WHERE id=? AND org_id=?", (aid, oid)).fetchone()))
