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
usage: p21249_zuschlag_teile_test.py <datadir>"""
import importlib.util
import os
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
print(f"p21249_zuschlag_teile: {OKS[0]} ok, {len(FAILS)} failed")
sys.exit(1 if FAILS else 0)
