#!/usr/bin/env python3
# kalmido-suite: fresh
"""2.1228.0 API tests (#6254): the surcharge in percent ("Zuschlag", e.g. "Mehraufwand 15 %") as its own line of every
quotation, no industry pack needed; once in the personal office of a person without an organisation (freelancer fixture;
freelancer-matrix: office) and once in an organisation's office (its admin). Invented companies, people and figures only.
 - the calculator alone (calc.office_calc, calc.calc_spread): the default title "Zuschlag" / "Surcharge", the surcharge on
   the marked positions only, spread over their tax keys (19 % and 7 %: 150.00 + 75.00), the rest cent to the largest
   base; a quotation whose marked positions share one rate computes exactly as before (all at that rate)
 - without a pack: a new quotation has no surcharge; switched on (markup_pct 15, markup_label "Mehraufwand") it adds its
   line after the positions, before the discount (the discount takes the positions only), the tax per rate is right;
   an unmarked position is not in it; off (null) = no line
 - the invoice from the quotation: the surcharge as one position per rate, the sums are the quotation's; finalised, its
   XML has the line per rate and the own check (einvoice.ein_check) finds nothing; a progress invoice of 50 % takes half
   of the net including the surcharge
 - an agent's quotation draft (POST / PATCH /api/v1/office/offers) sets the surcharge with {pct, title}, null switches it
   off, a title alone keeps the percent, unknown keys / a title that is no text are refused (400)
 - 2.1299.0 (#6661): a quotation from before (cached totals without "sur_split": the surcharge all at 19 %, tax 324.75 /
   gross 2349.75 instead of 315.75 / 2340.75) that left the draft without being finalised (accepted / sent by hand): a
   change, opening it (writes nothing), its print model and its invoice keep the former tax; a draft moves to the split
usage: p6254_zuschlag_test.py <datadir>"""
import importlib.util
import os
import sys
from decimal import Decimal

N = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, N)
from freelancer_fixture import FEATURES, freelancer  # noqa: E402
from kt import FAILS, OKS, check, sess  # noqa: E402
import requests  # noqa: E402
import dbx as dbxm  # noqa: E402  2.1299.0 (#6661)

SRC = os.environ.get("KALMIDO_SRC") or os.path.join(N, "..")
B = "http://127.0.0.1:" + os.environ.get("KALMIDO_TEST_PORT", "3048")
H = {"X-Requested-With": "kalmido"}
OFC = "/api/office"
D = OFC + "/docs"
V1 = B + "/api/v1/office/offers"
TEST_IBAN = "DE02120300000000202051"
COMPANY = {"name": "Studio Nordlicht", "street": "Hafenstraße 12", "zip": "20457", "city": "Hamburg", "country": "DE",
           "email": "hallo@nordlicht.example", "phone": "+49 40 000000", "tax_number": "12/345/67890", "vat_id": "DE999999999",
           "iban": TEST_IBAN, "bic": "BYLADEM1001", "bank_name": "Beispielbank"}


def load(name):
    spec = importlib.util.spec_from_file_location("p6254_" + name, os.path.join(SRC, "kalmido", "office", name + ".py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------- the calculator alone
calc = load("calc")
ein = load("einvoice")
Z = Decimal
PACK = {"tax": {"standard": 19, "reduced": 7, "exempt": 0}}
ITS = [{"title": "Regie", "qty": 1, "rate": 1000, "unit": "flat", "in_markup": 1},
       {"title": "Buchlizenz", "qty": 1, "rate": 500, "unit": "flat", "tax": "reduced", "in_markup": 1},
       {"title": "Hotel", "qty": 1, "rate": 300, "unit": "flat", "in_markup": 0}]
t = calc.office_calc({"lang": "de", "markup_pct": 15, "raw_mode": "none", "producing_on": 0}, ITS, PACK)
sur = [x for x in t["lines"] if x["kind"] == "surcharge"]
check(len(sur) == 1 and sur[0]["title"] == "Zuschlag" and sur[0]["total"] == 225 and sur[0]["by_tax"] == {"standard": 150, "reduced": 75},
      f"calc: the default title 'Zuschlag', 15 % of 1500.00 = 225.00, 150.00 at 19 % and 75.00 at 7 % (the hotel is not in it): {sur}")
check(sur[0].get("mixed_tax") is True and sur[0].get("tax_pct") is None and t.get("sur_split") == 1, f"calc: a mixed line prints no single rate: {sur}")
tl = {x["rate_key"]: (x["base"], x["amount"]) for x in t["tax_lines"]}
check(t["net"] == 2025 and tl == {"standard": (1450, 275.5), "reduced": (575, 40.25)} and t["gross"] == 2340.75,
      f"calc: net 2025.00, 19 % on 1450.00 = 275.50, 7 % on 575.00 = 40.25, gross 2340.75: {t['net']} {tl} {t['gross']}")
# 2.1327.0 (#6816): the surcharge line by its kind (the positions' subtotal stands before it now)
check([x["title"] for x in calc.office_calc({"lang": "en", "markup_pct": 15}, ITS, PACK)["lines"] if x["kind"] == "surcharge"] == ["Surcharge"], "calc: 'Surcharge' in English")
# the same positions all at 19 %: exactly the calculation of before (one line, all at the standard rate)
t1 = calc.office_calc({"lang": "de", "markup_pct": 15, "markup_label": '{"de": "Mehraufwand", "en": "Extra work"}'},
                      [dict(x, tax="standard") for x in ITS], PACK)
s1 = next(x for x in t1["lines"] if x["kind"] == "surcharge")
check(s1["title"] == "Mehraufwand" and s1["tax"] == "standard" and s1["by_tax"] == {"standard": 225} and t1["net"] == 2025
      and [(x["rate_key"], x["base"]) for x in t1["tax_lines"]] == [("standard", 2025)], f"calc: one rate = as before, own title: {s1} {t1['tax_lines']}")
# review: a negative marked sum gives no surcharge (was -50.00 in the net without a line)
t3 = calc.office_calc({"lang": "de", "markup_pct": 10}, [{"title": "Gutschrift", "qty": 1, "rate": -500, "unit": "flat", "in_markup": 1}], PACK)
check(t3["net"] == -500 and t3["markup_total"] == 0 and not [x for x in t3["lines"] if x["kind"] == "surcharge"], f"calc: no negative surcharge: {t3['net']} {t3['markup_total']}")
# review: a quotation finalised before 2.1228.0 (sur_standard): its invoice puts the surcharge on the standard rate as then
t4 = calc.office_calc({"lang": "de", "markup_pct": 15, "sur_standard": 1}, ITS, PACK)
check(next(x for x in t4["lines"] if x["kind"] == "surcharge")["by_tax"] == {"standard": 225}, "calc: sur_standard = all at the standard rate (as frozen)")
sp = calc.calc_spread({"standard": Z(1), "reduced": Z(1), "exempt": Z(1)}, Z("0.10"))
check(sum(sp.values()) == Z("0.10") and sorted(sp.values()) == [Z("0.03"), Z("0.03"), Z("0.04")], f"calc_spread: the parts add up exactly: {sp}")
check(calc.calc_spread({"standard": Z(0), "reduced": Z(0), "exempt": Z(0)}, Z(5)) == {"standard": Z(5)}, "calc_spread: no base = all at the standard rate")
# stacked on the handling costs: the markup's base includes their share per rate
t2 = calc.office_calc({"lang": "de", "handling_pct": 10, "markup_pct": 10, "markup_stacked": 1},
                      [dict(x, in_handling=x["in_markup"]) for x in ITS], PACK)
s2 = {x["slot"]: x for x in t2["lines"] if x["kind"] == "surcharge"}
check(s2["handling"]["by_tax"] == {"standard": 100, "reduced": 50} and s2["markup"]["total"] == 165 and s2["markup"]["by_tax"] == {"standard": 110, "reduced": 55},
      f"calc: handling 150.00 (100 + 50), markup 10 % of 1650.00 = 165.00 (110 + 55): {s2}")

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
assert A.patch(B + f"/api/orgs/{r.json()['id']}", json={"server_agents": True}).ok  # (#6363): the Kalmido AI is off in a new organisation
A.put(B + "/api/admin/agent-policy", json={"user_agents": True, "max_per_user": 10})
FID, Fr = freelancer(B, A)


def run(S, who):
    def ok(cond, what):
        check(cond, f"{who}: {what}")

    r = S.put(B + OFC + "/settings", json={"company": {"name": COMPANY["name"]}, "lang": "de", "currency": "EUR", "payment_days": 14,
                                         "company_fields": COMPANY, "industry_packs": []})
    ok(r.ok, "office settings without an industry pack " + r.text[:200])
    r = S.post(B + "/api/clients", json={"name": "Beispielkunde AG", "street": "Marktstraße 5", "zip": "50667", "city": "Köln", "country": "DE"})
    assert r.status_code == 201, r.text
    CL = r.json()["id"]

    r = S.post(B + D, json={"client_id": CL, "project_title": "Imagefilm", "raw_mode": "none", "producing_on": 0,
                            "service_from": "2026-10-01", "service_to": "2026-10-20"})
    assert r.status_code == 201, r.text
    q = r.json()
    OF = q["id"]
    ok(q.get("markup_pct") is None, f"a new quotation without a pack has no surcharge: {q.get('markup_pct')}")
    r = S.put(B + f"{D}/{OF}/items", json={"items": [{"title": "Regie", "qty": 1, "rate": 1000, "unit": "flat"},
                                                       {"title": "Buchlizenz", "qty": 1, "rate": 500, "unit": "flat", "tax": "reduced"},
                                                       {"title": "Hotel", "qty": 1, "rate": 300, "unit": "flat", "in_markup": 0}]})
    ok(r.ok and [x.get("in_markup") for x in r.json().get("items") or []] == [1, 1, 0], "new positions are in the surcharge, the hotel unticked " + r.text[:200])
    r = S.patch(B + f"{D}/{OF}", json={"markup_pct": 15, "markup_label": "Mehraufwand"})
    ok(r.ok, "the surcharge switched on without a pack " + r.text[:200])
    t = r.json().get("totals") or {}
    lines = t.get("lines") or []
    sur = [x for x in lines if x.get("kind") == "surcharge"]
    ok(len(sur) == 1 and sur[0]["title"] == "Mehraufwand" and sur[0]["total"] == 225 and sur[0]["by_tax"] == {"standard": 150, "reduced": 75},
       f"one line 'Mehraufwand' 225.00 (150.00 at 19 %, 75.00 at 7 %): {sur}")
    kinds = [x.get("kind") for x in lines]
    ok(kinds.index("surcharge") > max(i for i, k in enumerate(kinds) if k == "item"), f"the line comes after the positions: {kinds}")
    tl = {x["rate_key"]: (x["base"], x["amount"]) for x in t.get("tax_lines") or []}
    ok(t.get("net") == 2025 and tl == {"standard": (1450, 275.5), "reduced": (575, 40.25)} and t.get("gross") == 2340.75,
       f"net 2025.00, tax per rate, gross 2340.75: {t.get('net')} {tl} {t.get('gross')}")
    r = S.patch(B + f"{D}/{OF}", json={"discount_pct": 10})
    t = r.json().get("totals") or {}
    ok(r.ok and t.get("discount") == 180 and t.get("net") == 2025 - 180, f"the discount takes the positions only (10 % of 1800.00): {t.get('discount')} {t.get('net')}")
    r = S.patch(B + f"{D}/{OF}", json={"discount_pct": 0})
    rd = S.get(B + f"{D}/{OF}/render").json()
    ok(any(x.get("kind") == "surcharge" and x.get("title") == "Mehraufwand" and x.get("total_text") for x in rd.get("lines") or []),
       "the print model has the line")
    p = S.get(B + f"{D}/{OF}/pdf")
    ok(p.ok and p.content.startswith(b"%PDF-"), f"the PDF of the quotation {p.status_code}")

    # ---------------------------------------------------------------- the invoice and a progress invoice from the quotation
    r = S.post(B + f"{D}/{OF}/invoice", json={"inv_type": "progress", "pct": 50})
    ok(r.status_code == 201, "a progress invoice of 50 % " + r.text[:200])
    if r.status_code == 201:
        pt = r.json().get("totals") or {}
        ok(pt.get("net") == "1012.50", f"the progress invoice: half of 2025.00 with the surcharge = 1012.50: {pt.get('net')}")
        S.delete(B + f"{D}/{r.json()['id']}")
    r = S.post(B + f"{D}/{OF}/invoice", json={"force": True})
    ok(r.status_code == 201, "invoice from the quotation " + r.text[:200])
    iv = r.json()
    sp = sorted((x["tax"], float(x["rate"])) for x in iv.get("items") or [] if x.get("title") == "Mehraufwand")
    ok(sp == [("reduced", 75.0), ("standard", 150.0)], f"the surcharge as one position per rate: {sp}")
    it = iv.get("totals") or {}
    ok((it.get("net"), it.get("tax"), it.get("gross")) == ("2025.00", "315.75", "2340.75"), f"the invoice = the quotation: {it.get('net')} {it.get('tax')} {it.get('gross')}")
    r = S.post(B + f"{D}/{iv['id']}/finalize")
    ok(r.ok, "the invoice finalised " + r.text[:200])
    x = S.get(B + f"{D}/{iv['id']}/xml")
    ok(x.ok and x.content.count(b"Mehraufwand") == 2 and b"<ram:GrandTotalAmount>2340.75</ram:GrandTotalAmount>" in x.content,
       "the XML: the surcharge as a line per rate, total 2340.75")
    probs = ein.ein_check(x.content) if x.ok else ["no XML"]
    ok(probs == [], f"the own check of the XML finds nothing: {probs}")

    r = S.patch(B + f"{D}/{OF}", json={"markup_pct": None})
    ok(r.ok and not [x for x in (r.json().get("totals") or {}).get("lines") or [] if x.get("kind") == "surcharge"] and r.json()["totals"]["net"] == 1800,
       "switched off: no line, net 1800.00")

    # ---------------------------------------------------------------- an agent's quotation draft
    r = S.post(B + "/api/my/agents", json={"username": f"zuschlag{len(who)}", "display_name": "Zuschlag Agent", "provider": "kalmido-server", "scopes": ["read", "office"]})
    ok(r.status_code == 201, "a server agent " + r.text[:200])
    aj = r.json()
    AH = {"Authorization": "Bearer " + aj["token"], **H}
    ok(S.patch(B + f"{OFC}/agents/{aj['id']}", json={"office_drafts": True}).ok, "the agent's office switch on")
    ok(S.put(B + OFC + "/settings", json={"agents_read": 1}).ok, "agents may read office data")
    r = requests.post(V1, headers=AH, json={"client_id": CL, "title": "Agentenangebot", "surcharge": {"pct": 15, "title": "Mehraufwand"},
                                             "items": [{"text": "Schnitt", "qty": 2, "unit": "day", "price": 500}]})
    ok(r.status_code == 201, f"the agent's draft with a surcharge {r.status_code} {r.text[:200]}")
    dj = (r.json().get("doc") or {}) if r.status_code == 201 else {}
    sur = [x for x in (dj.get("totals") or {}).get("lines") or [] if x.get("kind") == "surcharge"]
    ok(float(dj.get("markup_pct") or 0) == 15 and len(sur) == 1 and sur[0]["title"] == "Mehraufwand" and sur[0]["total"] == 150,
       f"the draft: 'Mehraufwand' 15 % of 1000.00 = 150.00: {dj.get('markup_pct')} {sur}")
    if dj:
        r = requests.patch(V1 + f"/{dj['id']}", headers=AH, json={"surcharge": None, "expect_updated_at": dj.get("updated_at")})
        ok(r.ok and r.json()["doc"].get("markup_pct") is None and r.json()["doc"]["totals"]["net"] == 1000, f"null switches it off {r.status_code} {r.text[:200]}")
        cur = r.json()["doc"] if r.ok else dj
        r = requests.patch(V1 + f"/{dj['id']}", headers=AH, json={"surcharge": {"pct": 15, "colour": "red"}, "expect_updated_at": cur.get("updated_at")})
        ok(r.status_code == 400, f"an unknown key is refused: {r.status_code}")
        r = requests.patch(V1 + f"/{dj['id']}", headers=AH, json={"surcharge": {"pct": 150}, "expect_updated_at": cur.get("updated_at")})
        ok(r.status_code == 400, f"more than 100 % is refused: {r.status_code}")
        r = requests.patch(V1 + f"/{dj['id']}", headers=AH, json={"surcharge": {"pct": 10}, "expect_updated_at": cur.get("updated_at")})
        cur = r.json()["doc"] if r.ok else cur
        r = requests.patch(V1 + f"/{dj['id']}", headers=AH, json={"surcharge": {"title": "Extra"}, "expect_updated_at": cur.get("updated_at")})
        ok(r.ok and float(r.json()["doc"].get("markup_pct") or 0) == 10 and (r.json()["doc"].get("markup_label") or {}).get("de") == "Extra",
           f"a title alone renames and keeps the 10 %: {r.status_code} {r.text[:200]}")
        cur = r.json()["doc"] if r.ok else cur
        r = requests.patch(V1 + f"/{dj['id']}", headers=AH, json={"surcharge": {"title": 5}, "expect_updated_at": cur.get("updated_at")})
        ok(r.status_code == 400, f"a title that is no text is refused: {r.status_code}")




def dbx(sql, args=()):
    return dbxm.connect(sys.argv[1]).execute(sql, args).fetchall()


def legacy_6661(S, who):
    """2.1299.0 (#6661): a quotation from before #6254 that is no draft any more keeps the surcharge on the standard rate."""
    def ok(cond, what):
        check(cond, f"#6661 {who}: {what}")

    def strip(did, status=None):  # the state a quotation saved before 2.1228 has: its totals without sur_split
        dbx("UPDATE office_docs SET totals=(totals::jsonb - 'sur_split')::text" + (", status=?" if status else "") + " WHERE id=?",
            ((status,) if status else ()) + (did,))

    def tg(t):
        return (str(t.get("net")), str(t.get("tax_total")), str(t.get("gross")))

    r = S.post(B + "/api/clients", json={"name": "Altkunde GmbH", "street": "Altweg 1", "zip": "50667", "city": "Köln", "country": "DE"})
    cl = r.json()["id"]

    def offer(title):
        r = S.post(B + D, json={"client_id": cl, "project_title": title, "raw_mode": "none", "producing_on": 0, "service_from": "2026-10-01"})
        assert r.status_code == 201, r.text
        did = r.json()["id"]
        ok(S.put(B + f"{D}/{did}/items", json={"items": [{"title": "Regie", "qty": 1, "rate": 1000, "unit": "flat"},
                                                          {"title": "Buchlizenz", "qty": 1, "rate": 500, "unit": "flat", "tax": "reduced"},
                                                          {"title": "Hotel", "qty": 1, "rate": 300, "unit": "flat", "in_markup": 0}]}).ok, "positions")
        t = S.patch(B + f"{D}/{did}", json={"markup_pct": 15, "markup_label": "Mehraufwand"}).json().get("totals") or {}
        ok(float(t.get("gross")) == 2340.75 and t.get("sur_split") == 1, f"a new quotation: the split, gross 2340.75: {t.get('gross')}")
        return did

    old = (2025.0, 324.75, 2349.75)  # 225.00 all at 19 %: (1000 + 300 + 225) x 19 % + 500 x 7 %

    def is_old(t):
        return tuple(float(t.get(k) or 0) for k in ("net", "tax_total", "gross")) == old

    # accepted by hand, never finalised: a change keeps the former split
    OA = offer("Alt angenommen")
    strip(OA, "accepted")
    ok(S.patch(B + f"{D}/{OA}", json={"project_title": "Alt angenommen (geändert)"}).ok, "a change of the accepted quotation")
    d = S.get(B + f"{D}/{OA}").json()
    ok(is_old(d["totals"]) and not d["totals"].get("sur_split"), f"accepted: the surcharge stays at 19 % after a change: {tg(d['totals'])}")
    # sent by hand: opening writes nothing, the print model and the invoice keep the tax
    dbx("UPDATE office_docs SET status='sent' WHERE id=?", (OA,))
    before = dbx("SELECT totals, updated_at FROM office_docs WHERE id=?", (OA,))[0]
    d = S.get(B + f"{D}/{OA}").json()
    after = dbx("SELECT totals, updated_at FROM office_docs WHERE id=?", (OA,))[0]
    ok(is_old(d["totals"]) and tuple(before) == tuple(after), f"sent: opening shows the former tax and writes nothing: {tg(d['totals'])}")
    rd = S.get(B + f"{D}/{OA}/render").json()
    ok(is_old(rd.get("totals") or {}), f"sent: the print model (PDF, client's view) keeps it: {tg(rd.get('totals') or {})}")
    ok(S.get(B + f"{D}/{OA}/pdf").content.startswith(b"%PDF-"), "sent: the PDF")
    r = S.post(B + f"{D}/{OA}/invoice", json={"force": True})
    ok(r.status_code == 201, "sent: the invoice " + r.text[:200])
    if r.status_code == 201:
        ok(is_old(r.json().get("totals") or {}), f"sent: the invoice = the quotation as sent: {tg(r.json().get('totals') or {})}")
        S.delete(B + f"{D}/{r.json()['id']}")
    # a draft from before moves to the split with its next change
    OD = offer("Alt Entwurf")
    strip(OD)
    r = S.patch(B + f"{D}/{OD}", json={"project_title": "Alt Entwurf (geändert)"})
    t = r.json().get("totals") or {}
    ok(r.ok and float(t.get("gross")) == 2340.75 and t.get("sur_split") == 1, f"a draft from before: a change moves it to the split: {tg(t)}")


run(Fr, "freelancer")
run(A, "organisation")
legacy_6661(Fr, "freelancer")
legacy_6661(A, "organisation")
print(f"p6254_zuschlag: {OKS[0]} ok, {len(FAILS)} failed")
sys.exit(1 if FAILS else 0)
