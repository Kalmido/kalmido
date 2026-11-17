"""2.148.0 A (#2471): the export for a tax auditor (GoBD "Datenträgerüberlassung", Z3 access): one ZIP with the booking data
of a period as CSV tables plus index.xml in the description standard of the GDPdU (read by the auditors' software;
2.188.0 A (#2498): the official DTD gdpdu-01-03-2019.dtd, version 1.6, from gdpdudtd.py lies next to index.xml).
Tables: bookings (the lines of the DATEV batch, input side included), invoices / credit notes,
their positions, payments, receipts, cash book, clients, opening balances, the office log and (2.187.0 B, #2476) the log of
the office rights; 2.414.0 (#3502): the booking archive of past years (its lines in the period and the account labels).

CSV: UTF-8, ';', CRLF, text in double quotes, decimal comma, dates DD.MM.YYYY, no header line (the columns are in
index.xml). Only finalised documents; drafts are no bookings. Admins (and the accounting role) of the office area.
2.356.0 (#3097): no trial invoices (as DATEV and the bookkeeping export); the formula guard of text columns (a leading
' before = + - @, review of #2471) stays and index.xml says so; receipts left out (no date / no amount) are named in
missing.txt and counted in index.xml.

2.1309.0 (#6471, audit #4791 A1): the export is complete. The folder belege/ carries the stored PDF and e-invoice XML of the
invoices and reminders, the files of the receipts and the bills of the entertainment receipts byte for byte; invoices.csv,
dunning.csv, receipts.csv and meal_files.csv name each file and its SHA-256 (of the bytes in the ZIP). A file that cannot be
read, is missing or whose checksum differs from the one noted at storing is named in hinweise.txt (and a differing one logged
as store_mismatch, like the retention export). The further tables come from the retention export's list (admin/retexport.py
rx_tables(), with its where clause) plus a period filter of their own (GX_RX): bank lines, credit card statements and their
lines, the logbook (vehicles, drives, its change log), entertainment receipts and their bills, trips and their items, the asset
register and the bookings of the ledger. log.csv carries the values before and after (decrypted). Entries in the trash and
rows of an import taken back stay in, marked in the column Kennzeichen, instead of being left out.
#6467 (4): chain_check.csv = the result of the hash chain check (office/chain.py hch_check) at the time of the export,
chain_heads.csv = the head (last link) of each chain -- both over every chain of the office, whatever the period.
The module moved from office/ to admin/ with this: it reads the export lists of admin (tools/check_layers.py: no upward import)."""
import csv
import hashlib
import json
import os
import re
import tempfile
import time
import zipfile
from datetime import date, datetime, timedelta
from decimal import Decimal
from xml.sax.saxutils import escape

from flask import request

from ..core.access import trash_sql
from ..core.config import app
from ..core.i18n import tr
from ..core.db import db, local_day, local_now
from ..core.orgcrypt import oc_dec, oc_dec_fields, oc_read_file
from ..core.pg import qi, table_names
from ..collab.comments import user_names
from ..docs.store import doc_opener
from ..files.store import fs_read, fs_roles_many
from ..files.scan import sc_guard  # 2.1309.0 (#6471): a locked bill stays out
from ..personal.timetrack import BadInput
from ..office.books import bk_gaps_text, bk_receipts, bk_ws
from ..office.calc import dec, money
from ..office.chain import hch_check, hch_heads  # 2.1309.0 (#6467 (4))
from ..office.model import office_gate, office_org, office_settings, pb_cl_sql
from ..office.ledger import ofx_company, ofx_log
from ..office.gdpdudtd import GX_DTD, GX_DTD_NAME
from ..office.meals import bw_path
from ..office.pdfweb import _stored, epdf_name
from ..office.rights import ofr_log_rows
from ..office.datev import dx_rows  # 2.369.5 (#2517): pulled up from functions
from ..office.docs import odoc_imported  # 2.1289.0 (#6481 U4)
from ..files.bulk import abm_drop, abm_send_zip, abm_slot  # 2.674.0 (#4190): temporary files + the shared place of the large exports
from .orgexport import OX_AREAS, OX_GONE_WITH, OX_SECRET_COLS, _rows, _safe_part  # 2.1309.0 (#6471)
from .retexport import RX_DROP, RX_WHERE, rx_tables  # 2.1309.0 (#6471): the tables of the retention export (one list)

GX_MAX_DAYS = 11 * 366  # one call covers at most eleven years (ten years of keeping + the current one)
GX_RIGHTS_MAX = 100000  # 2.187.0 B (#2476): the rows of the rights log read for the export (changes of rights are rare)

A, N, D = "a", "n", "d"  # column types: alphanumeric, numeric (2 places), date; 2.1309.0 (#6471): "n<k>" = numeric with k places

# 2.1309.0 (#6471): the tables of the retention export (admin/retexport.py rx_tables: their rows and their where clause) that go
# into the auditor's export, each with its period: (table, file, name, description, period | None = every row). In the period
# :f / :t = the first / last day, :n = the day after, :y0 / :y1 = the years, :m0 / :m1 = the months (YYYY-MM).
GX_RX = (
    ("office_bank_tx", "bank_tx.csv", "Bankumsaetze", "Umsaetze der eingelesenen Kontoauszuege nach Buchungstag", "day>=:f AND day<=:t"),
    ("office_cc_statements", "card_statements.csv", "Kreditkartenabrechnungen", "Monatsabrechnungen der Kreditkarten",
     "month>=:m0 AND month<=:m1"),
    ("office_cc_lines", "card_lines.csv", "Kreditkartenzeilen", "Positionen der Kreditkartenabrechnungen nach Umsatztag",
     "day>=:f AND day<=:t"),
    ("office_vehicles", "vehicles.csv", "Fahrzeuge", "Fahrzeuge des Fahrtenbuchs (alle)", None),
    ("office_drives", "logbook.csv", "Fahrtenbuch", "Fahrten nach Tag", "day>=:f AND day<=:t"),
    ("office_drive_log", "logbook_log.csv", "Fahrtenbuch_Protokoll", "Aenderungen der Fahrten mit dem Wert davor", "at>=:f AND at<:n"),
    ("office_meals", "meals.csv", "Bewirtung", "Bewirtungsbelege nach Tag", "date>=:f AND date<=:t"),
    ("office_meal_files", "meal_files.csv", "Bewirtung_Dateien", "Rechnungen der Bewirtungen des Zeitraums (Dateien unter belege/bewirtung/)",
     "meal_id IN (SELECT id FROM office_meals WHERE date>=:f AND date<=:t)"),
    ("office_trips", "trips.csv", "Reisen", "Dienstreisen, die in den Zeitraum fallen", "date_to>=:f AND date_from<=:t"),
    ("office_trip_items", "trip_items.csv", "Reisebelege", "Kosten und Pauschalen der Dienstreisen des Zeitraums",
     "trip_id IN (SELECT id FROM office_trips WHERE date_to>=:f AND date_from<=:t)"),
    ("office_equipment", "assets.csv", "Anlagenverzeichnis",
     "Geraete mit Kaufdatum bis zum Ende des Zeitraums (Anschaffung, Nutzungsdauer, AfA-Art)", "purchase_date<>'' AND purchase_date<=:t"),
    ("office_ledger_entries", "ledger_entries.csv", "Hauptbuch_Buchungen", "Umbuchungen, Eroeffnungs- und Abschlussbuchungen des Hauptbuchs",
     "(day<>'' AND day>=:f AND day<=:t) OR (day='' AND year>=:y0 AND year<=:y1)"),
)
GX_MONEY = frozenset(("amount", "amount_home", "total", "tip", "orig_amount", "purchase_net", "new_value", "current_value"))  # text columns of money
GX_DAYS = frozenset(("day", "date", "date_from", "date_to", "purchase_date", "booked"))  # text columns of a day (YYYY-MM-DD)
GX_UNDONE = {"import_id": "office_bank_imports", "import_run_id": "office_import_runs"}  # a row of an import taken back
GX_NOT = frozenset(("legacy_aad", "cost_enc"))  # never a column of the export (orgexport._clean drops them as well)
TRASH, UNDONE = "Papierkorb", "zurueckgenommen"  # 2.1309.0 (#6471): the values of the column Kennzeichen


def _d(s):
    s = (s or "")[:10]
    return f"{s[8:10]}.{s[5:7]}.{s[:4]}" if len(s) == 10 and s[4] == "-" else ""


def _n(v, k=2):
    if v in (None, ""):
        return ""
    if k == 2:
        return f"{money(dec(v, '0')):.2f}".replace(".", ",")
    return f"{dec(v, '0').quantize(Decimal(1).scaleb(-k)):.{k}f}".replace(".", ",")  # 2.1309.0 (#6471): a rate with more places


def _acc(ct):
    """2.1309.0 (#6471): the places of numeric column type ct ("n" = 2, "n4" = 4)."""
    return int(ct[1:]) if len(ct) > 1 else 2


def _j(v):
    try:
        x = json.loads(v or "{}")
        return x if isinstance(x, dict) else {}
    except (TypeError, ValueError):
        return {}


class _Tbl:
    """2.674.0 (#4190): file = an open text file the CSV lines are written to (gx_zip: a temporary file, never one big string);
    None = only counted (?check=1: nothing is formatted or kept)."""
    def __init__(self, url, name, desc, cols, key=1, file=None):
        self.url, self.name, self.desc, self.cols, self.key = url, name, desc, cols, key
        self.buf = file
        self.w = csv.writer(file, delimiter=";", quotechar='"', quoting=csv.QUOTE_MINIMAL, lineterminator="\r\n") if file else None
        self.n = 0

    def add(self, *vals):
        if self.w is None:  # 2.674.0 (#4190): the check only counts
            self.n += 1
            return
        out = []
        for (cn, ct), v in zip(self.cols, vals):
            if ct[0] == N:
                out.append(_n(v, _acc(ct)))
            elif ct == D:
                out.append(_d(v))
            else:
                v = str(v if v is not None else "").replace("\r", " ").replace("\n", " ").replace("\t", " ")
                out.append("'" + v if v[:1] in ("=", "+", "-", "@") else v)  # no formula when a spreadsheet opens it (named in index.xml)
        self.w.writerow(out)
        self.n += 1

    def xml(self, frm, to):
        cols = []
        for i, (cn, ct) in enumerate(self.cols):
            tag = "VariablePrimaryKey" if i < self.key else "VariableColumn"
            typ = (f"<Numeric><Accuracy>{_acc(ct)}</Accuracy></Numeric>" if ct[0] == N else
                   "<Date><Format>DD.MM.YYYY</Format></Date>" if ct == D else "<AlphaNumeric/>")
            cols.append(f"        <{tag}><Name>{escape(cn)}</Name>{typ}</{tag}>")
        return ("    <Table>\n"
                f"      <URL>{escape(self.url)}</URL>\n      <Name>{escape(self.name)}</Name>\n"
                f"      <Description>{escape(self.desc)}</Description>\n"
                f"      <Validity><Range><From>{_d(frm)}</From><To>{_d(to)}</To></Range><Format>DD.MM.YYYY</Format></Validity>\n"
                "      <UTF8/>\n      <DecimalSymbol>,</DecimalSymbol>\n      <DigitGroupingSymbol>.</DigitGroupingSymbol>\n"
                "      <VariableLength>\n        <ColumnDelimiter>;</ColumnDelimiter>\n        <RecordDelimiter>&#13;&#10;</RecordDelimiter>\n"
                "        <TextEncapsulator>\"</TextEncapsulator>\n" + "\n".join(cols) + "\n      </VariableLength>\n    </Table>\n")


class _Files:
    """2.1309.0 (#6471): the folder belege/ of the ZIP being written (z): put(name, bytes) -> (name in the ZIP, SHA-256);
    notes = the lines of hinweise.txt (files missing, unreadable or with a differing checksum)."""
    def __init__(self, z):
        self.z, self.names, self.notes, self.n = z, set(), [], 0

    def put(self, name, data):
        base, k = name, 1
        while name in self.names:  # two files of the same name: number them
            k += 1
            stem, dot, ext = base.rpartition(".")
            name = f"{stem}-{k}.{ext}" if dot and "/" not in ext else f"{base}-{k}"
        self.names.add(name)
        zi = zipfile.ZipInfo(name, date_time=time.localtime()[:6])
        zi.compress_type = zipfile.ZIP_DEFLATED
        with self.z.open(zi, "w", force_zip64=True) as w:
            w.write(data)
        self.n += 1
        return name, hashlib.sha256(data).hexdigest()


def _flag(r, *gone):
    """2.1309.0 (#6471): Kennzeichen of a row: in the trash (its own deleted_at or a marker in gone) or taken back."""
    if r.get("deleted_at"):
        return TRASH
    return next((f for f in gone if f), "")


def _doc_files(c, oid, r, fl, folder):
    """2.1309.0 (#6471): the stored PDF / e-invoice XML of finalised document r into belege/<folder>/ ->
    [pdf name, pdf SHA-256, xml name, xml SHA-256] ('' when there is none or in the check)."""
    if fl is None:
        return ["", "", "", ""]
    out = []
    label = r["number"] or f"ID {r['id']}"
    stem = f"belege/{folder}/{int(r['id'])}-{_safe_part(epdf_name(r), 100)}"
    for ext in ("pdf", "xml"):
        want = (r[ext + "_sha256"] if (ext + "_sha256") in r.keys() else "") or ""
        p = _stored(oid, r, ext)
        if not p:
            if ext == "pdf" or want:  # an XML only when the document had one
                fl.notes.append(f"{label}: keine gespeicherte {ext.upper()}-Datei" + (" (Pruefsumme notiert, Datei fehlt)" if want else ""))
            out += ["", ""]
            continue
        try:
            data = oc_read_file(c, p)
        except Exception as e:  # noqa: BLE001 -- one unreadable file must not stop the export: named in hinweise.txt
            print("gobd export: document", r["id"], "not readable:", type(e).__name__, flush=True)
            fl.notes.append(f"{label}: {ext.upper()}-Datei nicht lesbar")
            out += ["", ""]
            continue
        name, sha = fl.put(f"{stem}.{ext}", data)
        if want and want != sha:  # the bytes as they are (the export hides nothing), named and logged (retexport._checked)
            fl.notes.append(f"{name}: Pruefsumme weicht von der beim Festschreiben notierten ab ({want})")
            ofx_log(c, oid, "store_mismatch", doc_id=r["id"], detail={"file": ext, "sha256": want, "found": sha, "at": "gobd export"})
        out += [name, sha]
    return out


def _fs_file(c, nid, name, fl):
    """2.1309.0 (#6471): the file of receipt node nid into belege/eingang/ -> [name in the ZIP, SHA-256]."""
    if fl is None:
        return ["", ""]
    try:
        data = fs_read(c, nid)  # a version the virus scanner locked raises (named, not exported)
    except Exception as e:  # noqa: BLE001 -- named in hinweise.txt
        print("gobd export: receipt", nid, "not readable:", type(e).__name__, flush=True)
        fl.notes.append(f"Beleg {nid} ({name}): Datei nicht lesbar oder gesperrt")
        return ["", ""]
    return list(fl.put(f"belege/eingang/{int(nid)}-{_safe_part(name or 'beleg', 100)}", data))


def _meal_file(c, oid, r, fl):
    """2.1309.0 (#6471): the bill of an entertainment receipt (office_meal_files row r) into belege/bewirtung/."""
    if fl is None:
        return ["", ""]
    try:
        sc_guard(c, "omf", r["id"])  # 2.1309.0 (#6471): a bill the virus scanner locked is named, not exported (like fs_read)
        data = oc_read_file(c, bw_path(oid, r.get("file")))
    except Exception as e:  # noqa: BLE001 -- named in hinweise.txt
        print("gobd export: meal file", r.get("id"), "not readable:", type(e).__name__, flush=True)
        fl.notes.append(f"Bewirtung {r.get('meal_id')}: Datei {r.get('name') or ''} nicht lesbar")
        return ["", ""]
    name, sha = fl.put(f"belege/bewirtung/{int(r['id'])}-{_safe_part(r.get('name') or 'datei', 100)}", data)
    if r.get("sha256") and r["sha256"] != sha:
        fl.notes.append(f"{name}: Pruefsumme weicht von der beim Speichern notierten ab ({r['sha256']})")
    return [name, sha]


def gx_rx_where(table):
    """2.1309.0 (#6471): the where clause of table in the retention export (rx_tables: the core's own, RX_WHERE, else the
    organisation export's OX_AREAS; every "?" is the office id). LookupError for a table that is not in it."""
    for _a, t, own in rx_tables():
        if t == table:
            w = own or RX_WHERE.get(table) or next((w for _n, tt, w in OX_AREAS if tt == table), None)
            if w:
                return w
    raise LookupError(f"gobd export: {table} is no table of the retention export (admin/retexport.py RX_TABLES)")


def _period(sql, frm, to):
    """2.1309.0 (#6471): the period of GX_RX with "?" -> (sql, args)."""
    v = {"f": frm, "t": to, "n": _next_day(to), "y0": int(frm[:4]), "y1": int(to[:4]), "m0": frm[:7], "m1": to[:7]}
    args = []

    def rep(m):
        args.append(v[m.group(1)])
        return "?"
    return re.sub(r":(y0|y1|m0|m1|f|t|n)\b", rep, sql), args


def _ctype(name, dt, scale):
    if dt == "numeric":
        return N if scale in (None, 2) else f"{N}{int(scale)}"
    if dt == "date":
        return D
    if dt == "text" and name in GX_MONEY:
        return N
    if dt == "text" and name in GX_DAYS:
        return D
    return A


def _cell(v):
    if isinstance(v, bool):
        return 1 if v else 0
    if isinstance(v, (dict, list)):
        return json.dumps(v, ensure_ascii=False, sort_keys=True, default=str)
    if isinstance(v, (datetime, date)):
        return v.isoformat()
    return v


def _gone(c, oid, table, names):
    """2.1309.0 (#6471): [(column, {ids}, Kennzeichen)] -- the parents in the trash (orgexport.OX_GONE_WITH) and the imports
    taken back (GX_UNDONE) a row of table hangs on."""
    out, tn = [], table_names(c)
    for parent, col in OX_GONE_WITH.get(table, ()):
        if col in names:
            out.append((col, {x[0] for x in c.execute(f"SELECT id FROM {qi(parent, tn)} WHERE org_id=? AND {trash_sql()}", (oid,))}, TRASH))
    for col, parent in GX_UNDONE.items():
        if col in names:
            out.append((col, {x[0] for x in c.execute(f"SELECT id FROM {qi(parent, tn)} WHERE org_id=? AND undone_at IS NOT NULL", (oid,))}, UNDONE))
    return out


def _gx_rx(c, oid, frm, to, T, fl):
    """2.1309.0 (#6471): the tables of GX_RX: every column of the table as the retention export decrypts it (secrets and
    RX_DROP left out), + Kennzeichen (+ the exported file of a bill)."""
    out = []
    for table, url, name, desc, per in GX_RX:
        base = gx_rx_where(table)
        meta = [(r[0], r[1], r[2]) for r in c.execute(
            "SELECT column_name, data_type, numeric_scale FROM information_schema.columns WHERE table_schema=current_schema() "
            "AND table_name=? ORDER BY ordinal_position", (table,))]
        names = {m[0] for m in meta}
        drop = OX_SECRET_COLS | GX_NOT | set(RX_DROP.get(table, ()))
        cols = [(m[0], _ctype(*m)) for m in meta if m[0] not in drop]
        withfile = table == "office_meal_files"
        t = T(url, name, desc, cols + [("Kennzeichen", A)] + ([("Dateiname", A), ("SHA-256", A)] if withfile else []))
        out.append(t)
        if not meta:
            continue
        where, args = base, [oid] * base.count("?")
        if per:
            p, pa = _period(per, frm, to)
            where, args = f"({where}) AND ({p})", args + pa
        if "wkx_held_at" in names:  # files held at a lock stay out (orgexport.ox_live)
            where = f"({where}) AND wkx_held_at IS NULL"
        if t.w is None:  # the check counts only
            t.n = c.execute(f"SELECT COUNT(*) FROM {qi(table, table_names(c))} WHERE {where}", tuple(args)).fetchone()[0]
            continue
        gone = _gone(c, oid, table, names)
        for r in _rows(c, oid, table, where, args):
            vals = [_cell(r.get(k)) for k, _t in cols] + [_flag(r, *(f for col, ids, f in gone if r.get(col) in ids))]
            if withfile:
                vals += _meal_file(c, oid, r, fl)
            t.add(*vals)
    return out


def _log_detail(c, oid, v):
    """2.1309.0 (#6471): (before, after, the rest) of an office log entry's detail, decrypted, as JSON texts."""
    try:
        txt = oc_dec(c, oid, "office_doc_log.detail", v) if isinstance(v, str) else v
    except Exception:  # noqa: BLE001 -- an entry that cannot be decrypted (an old key) stays in, marked
        return "", "", "(nicht entschluesselbar)"
    j = txt
    if isinstance(txt, str):
        try:
            j = json.loads(txt) if txt else {}
        except ValueError:
            return "", "", txt
    if not isinstance(j, dict):
        return "", "", json.dumps(j, ensure_ascii=False, default=str)
    j = dict(j)
    b, a = j.pop("before", None), j.pop("after", None)

    def dump(x):
        return json.dumps(x, ensure_ascii=False, sort_keys=True, default=str)
    return (dump(b) if b is not None else ""), (dump(a) if a is not None else ""), (dump(j) if j else "")


def _receipts(c, oid, frm, to, gaps, T, fl):
    """receipts.csv: the receipts of the period (books.bk_receipts, by document date) + 2.1309.0 (#6471) those of the period
    in the trash (marked), each with its file in belege/eingang/ and its SHA-256."""
    t = T("receipts.csv", "Belege", "Eingangsbelege (Belegfach) nach Belegdatum",
          [("Beleg_ID", A), ("Belegdatum", D), ("Bezahlt_am", D), ("Geprueft_am", D), ("Geprueft_von", A), ("Brutto", N), ("USt_Satz", A),
           ("Netto", N), ("USt", N), ("Kategorie", A), ("Datei", A), ("Kennzeichen", A), ("Dateiname", A), ("SHA-256", A)])
    rcs = bk_receipts(c, oid, frm, to, uid=0, by="doc", gaps=gaps)
    live = {r["node_id"] for r in rcs}
    ws = bk_ws(c, oid)
    day = "COALESCE(NULLIF(d.doc_date, ''), NULLIF(CAST(r.paid_at AS text), ''))"  # as bk_receipts by="doc"
    cand = [r for r in c.execute(
        f"SELECT r.node_id, r.vat_pct, r.paid_at, r.checked_at, r.checked_by, r.category, d.doc_date, d.amount, n.name, n.deleted_at, "
        f"{day} AS day FROM rc_receipts r JOIN doc_meta d ON d.node_id=r.node_id JOIN fs_nodes n ON n.id=r.node_id "
        f"WHERE d.ws=? AND n.kind='file' AND {day}>=? AND {day}<=? ORDER BY {day}, r.node_id", (ws, frm, to)).fetchall()
        if r["node_id"] not in live]
    acc = fs_roles_many(c, [r["node_id"] for r in cand], 0) if cand else {}
    gone = [r for r in cand if r["deleted_at"] or acc.get(r["node_id"], (False,))[0]]  # in the trash (itself or a folder above it)
    who = user_names(c, [r["checked_by"] for r in rcs] + [r["checked_by"] for r in gone])  # 2.420.0 C (#3448): + the person's tick "checked" (day, name)
    for r in rcs:
        t.add(r["node_id"], r["doc_date"] or r["date"], r["paid_at"] or "", str(local_day(r["checked_at"]) or ""), who.get(r["checked_by"], ""),
              r["amount"], r["vat_pct"] or "", r["net"], r["vat"], r["category"], r["title"], "", *_fs_file(c, r["node_id"], r["title"], fl))
    opener = doc_opener(c, ws, "doc_meta.amount") if gone and t.w is not None else None
    for r in gone:
        if t.w is None:
            t.add()
            continue
        raw = opener(r["amount"]) or ""
        t.add(r["node_id"], r["day"], r["paid_at"] or "", str(local_day(r["checked_at"]) or "") if r["checked_at"] else "",
              who.get(r["checked_by"], "") if r["checked_at"] else "", raw, r["vat_pct"] or "", "", "", r["category"] or "", r["name"] or "",
              TRASH, *_fs_file(c, r["node_id"], r["name"], fl))
    return t


def _dunning(c, oid, frm, to, T, fl):
    """2.1309.0 (#6471): dunning.csv: the finalised reminders of the period with their stored PDF."""
    t = T("dunning.csv", "Mahnungen", "Festgeschriebene Mahnungen mit den gemahnten Rechnungen",
          [("ID", A), ("Nummer", A), ("Datum", D), ("Kunde", A), ("Kundennummer", A), ("Stufe", A), ("Rechnungen", A), ("Gebuehr", N),
           ("Brutto", N), ("Waehrung", A), ("Status", A), ("Festgeschrieben", D), ("Kennzeichen", A), ("PDF_Dateiname", A), ("PDF_SHA-256", A)])
    rows = c.execute("SELECT d.*, cl.name AS cl_name, cl.customer_no AS cl_no FROM office_docs d LEFT JOIN clients cl ON cl.id=d.client_id "
                     "WHERE d.org_id=? AND d.kind='reminder' AND d.locked_at IS NOT NULL AND d.date>=? AND d.date<=? AND d.trial=0 "
                     "ORDER BY d.date, d.number", (oid, frm, to)).fetchall()
    if t.w is None:
        t.n = len(rows)
        return t

    def ids(r):
        try:
            x = json.loads(r["ref_doc_ids"] or "[]")
        except (TypeError, ValueError):
            return []
        return [int(i) for i in x if str(i).isdigit()] if isinstance(x, list) else []
    want = sorted({i for r in rows for i in ids(r)})
    nos = {}
    for k in range(0, len(want), 500):
        part = want[k:k + 500]
        nos.update({x[0]: x[1] for x in c.execute(f"SELECT id, number FROM office_docs WHERE org_id=? AND id IN ({','.join('?' * len(part))})",
                                                  (oid, *part))})
    for r in rows:
        f = _doc_files(c, oid, r, fl, "mahnungen")
        t.add(r["id"], r["number"], r["date"], r["cl_name"] or "", r["cl_no"] or "", r["reminder_level"] or "",
              ", ".join(nos.get(i) or f"ID {i}" for i in ids(r)), r["reminder_fee"], _j(r["totals"]).get("gross"), r["currency"], r["status"],
              r["locked_at"], _flag(dict(r)), f[0], f[1])
    return t


def _chain(c, oid, T):
    """2.1309.0 (#6467 (4)): chain_check.csv (one line: office/chain.py hch_check now) and chain_heads.csv (per chain its last link)."""
    t = T("chain_check.csv", "Kettenpruefung",
          "Pruefung der Hash-Kette der festgeschriebenen Dokumente beim Export (alle Nummernkreise, unabhaengig vom Zeitraum)",
          [("Geprueft_am", A), ("Ergebnis", A), ("Glieder", A), ("Ausstehend", A), ("Erster_Fehler_ID", A), ("Erster_Fehler_Nummer", A),
           ("Erster_Fehler_Reihe", A), ("Erster_Fehler_Position", A), ("Grund", A)])
    if t.w is None:
        t.add()
    else:
        h = hch_check(c, oid)
        fb = h.get("first_bad") or {}
        t.add(local_now().isoformat(timespec="seconds"), "intakt" if h["ok"] else "gebrochen", h["count"], h["pending"], fb.get("id", ""),
              fb.get("number", ""), fb.get("chain", ""), fb.get("seq", ""), fb.get("reason", ""))
    h = T("chain_heads.csv", "Kettenkoepfe", "Letztes Glied je Hash-Kette (Nummernkreis) beim Export, unabhaengig vom Zeitraum",
          [("Reihe", A), ("Glieder", A), ("Dokument_ID", A), ("Nummer", A), ("Datum", D), ("Hash", A), ("Kanon_Version", A)])
    for r in hch_heads(c, oid):  # office/chain.py (#6467)
        h.add(r["chain"], r["seq"], r["id"], r["number"], r["date"], r["hash"], r["ver"])
    return [t, h]


def gx_tables(c, oid, frm, to, gaps=None, files=False, fl=None):
    """The tables of the export for [frm, to] (ISO days). gaps: see books.bk_receipts (2.356.0, #3097).
    2.674.0 (#4190): files=True writes every table into its own temporary file (the caller closes them, gx_close); without,
    the rows are only counted. 2.1309.0 (#6471): fl = the folder belege/ of the ZIP (_Files) the stored files go to."""
    s = office_settings(c, oid)
    out = []

    def _T(*a):
        return _Tbl(*a, file=tempfile.TemporaryFile("w+", encoding="utf-8", newline="") if files else None)

    t = _T("bookings.csv", "Buchungen", "Buchungszeilen wie im DATEV-Buchungsstapel (Ausgang, Zahlungen, Eingang)",
             [("Zeile", A), ("Belegdatum", D), ("Belegnummer", A), ("Buchungstext", A), ("Umsatz", N), ("Soll/Haben", A),
              ("Konto", A), ("Gegenkonto", A), ("BU-Schluessel", A), ("Waehrung", A)])
    out.append(t)
    hints = []
    for i, r in enumerate(dx_rows(c, oid, frm, to, s=s, inside=True, hints_out=hints), 1):
        t.add(i, r.get("_date") or "", r.get("Belegfeld 1", ""), r.get("Buchungstext", ""),
              (r.get("Umsatz (ohne Soll/Haben-Kz)") or "").replace(",", "."), r.get("Soll/Haben-Kennzeichen", ""), r.get("Konto", ""),
              r.get("Gegenkonto (ohne BU-Schlüssel)", ""), r.get("BU-Schlüssel", ""), r.get("WKZ Umsatz", ""))

    # 2.1309.0 (#6471): the documents in the trash stay in, marked (Kennzeichen), with the stored PDF / XML and their SHA-256
    docs = c.execute("SELECT d.*, cl.name AS cl_name, cl.customer_no AS cl_no FROM office_docs d LEFT JOIN clients cl ON cl.id=d.client_id "
                     "WHERE d.org_id=? AND d.kind IN ('invoice','credit') AND d.locked_at IS NOT NULL AND d.date>=? AND d.date<=? "
                     "AND d.trial=0 ORDER BY d.date, d.number", (oid, frm, to)).fetchall()
    t = _T("invoices.csv", "Rechnungen", "Festgeschriebene Rechnungen und Rechnungskorrekturen (Dateien unter belege/rechnungen/)",
             [("ID", A), ("Art", A), ("Nummer", A), ("Datum", D), ("Kunde", A), ("Kundennummer", A), ("Netto", N), ("Steuer", N),
              ("Brutto", N), ("Waehrung", A), ("Status", A), ("Festgeschrieben", D), ("Storno_von", A),
              ("Importiert_am", D), ("Importiert_von", A),  # 2.1289.0 (#6481 U4): taken from a file by the organisation import
              ("Kennzeichen", A), ("PDF_Dateiname", A), ("PDF_SHA-256", A), ("XML_Dateiname", A), ("XML_SHA-256", A)])
    out.append(t)
    imp = odoc_imported(c, oid, None) if docs and files else {}
    gone_docs = set()
    for r in docs:
        if r["deleted_at"]:
            gone_docs.add(r["id"])
        if t.w is None:
            t.add()
            continue
        tt = _j(r["totals"])
        im = imp.get(r["id"]) or {}
        t.add(r["id"], r["kind"], r["number"], r["date"], r["cl_name"] or "", r["cl_no"] or "", tt.get("net"), tt.get("tax_total"),
              tt.get("gross"), r["currency"], r["status"], r["locked_at"], r["cancels_id"] or "", im.get("at") or "", im.get("by") or "",
              _flag(dict(r)), *_doc_files(c, oid, r, fl, "rechnungen"))

    t = _T("positions.csv", "Positionen", "Positionen der Rechnungen und Rechnungskorrekturen",
             [("ID", A), ("Rechnung_ID", A), ("Bezeichnung", A), ("Menge", N), ("Einheit", A), ("Einzelpreis", N), ("Steuersatz", N),
              ("Netto", N), ("Steuer", N), ("Kennzeichen", A)])
    out.append(t)
    ids = [r["id"] for r in docs]
    for k in range(0, len(ids), 500):
        part = ids[k:k + 500]
        q = ",".join("?" * len(part))
        if t.w is None:
            t.n += c.execute(f"SELECT COUNT(*) FROM office_doc_items WHERE doc_id IN ({q})", part).fetchone()[0]
            continue
        for it in c.execute(f"SELECT * FROM office_doc_items WHERE doc_id IN ({q}) ORDER BY doc_id, sort, id", part).fetchall():
            it = oc_dec_fields(c, oid, "office_doc_items", it)
            t.add(it["id"], it["doc_id"], it["title"], it["qty"], it["unit"], it["rate"], it.get("tax_pct"), it.get("net"), it.get("tax_amount"),
                  _flag(it, TRASH if it["doc_id"] in gone_docs else ""))  # 2.1309.0 (#6471): the trash marked, not left out

    t = _T("payments.csv", "Zahlungen", "Zahlungseingaenge auf Rechnungen",
             [("ID", A), ("Rechnung_ID", A), ("Rechnungsnummer", A), ("Datum", D), ("Betrag", N), ("Zahlart", A), ("Kennzeichen", A)])
    out.append(t)
    for r in c.execute("SELECT p.*, d.number, d.deleted_at AS doc_deleted FROM office_payments p JOIN office_docs d ON d.id=p.doc_id "
                       "WHERE p.org_id=? AND p.date>=? AND p.date<=? AND d.trial=0 ORDER BY p.date, p.id", (oid, frm, to)).fetchall():
        t.add(r["id"], r["doc_id"], r["number"], r["date"], r["amount"], r["method"], TRASH if r["doc_deleted"] else "")

    out.append(_dunning(c, oid, frm, to, _T, fl))  # 2.1309.0 (#6471)
    out.append(_receipts(c, oid, frm, to, gaps, _T, fl))

    t = _T("cashbook.csv", "Kassenbuch", "Kassenbuchungen aller Kassen",
             [("ID", A), ("Kasse", A), ("Nr", A), ("Datum", D), ("Richtung", A), ("Betrag", N), ("USt_Satz", A), ("Text", A),
              ("Kategorie", A), ("Storno_von", A)])
    out.append(t)
    for r in c.execute("SELECT e.*, b.name AS book FROM office_cash_entries e JOIN office_cashbooks b ON b.id=e.book_id WHERE e.org_id=? "
                       "AND e.day>=? AND e.day<=? ORDER BY e.book_id, e.no", (oid, frm, to)).fetchall():
        e = oc_dec_fields(c, oid, "office_cash_entries", r)
        t.add(e["id"], e["book"], e["no"], e["day"], e["dir"], e["amount"], e["vat_pct"] or "", e["text"], e["category"], e["storno_of"] or "")

    t = _T("clients.csv", "Kunden", "Kunden des Bueros", [("ID", A), ("Kundennummer", A), ("Name", A), ("Anschrift", A), ("USt_IdNr", A)])
    out.append(t)
    for r in c.execute(f"SELECT * FROM clients WHERE {pb_cl_sql(c, oid)} ORDER BY id").fetchall():  # a personal office: its owner's
        r = oc_dec_fields(c, oid, "clients", r)
        t.add(r["id"], r.get("customer_no") or "", r["name"], r.get("address") or "", r.get("vat_id") or "")

    t = _T("opening_balances.csv", "Eroeffnungsbestaende", "Eroeffnungsbestaende aus dem DATEV-Import",
             [("ID", A), ("Jahr", A), ("Konto", A), ("Bezeichnung", A), ("Betrag", N), ("Soll/Haben", A)])
    out.append(t)
    for r in c.execute("SELECT * FROM office_opening_balances WHERE org_id=? AND year>=? AND year<=? ORDER BY year, account, id",
                       (oid, int(frm[:4]), int(to[:4]))).fetchall():
        t.add(r["id"], r["year"], r["account"], r["label"], r["amount"], r["side"])

    # 2.414.0 (#3502): the booking archive of past years (office/bookarch.py) -- its lines of the period unchanged, only when there are any
    # (review F7: a line without a readable date comes with its fiscal year when the period covers that whole year);
    # 2.1309.0 (#6471): the lines of an import taken back stay in, marked
    arch = c.execute("SELECT b.*, r.undone_at AS run_undone FROM office_bookarch b JOIN office_import_runs r ON r.id=b.run_id WHERE b.org_id=? "
                     "AND ((b.day>=? AND b.day<=?) OR (b.day='' AND b.year>=? AND b.year<=?)) ORDER BY b.year, b.day, b.run_id, b.line, b.id",
                     (oid, frm, to, int(frm[:4]) + (frm[5:] != "01-01"), int(to[:4]) - (to[5:] != "12-31"))).fetchall()
    if arch:
        t = _T("archive_bookings.csv", "Buchungsarchiv", "Buchungen der Altjahre aus dem DATEV-Buchungsstapel (Buchungsarchiv, unveraendert)",
                 [("ID", A), ("Wirtschaftsjahr", A), ("Zeile", A), ("Belegdatum", D), ("Konto", A), ("Gegenkonto", A), ("Soll/Haben", A),
                  ("Umsatz", N), ("Waehrung", A), ("BU-Schluessel", A), ("Belegfeld1", A), ("Belegfeld2", A), ("Buchungstext", A),
                  ("Beleglink", A), ("Kennzeichen", A)])
        out.append(t)
        for r in arch:
            u = UNDONE if r["run_undone"] else ""
            r = oc_dec_fields(c, oid, "office_bookarch", r)
            t.add(r["id"], r["year"], r["line"], r["day"], r["account"], r["counter"], r["side"], r["amount"], r["currency"], r["bu"],
                  r["doc1"], r["doc2"], r["text"], r["link"], u)
        t = _T("archive_accounts.csv", "Kontenbeschriftungen", "Beschriftungen der Konten des Buchungsarchivs (Sachkonten, Personenkonten)",
                 [("ID", A), ("Konto", A), ("Wirtschaftsjahr", A), ("Beschriftung", A), ("Art", A), ("Kennzeichen", A)])
        out.append(t)
        years = sorted({r["year"] for r in arch})
        for r in c.execute("SELECT a.*, r.undone_at AS run_undone FROM office_bookarch_accts a JOIN office_import_runs r ON r.id=a.run_id "
                           "WHERE a.org_id=? AND (a.year IS NULL OR (a.year>=? AND a.year<=?)) ORDER BY a.account, a.year, a.id",
                           (oid, years[0], years[-1])).fetchall():
            u = UNDONE if r["run_undone"] else ""
            r = oc_dec_fields(c, oid, "office_bookarch_accts", r)
            t.add(r["id"], r["account"], r["year"] or "", r["label"], "Personenkonto" if r["kind"] == "person" else "Sachkonto", u)

    out += _gx_rx(c, oid, frm, to, _T, fl)  # 2.1309.0 (#6471): bank, cards, logbook, entertainment, trips, assets, ledger

    # 2.1309.0 (#6471): with the values before and after (the procedure documentation promises them), decrypted
    t = _T("log.csv", "Protokoll", "Aenderungsprotokoll des Bueros (GoBD) mit den Werten davor und danach",
             [("ID", A), ("Zeitpunkt", A), ("Person", A), ("Aktion", A), ("Ziel", A), ("Dokument_ID", A), ("Vorher", A), ("Nachher", A),
              ("Detail", A)])
    out.append(t)
    for r in c.execute("SELECT l.id, l.at, l.action, l.target, l.doc_id, l.detail, l.user_name, u.display_name, u.username FROM office_doc_log l "
                       "LEFT JOIN users u ON u.id=l.user_id WHERE l.org_id=? AND l.at>=? AND l.at<? ORDER BY l.id",
                       (oid, frm, _next_day(to))).fetchall():
        if t.w is None:
            t.add()
            continue
        # 2.1287.0 (#6470): a deleted account's name as the entry kept it
        who = r["display_name"] or r["username"] or oc_dec(c, oid, "office_doc_log.user_name", r["user_name"]) or ""
        t.add(r["id"], r["at"], who, r["action"], r["target"], r["doc_id"] or "", *_log_detail(c, oid, r["detail"]))

    # 2.187.0 B (#2476): every change of the office rights (groups, memberships) with the state before and after
    t = _T("rights_log.csv", "Rechteprotokoll", "Aenderungen der Buero-Zugriffsrechte (Gruppen und Zuordnungen), vorher und nachher",
             [("ID", A), ("Zeitpunkt", A), ("Geaendert_von", A), ("Betroffene_Person", A), ("Gruppe", A), ("Aktion", A), ("Vorher", A),
              ("Nachher", A)])
    out.append(t)
    hi = _next_day(to)
    for r in reversed(ofr_log_rows(c, oid, limit=GX_RIGHTS_MAX)):
        if frm <= (r["at"] or "") < hi:
            t.add(r["id"], r["at"], r["by_name"], r["user_name"], r["group"], r["action"],
                  json.dumps(r["before"], ensure_ascii=False, sort_keys=True) if r["before"] is not None else "",
                  json.dumps(r["after"], ensure_ascii=False, sort_keys=True) if r["after"] is not None else "")

    out += _chain(c, oid, _T)  # 2.1309.0 (#6467 (4))
    return out


def _next_day(d):
    return (date.fromisoformat(d) + timedelta(days=1)).isoformat()


def gx_close(tables):
    """2.674.0 (#4190): closes (and so removes) the temporary files of the tables."""
    for t in tables:
        if t.buf is not None:
            t.buf.close()


def gx_zip(c, oid, frm, to):
    """-> (path of the ZIP in a temporary file, counts); 2.674.0 (#4190): the tables are written into temporary files and
    copied into the ZIP piece by piece (no table as one string in memory). The caller sends the file (abm_send_zip) or drops it.
    2.1309.0 (#6471): the ZIP is open while the tables are made: the stored files go into belege/ one by one (one file in
    memory at a time), the tables after them."""
    gaps = {}
    fd, path = tempfile.mkstemp(prefix="kalmido-gobd-", suffix=".zip")
    try:
        with os.fdopen(fd, "wb") as fh, zipfile.ZipFile(fh, "w", zipfile.ZIP_DEFLATED, allowZip64=True) as z:
            fl = _Files(z)
            tables = []
            try:
                tables = gx_tables(c, oid, frm, to, gaps, files=True, fl=fl)
                counts = gx_zip_write(c, oid, frm, to, tables, gaps, z, fl)
            finally:
                gx_close(tables)
    except BaseException:
        abm_drop(path)
        raise
    return path, counts


def gx_zip_write(c, oid, frm, to, tables, gaps, z, fl):
    """index.xml, the DTD, the tables, missing.txt and (2.1309.0, #6471) hinweise.txt into the open ZIP z -> the counts."""
    left = len(gaps.get("no_date") or ()) + len(gaps.get("no_amount") or ())
    co = ofx_company(c, oid) or {}
    name = (co.get("name") or "").strip() or "Kalmido"
    loc = " ".join(x for x in ((co.get("zip") or "").strip(), (co.get("city") or "").strip()) if x)
    note = (f'Kalmido, Zeitraum {_d(frm)} - {_d(to)}. Textspalten, die mit = + - @ beginnen, tragen ein vorangestelltes Hochkomma (Formelschutz)'
            + (f', {left} Belege ohne Datum oder Betrag nicht enthalten (missing.txt)' if left else '')
            + f'. Ordner belege/: {fl.n} gespeicherte Dateien (PDF, E-Rechnungs-XML, Belegdateien) unveraendert, mit SHA-256 in den Tabellen'
            + (f'; {len(fl.notes)} Hinweise zu Dateien in hinweise.txt' if fl.notes else '')
            + '. Kennzeichen Papierkorb / zurueckgenommen: Eintraege im Papierkorb bzw. einer zurueckgenommenen Einlesung')
    xml = ('<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE DataSet SYSTEM "' + GX_DTD_NAME + '">\n<DataSet>\n  <Version>1.0</Version>\n'
           f"  <DataSupplier><Name>{escape(name)}</Name><Location>{escape(loc)}</Location><Comment>{escape(note)}</Comment></DataSupplier>\n"
           f"  <Media>\n    <Name>{escape(f'Kalmido {frm} {to}')}</Name>\n" + "".join(t.xml(frm, to) for t in tables) + "  </Media>\n</DataSet>\n")
    z.writestr("index.xml", xml)
    z.writestr(GX_DTD_NAME, GX_DTD.encode("utf-8"))  # 2.188.0 A (#2498)
    for t in tables:
        t.buf.seek(0)
        with z.open(t.url, "w", force_zip64=True) as zf:
            while True:
                part = t.buf.read(1 << 20)  # 2.674.0 (#4190): a megabyte of characters at a time
                if not part:
                    break
                zf.write(part.encode("utf-8"))
    if left:
        z.writestr("missing.txt", bk_gaps_text(gaps).encode("utf-8"))
    if fl.notes:
        z.writestr("hinweise.txt", ("\r\n".join(fl.notes) + "\r\n").encode("utf-8"))
    return dict({t.url: t.n for t in tables}, **({"missing.txt": left} if left else {}), **{"belege/": fl.n},
                **({"hinweise.txt": len(fl.notes)} if fl.notes else {}))


def _span():
    y = local_now().year - 1  # 2.355.0 B (#2847): the office's local year (date.today() is the server's)
    a = (request.args.get("from") or f"{y}-01-01").strip()
    b = (request.args.get("to") or f"{y}-12-31").strip()
    try:
        da, db_ = date.fromisoformat(a), date.fromisoformat(b)
    except ValueError:
        raise BadInput(tr("Invalid value: {0}", "from / to"))
    if db_ < da:
        raise BadInput(tr("The end lies before the start"))
    if (db_ - da).days > GX_MAX_DAYS:
        raise BadInput(tr("The period is too long (at most {0} years)", 11))
    return da.isoformat(), db_.isoformat()


@app.get("/api/office/gobd/export")
def gx_export_get():
    """Admin: ?from=YYYY-MM-DD&to=YYYY-MM-DD (default: the previous calendar year) -> the ZIP for the tax auditor;
    ?check=1 -> {from, to, counts} only."""
    c = db()
    uid = office_gate(c)
    oid = office_org(c, uid, admin=True)
    frm, to = _span()
    if request.args.get("check") == "1":
        gaps = {}
        counts = {t.url: t.n for t in gx_tables(c, oid, frm, to, gaps)}
        return {"from": frm, "to": to, "counts": counts, "left_out": len(gaps.get("no_date") or ()) + len(gaps.get("no_amount") or ())}
    with abm_slot():  # 2.674.0 (#4190): at most two large exports at once (429 else)
        path, counts = gx_zip(c, oid, frm, to)
    try:
        ofx_log(c, oid, "export", target="gobd", detail={"from": frm, "to": to, "counts": counts})
        c.commit()
        resp = abm_send_zip(path, f"GoBD_Export_{frm.replace('-', '')}_{to.replace('-', '')}.zip")
    except BaseException:
        abm_drop(path)
        raise
    resp.headers["Cache-Control"] = "no-store"  # 2.306.0 D2 (#2875)
    return resp
