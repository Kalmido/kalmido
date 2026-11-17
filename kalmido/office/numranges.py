"""Office & finance, 2.138.0 D (#2256): the number ranges -- the next running number of every series (quotation, invoice,
credit note, reminder, delivery note) set by the office admin. The counter only moves up (never to or below the last number given);
a jump in the invoice / credit note series needs a reason (GoBD), every change goes into the office log. A scheme with
a year ({yyyy}/{yy}) has one counter per year: the setting applies to the current year. office_numbers.last = next - 1,
no new table or column. Session routes only (office_gate: no agents), like the rest of the settings."""
import json
from datetime import date

from flask import jsonify

from ..core.config import app
from ..core.db import body, bump, db, err
from ..core.i18n import N_, tr
from ..core.orgcrypt import oc_dec
from ..core.pg import write_lock
from .docs import ODOC_KIND_WORDS  # 2.1315.0 (#6472)
from .invoices import INV_SKIP_REASON_MIN, inv_manual_seq, inv_number_year, inv_scheme
from .ledger import ofx_log
from .model import num_kind, num_scheme, office_first_invoice, office_gate, office_number_format, office_org, office_role, office_scheme_period, office_settings

ONUM_KINDS = ("offer", "invoice", "credit", "reminder", "delivery")  # delivery notes since 2.120.0 D (#2089)
ONUM_REASON_KINDS = ("invoice", "credit")  # a jump in these series needs a reason (GoBD)
ONUM_MAX = 999_999_999
ONUM_GAP_LIST = 5  # 2.1315.0 (#6472): the gaps the number ranges page names per series (the export names every one)


def onum_kinds(s):
    """The series with one counter; quotations counted per client / project (2.118.0 A, #2265) have no single one."""
    return tuple(k for k in ONUM_KINDS if k != "offer" or (s.get("offer_counter") or "org") == "org")


def onum_scheme(s, kind):
    return s.get("offer_scheme") if kind == "offer" else inv_scheme(s, kind)


def onum_range(c, oid, s, kind):
    """The state of one series: scheme, counter period, last value, the next number (formatted with example values).
    2.433.0 (#3597): invoice corrections on the invoices' counter (credit_shared) show that counter, shared = "invoice"
    (the page greys the row: it is set with the invoices)."""
    scheme = onum_scheme(s, kind) or ""
    ck = kind if kind == "offer" else num_kind(s, kind)
    period = office_scheme_period(scheme if ck == kind else num_scheme(s, kind))
    r = c.execute("SELECT last FROM office_numbers WHERE org_id=? AND kind=? AND period=?", (oid, ck, period)).fetchone()
    last = int(r["last"]) if r else 0
    return {"kind": kind, "scheme": scheme, "period": period, "yearly": bool(period), "last": last, "next": last + 1, "min_next": last + 1,
            "preview": office_number_format(scheme, last + 1, project=tr("Project"), client=tr("Client"), initials="AB", kuerzel="ABC"),
            "reason_needed": kind in ONUM_REASON_KINDS, **({"shared": ck} if ck != kind else {})}


def onum_reason(kind, skip, raw):
    """2.144.6 B (#2400 F2): the cleaned reason of a jump by skip numbers; None when the series needs one (GoBD) and it is
    missing. Shared with the legacy import's counter (legacyimport.fi_counter_post)."""
    reason = raw.strip()[:300] if isinstance(raw, str) else ""
    return None if kind in ONUM_REASON_KINDS and skip > 0 and len(reason) < INV_SKIP_REASON_MIN else reason


# ---------------------------------------------------------------- 2.1315.0 (#6472, audit #4791 A2 b): the gaps of the series
# A gap = a running number between 1 and the counter that no finalised document of the series carries. Each gap is a range
# with one reason (the precedence below): a draft carries the number, another document or the legacy archive carries it,
# the counter passed it (office log "skipped"), a number set by hand skipped it, the counter was set (number ranges, legacy
# counter) -- each with the reason of the log line -- else none. One function for the auditor's export (number_ranges.csv)
# and the number ranges page (its hint), never two counts.
ONUM_GAP_TEXTS = {  # code -> (the export's text, German without umlauts, the page's text (tr)); {0} = the logged reason
    "draft": ("Entwurf traegt die Nummer", N_("a draft carries the number")),
    "doc": ("vergeben an Dokument {0}", N_("taken by document #{0} ({1})")),
    "archive": ("Nummer im Altbestand (Archiv)", N_("number in the legacy archive")),
    "skipped": ("uebersprungen: {0}", N_("skipped: {0}")),
    "manual": ("Nummer von Hand: {0}", N_("number set by hand: {0}")),
    "start": ("Startnummer: {0}", N_("start number: {0}")),
    "set": ("Zaehler gesetzt: {0}", N_("counter set: {0}")),
    "legacy": ("Zaehler Altbestand: {0}", N_("counter of the legacy archive: {0}")),
    "none": ("ohne Grund", N_("no reason")),
}
ONUM_GAP_POINT = ("draft", "doc", "archive", "skipped")  # one number each, before the ranges below
ONUM_GAP_RANGE = ("manual", "start", "set", "legacy")


ONUM_GAP_KIND_DE = {"offer": "Angebot", "invoice": "Rechnung", "credit": "Rechnungskorrektur", "reminder": "Mahnung", "delivery": "Lieferschein"}


def onum_gap_text(g, lang=None):
    """The reason of gap g: lang None = the export's German text, else the page's (tr)."""
    de, en = ONUM_GAP_TEXTS.get(g["code"], ONUM_GAP_TEXTS["none"])
    arg = g.get("text") or ""
    if g["code"] == "doc":  # text = "<id> <kind>"
        did, _sp, kind = arg.partition(" ")
        if lang is None:
            return de.format(f"#{did} ({ONUM_GAP_KIND_DE.get(kind, kind)})")
        return tr(en, did, tr(ODOC_KIND_WORDS.get(kind, kind)))
    if lang is None:
        return (de.format(arg) if "{0}" in de else de).rstrip(": ")  # "Startnummer" when the log line has no reason
    return (tr(en, arg) if "{0}" in en else tr(en)).rstrip(": ")


def _onum_day(v):
    try:
        return date.fromisoformat(str(v or "")[:10])
    except ValueError:
        return None


def _onum_log(c, oid):
    """The office log lines number of organisation oid: [(at day, doc_id, target, detail dict)]."""
    out = []
    for r in c.execute("SELECT at, doc_id, target, detail FROM office_doc_log WHERE org_id=? AND action='number' ORDER BY id", (oid,)):
        try:
            v = r["detail"]
            txt = oc_dec(c, oid, "office_doc_log.detail", v) if isinstance(v, str) else v
            d = json.loads(txt) if isinstance(txt, str) else (txt or {})
        except Exception:  # noqa: BLE001 -- a line that cannot be read gives no reason (the gap stays "no reason")
            continue
        if isinstance(d, dict):
            out.append((_onum_day(str(r["at"])[:10]), r["doc_id"], r["target"], d))
    return out


def onum_gaps(c, oid, s=None, years=None):
    """2.1315.0 (#6472): the gaps of the invoice / correction series of organisation oid -> [{counter, kinds, period, last,
    count (missing numbers), ranges: [{from, to, code, text}], other (finalised numbers that do not follow today's scheme)}],
    one per counter (office_numbers) and period; years = (first, last) keeps the yearly periods within them."""
    s = s or office_settings(c, oid)
    series = {}
    for k in ONUM_REASON_KINDS:
        series.setdefault(num_kind(s, k), []).append(k)

    def where(num, day, kinds=None):
        """[(counter, period, seq)] of a number under the schemes of the series (kinds: only these)."""
        out = []
        for ck, ks in series.items():
            for k in ks:
                if kinds is not None and k not in kinds:
                    continue
                sch = inv_scheme(s, k) or ""
                seq = inv_manual_seq(sch, num or "") if sch else None
                if seq is None:
                    continue
                psch = num_scheme(s, k)
                y = inv_number_year(sch, num)
                per = str(y) if (y is not None and office_scheme_period(psch)) else office_scheme_period(psch, day)
                out.append((ck, per, seq))
                break
        return out

    S = {}  # (counter, period) -> {"have": set, "pt": {seq: (code, text)}, "rg": [(a, b, code, text)], "man": [(seq, text)], "other": n}

    def st(ck, per):
        return S.setdefault((ck, per), {"have": set(), "pt": {}, "rg": [], "man": [], "other": 0})

    docs = c.execute("SELECT id, kind, number, date, locked_at FROM office_docs WHERE org_id=? AND trial=0 AND COALESCE(number, '')<>'' ORDER BY id",
                     (oid,)).fetchall()
    kinds_of = {k for ks in series.values() for k in ks}
    later = []
    for r in docs:
        day = _onum_day(r["date"])
        mine = where(r["number"], day, kinds={r["kind"]}) if r["kind"] in kinds_of else []
        if r["kind"] in kinds_of and r["locked_at"] is not None:
            if mine:
                st(mine[0][0], mine[0][1])["have"].add(mine[0][2])
            else:  # finalised under another scheme: counted, named (its number cannot be placed)
                ck = num_kind(s, r["kind"])
                st(ck, office_scheme_period(num_scheme(s, r["kind"]), day))["other"] += 1
        elif r["kind"] in kinds_of and mine:
            later.append((mine[0], ("draft", "")))
        else:  # another kind with a number of the series (a quotation before 2.1289.0)
            for w in where(r["number"], day):
                later.append((w, ("doc", f"{r['id']} {r['kind']}")))
    for a in c.execute("SELECT number, date FROM office_archive WHERE org_id=? AND number<>''", (oid,)):
        for w in where(a["number"], _onum_day(a["date"])):
            later.append((w, ("archive", "")))
    dates = {r["id"]: _onum_day(r["date"]) for r in docs}
    for day, did, target, d in _onum_log(c, oid):
        why = str(d["after"].get("reason") or "").strip() if isinstance(d.get("after"), dict) else ""
        if "skipped" in d:
            for w in where(str(d["skipped"]), dates.get(did) or day):
                later.append((w, ("skipped", str(d.get("reason") or ""))))
        elif target == "number_range" and isinstance(d.get("before"), dict) and isinstance(d.get("after"), dict):
            b, a = d["before"], d["after"]
            try:
                lo, hi = int(b.get("next")), int(a.get("next")) - 1
            except (TypeError, ValueError):
                continue
            if b.get("kind") in series and hi >= lo:
                st(b["kind"], str(b.get("period") or ""))["rg"].append((lo, hi, "start" if lo == 1 else "set", str(a.get("reason") or "")))
        elif target == "legacy" and d.get("kind") in series:
            try:
                lo, hi = int(d.get("from")) + 1, int(d.get("to"))
            except (TypeError, ValueError):
                continue
            if hi >= lo:
                per = office_scheme_period(num_scheme(s, d["kind"]), day)
                st(d["kind"], per)["rg"].append((lo, hi, "start" if lo == 1 else "legacy", str(d.get("reason") or "")))
        elif did and isinstance(d.get("after"), dict) and d["after"].get("number") and why:
            for w in where(str(d["after"]["number"]), dates.get(did) or day):
                st(w[0], w[1])["man"].append((w[2], why))
    for (ck, per, seq), why in later:
        x = st(ck, per)
        if seq not in x["have"] and seq not in x["pt"]:
            x["pt"][seq] = why
    lasts = {(r["kind"], r["period"] or ""): int(r["last"]) for r in c.execute(
        "SELECT kind, period, last FROM office_numbers WHERE org_id=? AND kind IN (" + ",".join("?" * len(series)) + ")", (oid, *series))}
    out = []
    for key in sorted(set(lasts) | {k for k, v in S.items() if v["have"] or v["other"]}, key=lambda k: (k[0], k[1])):
        ck, per = key
        if years and per and not (years[0] <= int(per) <= years[1]):
            continue
        x = st(ck, per)
        last = max([lasts.get(key, 0)] + list(x["have"]))
        ranges, prev = [], 0
        for p in sorted(x["have"]) + [last + 1]:
            if p > prev + 1:
                ranges += _onum_split(prev + 1, p - 1, x)
            prev = max(prev, p)
        out.append({"counter": ck, "kinds": list(series[ck]), "period": per, "last": last, "ranges": ranges,
                     "count": sum(g["to"] - g["from"] + 1 for g in ranges), "other": x["other"]})
    return out


def _onum_split(a, b, x):
    """The missing numbers a..b of one series as ranges with one reason each (see onum_gaps)."""
    rg = [(lo, hi, code, why) for lo, hi, code, why in reversed(x["rg"]) if lo <= b and hi >= a]  # the latest setting first
    rg = [(a, b, "manual", why) for seq, why in x["man"] if seq == b + 1] + rg  # a number by hand explains the run just below it
    cuts = {a, b + 1}
    for seq in x["pt"]:
        if a <= seq <= b:
            cuts |= {seq, seq + 1}
    for lo, hi, _c, _w in rg:
        cuts |= {max(lo, a), min(hi, b) + 1}
    cuts = sorted(cuts)
    out = []
    for lo, nx in zip(cuts, cuts[1:]):
        hi = nx - 1
        if lo == hi and lo in x["pt"]:
            code, why = x["pt"][lo]
        else:
            m = next(((cd, w) for l2, h2, cd, w in rg if l2 <= lo and h2 >= hi), ("none", ""))
            code, why = m
        if out and out[-1]["code"] == code and out[-1]["text"] == why and out[-1]["to"] == lo - 1:
            out[-1]["to"] = hi
        else:
            out.append({"from": lo, "to": hi, "code": code, "text": why})
    return out


def onum_gap_hints(c, oid, s):
    """2.1315.0 (#6472): {kind: hint} of the current period of the invoice / correction series with gaps, for the number
    ranges page: {count, ranges (the first ONUM_GAP_LIST, each with its reason in the reader's language), more, none
    (missing numbers without a reason)}."""
    out, gaps = {}, None
    for kind in ONUM_REASON_KINDS:
        if num_kind(s, kind) != kind:
            continue
        if gaps is None:
            gaps = onum_gaps(c, oid, s)
        per = office_scheme_period(num_scheme(s, kind))
        g = next((x for x in gaps if x["counter"] == kind and x["period"] == per), None)
        if not g or not g["ranges"]:
            continue
        rs = [{"from": r["from"], "to": r["to"], "code": r["code"], "reason": onum_gap_text(r, lang="ui")} for r in g["ranges"]]
        out[kind] = {"count": g["count"], "ranges": rs[:ONUM_GAP_LIST], "more": max(0, len(rs) - ONUM_GAP_LIST),
                     "none": sum(r["to"] - r["from"] + 1 for r in g["ranges"] if r["code"] == "none")}
    return out


@app.get("/api/office/number-ranges")
def onum_list():
    """Every series of the office area I work in; members read (the settings page is the admins'), admin = may change."""
    c = db()
    uid = office_gate(c)
    oid = office_org(c, uid)
    s = office_settings(c, oid)
    ranges = [onum_range(c, oid, s, k) for k in onum_kinds(s)]
    hints = onum_gap_hints(c, oid, s)  # 2.1315.0 (#6472): the gaps of the series with their reason (as number_ranges.csv)
    for r in ranges:
        if r["kind"] in hints:
            r["gaps"] = hints[r["kind"]]
    # 2.1345.0 (#6532): first_invoice = no real invoice finalised yet: an empty series prefills the reason of a jump
    return jsonify(ranges=ranges, admin=office_role(c, uid, oid) == "admin", first_invoice=office_first_invoice(c, oid))


@app.post("/api/office/number-ranges/<kind>")
def onum_set(kind):
    """Org admin. {next, reason?}: the next running number of a series (current year with a yearly scheme). Only up;
    the invoice / credit note series need a reason when numbers are skipped. -> the series' new state."""
    c = db()
    uid = office_gate(c)
    oid = office_org(c, uid, admin=True)
    if kind not in onum_kinds(office_settings(c, oid)):
        return err(tr("Invalid value: {0}", "kind"))
    if kind != "offer" and num_kind(office_settings(c, oid), kind) != kind:  # 2.433.0 (#3597): set with the invoices
        return err(tr("Invoice corrections count with the invoice numbers; set the next number there"))
    b = body()
    b = b if isinstance(b, dict) else {}
    try:
        nxt = int(str(b.get("next", "")).strip())
    except ValueError:
        return err(tr("Invalid value: {0}", "next"))
    write_lock(c, f"office_num_{int(oid)}")  # the same lock as the number of a new document (docs._assign_number)
    s = office_settings(c, oid)
    cur = onum_range(c, oid, s, kind)
    if nxt < cur["min_next"] or nxt > ONUM_MAX:
        return err(tr("The next number must be at least {0}", cur["min_next"]))
    if nxt == cur["next"]:
        return jsonify(onum_range(c, oid, s, kind))
    reason = onum_reason(kind, nxt - cur["next"], b.get("reason"))
    if reason is None:
        return err(tr("The number skips {0} numbers of the series; give a reason (GoBD)", nxt - cur["next"]))
    # never down, also against a document numbered in parallel (the lock above + the condition on the row)
    row = c.execute("INSERT INTO office_numbers(org_id, kind, period, last) VALUES(?,?,?,?) ON CONFLICT(org_id, kind, period) "
                    "DO UPDATE SET last=excluded.last WHERE office_numbers.last < excluded.last RETURNING last",
                    (oid, kind, cur["period"], nxt - 1)).fetchone()
    if row is None:
        c.rollback()
        return err(tr("The next number must be at least {0}", cur["min_next"]))
    ofx_log(c, oid, "number", target="number_range", detail={"before": {"kind": kind, "period": cur["period"], "next": cur["next"]},
                                                             "after": {"next": nxt, **({"reason": reason} if reason else {})}})
    bump(c)
    c.commit()
    return jsonify(onum_range(c, oid, s, kind))
