"""2.146.0 D (#2468): the retention export before an account or an organisation is deleted.

Kalmido does not keep other people's records for ten years (the hosted instance, decision of 20.10.2026; the duty to keep them lies
with the person): before an account or an organisation goes, its records that the law asks to keep can be downloaded as one
readable ZIP -- invoices and other finalised documents (the stored PDF and e-invoice XML, else rendered from the snapshot),
receipts with their files, project receipts of lists, the cash books (PDF + CSV), the bank statements, the office log
(GoBD), the archive and every other file of the office folder, each table also as CSV, with a table of contents
(00-index.txt) and a manifest (SHA-256 per file).

Subjects: "user:<id>" = a person's own records (the personal office, the documents of the own space, the receipts of the
lists the person owns) -- only the person themself downloads them; "org:<id>" = an organisation's office, the receipts of its
documents space and of its lists -- only its admins. Nobody else (an instance admin neither: the organisation boundary).

The ZIP is streamed (built while it is sent, nothing on the disk); only a download that ran to its end is noted in
retention_log. Deleting the account (DELETE /api/users/<id>) or the organisation (DELETE /api/admin/orgs/<id>) while it has
such records needs ?retention=exported (a finished export of the subject within RX_VALID_DAYS) or ?retention=waived (the
deleting admin says so; noted too); both land in the security log (useradmin.ua8_audit style, notify.alerts).

#6474 (audit #4791, A4 to A7): an export counts only when it was complete (no file missing or locked: rx_export_check
names them) and nothing to keep came after it (rx_counts since); on the hosted instance only the person themself / an admin
of the organisation does without the export (declared before: POST /api/retention/.../waiver, or their own deletion), an
instance admin deletes after an export only; received e-invoices that are no receipt count and go into the ZIP
(received-einvoices/)."""
import csv
import hashlib
import io
import json
import os
import time
import zipfile
from datetime import timedelta

from flask import Response, g, jsonify, request, stream_with_context

from .exportleft import RX_LEFT_TABLES, left_lines  # 2.362.4 (#3107)
from .orgexport import _ox_locked  # 2.370.0 (#2781)
from ..core.access import Denied, live_sql
from ..core.config import app, APP_VERSION, ATT_DIR, OFFICE_DIR
from ..core.db import connect, db, iso, now_utc
from ..core.i18n import N_, lang, tr
from ..core.pg import system_ctx, insert_id
from ..accounts.session import me
from ..accounts.orgretain import odl_admin_export, odl_retention, odl_retired, upg_personal_state  # 2.186.0 A (#2599)
from .hosting import hosted  # 2.186.0 A: pulled up from rx_info
from ..core.orgcrypt import oc_read_file  # 2.149.0 G (#2517): pulled up from functions
from .offsite import stepup_download  # 2.223.2 C (#2871): the step-up before a download
from ..files.store import fs_read  # 2.184.0 A (#2628)
from ..life.budget import bud_dec  # 2.168.1: pulled up from _project_bookings
from ..lists.listtrash import otr_held, otr_need  # 2.168.1: the project download route lives here (no upward import)
from ..office.ledger import ofx_log  # 2.296.0 F (#3177)
from ..accounts.orgs import org_role  # 2.369.5 (#2517): pulled up from functions
from ..notify.alerts import aa_now  # 2.369.5 (#2517): pulled up from functions
from ..office.books import bk_csv_cell  # 2.369.5 (#2517): pulled up from functions
from .orgexport import OX_AREAS, OX_FMT, OX_PB_CLIENTS, _rows, ox_live, _safe_part, _under  # 2.369.5 (#2517): pulled up from functions
from ..core.objexport import oex_rx  # 2.1093.0 (#5289): the export register of the core
from ..core.movelock import mv_allow  # 2.1337.0 (#6600): the writes a move allows
from ..office.pdfweb import _render, _stored, epdf_name  # 2.369.5 (#2517): pulled up from functions
from ..office.pdfweb import epdf_ubl_sent  # 2.1321.0 (#6480)
from ..office.cashbook import cb_csv_text, cb_export_data, cb_pdf_bytes  # 2.369.5 (#2517): pulled up from functions

RX_VALID_DAYS = 7  # a finished export counts this long as "exported" for the deletion
RX_NAMES_MAX = 50  # #6474: so many names of unreadable / locked files the export's log row keeps (until the deletion: _rx_scrub)
RX_YEARS = {"documents": 8, "books": 10, "letters": 6}  # what the hint says (invoices / receipts 8, sent letters 6 (2.184.0 #2628), books 10 years)
RX_NOTE = N_("Keep these records yourself: invoices and receipts for 8 years, sent business letters for 6 years, books (cash book, logs, bank statements) for 10 years. Kalmido does not keep them after the deletion; the duty to keep them lies with you.")
RX_NEEDED = N_("This account or organisation has records you must keep (invoices, receipts, cash book, sent letters). Download the retention export first and confirm it, or say explicitly that you do without it.")
# (archive name, table) of the tables that go along as CSV; the where clause is the organisation export's (orgexport.OX_AREAS)
RX_TABLES = (
    ("invoices/documents.csv", "office_docs"),
    ("invoices/positions.csv", "office_doc_items"),
    ("invoices/payments.csv", "office_payments"),
    ("invoices/clients.csv", "clients"),
    ("invoices/company.csv", "office_company"),
    ("invoices/bank-accounts.csv", "office_bank_accounts"),  # 2.470.0 (#3596)
    # 2.362.2 (#3105): every other record of the office the books and the tax office ask for; exportleft.RX_LEFT_TABLES names the rest with its reason
    ("invoices/client-contacts.csv", "office_client_contacts"),
    ("invoices/document-parts.csv", "office_doc_parts"),
    ("invoices/dunning.csv", "office_dunning_marks"),
    ("invoices/purchases.csv", "office_purchases"),
    ("invoices/suppliers.csv", "office_suppliers"),
    ("invoices/peppol-sends.csv", "office_peppol_sends"),
    ("invoices/signoffs.csv", "office_signoffs"),
    ("invoices/generated-documents.csv", "office_gen_docs"),
    ("invoices/privacy-sheets.csv", "office_privacy_sheets"),
    ("contracts/contracts.csv", "office_contracts"),
    ("contracts/contract-files.csv", "office_contract_files"),
    ("contracts/agreements.csv", "office_agreements"),
    ("books/number-ranges.csv", "office_numbers"),
    ("books/extra-number-ranges.csv", "office_num_ranges"),  # 2.1365.0 (#6698): the additional ranges (code, scheme, suffix) the counters r<id> belong to
    ("books/opening-balances.csv", "office_opening_balances"),
    ("books/period-locks.csv", "office_period_locks"),
    ("books/ledger-entries.csv", "office_ledger_entries"),  # 2.666.0 (#3461): adjusting / opening entries of the balance sheet
    ("books/equipment.csv", "office_equipment"),
    ("archive/archive.csv", "office_archive"),
    ("archive/bookarch.csv", "office_bookarch"),  # 2.414.0 (#3502): the booking archive of past DATEV years (books, 10 years)
    ("archive/bookarch-accounts.csv", "office_bookarch_accts"),
    ("archive/bookarch-files.csv", "office_bookarch_files"),  # 2.362.2 (#3105)
    ("archive/bookarch-documents.csv", "office_bookarch_docs"),
    ("archive/datev-guids.csv", "office_datev_guids"),
    ("cashbook/cashbooks.csv", "office_cashbooks"),
    ("cashbook/entries.csv", "office_cash_entries"),
    ("cashbook/closings.csv", "office_cash_closings"),
    ("bank/imports.csv", "office_bank_imports"),
    ("bank/transactions.csv", "office_bank_tx"),
    ("bank/balances.csv", "office_bank_balances"),  # 2.362.2 (#3105)
    ("bank/card-cards.csv", "office_cc_cards"),  # 2.444.0 (#3447): credit card statements
    ("bank/card-statements.csv", "office_cc_statements"),
    ("bank/card-positions.csv", "office_cc_lines"),
    ("expenses/meals.csv", "office_meals"),
    ("expenses/meal-files.csv", "office_meal_files"),  # 2.362.2 (#3105)
    ("expenses/trips.csv", "office_trips"),
    ("expenses/trip-items.csv", "office_trip_items"),
    ("expenses/drives.csv", "office_drives"),
    ("expenses/vehicles.csv", "office_vehicles"),  # 2.362.2 (#3105): the logbook names them
    ("logs/office-log.csv", "office_doc_log"),
    ("logs/cashbook-log.csv", "office_cash_log"),
    ("logs/archive-log.csv", "office_archive_log"),
    ("logs/meal-log.csv", "office_meal_log"),
    ("logs/drive-log.csv", "office_drive_log"),
    ("logs/drive-closed.csv", "office_drive_closed"),  # 2.362.0 (#3096): the closed months of the logbook
    ("logs/rights-log.csv", "office_rights_log"),  # 2.362.2 (#3105)
    ("logs/import-runs.csv", "office_import_runs"),
    ("letters/letters.csv", "office_letters"),  # 2.184.0 A (#2628): sent letters (business letters, 6 years; RX_WHERE)
)
RX_WHERE = {"office_letters": "org_id=? AND status<>'draft'"}  # 2.184.0 A (#2628): a table's own rows instead of OX_AREAS'
# 2.1093.0 (#5289, stage Q11): the core's tables (the procedure documentation's versions in obj_versions, the letter links in
# obj_links) come from the export register with their own rows (core/objexport.py rx); RX_TABLES / RX_WHERE hold the old tables


def rx_tables():
    """-> (archive name, table, where | None) of every CSV file: RX_TABLES (where None = RX_WHERE or the organisation export's) +
    the core's register."""
    return tuple((a, t, None) for a, t in RX_TABLES) + oex_rx(OX_FMT)
# 2.372.0 (#3316): the signature snapshot of a receipt stays on its PDF, not in the CSV
RX_DROP = {"office_signoffs": ("ip", "user_agent"), "office_meals": ("sign_pic",)}  # 2.362.2 (#3105, review): a signer's network address is no business record
# 2.619.0 (#3862): the office tables that are NOT in RX_TABLES, with the reason, are in admin/exportleft.py RX_LEFT_TABLES (one list;
# the static guards tools/check_export_tables.py and tests/export_coverage_test.py fail on a new office_* table until it is in RX_TABLES or there)


# ---------------------------------------------------------------- the subject: whose records, who may download them
def rx_subject(c, kind, sid):
    """{key, kind, id, office (office area id or None), ws (documents space), lists (SQL for the list ids)} of user / org sid."""
    from ..docs.store import doc_ws
    with system_ctx(c):  # structure only: the personal office of a person, whether an organisation exists
        if kind == "user":
            r = c.execute("SELECT id FROM orgs WHERE personal_of=?", (sid,)).fetchone()
            return {"key": f"user:{int(sid)}", "kind": kind, "id": int(sid), "office": r[0] if r else None, "ws": doc_ws(None, sid),
                    # 2.239.0 C (#2874): the person's own projects only -- an organisation's project (receipts, bookings) never
                    # goes into the personal export, also not when the person owns it or left the organisation
                    "lists": ("SELECT id FROM lists WHERE owner_id=? AND NOT is_inbox AND org_id IS NULL", (sid,))}
        if not c.execute("SELECT 1 FROM orgs WHERE id=? AND personal_of IS NULL", (sid,)).fetchone():
            raise Denied(404)
    return {"key": f"org:{int(sid)}", "kind": kind, "id": int(sid), "office": int(sid), "ws": doc_ws(sid, None),
            "lists": ("SELECT id FROM lists WHERE org_id=? AND NOT is_inbox", (sid,))}


def _rx_person():
    """A signed-in person acts (a session / the proxy sign-in), never an agent or an API token."""
    from ..agents.core import is_agent
    return bool(g.user) and not is_agent(g.user) and getattr(g, "auth_via", None) in ("session", "proxy")


def rx_may_export(c, sub):
    """Only the person themself (user) or an admin of the organisation (org); people only, never an API token."""
    if not _rx_person():
        return False
    if sub["kind"] == "user":
        return sub["id"] == me()
    return org_role(c, me(), sub["id"]) == "admin" or odl_admin_export(c, sub["id"], retention=True)  # 2.186.0 A (#2599): a retired one: its former admins (2.239.0 C #2943: or the instance admins when none is left)


def _rx_kinds(c, sub, along):
    """#6474: (key, its COUNT query, the arguments, the time a row became a record to keep) of every kind rx_counts counts."""
    oid = sub["office"]
    out = []
    if oid:
        o = (oid,)
        new = "GREATEST(x.created_at, COALESCE(x.{0}, x.created_at))"
        out += [
            # 2.144.10 B (#2576): trial documents are no records to keep
            ("documents", "SELECT COUNT(*) FROM office_docs x WHERE x.org_id=? AND x.locked_at IS NOT NULL AND x.trial=0 AND " + live_sql("x"), o, "x.locked_at"),  # 2.1005.0 (#5415)
            ("archive", "SELECT COUNT(*) FROM office_archive x WHERE x.org_id=?", o, "x.created_at"),
            ("cash", "SELECT COUNT(*) FROM office_cash_entries x WHERE x.org_id=?", o, "x.created_at"),
            ("bank", "SELECT COUNT(*) FROM office_bank_tx x WHERE x.org_id=?", o, "x.created_at"),
            # 2.152.0 (#2167, review A9): the logbook, travel receipts in DATEV and approved entertainment receipts (all in RX_TABLES)
            ("drives", "SELECT COUNT(*) FROM office_drives x WHERE x.org_id=?", o, "x.created_at"),
            ("trip_receipts", "SELECT COUNT(*) FROM office_trip_items x WHERE x.org_id=? AND x.datev=1", o, new.format("updated_at")),
            ("meals", "SELECT COUNT(*) FROM office_meals x WHERE x.org_id=? AND x.status<>'draft'", o, new.format("approved_at")),
        ]
        if "office_letters" in _rx_have(c):  # 2.184.0 A (#2628): sent letters (drafts are no records)
            out.append(("letters", "SELECT COUNT(*) FROM office_letters x WHERE x.org_id=? AND x.status<>'draft'", o, new.format("sent_at")))
    if sub["ws"]:
        out.append(("receipts", "SELECT COUNT(*) FROM rc_receipts x JOIN doc_meta d ON d.node_id=x.node_id WHERE d.ws=?", (sub["ws"],), "x.set_at"))
    if along:
        q, a = sub["lists"]
        out.append(("project_receipts", f"SELECT COUNT(*) FROM budget_files x WHERE x.list_id IN ({q})", tuple(a), "x.created_at"))
    return out


def rx_counts(c, sub, along=True, since=None):
    """How many records of each kind the subject has (along = with the receipts of its lists: they go with the deletion only
    when the lists are deleted along). #6474: since (ISO) = only those that became a record to keep at or after that moment;
    einvoices = received e-invoices of the documents space nobody took over as a receipt (as orgretain.odl_einvoice_years)."""
    out = {}
    with system_ctx(c):  # counts only (no content): the deleting admin may not see the records themselves
        for key, q, args, at in _rx_kinds(c, sub, along):
            if since:  # at: one of the fixed column expressions of _rx_kinds
                q, args = q + " AND " + at + " >= CAST(? AS timestamptz)", args + (since,)
            out[key] = c.execute(q, args).fetchone()[0]
        out["einvoices"] = len(_rx_einvoices(c, sub, since))
    return {k: int(v) for k, v in out.items() if v}


def _rx_einvoices(c, sub, since=None):
    """#6474 (A7): [(doc_meta + file row, the invoice dict | None)] of the received e-invoices in the subject's documents space
    that are no receipt: kept by law also when nobody took them over (2.239.0 C #2874 counts them for self-hosting,
    orgretain.odl_einvoice_years; the hosted way did not, so they went without the export). The invoice data is sealed per
    space (doc_meta.extracted); one that cannot be opened counts (the careful side). Also those in the trash: they go with
    the deletion. The caller runs as system."""
    from ..docs.store import doc_open_as
    if not sub.get("ws"):
        return []
    q = ("SELECT m.node_id, m.ws, m.extracted, m.doc_date, m.created_at, n.name, n.deleted_at FROM doc_meta m JOIN fs_nodes n ON n.id=m.node_id "
         "WHERE m.ws=? AND m.extracted<>'' AND n.kind='file' AND NOT EXISTS (SELECT 1 FROM rc_receipts r WHERE r.node_id=m.node_id)")
    args = (sub["ws"],)
    if since:  # read as an e-invoice after the upload (done_at) = a record from then on
        q += " AND GREATEST(m.created_at, COALESCE(m.done_at, m.created_at)) >= CAST(? AS timestamptz)"
        args += (since,)
    out = []
    for m in c.execute(q + " ORDER BY m.node_id", args).fetchall():
        try:
            v = json.loads(doc_open_as(c, m["ws"], "doc_meta.extracted", m["extracted"])[0] or "null")  # as docs/store.meta_json
            if not isinstance(v, dict) or v.get("_einv") is None:
                continue
            inv = v["_einv"] if isinstance(v["_einv"], dict) else {}
        except Exception:  # noqa: BLE001 -- not readable: kept
            inv = None
        out.append((m, inv))
    return out


def _rx_have(c):
    return {r[0] for r in c.execute("SELECT table_name FROM information_schema.tables WHERE table_schema=current_schema()")}


def rx_last(c, sub, kind="export"):
    """When the subject's last finished export (or waiver) was (ISO) or None."""
    r = _rx_last_row(c, sub, (kind,))
    return r["at"] if r else None


def _rx_last_row(c, sub, kinds):
    """#6474: {kind, at, by, detail (dict)} of the subject's newest log row of one of kinds, or None."""
    with system_ctx(c):  # the log of the subject (the deleting admin and the exporting person may differ)
        r = c.execute(f"SELECT kind, at, by_user, detail FROM retention_log WHERE subject=? AND kind IN ({','.join('?' * len(kinds))}) "
                      "ORDER BY id DESC LIMIT 1", (sub["key"],) + tuple(kinds)).fetchone()
    if not r:
        return None
    d = r[3]
    if isinstance(d, str):
        try:
            d = json.loads(d or "{}")
        except ValueError:
            d = {}
    return {"kind": r[0], "at": r[1], "by": r[2], "detail": d if isinstance(d, dict) else {}}


def rx_fresh(at):
    if not at:
        return False
    try:
        from datetime import datetime
        t = datetime.fromisoformat(str(at).replace("Z", "+00:00"))
    except ValueError:
        return False
    return (now_utc() - t).total_seconds() < RX_VALID_DAYS * 86400


def _rx_int(v):
    try:
        return int(v or 0)
    except (TypeError, ValueError):
        return 0


def rx_export_check(c, sub, along=True):
    """#6474 (A4, A5): whether the subject's last finished export lets the deletion go -> (at, None) when it does, else
    (at | None, {"reason": ...}): "none" = no finished export within RX_VALID_DAYS; "incomplete" = files could not be read
    or were locked by the virus scanner (missing / locked: how many; missing_names / locked_names only for who may export:
    the deleting admin never sees what the records are); "newer" = records to keep came after the export began (newer: how
    many) -- they are not in the ZIP, so it is downloaded again."""
    row = _rx_last_row(c, sub, ("export",))
    if not row or not rx_fresh(row["at"]):
        return None, {"reason": "none"}
    d = row["detail"]
    miss, lock = _rx_int(d.get("missing")), _rx_int(d.get("locked"))
    if miss or lock:
        prob = {"reason": "incomplete", "missing": miss, "locked": lock}
        if rx_may_export(c, sub):
            prob["missing_names"] = [str(x) for x in (d.get("missing_names") or [])][:RX_NAMES_MAX]
            prob["locked_names"] = [str(x) for x in (d.get("locked_names") or [])][:RX_NAMES_MAX]
        return row["at"], prob
    newer = sum(rx_counts(c, sub, along, since=d.get("started") or row["at"]).values())  # a row of before #6474: its end
    if newer:
        return row["at"], {"reason": "newer", "newer": newer}
    return row["at"], None


def rx_owner(c, sub):
    """#6474 (A6): the acting person is whose records these are: the person themself (user) or an admin of the organisation
    (org); people only, never an API token. Not: an instance admin as such, the former admins of a retired organisation."""
    if not _rx_person():
        return False
    if sub["kind"] == "user":
        return sub["id"] == me()
    return sub["kind"] == "org" and org_role(c, me(), sub["id"]) == "admin"


def rx_may_waive(c, sub):
    """#6474 (A6): may the acting person do without the export while deleting? Self-hosting: whoever may delete (as before:
    the server's admin answers for its records). Hosted: only whose records these are (rx_owner) -- the hosting operator
    never waives for a customer (the console never did, admin/operator.py; the old routes took ?retention=waived from any
    instance admin, and the purge then drops the receipt locks, OLK_BYPASS)."""
    return not hosted() or rx_owner(c, sub)


def rx_waiver_declared(c, sub, along=True):
    """#6474 (A6): the waiver the person / an admin of the organisation declared beforehand (POST .../waiver) while it holds:
    {at, by} or None. It holds RX_VALID_DAYS, until it is taken back, and while no kind of record grew since (the numbers
    it was declared for, as the own deletion's check: selfdelete review M2)."""
    row = _rx_last_row(c, sub, ("waiver_declared", "waiver_revoked"))
    if not row or row["kind"] != "waiver_declared" or not rx_fresh(row["at"]):
        return None
    old = row["detail"].get("counts") if isinstance(row["detail"].get("counts"), dict) else {}
    if any(n > _rx_int(old.get(k)) for k, n in rx_counts(c, sub, along).items()):
        return None
    return {"at": row["at"], "by": row["by"]}


def rx_info(c, sub, along=True):
    """What the delete dialogs and the settings show: needed (records exist), can_export, exported_at (a finished export within
    RX_VALID_DAYS that lets the deletion go, #6474: complete and nothing newer; else export_problem says why, rx_export_check),
    the counts (only to who may export), the years of the hint, hosted; #6474: can_waive (the acting person may do without
    it while deleting), may_declare + waived_at (the waiver declared beforehand)."""
    counts = rx_counts(c, sub, along)
    can = rx_may_export(c, sub)
    at, prob = rx_export_check(c, sub, along) if counts else (None, None)
    w = rx_waiver_declared(c, sub, along) if counts else None
    d = {"needed": bool(counts), "can_export": can, "exported_at": at if at and not prob else None, "years": RX_YEARS,
         "note": tr(RX_NOTE), "hosted": hosted(), "valid_days": RX_VALID_DAYS,
         "export_problem": prob if prob and prob["reason"] != "none" else None,
         "can_waive": rx_may_waive(c, sub), "may_declare": rx_owner(c, sub), "waived_at": w["at"] if w else None,
         "state": rx_state(c, sub) if counts else None}  # 2.186.0 A (#2599): retire / expired = no export step on deletion
    if can:
        d["counts"] = counts
        d["url"] = "/api/retention/me/export.zip" if sub["kind"] == "user" else f"/api/retention/org/{sub['id']}/export.zip"
    return d


def _rx_scrub(c, sub):
    """#6474: the names of unreadable / locked files leave the subject's log rows when it is deleted (the log outlives the
    account / organisation; the numbers stay)."""
    with system_ctx(c):  # the subject's log rows
        c.execute("UPDATE retention_log SET detail = detail - 'missing_names' - 'locked_names' WHERE subject=? AND kind='export'", (sub["key"],))


def rx_problem_text(prob):
    """#6474: the sentence of a 409 for the export problem prob (rx_export_check)."""
    if prob["reason"] == "incomplete":
        names = (prob.get("missing_names") or []) + (prob.get("locked_names") or [])
        msg = tr("The last retention export was not complete: {0} files could not be read, {1} were locked by the virus scanner. Check them in Kalmido and download the export again.", prob["missing"], prob["locked"])
        return msg + (" (" + ", ".join(names[:10]) + (" ..." if len(names) > 10 else "") + ")" if names else "")
    if prob["reason"] == "newer":
        return tr("Records to keep were added after the last retention export (number: {0}). Download it again.", prob["newer"])
    return tr("No finished retention export of the last {0} days was found. Download it again or do without it.", RX_VALID_DAYS)


def rx_log(c, sub, kind, detail=None):
    with system_ctx(c):  # the subject's log row (no organisation column: it outlives the deleted organisation / account)
        return insert_id(c, "INSERT INTO retention_log(subject, kind, by_user, at, detail) VALUES(?,?,?,?,?)",
                         (sub["key"], kind, me(), iso(now_utc()), json.dumps(detail or {}, ensure_ascii=False)))


def rx_alert(text, args):
    aa_now("security", f"retention:{int(time.time() * 1000)}", text, args)


def rx_state(c, sub):
    """2.186.0 A (#2599): what the deletion of sub does with its records: "retire" = they stay (self-hosting: the
    organisation / the personal office is retired by law, accounts/orgretain.py; its former admins export it later), "expired"
    = a retired organisation whose period is over (nothing is kept any more), else None (the records go: export or waiver)."""
    if sub["kind"] == "org":
        kept = odl_retired(c, sub["id"])
        if kept is not None:
            return "expired" if kept < now_utc().date().isoformat() else None
        return "retire" if odl_retention(c, sub["id"])["until"] else None
    return "retire" if upg_personal_state(c, sub["id"])[1]["until"] else None


def rx_lists_how():
    """2.186.0 A (#2566): on the hosted instance the ?retention= of an account deletion ("exported" | "waived"; rx_gate checks
    it in the same transaction) decides what happens to its projects with receipts (useradmin.ua8_lists_settle); else None."""
    how = request.args.get("retention")
    return how if hosted() and how in ("exported", "waived") else None


def rx_gate(c, sub, along=True, how=None):
    """Before the deletion of sub: None = it may go (no records, a fresh export, or ?retention=waived -- noted), else the 409
    answer (#6474: with reason = needed | none | incomplete | newer | waiver; rx_export_check, rx_may_waive). The caller deletes in the same transaction (a waiver row goes away with a failed deletion). 2.186.0 A (#2599):
    records that are retired need neither (no waiver is noted); after the period of a retired organisation it goes as such.
    #3939: how = the caller's choice instead of the request's ?retention= ("" = neither export nor waiver: the hosting
    operator's console, which never waives)."""
    counts = rx_counts(c, sub, along)
    if not counts:
        return None, None
    st = rx_state(c, sub)
    if st == "retire":
        return None, None
    if st == "expired":
        rx_log(c, sub, "expired", {"counts": counts})
        return None, (N_("{0} deleted {1}: its legal retention period was over."), "expired")
    if how is None:
        how = request.args.get("retention") or ""
        how = "" if how == "requested" else how  # 2.553.0 (#1413): never from a request (below: only the background run passes it)
    if how == "requested":  # 2.553.0 (#1413): the person's own deletion: the export / waiver passed this gate when it was asked for
        _rx_scrub(c, sub)
        return None, (N_("{0} deleted {1}: the retention step was done when the deletion was asked for."), "exported")
    prob = None
    if how == "waived":
        if rx_may_waive(c, sub):
            rx_log(c, sub, "waiver", {"counts": counts})
            _rx_scrub(c, sub)
            return None, (N_("{0} deleted {1} without the retention export (waived explicitly)."), "waiver")
        w = rx_waiver_declared(c, sub, along)  # #6474 (A6): hosted, somebody else deletes: the waiver was declared by whose records these are
        if w:
            rx_log(c, sub, "waiver", {"counts": counts, "declared_by": w["by"], "declared_at": w["at"]})
            _rx_scrub(c, sub)
            return None, (N_("{0} deleted {1} without the retention export (waived explicitly)."), "waiver")
        prob = {"reason": "waiver"}
    elif how == "exported":
        _at, prob = rx_export_check(c, sub, along)  # #6474 (A4, A5): complete, and nothing to keep came after it
        if prob is None:
            _rx_scrub(c, sub)
            return None, (N_("{0} deleted {1} after the retention export."), "exported")
    info = rx_info(c, sub, along)
    if prob and prob["reason"] == "waiver":
        msg = tr("Only the person themself or an admin of the organisation can do without the retention export (Settings, at the retention export). Delete after a finished export, or ask them to declare it.")
    elif prob:
        msg = rx_problem_text(prob)
    else:
        msg = tr(RX_NEEDED)
    return (jsonify(error=msg, code="retention", reason=prob["reason"] if prob else "needed", retention=info), 409), None


# ---------------------------------------------------------------- the ZIP
class _Pipe:
    """A write-only, unseekable stream: zipfile writes into it (data descriptors), the generator takes the bytes out."""

    def __init__(self):
        self.buf = bytearray()

    def write(self, b):
        self.buf += b
        return len(b)

    def flush(self):
        pass

    def take(self):
        b = bytes(self.buf)
        self.buf.clear()
        return b


def _cell(v):
    if v is None:
        return ""
    if isinstance(v, (dict, list)):
        v = json.dumps(v, ensure_ascii=False)
    return bk_csv_cell(v) if isinstance(v, str) else str(v)


def _csv(rows, cols=None):
    """Rows (dicts) as CSV text (semicolon, byte order mark, formula-safe cells); cols = the column order (default: as they come)."""
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";", lineterminator="\r\n")
    rows = list(rows)
    if cols is None:
        cols = []
        for r in rows:
            cols += [k for k in r if k not in cols]
    w.writerow(cols)
    for r in rows:
        w.writerow([_cell(r.get(k)) for k in cols])
    return "﻿" + buf.getvalue(), len(rows)


class _Zip:
    def __init__(self):
        self.pipe = _Pipe()
        self.zf = zipfile.ZipFile(self.pipe, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6)
        self.files, self.sections, self.missing, self.names = {}, {}, [], set()
        self.locked, self.lk = [], None  # 2.370.0 (#2781): files the virus scanner locked: left out, listed (orgexport._ox_locked)

    def put(self, name, data, section=None):
        if isinstance(data, str):
            data = data.encode("utf-8")
        base, n = name, 1
        while name in self.names:  # two files of the same name: number them
            n += 1
            stem, dot, ext = base.rpartition(".")
            name = f"{stem}-{n}.{ext}" if dot else f"{base}-{n}"
        self.names.add(name)
        zi = zipfile.ZipInfo(name, date_time=time.localtime()[:6])
        zi.compress_type = zipfile.ZIP_DEFLATED
        self.zf.writestr(zi, data)
        self.files[name] = {"sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}
        if section:
            self.sections[section] = self.sections.get(section, 0) + 1
        return self.pipe.take()


def _names(c):
    cache = {}

    def name(uid):
        if not uid:
            return ""
        if uid not in cache:
            r = c.execute("SELECT COALESCE(display_name, username) FROM users WHERE id=?", (uid,)).fetchone()
            cache[uid] = r[0] if r else f"#{uid}"
        return cache[uid]
    return name


def _tables(c, z, sub):
    """The office tables as CSV (decrypted like the organisation export, secrets dropped) -> chunks."""
    oid = sub["office"]
    where = {t: w for _n, t, w in OX_AREAS}  # the old tables (2.1093.0, #5289: the core's bring their own, rx_tables)
    have = {r[0] for r in c.execute("SELECT table_name FROM information_schema.tables WHERE table_schema=current_schema()")}
    name = _names(c)
    for arc, table, own in rx_tables():
        if table not in have or (own is None and table not in where):
            continue
        if sub["kind"] == "user" and table in OX_PB_CLIENTS:  # a personal office: the owner's private clients
            rows = _rows(c, oid, table, ox_live(c, table, OX_PB_CLIENTS[table]), (sub["id"],))
        else:  # 2.223.3 B (#2879): without the trash and undone entries (ox_live; removed drives stay for the change log)
            w = ox_live(c, table, own or RX_WHERE.get(table) or where[table])
            rows = _rows(c, oid, table, w, (oid,) * w.count("?"))
        rows = [{k: v for k, v in r.items() if k not in RX_DROP.get(table, ())} for r in rows]
        # 2.1287.0 (#6470, review): a row that kept its person's name (office_doc_log.user_name) shows it when the account is gone
        rows = [dict(r, user_name=name(r.get("user_id") or r.get("by_user")) or r.get("user_name") or "") if ("user_id" in r or "by_user" in r) else r for r in rows]
        if not rows:
            continue
        text, _n = _csv(rows)
        yield z.put(arc, text, arc.split("/")[0])


def _checked(c, oid, z, r, ext, data, stem):
    """2.296.0 F (#3177, GoBD): the stored bytes as they are (the export hides nothing), but a file whose SHA-256 differs from
    the one noted at storing is named in the index and logged (store_mismatch) -- never a 409 that would stop the export."""
    sha = r[ext + "_sha256"] if (ext + "_sha256") in r.keys() else ""
    got = hashlib.sha256(data).hexdigest()
    if sha and got != sha:
        z.missing.append(f"{stem}.{ext} (checksum mismatch)")
        ofx_log(c, oid, "store_mismatch", doc_id=r["id"], detail={"file": ext, "sha256": sha, "found": got, "at": "retention export"})
    return data


def _ubl_sent(c, oid, z, r, stem, done):
    """2.1321.0 (#6480): the UBL of each Peppol send of document r that went out, byte for byte as it was sent
    (<stem>.peppol-<send>.xml); a file whose SHA-256 differs from the send's is named in the index and logged."""
    for sid, p, want in epdf_ubl_sent(c, oid, r):
        name = f"{stem}.peppol-{sid}.xml"
        done.add(os.path.realpath(p))
        try:
            data = oc_read_file(c, p)
        except Exception as e:  # noqa: BLE001 -- one unreadable file must not stop the export: named in the index
            print("retention export: Peppol UBL of document", r["id"], "not readable:", type(e).__name__, flush=True)
            z.missing.append(name)
            continue
        got = hashlib.sha256(data).hexdigest()
        if want and got != want:
            z.missing.append(f"{name} (checksum mismatch)")
            ofx_log(c, oid, "store_mismatch", doc_id=r["id"], detail={"file": "ubl", "send": sid, "sha256": want, "found": got, "at": "retention export"})
        yield z.put(name, data, "invoices")


def _fs_locked(c, z, nid, name):
    """2.370.0 (#2781): the current version of file nid is locked by the virus scanner -> True (listed in z.locked)."""
    r = c.execute("SELECT cur_version FROM fs_nodes WHERE id=?", (nid,)).fetchone()
    return bool(r) and z.lk("fs", {"id": nid}, name, r[0])


def _invoices(c, z, sub, done):
    """Every finalised document: its stored PDF / XML (decrypted), else rendered from its snapshot."""
    oid = sub["office"]
    # 2.144.10 B (#2576): no trial documents (the tables below keep their rows with the trial column)
    for r in c.execute(f"SELECT * FROM office_docs WHERE org_id=? AND locked_at IS NOT NULL AND trial=0 AND {live_sql()} ORDER BY date, id", (oid,)).fetchall():  # 2.1005.0 (#5415): never one of the trash (a draft is never finalised anyway)
        stem = "invoices/" + _safe_part(epdf_name(r), 100)
        p, x = _stored(oid, r, "pdf"), _stored(oid, r, "xml")
        yield from _ubl_sent(c, oid, z, r, stem, done)  # 2.1321.0 (#6480): the e-invoice as it went over Peppol
        try:
            if p:
                done.add(os.path.realpath(p))
                yield z.put(stem + ".pdf", _checked(c, oid, z, r, "pdf", oc_read_file(c, p), stem), "invoices")
                if x:
                    done.add(os.path.realpath(x))
                    yield z.put(stem + ".xml", _checked(c, oid, z, r, "xml", oc_read_file(c, x), stem), "invoices")
                continue
            pdf, xml, _fmt = _render(c, oid, r)
        except Exception as e:  # noqa: BLE001 -- one unreadable document must not stop the export: named in the index
            print("retention export: document", r["id"], "of area", oid, "not readable:", type(e).__name__, flush=True)
            z.missing.append(f"{stem}.pdf")
            continue
        yield z.put(stem + ".pdf", pdf, "invoices")
        if xml:
            yield z.put(stem + ".xml", xml, "invoices")


def _receipts(c, z, sub):
    """The receipts of the documents space (also those in the trash: they go with the deletion) with their files + receipts.csv."""
    from ..docs.store import doc_open
    rows = c.execute("SELECT r.node_id, r.category, r.vat_pct, r.paid_at, d.doc_date, d.amount, d.currency, d.ws, n.name, n.deleted_at "
                     "FROM rc_receipts r JOIN doc_meta d ON d.node_id=r.node_id JOIN fs_nodes n ON n.id=r.node_id "
                     "WHERE d.ws=? AND n.kind='file' ORDER BY COALESCE(NULLIF(d.doc_date, ''), CAST(r.paid_at AS text)), r.node_id",  # 2.1115.0 (#5951): paid_at DATE
                     (sub["ws"],)).fetchall()
    out = []
    for r in rows:
        fn = f"receipts/{int(r['node_id'])}-{_safe_part(r['name'], 100)}"
        try:
            if _fs_locked(c, z, r["node_id"], r["name"]):
                data, fn = None, ""
            else:
                data = fs_read(c, r["node_id"])
        except Exception as e:  # noqa: BLE001 -- a file without content (or held by the scan guard): named in the index
            print("retention export: receipt", r["node_id"], "not readable:", type(e).__name__, flush=True)
            z.missing.append(fn)
            data, fn = None, ""
        if data is not None:
            yield z.put(fn, data, "receipts")
        out.append({"node_id": r["node_id"], "file": fn, "name": r["name"], "doc_date": r["doc_date"], "paid_at": r["paid_at"],
                    "amount": doc_open(c, r["ws"], "doc_meta.amount", r["amount"]) or "", "currency": r["currency"] or "",
                    "vat_pct": r["vat_pct"], "category": r["category"] or "", "in_trash": 1 if r["deleted_at"] else 0})
    if out:
        yield z.put("receipts/receipts.csv", _csv(out)[0])


def _einvoices(c, z, sub):
    """#6474 (A7): the received e-invoices of the documents space that are no receipt (those are under receipts/), with
    their files + received-einvoices.csv (number, seller, amount as read from the invoice)."""
    out = []
    for m, inv in _rx_einvoices(c, sub):
        inv = inv or {}
        fn = f"received-einvoices/{int(m['node_id'])}-{_safe_part(m['name'], 100)}"
        try:
            if _fs_locked(c, z, m["node_id"], m["name"]):
                data, fn = None, ""
            else:
                data = fs_read(c, m["node_id"])
        except Exception as e:  # noqa: BLE001 -- a file without content: named in the index
            print("retention export: e-invoice", m["node_id"], "not readable:", type(e).__name__, flush=True)
            z.missing.append(fn)
            data, fn = None, ""
        if data is not None:
            yield z.put(fn, data, "received-einvoices")
        seller = inv.get("seller")
        out.append({"node_id": m["node_id"], "file": fn, "name": m["name"], "doc_date": m["doc_date"] or inv.get("date") or "",
                    "number": inv.get("number") or "", "seller": (seller.get("name") if isinstance(seller, dict) else seller) or "",
                    "gross": inv.get("gross") or inv.get("payable") or "", "currency": inv.get("currency") or "",
                    "in_trash": 1 if m["deleted_at"] else 0})
    if out:
        yield z.put("received-einvoices/received-einvoices.csv", _csv(out)[0])


def _project_receipts(c, z, sub):
    """The receipt files of the lists (budget_files) + project-receipts.csv."""
    q, a = sub["lists"]
    rows = c.execute(f"SELECT f.*, l.name AS list_name FROM budget_files f JOIN lists l ON l.id=f.list_id WHERE f.list_id IN ({q}) "
                     "AND f.entry_id IN (SELECT id FROM budget_entries WHERE deleted_at IS NULL) "  # 2.567.0 A (#4707): not those in the trash
                     "ORDER BY f.list_id, f.id", a).fetchall()
    out = []
    for r in rows:
        fn = f"project-receipts/{int(r['list_id'])}-{_safe_part(r['list_name'], 40)}/{int(r['id'])}-{_safe_part(r['name'], 100)}"
        full = _under(ATT_DIR, r["path"])
        data = None
        if z.lk("budget", {"id": r["id"]}, r["name"]):  # 2.370.0 (#2781)
            fn = ""
        else:
            try:
                data = oc_read_file(c, full) if full else None
            except Exception as e:  # noqa: BLE001 -- named in the index
                print("retention export: project receipt", r["id"], "not readable:", type(e).__name__, flush=True)
            if data is None:
                z.missing.append(fn)
                fn = ""
        if data is not None:
            yield z.put(fn, data, "project-receipts")
        out.append({"id": r["id"], "file": fn, "list_id": r["list_id"], "list": r["list_name"], "entry_id": r["entry_id"], "name": r["name"],
                    "size": r["size"], "created_at": r["created_at"]})
    if out:
        yield z.put("project-receipts/project-receipts.csv", _csv(out)[0])


def _project_bookings(c, z, sub):
    """2.186.1 (#2732): the bookings of a kept project (budget_entries, decrypted) as project-bookings/bookings.csv."""
    q, a = sub["lists"]
    cats = {r["id"]: r["name"] for r in c.execute(f"SELECT id, name FROM budget_cats WHERE list_id IN ({q})", a).fetchall()}
    out = []
    # 2.567.0 A (#4707): not the entries in the trash
    for r in c.execute(f"SELECT * FROM budget_entries WHERE list_id IN ({q}) AND deleted_at IS NULL ORDER BY list_id, day, id", a).fetchall():
        d = bud_dec(c, "budget_entries", r)
        out.append({"id": d["id"], "list_id": d["list_id"], "day": d["day"], "kind": d["kind"], "amount": d["amount"],
                    "title": d["title"], "counterpart": d["counterpart"], "note": d["note"],
                    "category": cats.get(d["cat_id"], ""), "source": d["source"]})
    if out:
        yield z.put("project-bookings/bookings.csv", _csv(out)[0], "project-bookings")


def _letters(c, z, sub):
    """2.184.0 A (#2628): the PDFs of the sent letters as filed in the documents space (the list: letters/letters.csv)."""
    if "office_letters" not in _rx_have(c):
        return
    for r in c.execute("SELECT id, letter_date, node_id FROM office_letters WHERE org_id=? AND status<>'draft' ORDER BY letter_date, id",
                       (sub["office"],)).fetchall():
        day = "".join(ch for ch in str(r["letter_date"] or "")[:10] if ch.isdigit() or ch == "-")
        fn = f"letters/{int(r['id'])}-{day or 'letter'}.pdf"
        if r["node_id"] and _fs_locked(c, z, r["node_id"], fn):  # 2.370.0 (#2781)
            continue
        try:
            data = fs_read(c, r["node_id"]) if r["node_id"] else None
        except Exception as e:  # noqa: BLE001 -- named in the index
            print("retention export: letter", r["id"], "not readable:", type(e).__name__, flush=True)
            data = None
        if data is None:
            z.missing.append(fn)
        else:
            yield z.put(fn, data, "letters")


def _cashbooks(c, z, sub, uid, lg):
    """Every cash book of the office as PDF (entries, day closings, change log) and CSV, over its whole time."""
    oid = sub["office"]
    today = now_utc().date().isoformat()
    for b in c.execute("SELECT * FROM office_cashbooks WHERE org_id=? ORDER BY id", (oid,)).fetchall():
        first, last = c.execute("SELECT MIN(day), MAX(day) FROM office_cash_entries WHERE book_id=?", (b["id"],)).fetchone()
        frm = min(x for x in (b["opening_day"], first, today) if x)
        vals = cb_export_data(c, oid, uid, b, frm, max(today, last or today))
        stem = f"cashbook/{int(b['id'])}-{_safe_part(b['name'], 60)}"
        yield z.put(stem + ".csv", cb_csv_text(*vals), "cashbook")
        try:
            yield z.put(stem + ".pdf", cb_pdf_bytes(c, oid, *vals, lg), "cashbook")
        except Exception as e:  # noqa: BLE001 -- the CSV holds the same
            print("retention export: cash book PDF", b["id"], "failed:", type(e).__name__, flush=True)
            z.missing.append(stem + ".pdf")


def _office_files(c, z, sub, done):
    """Every other file of the office folder (archive PDFs, accepted quotations, meal bills, contract files ...), decrypted."""
    base = os.path.join(OFFICE_DIR, str(int(sub["office"])))
    if not os.path.isdir(base):
        return
    for root, dirs, files in os.walk(base):
        dirs[:] = sorted(d for d in dirs if not os.path.islink(os.path.join(root, d)))
        for fn in sorted(files):
            full = os.path.join(root, fn)
            if os.path.islink(full) or not os.path.isfile(full) or os.path.realpath(full) in done or fn.endswith(".tmp"):
                continue
            if root == base and fn in z.lk.office:  # 2.370.0 (#2781): as orgexport, the office's uploads lie directly in its folder
                z.lk(*z.lk.office[fn][:2], fn)
                continue
            rel = os.path.relpath(full, base).split(os.sep)
            try:
                data = oc_read_file(c, full)
            except Exception as e:  # noqa: BLE001 -- named in the index
                print("retention export: office file not readable:", type(e).__name__, flush=True)
                z.missing.append("office-files/" + "/".join(_safe_part(p) for p in rel))
                continue
            yield z.put("office-files/" + "/".join(_safe_part(p) for p in rel), data, "office-files")


RX_SECTIONS = (
    ("invoices", N_("Invoices, credit notes and other finalised documents (PDF, e-invoice XML) and their lists (CSV)")),
    ("receipts", N_("Receipts with their files and receipts.csv")),
    ("received-einvoices", N_("Received e-invoices that are no receipt, with their files and received-einvoices.csv")),  # #6474 (A7)
    ("project-receipts", N_("Receipts of projects")),
    ("project-bookings", N_("Bookings of projects (CSV)")),  # 2.186.1 (#2732): a kept project's export (rx_list_download)
    ("books", N_("Procedure documentation, number ranges, opening balances, locked periods, equipment (CSV)")),  # 2.362.2 (#3105)
    ("contracts", N_("Contracts and agreements (CSV; the files are under office-files)")),  # 2.362.2 (#3105)
    ("cashbook", N_("Cash books (PDF and CSV with day closings and change log)")),
    ("bank", N_("Imported bank statements (CSV)")),
    ("expenses", N_("Entertainment receipts, travel expenses, logbook (CSV)")),
    ("archive", N_("Archive of imported documents (CSV; the files are under office-files)")),
    ("letters", N_("Sent letters (PDF) and their list (CSV)")),  # 2.184.0 A (#2628)
    ("logs", N_("Office log and change logs (GoBD)")),
    ("office-files", N_("All other files of the office folder")),
)


def _index(z, sub, title, by, when):
    lines = [tr("Retention export"), "=" * 40, "", tr("Of: {0}", title), tr("Created: {0}", when), tr("By: {0}", by),
             f"Kalmido {APP_VERSION}", "", tr(RX_NOTE), "", tr("Contents"), "-" * 40]
    for key, label in RX_SECTIONS:
        n = z.sections.get(key, 0)
        if n:
            lines.append(f"{key}/  ({n})  {tr(label)}")
    if not z.sections:
        lines.append(tr("No records found."))
    if z.missing:
        lines += ["", tr("Could not be read (please check in Kalmido before the deletion):")] + [f"  {m}" for m in z.missing]
    if z.locked:  # 2.370.0 (#2781)
        lines += ["", tr("Left out, locked by the virus scanner:")] + [f"  {m['name']} ({m['signature']})" for m in z.locked]
    lines += ["", tr("manifest.json lists every file with its SHA-256 checksum."), ""]
    return "\r\n".join(lines)


def rx_stream(sub, uid, by, title, lg):
    """The generator of the ZIP (own connection, system context for the subject's rows only; the caller checked the right)."""
    c = connect()
    z = _Zip()
    done = set()
    ok = False
    # #6474 (A5): what becomes a record from `started` on is "newer than this export" (rx_export_check). Many rows carry whole
    # seconds, so the export begins at the next full second: a row of this second is before it and is read below, one after
    # it compares as newer -- nothing falls between (up to one second before the first byte).
    t0 = now_utc()
    if t0.microsecond:
        time.sleep(1 - t0.microsecond / 1e6)
        t0 = t0.replace(microsecond=0) + timedelta(seconds=1)
    started = iso(t0)
    try:
        with system_ctx(c):  # the subject's records only (every query names its office / documents space / lists); checked by rx_may_export
            z.lk = _ox_locked(c, sub["office"], z)  # 2.370.0 (#2781): files the virus scanner locked stay out, listed in the manifest
            if sub["office"]:
                yield from _invoices(c, z, sub, done)
            if sub["kind"] != "list":  # 2.186.1 (#2732): a kept project has no documents space of its own
                yield from _receipts(c, z, sub)
                yield from _einvoices(c, z, sub)  # #6474 (A7)
            yield from _project_receipts(c, z, sub)
            if sub["kind"] == "list":
                yield from _project_bookings(c, z, sub)
            if sub["office"]:
                yield from _cashbooks(c, z, sub, uid, lg)
                yield from _letters(c, z, sub)  # 2.184.0 A (#2628)
                yield from _tables(c, z, sub)
                yield from _office_files(c, z, sub, done)
            when = iso(now_utc())
            idx = _index(z, sub, title, by, when)
            man = {"format": "kalmido-retention-export", "format_version": 1, "kalmido_version": APP_VERSION, "subject": sub["key"],
                   "created_at": when, "created_by": by, "files": dict(z.files), "missing": z.missing, "locked_files": z.locked,
                   "not_included": left_lines(RX_LEFT_TABLES, lg)}  # 2.362.4 (#3107), 2.464.0 (#3841)
            yield z.put("00-index.txt", idx)
            yield z.put("manifest.json", json.dumps(man, ensure_ascii=False, indent=1))
            z.zf.close()
            yield z.pipe.take()
            ok = True
    finally:
        if ok:  # only a download that ran to its end counts as "exported"
            try:
                with system_ctx(c):  # the subject's log row + the office log
                    c.execute("INSERT INTO retention_log(subject, kind, by_user, at, detail) VALUES(?,?,?,?,?)",
                              (sub["key"], "export", uid, iso(now_utc()), json.dumps({
                                  "files": len(z.files), "missing": len(z.missing), "locked": len(z.locked), "started": started,
                                  # #6474 (A4): which ones, for the 409 of the deletion (only who may export sees them)
                                  "missing_names": [str(m)[:200] for m in z.missing[:RX_NAMES_MAX]],
                                  "locked_names": [str(m.get("name") or "")[:200] for m in z.locked[:RX_NAMES_MAX]]}, ensure_ascii=False)))
                    if sub["office"]:
                        from ..office.ledger import ofx_log
                        ofx_log(c, sub["office"], "export", target="retention", detail={"files": len(z.files), "missing": len(z.missing)})
                c.commit()
                rx_alert(N_("{0} downloaded the retention export of {1}."), [by, title])
            except Exception as e:  # noqa: BLE001 -- the file is sent; a failed note only means "export again"
                print("retention export: note failed:", type(e).__name__, flush=True)
        c.close()


def _download(sub, title):
    c = db()
    if not rx_may_export(c, sub):
        raise Denied(404 if sub["kind"] == "org" else 403)
    e = stepup_download(c)  # 2.223.2 C (#2871): POST with the step-up -> a ticket, GET with it -> the ZIP
    if e is not None:
        return e
    by = g.user["username"]
    lg = lang()
    name = f"kalmido-retention-{sub['kind']}{sub['id']}-{now_utc().strftime('%Y-%m-%d')}.zip"
    resp = Response(stream_with_context(rx_stream(sub, me(), by, title, lg)), mimetype="application/zip")
    resp.headers["Content-Disposition"] = f'attachment; filename="{name}"'
    resp.headers["Cache-Control"] = "private, no-store"
    resp.headers["X-Content-Type-Options"] = "nosniff"
    return resp


@app.get("/api/trash/lists/<int:lid>/export.zip")
@app.post("/api/trash/lists/<int:lid>/export.zip")  # 2.223.2 C (#2871): POST = the step-up
def otr_export(lid):
    """2.186.1 (#2732): the custodian downloads a kept private project (lists/listtrash.py otr_held): its receipts with their
    files and its bookings as the retention export ZIP (subject "list:<id>"). People only, no API token."""
    c = db()
    r = otr_need(c, lid)
    if not otr_held(r, me()) or getattr(g, "auth_via", None) not in ("session", "proxy"):
        raise Denied(404)
    e = stepup_download(c)  # 2.223.2 C (#2871)
    if e is not None:
        return e
    return rx_list_download(r)


def rx_list_download(r):
    """2.186.1 (#2732): the export of the kept project row r (otr_export checked the custodian)."""
    lid = int(r["id"])
    sub = {"key": f"list:{lid}", "kind": "list", "id": lid, "office": None, "ws": None,
           "lists": ("SELECT id FROM lists WHERE id=?", (lid,))}
    name = f"kalmido-retention-project{lid}-{now_utc().strftime('%Y-%m-%d')}.zip"
    resp = Response(stream_with_context(rx_stream(sub, me(), g.user["username"], r["name"], lang())), mimetype="application/zip")
    resp.headers["Content-Disposition"] = f'attachment; filename="{name}"'
    resp.headers["Cache-Control"] = "private, no-store"
    resp.headers["X-Content-Type-Options"] = "nosniff"
    return resp


# ---------------------------------------------------------------- routes (people only, app only)
def _org_sub(c, oid):
    """The organisation subject for an admin of it or an instance admin (who sees only whether records exist); else 404."""
    sub = rx_subject(c, "org", oid)
    if not rx_may_export(c, sub) and not (g.user and g.user["is_admin"] and getattr(g, "auth_via", None) in ("session", "proxy")):
        raise Denied(404)
    return sub


@app.get("/api/retention/me")
def rx_me_get():
    """The own records: {needed, can_export, exported_at, counts, years, note, url}."""
    c = db()
    sub = rx_subject(c, "user", me())
    if not rx_may_export(c, sub):
        raise Denied(403)
    return jsonify(rx_info(c, sub))


@app.get("/api/retention/me/export.zip")
@app.post("/api/retention/me/export.zip")  # 2.223.2 C (#2871): POST = the step-up
def rx_me_zip():
    return _download(rx_subject(db(), "user", me()), g.user["display_name"] or g.user["username"])


@app.get("/api/retention/org/<int:oid>")
def rx_org_get(oid):
    c = db()
    return jsonify(rx_info(c, _org_sub(c, oid)))


@app.get("/api/retention/org/<int:oid>/export.zip")
@app.post("/api/retention/org/<int:oid>/export.zip")  # 2.223.2 C (#2871): POST = the step-up
def rx_org_zip(oid):
    c = db()
    mv_allow(c)  # 2.1337.0 (#6600): a download, also while the organisation is moving (its log line)
    sub = rx_subject(c, "org", oid)
    with system_ctx(c):  # the organisation's name for the index (the right is checked in _download)
        name = (c.execute("SELECT name FROM orgs WHERE id=?", (oid,)).fetchone() or [""])[0]
    return _download(sub, name)


def _rx_declare(sub, title, on):
    """#6474 (A6): the person / an admin of the organisation declares (on) or takes back that the records may be deleted
    without the retention export. Noted with the numbers it was declared for (it ends when more come), in the security log."""
    c = db()
    if not rx_owner(c, sub):
        raise Denied(404 if sub["kind"] == "org" else 403)
    if on:
        counts = rx_counts(c, sub)
        if not counts:
            return jsonify(error=tr("There are no records to keep."), code="nothing"), 409
        rx_log(c, sub, "waiver_declared", {"counts": counts})
    elif rx_waiver_declared(c, sub):
        rx_log(c, sub, "waiver_revoked")
    c.commit()
    if on:
        rx_alert(N_("{0} declared that {1} may be deleted without the retention export."), [g.user["username"], title])
    return jsonify(rx_info(c, sub))


@app.post("/api/retention/me/waiver")
@app.delete("/api/retention/me/waiver")
def rx_me_waiver():
    """#6474 (A6): the own records may go without the export (POST) / the declaration is taken back (DELETE). People only."""
    return _rx_declare(rx_subject(db(), "user", me()), g.user["display_name"] or g.user["username"], request.method == "POST")


@app.post("/api/retention/org/<int:oid>/waiver")
@app.delete("/api/retention/org/<int:oid>/waiver")
def rx_org_waiver(oid):
    """#6474 (A6): the same for an organisation, by one of its admins (everybody else 404, an instance admin too)."""
    c = db()
    mv_allow(c)  # 2.1337.0 (#6600): part of having a moving organisation deleted (#2956)
    sub = rx_subject(c, "org", oid)
    if not rx_owner(c, sub):
        raise Denied(404)
    with system_ctx(c):  # the organisation's name for the security log
        name = (c.execute("SELECT name FROM orgs WHERE id=?", (oid,)).fetchone() or [""])[0]
    return _rx_declare(sub, name, request.method == "POST")


def rx_user_info(c, uid, along=True):
    """For the account delete dialog (useradmin.ua8_delete_info)."""
    return rx_info(c, rx_subject(c, "user", uid), along)
