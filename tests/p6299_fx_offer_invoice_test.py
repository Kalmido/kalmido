#!/usr/bin/env python3
# kalmido-suite: after=office_calc nodata
"""2.1254.0 (#6299, audit #4740 F1): an invoice from a quotation in a foreign currency equals the quotation to the cent.
The quotation computes its automatic lines (producing, handling / markup, raw data, discount per tax key, a percent position)
in its own currency; the invoice took them from a second run in the home currency and converted them with the rate again
(rounded twice: 1 x 80.00 EUR, rate 1.0837, 5 % discount -> quotation 82.36 / 98.01 USD, invoice 82.37 / 98.02). Now each
such line's rate = its amount / the rate (calc_home_rate, like the deductions of a final invoice #4082).
 - a fixed example (the audit's) and a seeded random comparison of some hundred quotations in USD (and a few in a currency
   with a large rate): net, every tax line and gross of the invoice (rates stored as floats like _put_rows) = the quotation's
 - flat price quotations (one position per tax rate) and quotations with parts in all three invoice forms (summary / title /
   full, part quantities with halves), in USD, HUF and the home currency
 - home currency: the positions are exactly those of before (the reference below is the code of 2.1252.0)
Pure Python, no server: the functions are lifted from kalmido/office/invoices.py and parts.py with fictional data.
usage: python3 tests/p6299_fx_offer_invoice_test.py   (KALMIDO_SRC=<dir with kalmido/> to test another tree)"""
import ast
import importlib.util
import json
import os
import random
import sys
import types
from decimal import Decimal

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


def stored(items):
    """The positions as the database keeps them (invoices._put_rows: qty / rate / cost as float)."""
    return [{**x, "qty": float(D(str(x.get("qty") if x.get("qty") is not None else 1))), "rate": float(D(str(x.get("rate") or 0)))} for x in items]


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
ex = [{"id": 1, "kind": "service", "title": "Schnitt", "qty": 1, "rate": 80, "tax": "standard", "unit": "day", "discountable": 1, "intext": "intern"}]
o, i = compare(row(currency="USD", fx_rate=1.0837, discount_pct=5), ex)
check(o[0] == D("82.36") and o[1] == D("98.01"), f"the quotation: 82.36 net / 98.01 gross USD, got {o[0]} / {o[1]}")
check(i[0] == D("82.36") and i[1] == D("98.01"), f"its invoice the same: 82.36 / 98.01 USD (was 82.37 / 98.02), got {i[0]} / {i[1]}")


# ---------------------------------------------------------------- 2. seeded random quotations
def rnd_doc(rng, cur, fx):
    d = row(currency=cur, fx_rate=fx, discount_pct=rng.choice([0, 0, 5, 7.5, 10]), markup_pct=rng.choice([None, 10, 12.5]),
            handling_pct=rng.choice([None, None, 8]), markup_stacked=rng.choice([0, 1]), raw_mode=rng.choice(["none", "included", "optional"]),
            producing_on=rng.choice([0, 1]), producing_mode=rng.choice([None, None, "amount"]))
    if rng.random() < 0.2:
        d.update(discount_pct=0, discount_amount=rng.choice([50, 99.99, 123.45]))
    return d


def rnd_items(rng, base_id=1, n=None, percent=True):
    out = []
    for i in range(n or rng.randint(1, 6)):
        out.append({"id": base_id + i, "kind": "service", "title": "p", "qty": rng.choice([1, 2, 3, 0.5, 1.5, 7, 2.25]),
                    "rate": rng.choice([100, 333.33, 77.77, 19.99, 1250, 0.125, 49.5]), "tax": rng.choice(["standard", "standard", "reduced", "exempt"]),
                    "unit": "day", "in_markup": rng.choice([0, 1]), "in_handling": rng.choice([0, 1]), "raw_fee": rng.choice([0, 1]),
                    "producing": rng.choice([0, 1]), "discountable": rng.choice([1, 1, 0]), "discount_pct": rng.choice([0, 0, 0, 10, 33.3]),
                    "intext": rng.choice(["intern", "extern"])})
    if percent and rng.random() < 0.2:
        out.append({"id": base_id + 99, "kind": "service", "unit": "percent", "rate": 5, "tax": "standard", "qty": 1, "title": "KSK"})
    return out


rng = random.Random(6299)
bad, n, worst = 0, 0, D(0)
for k in range(400):
    cur, fx = ("USD", round(rng.uniform(0.8, 1.4), 4)) if k % 10 else ("HUF", round(rng.uniform(150, 420), 2))  # + a large rate
    r = rnd_doc(rng, cur, fx)
    o, i = compare(r, rnd_items(rng))
    n += 1
    if not same(o, i):
        bad += 1
        worst = max(worst, abs(o[0] - i[0]), abs(o[1] - i[1]))
check(bad == 0, f"{n} random quotations in USD / HUF: the invoice equals the quotation (net, tax per rate, gross): {bad} deviate (worst {worst})")

# flat price quotations (#5817): one position per tax rate
bad = 0
for k in range(150):
    r = rnd_doc(rng, "USD", round(rng.uniform(0.8, 1.4), 4))
    r["flat_print"] = 1
    o, i = compare(r, rnd_items(rng))
    bad += 0 if same(o, i) else 1
check(bad == 0, f"150 flat price quotations in USD: invoice = quotation, {bad} deviate")

# quotations with parts in every invoice form (summary: one position per tax rate; title: a part = its amount x its qty;
# full: the part's positions with its producing / surcharges / discount x its qty, the rest cent on the last one); part
# quantities with halves (a half cent per unit must not be left to a float rate), USD / HUF and the home currency
for mode in ("summary", "title", "full"):
    for cur in ("USD", "HUF", "EUR"):
        bad = 0
        for k in range(60):
            r = rnd_doc(rng, cur, round(rng.uniform(0.8, 1.4), 4) if cur == "USD" else round(rng.uniform(150, 420), 2) if cur == "HUF" else None)
            parts, pi, items = [], {}, []
            for p in range(rng.randint(1, 3)):
                pid = 10 + p
                parts.append({"id": pid, "kind": "items", "title": f"T{p}", "print": rng.choice([1, 1, 0]),
                              "settings": {"discount_pct": rng.choice([0, 5, 12.5])} if rng.random() < 0.3 else {}})
                pi[pid] = rnd_items(rng, pid * 100, percent=rng.random() < 0.3)
                items.append({"id": p + 1, "kind": "part", "ref_part_id": pid, "qty": rng.choice([1, 2, 3, 1.5, 0.5]), "unit": "piece", "title": f"T{p}",
                              "discountable": rng.choice([1, 1, 0])})
            items += rnd_items(rng, 50, rng.randint(1, 2))
            o, i = compare(r, items, parts, pi, mode)
            bad += 0 if same(o, i) else 1
        check(bad == 0, f"60 quotations with parts in {cur}, invoice form {mode}: invoice = quotation, {bad} deviate")
DB.update(parts=[], part_items={})


# ---------------------------------------------------------------- 3. home currency: exactly the positions of before
def old_items(r, items):
    """inv_items_from_offer of 2.1252.0 (no parts, not flat): the automatic lines of a run in the home currency."""
    d = _calc_doc(r)
    d["currency"] = d["home"]
    lines = calc.office_calc(d, items)["lines"]
    dec, TAX_KEYS = calc.dec, calc.TAX_KEYS
    pct = {ln.get("id"): ln for ln in lines if ln.get("kind") == "item" and ln.get("pct") is not None}
    out = []
    for it in items:
        row_ = {k: it.get(k) for k in ("kind", "service_id", "title", "detail", "qty", "unit", "rate", "tax", "intext", "cost", "discount_pct")}
        row_.update(raw_fee=0, producing=0, discountable=1)
        if it.get("unit") == "percent" and it.get("id") in pct:
            row_.update(qty=1, unit="flat", rate=pct[it["id"]]["total"], discount_pct=0)
        out.append(row_)
    for ln in lines:
        if ln["kind"] == "producing":
            out.append({"kind": "service", "qty": ln["qty"], "unit": "day", "rate": ln["rate"], "tax": "standard"})
        elif ln["kind"] == "surcharge":
            for k, v in (ln.get("by_tax") or {"standard": ln["total"]}).items():
                out.append({"kind": "service", "qty": 1, "unit": "flat", "rate": dec(v), "tax": k if k in TAX_KEYS else "standard"})
        elif ln["kind"] == "raw" and not ln.get("optional"):
            out.append({"kind": "service", "qty": 1, "unit": "flat", "rate": ln["total"], "tax": "standard"})
        elif ln["kind"] == "discount":
            for k, v in (ln.get("by_tax") or {"standard": abs(dec(ln["total"]))}).items():
                out.append({"kind": "discount", "qty": 1, "unit": "flat", "rate": abs(dec(v)), "tax": k if k in TAX_KEYS else "standard"})
    return [(x["kind"], x.get("unit"), D(str(x.get("qty") if x.get("qty") is not None else 1)), D(str(x.get("rate") or 0)), x.get("tax")) for x in out]


bad, dev = 0, 0
for k in range(300):
    r = rnd_doc(rng, "EUR", None)
    items = rnd_items(rng)
    DB.update(items=items, settings={})
    now = [(x["kind"], x.get("unit"), D(str(x.get("qty") if x.get("qty") is not None else 1)), D(str(x.get("rate") or 0)), x.get("tax"))
           for x in inv_items_from_offer(None, 1, r)]
    bad += 0 if now == old_items(r, items) else 1
    o, i = compare(r, items)
    dev += 0 if same(o, i) else 1
check(bad == 0, f"home currency: 300 random quotations give exactly the positions of before, {bad} differ")
check(dev == 0, f"home currency: invoice = quotation, {dev} deviate")

sys.exit(done("p6299_fx_offer_invoice"))
