#!/usr/bin/env python3
# kalmido-suite: fresh
"""2.1249.0 API tests (#6281): a quotation with parts has its surcharge ("Zuschlag", markup) as ONE line on the title page:
the percent of the title page's marked positions plus the part lines (each with its full net x qty, the part's handling
costs included); the parts show no surcharge line of their own; the handling costs stay per part and on the title page.
Once in the personal office of a person without an organisation (freelancer fixture; freelancer-matrix: office) and once
in an organisation's office (its admin). Invented companies, people and figures only.
 - the calculator alone (calc.office_calc with doc["mk_extra"]): the extra base joins the marked positions, the line is
   spread over the tax keys and says "... und die Teilangebote"; stacked on the handling costs it says so too
 - a quotation (title page "Regie" 1000.00 at 19 %, part A "Schnitt" 2 x 500.00 at 19 %, part B "Buchlizenz" 400.00 at
   7 % twice on the title page), 15 %: one line 420.00 (300.00 at 19 %, 120.00 at 7 %), the parts have none, net 3220.00
 - with handling costs of 10 % (per part and on the title page as before): the markup takes the parts' nets including
   their handling costs: 15 % of (1000 + 1100 + 2 x 440) = 447.00
 - the invoice from the quotation (as the quotation: the parts' positions) has the surcharge once per tax rate and the
   quotation's net; a finalised quotation keeps the one line
 - 2.1287.0 (#6443): a quotation from before (cached totals without "mk_title", 2 parts of 10,000.00 with 2,000.00 marked
   each, 15 %: 20,600.00 by the former rule, 23,000.00 by the one line) that left the draft without being finalised
   (status accepted / sent by hand): a change, opening it (GET writes nothing), its print model and its invoices (all three
   forms) keep 20,600.00; finalised, its invoice = the frozen net / gross; a draft from before moves to the one line
   (23,000.00, mk_title) when it is opened
 - 2.1309.0 (#6490): the markup line shows "15 %" | the base | the amount (10,305.00 x 15 % = 1,545.75) in the calculator, the
   print model, the PDF and the invoice from the quotation (its position keeps the percentage and the base: "15 %" | 10.305,00
   | 1.545,75 while it stays 1 flat at that amount; edited, it prints as it is); the e-invoice keeps quantity 1 x 1,545.75
   (EN 16931: quantity x price = line net); handling costs stay "1 pauschal"; a quotation that left the draft before (cached
   totals without "mk_pct_line") keeps "1 pauschal" in its print model and invoices; a draft from before that is set to sent
   takes the new line (computed once more first); with parts: one invoice position per tax rate with its own base
usage: p21249_zuschlag_teile_test.py <datadir>"""
import importlib.util
import os
import re
import sys
from decimal import Decimal

N = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, N)
from freelancer_fixture import FEATURES, freelancer  # noqa: E402
from kt import FAILS, OKS, check, sess  # noqa: E402
import requests  # noqa: E402
import dbx as dbxm  # noqa: E402  2.1287.0 (#6443)

SRC = os.environ.get("KALMIDO_SRC") or os.path.join(N, "..")
B = "http://127.0.0.1:" + os.environ.get("KALMIDO_TEST_PORT", "3048")
H = {"X-Requested-With": "kalmido"}
OFC = "/api/office"
D = OFC + "/docs"
COMPANY = {"name": "Studio Nordlicht", "street": "Hafenstraße 12", "zip": "20457", "city": "Hamburg", "country": "DE",
           "email": "hallo@nordlicht.example", "phone": "+49 40 000000", "tax_number": "12/345/67890", "vat_id": "DE999999999",
           "iban": "DE02120300000000202051", "bic": "BYLADEM1001", "bank_name": "Beispielbank"}


def load(name):
    spec = importlib.util.spec_from_file_location("p21249_" + name, os.path.join(SRC, "kalmido", "office", name + ".py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------- the calculator alone
calc = load("calc")
ein = load("einvoice")  # 2.1309.0 (#6490): ein_check of the stored XML
PACK = {"tax": {"standard": 19, "reduced": 7, "exempt": 0}}
ITS = [{"title": "Regie", "qty": 1, "rate": 1000, "unit": "flat", "in_markup": 1}]
t = calc.office_calc({"lang": "de", "markup_pct": 15, "mk_extra": {"standard": Decimal(1000), "reduced": Decimal(800)}}, ITS, PACK)
sur = [x for x in t["lines"] if x["kind"] == "surcharge"]
check(len(sur) == 1 and sur[0]["total"] == 420 and sur[0]["by_tax"] == {"standard": 300, "reduced": 120},
      f"calc: one line 15 % of 2800.00 = 420.00 (300.00 + 120.00): {sur}")
check(sur and sur[0]["detail"] == "15 % auf die markierten Positionen und die Teilangebote", f"calc: the detail names the parts: {sur and sur[0]['detail']}")
check(t["net"] == 1420 and t["items_net"] == 1000, f"calc: the extra base is no position (net 1000 + 420): {t['net']} {t['items_net']}")
t0 = calc.office_calc({"lang": "de", "markup_pct": 15}, ITS, PACK)
check([x["detail"] for x in t0["lines"] if x["kind"] == "surcharge"] == ["15 % auf die markierten Positionen"], "calc: without parts as before")
t2 = calc.office_calc({"lang": "de", "markup_pct": 10, "handling_pct": 10, "markup_stacked": 1, "mk_extra": {"standard": Decimal(500)}},
                      [dict(ITS[0], in_handling=1)], PACK)
s2 = {x["slot"]: x for x in t2["lines"] if x["kind"] == "surcharge"}
check(s2["handling"]["total"] == 100 and s2["markup"]["total"] == 160
      and s2["markup"]["detail"] == "10 % auf die markierten Positionen, die Teilangebote und die Handlungskosten",
      f"calc: stacked: 10 % of (1000 + 500 + 100) = 160.00, the detail says so: {s2}")
# 2.1309.0 (#6490): "15 %" | base | amount; the handling costs stay "1 pauschal"; the base per tax key for the invoice
check(sur[0]["qty_text"] == "15 %" and sur[0]["unit_text"] == "" and sur[0]["sur_base"] == 2800 and sur[0]["by_base"] == {"standard": 2000, "reduced": 800},
      f"calc #6490: the markup 15 % of 2800.00 with its base per tax key: {sur}")
check(s2["markup"]["qty_text"] == "10 %" and s2["markup"]["sur_base"] == 1600 and s2["handling"]["qty_text"] == "1"
      and s2["handling"]["unit_text"] == "pauschal" and "sur_base" not in s2["handling"],
      f"calc #6490: stacked: the base takes the handling costs (1600.00), the handling line stays 1 pauschal: {s2}")
t3 = calc.office_calc({"lang": "de", "markup_pct": 15}, [{"title": "Kamera", "qty": 1, "rate": 10305, "unit": "flat", "in_markup": 1}], PACK)
s3 = [x for x in t3["lines"] if x["kind"] == "surcharge"]
check(len(s3) == 1 and s3[0]["qty_text"] == "15 %" and s3[0]["sur_base"] == 10305 and s3[0]["total"] == 1545.75 and s3[0]["rate"] == 1545.75
      and s3[0]["qty"] == 1 and t3.get("mk_pct_line") == 1,
      f"calc #6490: 15 % | 10305.00 | 1545.75, the numbers stay 1 x 1545.75: {s3}")
t4 = calc.office_calc({"lang": "de", "markup_pct": 15, "mk_flat_line": 1}, [{"title": "Kamera", "qty": 1, "rate": 10305, "unit": "flat", "in_markup": 1}], PACK)
s4 = [x for x in t4["lines"] if x["kind"] == "surcharge"]
check(s4 and s4[0]["qty_text"] == "1" and s4[0]["unit_text"] == "pauschal" and "sur_base" not in s4[0] and "mk_pct_line" not in t4,
      f"calc #6490: a quotation sent with the former line keeps 1 pauschal: {s4}")
# the invoice position: shown as "15 %" while it is 1 flat at base x percent; edited, as it is
IV = {"title": "Zuschlag", "qty": 1, "unit": "flat", "rate": 1545.75, "sur_pct": 15, "sur_base": 10305}
li = calc.inv_calc({"lang": "de"}, [IV], PACK)["lines"][0]
check(li["qty_text"] == "15 %" and li["unit_text"] == "" and li["rate_text"] == calc.fmt_money(10305, "de", "EUR") and li["rate"] == 1545.75
      and li["total"] == 1545.75, f"inv_calc #6490: 15 % | 10.305,00 | 1.545,75, the rate stays the amount: {li}")
for chg in ({"rate": 1600}, {"qty": 2}, {"unit": "piece"}, {"discount_pct": 10}):
    li = calc.inv_calc({"lang": "de"}, [dict(IV, **chg)], PACK)["lines"][0]
    check(li["qty_text"] != "15 %" and "sur_base" not in li, f"inv_calc #6490: edited ({chg}): printed as it is: {li.get('qty_text')}")


def surs(totals):
    return [x for x in (totals or {}).get("lines") or [] if x.get("kind") == "surcharge"]


def run(S, who):
    def ok(cond, what):
        check(cond, f"{who}: {what}")

    r = S.put(B + OFC + "/settings", json={"company": {"name": COMPANY["name"]}, "lang": "de", "currency": "EUR", "payment_days": 14,
                                         "company_fields": COMPANY, "industry_packs": []})
    ok(r.ok, "office settings " + r.text[:200])
    r = S.post(B + "/api/clients", json={"name": "Beispielkunde AG", "street": "Marktstraße 5", "zip": "50667", "city": "Köln", "country": "DE"})
    assert r.status_code == 201, r.text
    r = S.post(B + D, json={"client_id": r.json()["id"], "project_title": "Imagefilm", "raw_mode": "none", "producing_on": 0,
                            "service_from": "2026-10-01", "service_to": "2026-10-20"})
    assert r.status_code == 201, r.text
    OF = r.json()["id"]
    pids = []
    for title in ("Modul A", "Modul B"):
        r = S.post(B + f"{D}/{OF}/parts", json={"kind": "items", "title": title})
        ok(r.status_code in (200, 201), f"part {title} created {r.status_code} {r.text[:160]}")
        pids.append((r.json().get("part") or {}).get("id"))
    PA, PB = pids
    ok(S.put(B + f"{D}/{OF}/parts/{PA}/items", json={"items": [{"title": "Schnitt", "qty": 2, "rate": 500, "unit": "day"}]}).ok, "part A: its position")
    ok(S.put(B + f"{D}/{OF}/parts/{PB}/items", json={"items": [{"title": "Buchlizenz", "qty": 1, "rate": 400, "unit": "flat", "tax": "reduced"}]}).ok,
       "part B: its position")
    d = S.get(B + f"{D}/{OF}").json()
    title = [{k: x.get(k) for k in ("id", "kind", "title", "qty", "unit", "ref_part_id")} for x in d.get("items") or []]
    for x in title:
        if x.get("ref_part_id") == PB:
            x["qty"] = 2
    r = S.put(B + f"{D}/{OF}/items", json={"items": [{"title": "Regie", "qty": 1, "rate": 1000, "unit": "flat"}] + title,
                                            "parts_known": [PA, PB]})
    ok(r.ok, "title page: Regie + the two part lines (B twice) " + r.text[:200])
    r = S.patch(B + f"{D}/{OF}", json={"markup_pct": 15})
    ok(r.ok, "the surcharge 15 % on " + r.text[:200])
    d = S.get(B + f"{D}/{OF}").json()
    t = d.get("totals") or {}
    sl = surs(t)
    ok(len(sl) == 1 and sl[0]["total"] == 420 and sl[0]["by_tax"] == {"standard": 300, "reduced": 120},
       f"one surcharge line on the title page: 15 % of 2800.00 = 420.00 (300.00 at 19 %, 120.00 at 7 %): {sl}")
    ok(not any(surs(p.get("totals")) for p in d.get("parts") or []), f"the parts show no surcharge line: {[surs(p.get('totals')) for p in d.get('parts') or []]}")
    tl = {x["rate_key"]: x["base"] for x in t.get("tax_lines") or []}
    ok(t.get("net") == 3220 and tl == {"standard": 2300, "reduced": 920}, f"net 3220.00, bases per rate: {t.get('net')} {tl}")
    rd = S.get(B + f"{D}/{OF}/render").json()
    ok(len([x for x in rd.get("lines") or [] if x.get("kind") == "surcharge"]) == 1, "the print model has the one line")
    ok([(x.get("qty_text"), x.get("rate_text")) for x in rd.get("lines") or [] if x.get("kind") == "surcharge"] == [("15 %", calc.fmt_money(2800, "de", "EUR"))],
       "#6490: the print model shows 15 % of 2.800,00 (title page and parts)")
    ok(not any(x.get("kind") == "surcharge" for p in rd.get("parts") or [] for x in p.get("lines") or []), "the printed parts have none")
    p = S.get(B + f"{D}/{OF}/pdf")
    ok(p.ok and p.content.startswith(b"%PDF-"), f"the PDF of the quotation {p.status_code}")

    # handling costs stay per part and on the title page; the markup takes the parts' nets with them
    r = S.patch(B + f"{D}/{OF}", json={"handling_pct": 10})
    ok(r.ok, "handling costs 10 % " + r.text[:200])
    d = S.get(B + f"{D}/{OF}").json()
    t = d.get("totals") or {}
    by = {x.get("slot"): x for x in surs(t)}
    ok(set(by) == {"handling", "markup"} and by["handling"]["total"] == 100 and by["markup"]["total"] == 447,
       f"title page: handling 100.00 on Regie, markup 15 % of (1000 + 1100 + 2 x 440) = 447.00: {by}")
    pt = {p["id"]: [x.get("slot") for x in surs(p.get("totals"))] for p in d.get("parts") or []}
    ok(pt == {PA: ["handling"], PB: ["handling"]}, f"each part keeps its handling line, no markup: {pt}")
    ok(t.get("net") == 3527, f"net 1000 + 100 + 1100 + 880 + 447 = 3527.00: {t.get('net')}")
    r = S.patch(B + f"{D}/{OF}", json={"handling_pct": None})
    ok(r.ok and r.json()["totals"]["net"] == 3220, "handling off again: net 3220.00")

    # the invoice from the quotation: the surcharge once per tax rate, the quotation's sums
    r = S.post(B + f"{D}/{OF}/invoice", json={"force": True, "parts_mode": "full"})
    ok(r.status_code == 201, "invoice from the quotation " + r.text[:200])
    if r.status_code == 201:
        iv = r.json()
        sp = sorted((x["tax"], float(x["rate"])) for x in iv.get("items") or [] if x.get("title") == "Zuschlag")
        ok(sp == [("reduced", 120.0), ("standard", 300.0)], f"the surcharge as one position per rate: {sp}")
        # 2.1309.0 (#6490): each with its own base: 15 % of 2000.00 (19 %) and of 800.00 (7 %)
        zl = sorted((x["tax"], x.get("qty_text"), x.get("sur_base")) for x in (iv.get("totals") or {}).get("lines") or [] if x.get("title") == "Zuschlag")
        ok(zl == [("reduced", "15 %", 800), ("standard", "15 %", 2000)], f"#6490: the invoice shows 15 % and the base per rate: {zl}")
        ok((iv.get("totals") or {}).get("net") == "3220.00", f"the invoice's net = the quotation's: {(iv.get('totals') or {}).get('net')}")
        S.delete(B + f"{D}/{iv['id']}")
    r = S.post(B + f"{D}/{OF}/finalize")
    ok(r.ok, "the quotation finalised " + r.text[:200])
    d = S.get(B + f"{D}/{OF}").json()
    ok(len(surs(d.get("totals"))) == 1 and d["totals"].get("net") == 3220, "finalised: still the one line, net 3220.00")
    ok(d["totals"].get("mk_title") == 1 and not any(x.get("slot") == "markup" for p in d.get("parts") or [] for x in surs(p.get("totals"))),
       "finalised: the frozen totals say one markup line (mk_title), the frozen parts have none")
    rd = S.get(B + f"{D}/{OF}/render").json()
    ok(not any(x.get("kind") == "surcharge" for p in rd.get("parts") or [] for x in p.get("lines") or []), "finalised: the printed parts have none")
    r = S.post(B + f"{D}/{OF}/invoice", json={"force": True, "parts_mode": "title"})
    ok(r.status_code == 201 and (r.json().get("totals") or {}).get("net") == "3220.00", f"invoice from the finalised quotation: net 3220.00 {r.text[:200]}")


def dbx(sql, args=()):
    return dbxm.connect(sys.argv[1]).execute(sql, args).fetchall()


def legacy_6443(S, who):
    """2.1287.0 (#6443): a quotation from before #6281 that is no draft any more keeps the markup per part."""
    def ok(cond, what):
        check(cond, f"#6443 {who}: {what}")

    def strip(did, status=None):  # the state a quotation saved before 2.1249 has: its totals without mk_title
        dbx("UPDATE office_docs SET totals=(totals::jsonb - 'mk_title')::text" + (", status=?" if status else "") + " WHERE id=?",
            ((status,) if status else ()) + (did,))

    def net(d):
        return Decimal(str((d.get("totals") or {}).get("net")))

    r = S.post(B + "/api/clients", json={"name": "Altkunde GmbH", "street": "Altweg 1", "zip": "50667", "city": "Köln", "country": "DE"})
    cl = r.json()["id"]

    def offer(title):
        r = S.post(B + D, json={"client_id": cl, "project_title": title, "raw_mode": "none", "producing_on": 0, "service_from": "2026-10-01"})
        assert r.status_code == 201, r.text
        did = r.json()["id"]
        pids = [(S.post(B + f"{D}/{did}/parts", json={"kind": "items", "title": t}).json().get("part") or {}).get("id") for t in ("Teil 1", "Teil 2")]
        for pid in pids:
            ok(S.put(B + f"{D}/{did}/parts/{pid}/items", json={"items": [
                {"title": "Technik", "qty": 1, "rate": 8000, "unit": "flat", "in_markup": 0},
                {"title": "Regie", "qty": 1, "rate": 2000, "unit": "flat", "in_markup": 1}]}).ok, "part positions")
        ok(S.patch(B + f"{D}/{did}", json={"markup_pct": 15}).ok, "markup 15 %")
        d = S.get(B + f"{D}/{did}").json()
        ok(net(d) == 23000 and d["totals"].get("mk_title") == 1, f"a new quotation: the one line, 23000.00: {net(d)}")
        return did

    # accepted by hand, never finalised: a change keeps the former rule
    OA = offer("Alt angenommen")
    strip(OA, "accepted")
    ok(S.patch(B + f"{D}/{OA}", json={"project_title": "Alt angenommen (geändert)"}).ok, "a change of the accepted quotation")
    d = S.get(B + f"{D}/{OA}").json()
    ok(net(d) == 20600 and not d["totals"].get("mk_title"), f"accepted: the markup per part stays (20600.00): {net(d)}")
    ok(not any(x.get("kind") == "surcharge" for x in d["totals"].get("lines") or []), "accepted: no markup line on the title page")
    # sent by hand: opening writes nothing, the print model and the invoices keep the sum
    dbx("UPDATE office_docs SET status='sent' WHERE id=?", (OA,))
    before = dbx("SELECT totals, updated_at FROM office_docs WHERE id=?", (OA,))[0]
    d = S.get(B + f"{D}/{OA}").json()
    after = dbx("SELECT totals, updated_at FROM office_docs WHERE id=?", (OA,))[0]
    ok(net(d) == 20600 and tuple(before) == tuple(after), f"sent: opening shows 20600.00 and writes nothing: {net(d)}")
    rd = S.get(B + f"{D}/{OA}/render").json()
    ok(Decimal(str(rd["totals"]["net"])) == 20600, f"sent: the print model (PDF, client's view) 20600.00: {rd['totals']['net']}")
    ok(S.get(B + f"{D}/{OA}/pdf").content.startswith(b"%PDF-"), "sent: the PDF")
    gross = Decimal(str(rd["totals"]["gross"]))
    for mode in ("full", "title", "summary"):
        r = S.post(B + f"{D}/{OA}/invoice", json={"force": True, "parts_mode": mode})
        ok(r.status_code == 201, f"sent: invoice {mode} " + r.text[:200])
        if r.status_code == 201:
            t = r.json().get("totals") or {}
            ok(Decimal(str(t.get("net"))) == 20600 and Decimal(str(t.get("gross"))) == gross,
               f"sent: invoice {mode} = the quotation 20600.00 / {gross}: {t.get('net')} / {t.get('gross')}")
            S.delete(B + f"{D}/{r.json()['id']}")
    # finalised: the frozen sums, its invoice the same
    dbx("UPDATE office_docs SET status='accepted' WHERE id=?", (OA,))
    r = S.post(B + f"{D}/{OA}/finalize")
    ok(r.ok, "the old quotation finalised " + r.text[:200])
    d = S.get(B + f"{D}/{OA}").json()
    ok(net(d) == 20600 and not d["totals"].get("mk_title"), f"finalised: frozen by the former rule, 20600.00: {net(d)}")
    for mode in ("full", "title", "summary"):
        r = S.post(B + f"{D}/{OA}/invoice", json={"force": True, "parts_mode": mode})
        t = (r.json().get("totals") or {}) if r.status_code == 201 else {}
        ok(r.status_code == 201 and Decimal(str(t.get("net"))) == 20600 and Decimal(str(t.get("gross"))) == Decimal(str(d["totals"]["gross"])),
           f"finalised: invoice {mode} = the frozen net / gross: {t.get('net')} / {t.get('gross')} {r.text[:120] if r.status_code != 201 else ''}")
    # (review) a NEW quotation that had no parts when it was accepted by hand: its first part takes the new rule (its totals
    # carried no mk_title only because it had no parts - nothing was ever sent by the former rule)
    r = S.post(B + D, json={"client_id": cl, "project_title": "Neu ohne Teile", "raw_mode": "none", "producing_on": 0, "service_from": "2026-10-01"})
    assert r.status_code == 201, r.text
    ON = r.json()["id"]
    ok(S.patch(B + f"{D}/{ON}", json={"markup_pct": 15}).ok, "new without parts: markup 15 %")
    dbx("UPDATE office_docs SET status='accepted' WHERE id=?", (ON,))
    pid = (S.post(B + f"{D}/{ON}/parts", json={"kind": "items", "title": "Teil 1"}).json().get("part") or {}).get("id")
    ok(pid and S.put(B + f"{D}/{ON}/parts/{pid}/items", json={"items": [
        {"title": "Technik", "qty": 1, "rate": 8000, "unit": "flat", "in_markup": 0},
        {"title": "Regie", "qty": 1, "rate": 2000, "unit": "flat", "in_markup": 1}]}).ok, "new without parts: accepted by hand, then its first part")
    d = S.get(B + f"{D}/{ON}").json()
    ok(net(d) == 11500 and d["totals"].get("mk_title") == 1, f"new, accepted before its first part: the one markup line (11500.00), not the former rule (10300.00): {net(d)}")
    # a draft from before moves to the one line when it is opened
    OD = offer("Alt Entwurf")
    strip(OD)
    d = S.get(B + f"{D}/{OD}").json()
    ok(net(d) == 23000 and d["totals"].get("mk_title") == 1, f"a draft from before: opening moves it to the one line (23000.00): {net(d)}")


def pct_line_6490(S, who):
    """2.1309.0 (#6490): the decision's example: 15 % of 10,305.00 = 1,545.75 on the quotation, its PDF, the invoice and its e-invoice."""
    def ok(cond, what):
        check(cond, f"#6490 {who}: {what}")

    def zline(lines, title="Zuschlag"):
        return next((x for x in lines or [] if x.get("title") == title), {})

    def offer(title):
        r = S.post(B + D, json={"client_id": cl, "project_title": title, "raw_mode": "none", "producing_on": 0, "service_from": "2026-10-01"})
        assert r.status_code == 201, r.text
        did = r.json()["id"]
        ok(S.put(B + f"{D}/{did}/items", json={"items": [{"title": "Kamera", "qty": 1, "rate": 10305, "unit": "flat", "in_markup": 1, "in_handling": 1}]}).ok,
           "the position")
        ok(S.patch(B + f"{D}/{did}", json={"markup_pct": 15, "handling_pct": 10}).ok, "markup 15 %, handling costs 10 %")
        return did

    r = S.post(B + "/api/clients", json={"name": "Prozentkunde GmbH", "street": "Rechenweg 3", "zip": "50667", "city": "Köln", "country": "DE"})
    cl = r.json()["id"]
    OF = offer("Zuschlag Prozent")
    rd = S.get(B + f"{D}/{OF}/render").json()
    z, hu = zline(rd.get("lines")), next((x for x in rd.get("lines") or [] if x.get("slot") == "handling"), {})
    ok(z.get("qty_text") == "15 %" and z.get("unit_text") == "" and z.get("rate_text") == calc.fmt_money(10305, "de", "EUR")
       and z.get("total_text") == calc.fmt_money(1545.75, "de", "EUR") and not z.get("detail"),
       f"the print model: Zuschlag | 15 % | 10.305,00 € | 1.545,75 €, the calculation text internal: {z}")
    ok(hu.get("qty_text") == "1" and hu.get("unit_text") and hu.get("rate_text") == hu.get("total_text"),
       f"the handling costs stay 1 pauschal | amount | amount: {hu}")
    p = S.get(B + f"{D}/{OF}/pdf")
    ok(p.ok and p.content.startswith(b"%PDF-"), f"the PDF {p.status_code}")
    r = S.post(B + f"{D}/{OF}/invoice", json={"force": True})
    ok(r.status_code == 201, "invoice from the quotation " + r.text[:200])
    if r.status_code == 201:
        IV = r.json()["id"]
        it = zline(r.json().get("items"))
        ok(Decimal(str(it.get("sur_pct"))) == 15 and Decimal(str(it.get("sur_base"))) == 10305 and Decimal(str(it.get("rate"))) == Decimal("1545.75")
           and Decimal(str(it.get("qty"))) == 1, f"the invoice position: 1 x 1545.75, percent and base kept: {it}")
        rv = S.get(B + f"{D}/{IV}/render").json()
        z = zline(rv.get("lines"))
        ok(z.get("qty_text") == "15 %" and z.get("rate_text") == calc.fmt_money(10305, "de", "EUR") and z.get("total_text") == calc.fmt_money(1545.75, "de", "EUR"),
           f"the invoice's print model: 15 % | 10.305,00 € | 1.545,75 €: {z}")
        ok(Decimal(str(rv["totals"]["net"])) == Decimal("12881.25"), f"the invoice's net = the quotation's (10305 + 1030.50 + 1545.75): {rv['totals'].get('net')}")
        ok(S.patch(B + f"{D}/{IV}", json={"einvoice_format": "zugferd"}).ok, "the invoice as ZUGFeRD")
        ok(S.post(B + f"{D}/{IV}/finalize").ok, "the invoice finalised")
        x = S.get(B + f"{D}/{IV}/xml")
        ok(x.ok and ein.ein_check(x.content) == [], f"the e-invoice passes the own check: {x.status_code} {ein.ein_check(x.content) if x.ok else ''}")
        blk = next((b for b in x.content.decode().split("<ram:IncludedSupplyChainTradeLineItem>") if "<ram:Name>Zuschlag</ram:Name>" in b), "")
        q = re.search(r"<ram:BilledQuantity[^>]*>([^<]+)<", blk)
        pr = re.search(r"<ram:NetPriceProductTradePrice>\s*<ram:ChargeAmount>([^<]+)<", blk)
        ok(q and Decimal(q.group(1)) == 1 and pr and Decimal(pr.group(1)) == Decimal("1545.75") and "<ram:LineTotalAmount>1545.75<" in blk,
           f"the e-invoice keeps quantity 1 x 1545.75 (quantity x price = line net): {blk[:600]}")
        rv = S.get(B + f"{D}/{IV}/render").json()
        ok(zline(rv.get("lines")).get("qty_text") == "15 %", "the finalised invoice keeps its frozen line")
        # an edited position prints as it is
        r = S.post(B + f"{D}/{OF}/invoice", json={"force": True})
        I2 = r.json()["id"]
        its = [{k: x.get(k) for k in ("id", "kind", "title", "qty", "unit", "rate", "tax")} for x in r.json().get("items") or []]
        for x in its:
            if x["title"] == "Zuschlag":
                x["rate"] = 1600
        ok(S.put(B + f"{D}/{I2}/items", json={"items": its}).ok, "the invoice's surcharge edited to 1600.00")
        z = zline(S.get(B + f"{D}/{I2}/render").json().get("lines"))
        ok(z.get("qty_text") == "1" and z.get("rate_text") == z.get("total_text"), f"edited: 1 pauschal | 1.600,00 | 1.600,00: {z}")
        S.delete(B + f"{D}/{I2}")

    # a quotation sent before (its totals without "mk_pct_line"): unchanged, its invoice too
    OS = offer("Zuschlag alt versendet")
    dbx("UPDATE office_docs SET totals=(totals::jsonb - 'mk_pct_line')::text, status='sent' WHERE id=?", (OS,))
    z = zline(S.get(B + f"{D}/{OS}/render").json().get("lines"))
    ok(z.get("qty_text") == "1" and z.get("unit_text") and z.get("rate_text") == z.get("total_text") == calc.fmt_money(1545.75, "de", "EUR"),
       f"sent before: the print model keeps 1 pauschal | 1.545,75 | 1.545,75: {z}")
    r = S.post(B + f"{D}/{OS}/invoice", json={"force": True})
    ok(r.status_code == 201 and zline(r.json().get("items")).get("sur_pct") is None
       and zline((r.json().get("totals") or {}).get("lines")).get("qty_text") == "1", f"sent before: its invoice keeps 1 pauschal {r.text[:200]}")
    # a draft from before, set to sent: computed once more, it takes the new line and keeps it
    ODR = offer("Zuschlag Entwurf alt")
    dbx("UPDATE office_docs SET totals=(totals::jsonb - 'mk_pct_line')::text WHERE id=?", (ODR,))
    r = S.post(B + f"{D}/{ODR}/status", json={"status": "sent"})
    ok(r.ok, "the draft from before set to sent " + r.text[:200])
    ok(dbx("SELECT (totals::jsonb ->> 'mk_pct_line') FROM office_docs WHERE id=?", (ODR,))[0][0] == "1", "sent: its totals now say mk_pct_line")
    ok(zline(S.get(B + f"{D}/{ODR}/render").json().get("lines")).get("qty_text") == "15 %", "sent: it keeps 15 % | base | amount")


s0 = requests.Session()
s0.headers.update(H)
assert s0.post(B + "/api/auth/setup", json={"username": "alice", "display_name": "Alice Admin", "password": "password123"}).ok
A = sess("alice")
A.post(B + "/api/admin/setup", json={"lang": "en"})
FEAT = FEATURES if "office" in FEATURES else FEATURES + ",office"
A.patch(B + "/api/settings", json={"lang": "en", "features": FEAT, "tour": "done"})
ALICE = A.get(B + "/api/state").json()["me"]["id"]
r = A.post(B + "/api/admin/orgs", json={"name": "Alpha", "admin_id": ALICE})
assert r.status_code == 201, r.text
A.patch(B + "/api/settings", json={"workspace": f"org:{r.json()['id']}"})
FID, Fr = freelancer(B, A)

run(Fr, "freelancer")
run(A, "organisation")
legacy_6443(Fr, "freelancer")
legacy_6443(A, "organisation")
pct_line_6490(Fr, "freelancer")
pct_line_6490(A, "organisation")
print(f"p21249_zuschlag_teile: {OKS[0]} ok, {len(FAILS)} failed")
sys.exit(1 if FAILS else 0)
