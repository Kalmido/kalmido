#!/usr/bin/env python3
# kalmido-suite: after=office_calc nodata
"""2.1287.0 (#6300, audit #4740 F2): an invoice from a quotation with parts hits the quotation's net and gross in every
invoice form (full / title / summary). In the form "full" the part's positions are rounded one by one (qty x the part's
qty); the rest per tax rate was only settled up to 0.05 - now always: with exactly one position of that rate it becomes
that position's flat amount (as before), with several the part gets its own position "Rounding adjustment" (qty 1, flat)
and no hour position silently turns into a flat amount.
 - the audit's example: a part with 20 positions 0.5 x 33.33 (16.67 each), 3 times on the title page: quotation 1,000.20 /
   1,190.24; every invoice form the same (full was 1,000.00 / 1,190.00); full has one adjustment line of 0.20, its 20
   positions stay days
 - one position of the rate: the rest goes on it as before (flat, its qty x rate in the detail), no extra line
 - a seeded random comparison: quotations with up to 25 positions per part, percent positions, the one surcharge line of
   the title page (#6281) and the former surcharge per part (mk_per_part), in the home currency, USD and HUF (#6299), all
   three invoice forms: net, tax per rate and gross of the invoice = the quotation's
Pure Python, no server (the functions lifted from kalmido/office/parts.py and invoices.py like p6299_fx_offer_invoice_test.py).
The same route with a database, also for a person without an organisation: p258_b_api_test.py (#1759 / #6300).
usage: python3 tests/p21287_c_rundung_test.py   (KALMIDO_SRC=<dir with kalmido/> to test another tree)"""
import ast
import importlib.util
import json
import os
import random
import re
import sys
import types
from decimal import ROUND_HALF_UP, Decimal

N = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.abspath(os.environ.get("KALMIDO_SRC") or os.path.join(N, ".."))
from kt import check, done  # noqa: E402

D = Decimal
OFF = os.path.join(SRC, "kalmido", "office")
spec = importlib.util.spec_from_file_location("kalmido.office.calc", os.path.join(OFF, "calc.py"))
calc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(calc)

# ---------------------------------------------------------------- the pure part of parts.py (no database), fictional data
DB = {}
PRD_DOC_KEYS = ("handling_pct", "handling_label", "markup_pct", "markup_label", "markup_stacked")


def _calc_doc(r, home="EUR"):  # as docs._calc_doc (an open quotation: no frozen surcharge split)
    return {"home": home, "lang": r["lang"], "currency": r["currency"], "fx_rate": r["fx_rate"], "vat_mode": r["vat_mode"], "raw_mode": r["raw_mode"],
            "raw_factor": r["raw_factor"], "prod_quotient": r["prod_quotient"], "producing_rate": r["producing_rate"], "discount_pct": r["discount_pct"],
            "producing_on": r.get("producing_on"), "discount_amount": r.get("discount_amount"), "producing_mode": r.get("producing_mode"),
            "share_label": r.get("share_label"), **{k: r.get(k) for k in PRD_DOC_KEYS}, "vat_note": r.get("vat_note"), "subtotals": r.get("subtotals"),
            "date": r.get("date"), "service_to": r.get("service_to"), "sur_standard": 0}


def doc_items(c, did, oid, part=None):
    return [dict(x) for x in (DB["part_items"].get(part, []) if part is not None else DB["items"])]


src = open(os.path.join(OFF, "parts.py"), encoding="utf-8").read()
ns = {k: getattr(calc, k) for k in dir(calc) if not k.startswith("__")}
ns.update(json=json, Decimal=Decimal, _dk_sheet=None, _calc_doc=_calc_doc, doc_items=doc_items, office_settings=lambda c, oid: DB.get("settings", {}),
          office_pack_for=lambda s, day=None: None, hc_home=lambda s: s.get("home_currency") or "EUR", doc_txt=lambda de, en, lang: de or en or "",
          PARTS_TITLE_FILM={}, UNITS=(), tr=lambda k, *a, **kw: k.split("|")[0], N_=lambda s: s, BadInput=ValueError, Denied=ValueError)
exec(compile(src[src.index("PART_KINDS = ("):src.index("# ---------------------------------------------------------------- routes")], "parts.py", "exec"), ns)
ns["tp_parts"] = lambda c, oid, did: [dict(p) for p in DB.get("parts") or []]
ns["tp_has_parts"] = lambda c, oid, did: bool(DB.get("parts"))
P = types.SimpleNamespace(**ns)

# ---------------------------------------------------------------- invoices.inv_items_from_offer with its helpers
for name, mod in (("kalmido", {}), ("kalmido.office", {}), ("kalmido.office.calc", calc),
                  ("kalmido.office.docs", {"_calc_doc": _calc_doc, "doc_items": doc_items}),
                  ("kalmido.office.parts", {"tp_inv_items": P.tp_inv_items, "tp_flat_items": P.tp_flat_items})):
    if not isinstance(mod, types.ModuleType):
        m = types.ModuleType(name)
        m.__path__ = []
        m.__dict__.update(mod)
        mod = m
    sys.modules[name] = mod
isrc = open(os.path.join(OFF, "invoices.py"), encoding="utf-8").read()
tree = ast.parse(isrc)
keep = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in ("inv_items_from_offer", "_offer_lines", "_lines_eur")]
INV = {k: getattr(calc, k) for k in dir(calc) if not k.startswith("__")}
INV.update(__name__="kalmido.office.invoices", __package__="kalmido.office", office_settings=ns["office_settings"], office_pack_for=ns["office_pack_for"],
           hc_home=ns["hc_home"], _col=lambda r, k: r.get(k))
exec(compile(ast.Module(body=keep, type_ignores=[]), "invoices.py", "exec"), INV)
inv_items_from_offer = INV["inv_items_from_offer"]


def row(**kw):
    r = {"id": 1, "kind": "offer", "lang": "de", "currency": "EUR", "fx_rate": None, "vat_mode": "vat", "raw_mode": "none", "raw_factor": 0.25,
         "prod_quotient": 3, "producing_rate": 650, "discount_pct": 0, "producing_on": 0, "flat_print": 0}
    r.update(kw)
    return r


def col_scale(table, col):
    """The decimal places of NUMERIC column table.col as the database has it: its CREATE TABLE in core/schema.py, widened by a
    fragment's ALTER COLUMN .. TYPE NUMERIC(p,s) (core/migrations.d) - read from the source, so the test follows the column."""
    scale = None
    with open(os.path.join(SRC, "kalmido", "core", "schema.py"), encoding="utf-8") as f:
        m = re.search(rf"CREATE TABLE IF NOT EXISTS {table} \((.*?)\);", f.read(), re.S)
    m = m and re.search(rf"\b{col} NUMERIC\((\d+),(\d+)\)", m.group(1))
    if m:
        scale = int(m.group(2))
    mig = os.path.join(SRC, "kalmido", "core", "migrations.d")
    for n in sorted(os.listdir(mig)):
        if n.endswith(".py"):
            with open(os.path.join(mig, n), encoding="utf-8") as f:
                for m in re.finditer(rf"ALTER TABLE {table} ALTER COLUMN {col} TYPE NUMERIC\((\d+),(\d+)\)", f.read()):
                    scale = int(m.group(2))
    return scale


RATE_SCALE, QTY_SCALE = col_scale("office_doc_items", "rate"), col_scale("office_doc_items", "qty")


def pg_numeric(v, scale):
    """What a NUMERIC(p, scale) column keeps of v sent as a float (invoices._put_rows: float(...); Postgres turns a float8 into
    numeric with 15 significant digits, then rounds to the column's places, half away from zero)."""
    return D(format(float(D(str(v))), ".15g")).quantize(D(1).scaleb(-scale), rounding=ROUND_HALF_UP)


def stored(items):
    """The positions as the database keeps them (invoices._put_rows: qty / rate as float into office_doc_items, read back as
    a float again by core/pg.py). 2.1254.0 (#6299, review): with the column's places - was the float itself, which hid that
    NUMERIC(14,4) cut the rate a foreign line needs (49,984.02 HUF -> rate 126.3818 -> 49,984.00)."""
    return [{**x, "qty": float(pg_numeric(x.get("qty") if x.get("qty") is not None else 1, QTY_SCALE)),
             "rate": float(pg_numeric(x.get("rate") or 0, RATE_SCALE))} for x in items]


def offer_totals(r, items, parts=None, part_items=None):
    DB.update(items=items, parts=parts or [], part_items=part_items or {}, settings={})
    t = P.tp_doc_totals(None, 1, r, items, None, home="EUR") if parts else calc.office_calc(_calc_doc(r), items)
    if t and "_part_calcs" in t:
        t.pop("_part_calcs")
    return t


def compare(r, items, parts=None, part_items=None, mode=None):
    """(offer net, gross, {key: tax}) and the invoice's, the invoice from inv_items_from_offer as the database keeps it."""
    t = offer_totals(r, items, parts, part_items)
    rows = inv_items_from_offer(None, 1, r, mode)
    i = calc.inv_calc({"lang": r["lang"], "currency": r["currency"], "fx_rate": r["fx_rate"], "home": "EUR", "vat_mode": r["vat_mode"]}, stored(rows))
    ot = {x["rate_key"]: D(str(x["amount"])) for x in t["tax_lines"]}
    it = {x["rate_key"]: D(str(x["amount"])) for x in i["tax_lines"]} if "tax_lines" in i else None
    return (D(str(t["net"])), D(str(t["gross"])), ot), (D(i["net"]), D(i["gross"]), it if it is not None else ot)


def same(a, b):
    return a[0] == b[0] and a[1] == b[1] and {k: v for k, v in a[2].items() if v} == {k: v for k, v in (b[2] or {}).items() if v}


# ---------------------------------------------------------------- 1. the audit's example


# ---------------------------------------------------------------- 1. the audit's example
PIT = {7: [{"id": 100 + i, "kind": "service", "title": f"Tag {i}", "qty": 0.5, "unit": "day", "rate": 33.33, "tax": "standard",
            "discountable": 1, "intext": "intern"} for i in range(20)]}
PARTS = [{"id": 7, "kind": "items", "title": "Teil A", "settings": {}, "print": 1}]
ITEMS = [{"id": 1, "kind": "part", "ref_part_id": 7, "qty": 3, "unit": "piece", "title": "Teil A", "discountable": 1}]
for mode in ("full", "title", "summary"):
    o, i = compare(row(), ITEMS, PARTS, PIT, mode)
    check(o[0] == D("1000.20") and o[1] == D("1190.24"), f"example: the quotation 1000.20 / 1190.24, got {o[0]} / {o[1]}")
    check(same(o, i), f"example, invoice form {mode}: invoice = quotation 1000.20 / 1190.24, got {i[0]} / {i[1]}")
rows = inv_items_from_offer(None, 1, row(), "full")
adj = [x for x in rows if x.get("title") == "Rounding adjustment"]
check(len(adj) == 1 and adj[0]["unit"] == "flat" and D(str(adj[0]["qty"])) == 1 and D(str(adj[0]["rate"])) == D("0.20") and adj[0]["tax"] == "standard",
      f"example, full: one position 'Rounding adjustment' 1 x 0.20 flat at the standard rate: {adj}")
days = [x for x in rows if x.get("kind") == "service" and x.get("title", "").startswith("Tag")]
check(len(days) == 20 and all(x["unit"] == "day" and D(str(x["qty"])) == D("1.5") for x in days),
      f"example, full: the 20 positions stay 1.5 days each (none became a flat amount): {[(x['unit'], x['qty']) for x in days][:3]}")

# one position of the rate: the rest goes on it (flat, qty x rate in the detail), no extra line (part 10.13 x 3 = 30.39,
# the position 3 x 10.125 = 30.38)
PIT1 = {7: [{"id": 100, "kind": "service", "title": "Schnitt", "qty": 1, "unit": "day", "rate": 10.125, "tax": "standard", "discountable": 1}]}
o, i = compare(row(), ITEMS, PARTS, PIT1, "full")
rows = inv_items_from_offer(None, 1, row(), "full")
one = [x for x in rows if x.get("title") == "Schnitt"]
check(same(o, i) and not [x for x in rows if x.get("title") == "Rounding adjustment"] and len(one) == 1 and one[0]["unit"] == "flat"
      and D(str(one[0]["rate"])) == D("30.39") and "3 × " in (one[0].get("detail") or ""), f"one position: the rest on it as before, no extra line: {one} {o} {i}")

# review: without VAT the part line names one base ("standard") while the positions keep their rates - the rates must not
# be "settled" against each other (was: the standard position turned into a flat 1500 plus "Rounding adjustment" -500)
PITN = {7: [{"id": 100, "kind": "service", "title": "Dreh", "qty": 1, "unit": "day", "rate": 1000, "tax": "standard", "discountable": 1},
            {"id": 101, "kind": "service", "title": "Buch A", "qty": 1, "unit": "piece", "rate": 250, "tax": "reduced", "discountable": 1},
            {"id": 102, "kind": "service", "title": "Buch B", "qty": 1, "unit": "piece", "rate": 250, "tax": "reduced", "discountable": 1}]}
ITEMS1 = [{"id": 1, "kind": "part", "ref_part_id": 7, "qty": 1, "unit": "piece", "title": "Teil A", "discountable": 1}]
o, i = compare(row(vat_mode="novat"), ITEMS1, PARTS, PITN, "full")
rows = inv_items_from_offer(None, 1, row(vat_mode="novat"), "full")
dreh = [x for x in rows if x.get("title") == "Dreh"]
check(o[0] == i[0] == D("1500.00") and not [x for x in rows if x.get("title") == "Rounding adjustment"] and len(dreh) == 1
      and dreh[0]["unit"] == "day" and D(str(dreh[0]["rate"])) == 1000,
      f"without VAT, mixed rates in the part: no adjustment line, the positions stay as they are: {[(x.get('title'), x.get('unit'), x.get('rate')) for x in rows]}")
PITM = {7: [dict(x, tax="reduced" if n % 2 else "standard") for n, x in enumerate(PIT[7])]}
o, i = compare(row(vat_mode="novat"), ITEMS, PARTS, PITM, "full")
rows = inv_items_from_offer(None, 1, row(vat_mode="novat"), "full")
adj = [x for x in rows if x.get("title") == "Rounding adjustment"]
check(o[0] == i[0] == D("1000.20") and len(adj) == 1 and D(str(adj[0]["rate"])) == D("0.20"),
      f"without VAT, a real rest over mixed rates: one adjustment 0.20 for the whole part, invoice = quotation: {o[0]} / {i[0]} {adj}")
# review: a delivery note takes the positions of the form "full" without prices - no settlement there (fix=False)
DB.update(items=ITEMS, parts=PARTS, part_items=PIT, settings={})
rows = P.tp_inv_items(None, 1, row(), "full", None, fix=False)
days = [x for x in rows if (x.get("title") or "").startswith("Tag")]
check(not [x for x in rows if x.get("title") == "Rounding adjustment"] and len(days) == 20 and all(x["unit"] == "day" for x in days),
      "fix=False (delivery note): no 'Rounding adjustment' line, the positions keep their quantities")
check('tp_inv_items(c, oid, src, "full", None, fix=False)' in open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "kalmido", "office", "delivery.py")).read(),
      "the delivery note asks for its positions without the cent settlement")


# ---------------------------------------------------------------- 2. seeded random quotations with parts
def rnd_doc(rng, cur, fx):
    d = row(currency=cur, fx_rate=fx, discount_pct=rng.choice([0, 0, 5, 7.5]), markup_pct=rng.choice([None, 10, 12.5, 15]),
            handling_pct=rng.choice([None, None, 8]), markup_stacked=rng.choice([0, 1]), raw_mode=rng.choice(["none", "included", "optional"]),
            producing_on=rng.choice([0, 1]))
    if rng.random() < 0.2:
        d.update(discount_pct=0, discount_amount=rng.choice([50, 123.45]))
    return d


def rnd_items(rng, base_id, n, percent):
    out = [{"id": base_id + i, "kind": "service", "title": "p", "qty": rng.choice([1, 2, 3, 0.5, 1.5, 7, 2.25]),
            "rate": rng.choice([100, 333.33, 77.77, 19.99, 1250, 49.5, 33.33, 16.67]), "tax": rng.choice(["standard", "standard", "reduced"]),
            "unit": "day", "in_markup": rng.choice([0, 1]), "in_handling": rng.choice([0, 1]), "raw_fee": rng.choice([0, 1]),
            "producing": rng.choice([0, 1]), "discountable": rng.choice([1, 1, 0]), "discount_pct": rng.choice([0, 0, 0, 10, 33.3]),
            "intext": rng.choice(["intern", "extern"])} for i in range(n)]
    if percent:
        out.append({"id": base_id + 99, "kind": "service", "unit": "percent", "rate": 5, "tax": "standard", "qty": 1, "title": "KSK"})
    return out


rng = random.Random(6300)
for cur in ("EUR", "USD", "HUF"):
    for mode in ("full", "title", "summary"):
        bad, n, worst = 0, 0, D(0)
        for k in range(80):
            r = rnd_doc(rng, cur, None if cur == "EUR" else round(rng.uniform(0.8, 1.4), 4) if cur == "USD" else round(rng.uniform(150, 420), 2))
            parts, pi, items = [], {}, []
            for p in range(rng.randint(1, 3)):
                pid = 10 + p
                st = {"discount_pct": rng.choice([5, 12.5])} if rng.random() < 0.3 else {}
                if rng.random() < 0.3:
                    st["mk_per_part"] = 1  # the former surcharge per part (a quotation from before #6281)
                parts.append({"id": pid, "kind": "items", "title": f"T{p}", "print": rng.choice([1, 1, 0]), "settings": st})
                pi[pid] = rnd_items(rng, pid * 100, rng.randint(1, 25), rng.random() < 0.3)
                items.append({"id": p + 1, "kind": "part", "ref_part_id": pid, "qty": rng.choice([1, 2, 3, 1.5, 0.5]), "unit": "piece",
                              "title": f"T{p}", "discountable": rng.choice([1, 1, 0])})
            items += rnd_items(rng, 50, rng.randint(0, 2), False)
            o, i = compare(r, items, parts, pi, mode)
            n += 1
            if not same(o, i):
                bad += 1
                worst = max(worst, abs(o[0] - i[0]), abs(o[1] - i[1]))
        check(bad == 0, f"{n} quotations with parts in {cur}, invoice form {mode}: invoice = quotation (net, tax per rate, gross), "
                        f"{bad} deviate (worst {worst})")

sys.exit(done("p21287_c_rundung"))
