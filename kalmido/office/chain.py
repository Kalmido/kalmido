"""2.531.0 (#4497): the hash chain over finalised documents.

Every finalised invoice, credit note, reminder and delivery note joins the chain of its office (organisation or personal
office) and number series (chain_key = the counter it counts with, models.num_kind: credit notes on the invoices' counter share
that chain) when it is finalised:

    chain_hash = sha256(chain_prev + canonical data of the document)      chain_prev = chain_hash of the one before ('' = first)
    chain_seq  = its place in that chain (1, 2, ...)

Quotations and trial documents stay outside: a quotation may be taken back to a draft (ledger.ofx_unlock_post) and a trial
document deleted at any time (docs.trial_drop_doc) -- both would break the chain in everyday use.

The canonical data (hch_canon) is deterministic JSON (sorted keys, fixed separators, numbers as plain text) of the fields that
never change after finalising (HCH_DOC_FIELDS, HCH_ITEM_FIELDS, HCH_TAX_KEYS): number, kind, date, service period, currency,
locked_at, the recipient snapshot, the sender snapshot (decrypted: switching the encryption on or a new key changes nothing),
the positions, the totals (without the internal purchase prices / margin) and the frozen rates. Fields that change after
finalising on purpose stay out: status, paid / paid_at, due date, reminder level / fee state, sent_at, DATEV mark, the stored
files' checksums, notes, project / list links, cash flow, terms.

2.1309.0 (#6467): the canonical data has a version, kept per link in office_docs.chain_ver (NULL = 1). Version 1 = the fields
above. Version 2 (HCH_VER, every link made since) adds what an audit (#4791) found missing: the stored PDF's and XML's
checksums (pdf_sha256 / xml_sha256: ledger.ofx_finalize stores the files in inv_after_finalize BEFORE hch_append, and the
database lets them change only while empty) and the head fields vat_mode, vat_note, fx_rate, cancels_id, inv_type, abs_refs,
due_date, skonto_pct / skonto_days, intro / closing and order_ref (all held by the trigger of core/migrations.d/4598.py once
finalised). A document whose PDF checksum is still empty when it is linked (no stored file: an import, a version without the
file writer) is linked with version 1 -- the catch-up of office/storefill.py fills the checksums later and would break a
version-2 link. Old links keep their version and stay valid; hch_check reads each with its own.

hch_check recomputes every chain of an office: {ok, count, pending, first_bad: {id, number, chain, seq, reason} | None, unreadable}
(reason gap / link / unlocked / data, or unreadable: the office's key cannot open a value now -- no proof of a change; 2.1319.0,
#6770: the check goes on behind an unreadable link, first_bad prefers a real break, unreadable names the first unreadable one). A document that was
changed, removed from the middle, moved to another chain or unlocked in the database is the first bad one of its chain;
pending = finalised documents not chained yet (an import of a whole office, a start before the next one chains them).
Removing the newest document of a chain leaves no trace in the chain itself (the office log keeps its finalise entry)."""
import hashlib
import json
import time
from datetime import date, timedelta
from decimal import Decimal

from ..core.config import app
from ..core.db import gset, gsetting, iso, local_now, now_utc  # 2.1309.0 (#6467): the daily check; 2.1319.0 (#6770): local_now
from ..core.moneycol import mc_fields  # 2.755.0 (#5293)
from ..core.orgcrypt import OrgCryptError, oc_dec_fields, oc_log_detail
from ..core.i18n import N_  # 2.1309.0 (#6467)
from ..notify.alerts import aa_now  # 2.1309.0 (#6467)
from ..core.pg import system_ctx, write_lock
from ..core.access import live_sql  # 2.1005.0 (#5415)
from .model import num_kind, office_settings, ofx_release  # 2.542.0 (#4598): freeing a copied place passes the trigger

HCH_DOC_FIELDS = ("number", "kind", "date", "service_from", "service_to", "currency", "locked_at")
HCH_JSON_FIELDS = {"recipient_snapshot": "recipient", "sender": "sender", "totals": "totals"}
HCH_TOTALS_SKIP = ("costs", "margin")  # internal (purchase side), encrypted on their own, never printed
HCH_TAX_KEYS = ("rates", "tax")  # of tax_snapshot
HCH_ITEM_FIELDS = ("kind", "title", "detail", "qty", "unit", "rate", "tax", "tax_pct", "net", "tax_amount")
HCH_VER = 2  # 2.1309.0 (#6467): the version new links are made with (see above)
HCH_V2_FIELDS = ("pdf_sha256", "xml_sha256", "vat_mode", "vat_note", "fx_rate", "cancels_id", "inv_type", "due_date", "skonto_pct",
                 "skonto_days", "intro", "closing", "order_ref")
HCH_V2_JSON = ("abs_refs",)


def hch_chained(r):
    """Does document row r join a chain when it is finalised? (not a quotation, not a trial document)"""
    return r["kind"] != "offer" and not (r["trial"] if "trial" in r.keys() else 0)


def _plain(v):
    if isinstance(v, Decimal):
        return format(v.normalize(), "f")
    if isinstance(v, dict):
        return {str(k): _plain(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [_plain(x) for x in v]
    return v


def _json(v, dflt):
    if isinstance(v, (dict, list)):
        return v
    try:
        x = json.loads(v or "")
    except (TypeError, ValueError):
        return dflt
    return x


def hch_ver(r):
    """The canonical version of document row r's link (2.1309.0, #6467: NULL / no column = 1)."""
    v = r["chain_ver"] if "chain_ver" in r.keys() else None
    return int(v or 1)


def _v2(v):
    """A head field of version 2 as one value whatever its column type becomes (an empty text = NULL, a date = its ISO day)."""
    if v is None or v == "":
        return None
    if hasattr(v, "isoformat"):
        return v.isoformat()
    return v


def hch_canon(c, oid, r, ver=None):
    """The canonical text of document row r (a raw or decrypted office_docs row) of office oid in version ver (None = the
    version of r's link, hch_ver)."""
    ver = hch_ver(r) if ver is None else int(ver)
    d = oc_dec_fields(c, oid, "office_docs", r)
    out = {k: d.get(k) for k in HCH_DOC_FIELDS}
    if ver >= 2:  # 2.1309.0 (#6467)
        out["v"] = 2
        for k in HCH_V2_FIELDS:
            out[k] = _v2(d.get(k))
        for k in HCH_V2_JSON:
            out[k] = _json(d.get(k), [])
    for col, key in HCH_JSON_FIELDS.items():
        out[key] = _json(d.get(col), {})
    if isinstance(out["totals"], dict):
        out["totals"] = {k: v for k, v in out["totals"].items() if k not in HCH_TOTALS_SKIP}
    tax = _json(d.get("tax_snapshot"), {})
    out["tax"] = {k: tax.get(k) for k in HCH_TAX_KEYS} if isinstance(tax, dict) else {}
    # 2.755.0 (#5293): net / tax_amount are NUMERIC now: the same text as before ("23.80", None), the checksums stay
    out["items"] = [mc_fields("office_doc_items", {k: it[k] for k in HCH_ITEM_FIELDS}) for it in c.execute(
        f"SELECT {', '.join(HCH_ITEM_FIELDS)} FROM office_doc_items WHERE doc_id=? AND {live_sql()} ORDER BY sort, id", (d["id"],))]  # 2.1005.0 (#5415): not the trash (a trashed part's positions may be purged later)
    return json.dumps(_plain(out), sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def hch_hash(prev, canon):
    return hashlib.sha256((prev + canon).encode("utf-8")).hexdigest()


def _tail(c, oid, key):
    t = c.execute("SELECT chain_seq, chain_hash FROM office_docs WHERE org_id=? AND chain_key=? AND chain_seq IS NOT NULL "
                  "ORDER BY chain_seq DESC LIMIT 1", (oid, key)).fetchone()
    return (int(t["chain_seq"]), t["chain_hash"] or "") if t else (0, "")


def hch_link_ver(r):
    """2.1309.0 (#6467): the version a new link of document row r gets: HCH_VER once its stored PDF's checksum is noted, else 1."""
    return HCH_VER if (r["pdf_sha256"] if "pdf_sha256" in r.keys() else "") else 1


def _link(c, oid, r, key):
    seq, prev = _tail(c, oid, key)
    ver = hch_link_ver(r)
    h = hch_hash(prev, hch_canon(c, oid, r, ver))
    c.execute("UPDATE office_docs SET chain_key=?, chain_seq=?, chain_prev=?, chain_hash=?, chain_ver=? WHERE id=? AND org_id=?",
              (key, seq + 1, prev, h, ver, r["id"], oid))
    return h


def hch_pending(c, oid):
    """Finalised documents of office oid that belong in a chain and have no place yet, oldest first."""
    return [r for r in c.execute("SELECT * FROM office_docs WHERE org_id=? AND locked_at IS NOT NULL AND chain_seq IS NULL AND kind<>'offer' "
                                 f"AND COALESCE(trial, 0)=0 AND {live_sql()} ORDER BY locked_at, id", (oid,))]  # 2.1005.0 (#5415): not the trash


def hch_append(c, oid, did=None, s=None):
    """Chains the finalised documents of office oid that have no place yet (older ones first: an import, documents from
    before 2.531), then document did (just finalised). Under the office's chain lock; the caller commits."""
    write_lock(c, f"office_chain_{int(oid)}")
    s = s if s is not None else office_settings(c, oid)
    for r in hch_pending(c, oid):
        _link(c, oid, r, num_kind(s, r["kind"]))
    if did is not None:
        r = c.execute(f"SELECT * FROM office_docs WHERE id=? AND org_id=? AND {live_sql()}", (did, oid)).fetchone()  # 2.1005.0 (#5415): not the trash
        if r is not None and r["chain_seq"] is None and r["locked_at"] and hch_chained(r):
            _link(c, oid, r, num_kind(s, r["kind"]))


def hch_check(c, oid):
    """Recomputes every chain of office oid -> {ok, count, pending, first_bad, unreadable}. first_bad = the first document (of the
    first broken chain, by its first finalising) whose link or data does not fit. 2.1319.0 (#6770): a link whose value the
    office's key cannot open now (reason "unreadable") no longer ends its chain's check: the check goes on behind it with the
    stored hash (the next link must still start from it), so a real break further on is still found and named first_bad before
    any unreadable one; unreadable = the first unreadable document {id, number, chain, seq} | None (then ok is False too)."""
    bad, unread, count = [], [], 0
    keys = [x[0] for x in c.execute("SELECT DISTINCT chain_key FROM office_docs WHERE org_id=? AND chain_seq IS NOT NULL ORDER BY chain_key", (oid,))]
    for key in keys:
        prev, want = "", 1
        for r in c.execute("SELECT * FROM office_docs WHERE org_id=? AND chain_key=? AND chain_seq IS NOT NULL ORDER BY chain_seq, id", (oid, key)).fetchall():
            count += 1
            # review job/2606: why it breaks - gap (a document before it is gone), link, unlocked or data
            why = "gap" if int(r["chain_seq"]) != want else "link" if (r["chain_prev"] or "") != prev else "unlocked" if not r["locked_at"] else ""
            if not why:
                try:
                    why = "" if hch_hash(prev, hch_canon(c, oid, r)) == (r["chain_hash"] or "") else "data"
                except OrgCryptError:  # 2.1309.0 (#6467): a value the key cannot open now is a break as well, named apart (no alarm)
                    why = "unreadable"
                except Exception:  # noqa: BLE001 -- a value that cannot be read is a break as well
                    why = "data"
            item = {"id": r["id"], "number": r["number"] or "", "chain": key, "seq": int(r["chain_seq"]), "reason": why}
            if why == "unreadable":  # 2.1319.0 (#6770): noted, and the check goes on behind it (see above)
                unread.append(item)
            elif why:
                bad.append(item)
                break
            prev, want = r["chain_hash"] or "", want + 1
    first = min(bad, key=lambda b: b["id"]) if bad else min(unread, key=lambda b: b["id"]) if unread else None
    first_unread = min(unread, key=lambda b: b["id"]) if unread else None
    return {"ok": not bad and not unread, "count": count, "pending": len(hch_pending(c, oid)), "first_bad": first,
            "unreadable": first_unread}


def hch_heads(c, oid):
    """2.1309.0 (#6467): the head (newest link) of every chain of office oid, by chain key -> [{chain, seq, id, number, date, hash, ver}]
    (the prüfer export names them; a later link would have to start from that hash)."""
    return [{"chain": r["chain_key"], "seq": int(r["chain_seq"]), "id": r["id"], "number": r["number"] or "", "date": r["date"], "hash": r["chain_hash"] or "",
             "ver": hch_ver(r)} for r in c.execute(
        "SELECT DISTINCT ON (chain_key) * FROM office_docs WHERE org_id=? AND chain_seq IS NOT NULL ORDER BY chain_key, chain_seq DESC, id DESC",
        (oid,)).fetchall()]


def hch_migrate(c):
    """Every start (core/db.py init_db through ledger.ofx_migrate): offices with finalised documents not chained yet (documents
    from before 2.531, an imported office) get them chained in the order they were finalised. Idempotent (only rows without a
    place); an office whose data cannot be read now (decryption) is left for the next start / its next finalising."""
    # review job/2606: a place copied by an older version (rollback: duplicate / recurring invoice took the chain columns along)
    # is no place - a draft, or the later of two rows on one place, gets chained anew when it is finalised / at this start
    with ofx_release(c):
        c.execute("UPDATE office_docs SET chain_key='', chain_seq=NULL, chain_prev='', chain_hash='', chain_ver=NULL WHERE chain_seq IS NOT NULL AND "
                  "(locked_at IS NULL OR EXISTS (SELECT 1 FROM office_docs o WHERE o.org_id=office_docs.org_id AND o.chain_key=office_docs.chain_key "
                  "AND o.chain_seq=office_docs.chain_seq AND o.chain_hash=office_docs.chain_hash AND o.id<office_docs.id))")
    for (oid,) in c.execute("SELECT DISTINCT org_id FROM office_docs WHERE locked_at IS NOT NULL AND chain_seq IS NULL AND kind<>'offer' "
                            f"AND COALESCE(trial, 0)=0 AND {live_sql()}").fetchall():  # 2.1005.0 (#5415): not the trash
        try:
            with c.savepoint():
                hch_append(c, oid)
        except Exception:  # noqa: BLE001 -- never stop the start for this
            continue


# ---------------------------------------------------------------- the daily check (2.1309.0, #6467)
HCH_WATCH = {"at": 0.0}
HCH_WATCH_EVERY = 86400  # s: once after the start, then daily (watchdog)
# Both marks below live in the global settings of the SAME database as the chains (docs/dev/hashkette.md): they keep a mistake
# (a script, a restore, a broken migration) from going unnoticed, not someone with write access to the database -- whoever can
# change a document there can set the mark as well, and the alert never comes.
HCH_WATCH_KEY = "office_chain_watch"  # global settings: {office id: "chain:seq:id:reason"} of the breaks already reported
HCH_UNREAD_KEY = "office_chain_unreadable"  # 2.1319.0 (#6770): {office id: {id, since, last, told}} of offices with an unreadable link
HCH_UNREAD_DAYS = 3  # 2.1319.0 (#6770): days in a row an unreadable link is found before its one admin alert


def _load(c, key):
    try:
        v = json.loads(gsetting(c, key) or "{}")
    except ValueError:
        v = {}
    return v if isinstance(v, dict) else {}


def _unread_day(seen, k, ur, today):
    """2.1319.0 (#6770): notes today's unreadable link ur of office k in seen (HCH_UNREAD_KEY) -> True when it is due for its one
    alert now: found on HCH_UNREAD_DAYS days in a row (a day without a check, or with the office readable, starts anew)."""
    e = seen.get(k) if isinstance(seen.get(k), dict) else {}
    last = e.get("last") or ""
    yesterday = (today - timedelta(days=1)).isoformat()
    if last not in (today.isoformat(), yesterday):
        e = {"since": today.isoformat(), "told": False}
    e.update({"id": ur["id"], "last": today.isoformat()})
    seen[k] = e
    try:
        days = (today - date.fromisoformat(e["since"])).days + 1
    except (TypeError, ValueError):
        e["since"], days = today.isoformat(), 1
    if days >= HCH_UNREAD_DAYS and not e.get("told"):
        e["told"] = True
        return True
    return False


def hch_watch_tick(c, force=False):
    """2.1309.0 (#6467): daily in the watchdog (notify/push.py): hch_check for every office with a chain. A break found the first
    time -> one admin alert (kind "security", switchable in the admin alert settings) and one line "chain_broken" in that
    office's log on the first bad document; the same break the next days says nothing again (HCH_WATCH_KEY), a chain intact
    again forgets it. A value the key cannot open now (reason "unreadable") is no proof of a change: server log only --
    2.1319.0 (#6770): found on HCH_UNREAD_DAYS days in a row it gets one admin alert of its own (HCH_UNREAD_KEY), and the
    check goes on behind it (hch_check), so it no longer hides a later break. Each office runs in its own savepoint: one that
    fails rolls back only its own statements, never the log lines of the offices before it.
    Returns the number of new breaks."""
    if not force and time.time() - HCH_WATCH["at"] < HCH_WATCH_EVERY:
        return 0
    HCH_WATCH["at"] = time.time()
    seen, unread = _load(c, HCH_WATCH_KEY), _load(c, HCH_UNREAD_KEY)
    today = local_now().date()
    new = 0
    with system_ctx(c):  # every office's chain (row-level security); reads only, its own line per new break
        oids = [r[0] for r in c.execute("SELECT DISTINCT org_id FROM office_docs WHERE chain_seq IS NOT NULL ORDER BY org_id").fetchall()]
        for oid in oids:
            k = str(oid)
            try:
                with c.savepoint():  # 2.1319.0 (#6770): was c.rollback(), which dropped the lines of the offices before
                    res = hch_check(c, oid)
                    fb, ur = res["first_bad"], res.get("unreadable")
                    if ur is None:
                        unread.pop(k, None)
                    else:
                        app.logger.warning("office chain check: office %s, document %s cannot be read now", oid, ur["id"])
                        if _unread_day(unread, k, ur, today):
                            aa_now("security", f"office_chain_unreadable:{oid}",
                                   N_("Office hash chain cannot be checked: office {0}, document id {1} (series {2}, place {3}) cannot be read with the office's key for {4} days. The check goes on behind it."),
                                   (oid, ur["id"], ur["chain"], ur["seq"], HCH_UNREAD_DAYS))
                    if fb is None or fb["reason"] == "unreadable":
                        if fb is None:
                            seen.pop(k, None)
                        continue
                    mark = f"{fb['chain']}:{fb['seq']}:{fb['id']}:{fb['reason']}"
                    if seen.get(k) == mark:
                        continue
                    det = {"chain": fb["chain"], "seq": fb["seq"], "reason": fb["reason"], "number": fb["number"], "count": res["count"]}
                    c.execute("INSERT INTO office_doc_log(org_id, doc_id, user_id, at, action, target, detail, user_name) VALUES(?,?,NULL,?,?,'doc',?,'')",
                              (oid, fb["id"], iso(now_utc()), "chain_broken", oc_log_detail(c, oid, json.dumps(det, ensure_ascii=False))))  # ledger.ofx_log without a person
                    seen[k] = mark
                    aa_now("security", f"office_chain:{oid}", N_("Office hash chain broken: office {0}, document id {1} (series {2}, place {3}, {4}). The office log names it."),
                           (oid, fb["id"], fb["chain"], fb["seq"], fb["reason"]))
                    new += 1
            except Exception as e:  # noqa: BLE001 -- one office never stops the others
                app.logger.warning("office chain check: office %s failed: %s", oid, type(e).__name__)
                continue
        gset(c, HCH_WATCH_KEY, json.dumps(seen, sort_keys=True))
        gset(c, HCH_UNREAD_KEY, json.dumps(unread, sort_keys=True))
    c.commit()
    return new
