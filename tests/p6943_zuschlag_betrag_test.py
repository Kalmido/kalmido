#!/usr/bin/env python3
# kalmido-suite: fresh
"""2.1345.0 API tests (#6943): the surcharge ("Zuschlag") of a quotation as a fixed net amount instead of the percent, like
the discount's amount since #5815; once in the personal office of a person without an organisation (freelancer fixture;
freelancer-matrix: office) and once in an organisation's office (its admin). Invented companies, people and figures only.
 - the calculator alone (calc.office_calc): markup_amount 300 = one line "1 flat" | 300.00 without a percent and without
   a percent detail, spread over the tax keys of the marked positions (200.00 at 19 %, 100.00 at 7 %); it counts instead
   of markup_pct; a negative amount gives no line; with the part lines of a title page (mk_extra) it stays the one amount
 - PATCH markup_amount: the line as above, markup_pct becomes 0 (the markup stays on); a percent > 0 clears the amount;
   switched off (markup_pct null) clears it too; a negative amount is refused (400)
 - the invoice from the quotation: the amount as one position per rate, the sums are the quotation's; finalised, its XML
   has the line per rate, no percent, and the own check (einvoice.ein_check) finds nothing
 - repricing to a target net sum keeps the amount as a fixed part of the sum
 - an agent's quotation draft (POST / PATCH /api/v1/office/offers) sets it with {amount, title}; pct and amount together
   are refused (400)
usage: p6943_zuschlag_betrag_test.py <datadir>"""
import importlib.util
import os
import sys

N = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, N)
from freelancer_fixture import FEATURES, freelancer  # noqa: E402
from kt import FAILS, OKS, check, sess  # noqa: E402
import requests  # noqa: E402

SRC = os.environ.get("KALMIDO_SRC") or os.path.join(N, "..")
B = "http://127.0.0.1:" + os.environ.get("KALMIDO_TEST_PORT", "3048")
H = {"X-Requested-With": "kalmido"}
OFC = "/api/office"
D = OFC + "/docs"
V1 = B + "/api/v1/office/offers"
COMPANY = {"name": "Studio Westwind", "street": "Deichweg 3", "zip": "20457", "city": "Hamburg", "country": "DE",
           "email": "hallo@westwind.example", "phone": "+49 40 000001", "tax_number": "12/345/67891", "vat_id": "DE999999998",
           "iban": "DE02120300000000202051", "bic": "BYLADEM1001", "bank_name": "Beispielbank"}


def load(name):
    spec = importlib.util.spec_from_file_location("p6943_" + name, os.path.join(SRC, "kalmido", "office", name + ".py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------- the calculator alone
calc = load("calc")
ein = load("einvoice")
PACK = {"tax": {"standard": 19, "reduced": 7, "exempt": 0}}
ITS = [{"title": "Regie", "qty": 1, "rate": 1000, "unit": "flat", "in_markup": 1},
       {"title": "Buchlizenz", "qty": 1, "rate": 500, "unit": "flat", "tax": "reduced", "in_markup": 1},
       {"title": "Hotel", "qty": 1, "rate": 300, "unit": "flat", "in_markup": 0}]
t = calc.office_calc({"lang": "de", "markup_pct": 15, "markup_amount": 300, "raw_mode": "none", "producing_on": 0}, ITS, PACK)
sur = [x for x in t["lines"] if x["kind"] == "surcharge"]
check(len(sur) == 1 and sur[0]["total"] == 300 and sur[0]["by_tax"] == {"standard": 200, "reduced": 100} and sur[0]["qty_text"] == "1"
      and sur[0]["pct"] is None and sur[0]["detail"] == "" and "sur_pct" not in sur[0] and sur[0].get("amount") == 300,
      f"calc: 300.00 instead of 15 %, '1 flat', no percent, no detail, 200.00 at 19 % and 100.00 at 7 %: {sur}")
tl = {x["rate_key"]: (x["base"], x["amount"]) for x in t["tax_lines"]}
check(t["net"] == 2100 and t["markup_total"] == 300 and t["markup_amount"] == 300 and tl == {"standard": (1500, 285), "reduced": (600, 42)},
      f"calc: net 2100.00, 19 % on 1500.00, 7 % on 600.00: {t['net']} {tl}")
t2 = calc.office_calc({"lang": "de", "markup_pct": 0, "markup_amount": -50}, ITS, PACK)
check(t2["markup_total"] == 0 and not [x for x in t2["lines"] if x["kind"] == "surcharge"], f"calc: never negative: {t2['markup_total']}")
t3 = calc.office_calc({"lang": "de", "markup_pct": 0, "markup_amount": 300, "mk_extra": {"standard": 3000}}, ITS, PACK)
s3 = [x for x in t3["lines"] if x["kind"] == "surcharge"]
check(len(s3) == 1 and s3[0]["total"] == 300 and s3[0]["by_tax"] == {"standard": 266.67, "reduced": 33.33},
      f"calc: with the part lines of a title page still the one amount, spread with them: {s3}")

# review F5 (decision 17.11.2026): no marked position: the amount over all positions by their rates (here only reduced ones)
t4 = calc.office_calc({"lang": "de", "markup_pct": 0, "markup_amount": 100},
                      [{"title": "Buch", "qty": 1, "rate": 600, "unit": "flat", "tax": "reduced", "in_markup": 0},
                       {"title": "Lizenz", "qty": 1, "rate": 400, "unit": "flat", "tax": "reduced", "in_markup": 0}], PACK)
s4 = [x for x in t4["lines"] if x["kind"] == "surcharge"]
check(len(s4) == 1 and s4[0]["by_tax"] == {"reduced": 100} and [(x["rate_key"], x["base"]) for x in t4["tax_lines"]] == [("reduced", 1100)],
      f"calc F5: no marked base, only reduced positions: the 100.00 at 7 %, not at 19 %: {s4} {t4['tax_lines']}")
t5 = calc.office_calc({"lang": "de", "markup_pct": 0, "markup_amount": 100}, [dict(x, in_markup=0) for x in ITS], PACK)
check(next(x for x in t5["lines"] if x["kind"] == "surcharge")["by_tax"] == {"standard": 72.22, "reduced": 27.78},
      f"calc F5: no marked base, mixed: by the share of every position (1300.00 / 500.00): {t5['lines'][-1]}")

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
assert A.patch(B + f"/api/orgs/{r.json()['id']}", json={"server_agents": True}).ok  # 2.1409.0 (#6363): the Kalmido AI is off in a new organisation
A.put(B + "/api/admin/agent-policy", json={"user_agents": True, "max_per_user": 10})
FID, Fr = freelancer(B, A)


def run(S, who):
    def ok(cond, what):
        check(cond, f"{who}: {what}")

    def sur_of(t):
        return [x for x in (t or {}).get("lines") or [] if x.get("kind") == "surcharge"]

    r = S.put(B + OFC + "/settings", json={"company": {"name": COMPANY["name"]}, "lang": "de", "currency": "EUR", "payment_days": 14,
                                         "company_fields": COMPANY, "industry_packs": []})
    ok(r.ok, "office settings " + r.text[:200])
    r = S.post(B + "/api/clients", json={"name": "Beispielkunde GmbH", "street": "Marktstraße 7", "zip": "50667", "city": "Köln", "country": "DE"})
    assert r.status_code == 201, r.text
    CL = r.json()["id"]
    r = S.post(B + D, json={"client_id": CL, "project_title": "Messefilm", "raw_mode": "none", "producing_on": 0,
                            "service_from": "2026-10-01", "service_to": "2026-10-20"})
    assert r.status_code == 201, r.text
    OF = r.json()["id"]
    r = S.put(B + f"{D}/{OF}/items", json={"items": [{"title": "Regie", "qty": 1, "rate": 1000, "unit": "flat"},
                                                       {"title": "Buchlizenz", "qty": 1, "rate": 500, "unit": "flat", "tax": "reduced"},
                                                       {"title": "Hotel", "qty": 1, "rate": 300, "unit": "flat", "in_markup": 0}]})
    ok(r.ok, "positions " + r.text[:200])
    r = S.patch(B + f"{D}/{OF}", json={"markup_pct": 15, "markup_label": "Mehraufwand"})
    ok(r.ok and sur_of(r.json().get("totals"))[0]["total"] == 225, "15 % first " + r.text[:200])
    r = S.patch(B + f"{D}/{OF}", json={"markup_amount": 300})
    j = r.json() if r.ok else {}
    s = sur_of(j.get("totals"))
    ok(r.ok and float(j.get("markup_amount") or 0) == 300 and float(j.get("markup_pct") if j.get("markup_pct") is not None else -1) == 0
       and len(s) == 1 and s[0]["title"] == "Mehraufwand" and s[0]["total"] == 300 and s[0]["pct"] is None and s[0]["by_tax"] == {"standard": 200, "reduced": 100}
       and j["totals"]["net"] == 2100, f"the amount: one line 300.00 without a percent, the percent 0 (still on): {j.get('markup_pct')} {s}")
    rd = S.get(B + f"{D}/{OF}/render").json()
    ln = next((x for x in rd.get("lines") or [] if x.get("kind") == "surcharge"), {})
    ok(ln.get("title") == "Mehraufwand" and "%" not in (ln.get("qty_text") or "") + (ln.get("detail") or ""), f"the print model: no percent: {ln}")
    p = S.get(B + f"{D}/{OF}/pdf")
    ok(p.ok and p.content.startswith(b"%PDF-"), f"the PDF of the quotation {p.status_code}")
    r = S.patch(B + f"{D}/{OF}", json={"markup_amount": -5})
    ok(r.status_code == 400, f"a negative amount is refused: {r.status_code}")

    # ---------------------------------------------------------------- repricing: the amount is a fixed part of the sum
    r = S.post(B + f"{D}/{OF}/reprice", json={"mode": "net", "value": 2280})
    rp = r.json() if r.ok else {}
    ok(r.ok and (rp.get("after") or {}).get("net") == 2280 and all(round(x["after"] / x["before"], 4) == 1.1 for x in rp.get("items") or []),
       f"to 2280.00 net: the positions +10 % (1980.00), the 300.00 stay: {r.status_code} {rp.get('after')} {rp.get('items')}")

    # ---------------------------------------------------------------- the invoice from the quotation
    r = S.post(B + f"{D}/{OF}/invoice", json={"force": True})
    ok(r.status_code == 201, "invoice from the quotation " + r.text[:200])
    iv = r.json()
    sp = sorted((x["tax"], float(x["rate"]), float(x["qty"]), x["unit"]) for x in iv.get("items") or [] if x.get("title") == "Mehraufwand")
    ok(sp == [("reduced", 100.0, 1.0, "flat"), ("standard", 200.0, 1.0, "flat")], f"the amount as one position per rate, 1 flat: {sp}")
    it = iv.get("totals") or {}
    ok((it.get("net"), it.get("tax"), it.get("gross")) == ("2100.00", "327.00", "2427.00"), f"the invoice = the quotation: {it.get('net')} {it.get('tax')} {it.get('gross')}")
    r = S.post(B + f"{D}/{iv['id']}/finalize")
    ok(r.ok, "the invoice finalised " + r.text[:200])
    x = S.get(B + f"{D}/{iv['id']}/xml")
    ok(x.ok and x.content.count(b"Mehraufwand") == 2 and b"<ram:GrandTotalAmount>2427.00</ram:GrandTotalAmount>" in x.content,
       "the XML: the amount as a line per rate, total 2427.00")
    probs = ein.ein_check(x.content) if x.ok else ["no XML"]
    ok(probs == [], f"the own check of the XML finds nothing: {probs}")

    # ---------------------------------------------------------------- percent and switch clear the amount
    r = S.post(B + D, json={"client_id": CL, "project_title": "Zweitfilm", "raw_mode": "none", "producing_on": 0})
    O2 = r.json()["id"]
    S.put(B + f"{D}/{O2}/items", json={"items": [{"title": "Schnitt", "qty": 1, "rate": 1000, "unit": "flat"}]})
    S.patch(B + f"{D}/{O2}", json={"markup_pct": 0})
    r = S.patch(B + f"{D}/{O2}", json={"markup_amount": 120})
    ok(r.ok and sur_of(r.json().get("totals"))[0]["total"] == 120, "an amount of 120.00 " + r.text[:200])
    r = S.patch(B + f"{D}/{O2}", json={"markup_pct": 10})
    ok(r.ok and r.json().get("markup_amount") is None and sur_of(r.json().get("totals"))[0]["total"] == 100, f"a percent clears the amount: {r.text[:200]}")
    S.patch(B + f"{D}/{O2}", json={"markup_amount": 120})
    r = S.patch(B + f"{D}/{O2}", json={"markup_pct": None})
    ok(r.ok and r.json().get("markup_amount") is None and not sur_of(r.json().get("totals")), f"switched off clears the amount: {r.text[:200]}")

    # ---------------------------------------------------------------- an agent's quotation draft
    r = S.post(B + "/api/my/agents", json={"username": f"zbetrag{len(who)}", "display_name": "Betrag Agent", "provider": "kalmido-server", "scopes": ["read", "office"]})
    ok(r.status_code == 201, "a server agent " + r.text[:200])
    aj = r.json()
    AH = {"Authorization": "Bearer " + aj["token"], **H}
    ok(S.patch(B + f"{OFC}/agents/{aj['id']}", json={"office_drafts": True}).ok, "the agent's office switch on")
    ok(S.put(B + OFC + "/settings", json={"agents_read": 1}).ok, "agents may read office data")
    r = requests.post(V1, headers=AH, json={"client_id": CL, "title": "Agentenangebot", "surcharge": {"amount": 250, "title": "Pauschale"},
                                             "items": [{"text": "Schnitt", "qty": 2, "unit": "day", "price": 500}]})
    ok(r.status_code == 201, f"the agent's draft with an amount {r.status_code} {r.text[:200]}")
    dj = (r.json().get("doc") or {}) if r.status_code == 201 else {}
    s = sur_of(dj.get("totals"))
    ok(float(dj.get("markup_amount") or 0) == 250 and len(s) == 1 and s[0]["title"] == "Pauschale" and s[0]["total"] == 250 and s[0]["pct"] is None,
       f"the draft: 'Pauschale' 250.00: {dj.get('markup_amount')} {s}")
    if dj:
        r = requests.patch(V1 + f"/{dj['id']}", headers=AH, json={"surcharge": {"pct": 10, "amount": 50}, "expect_updated_at": dj.get("updated_at")})
        ok(r.status_code == 400, f"pct and amount together are refused: {r.status_code}")
        r = requests.patch(V1 + f"/{dj['id']}", headers=AH, json={"surcharge": {"pct": 10}, "expect_updated_at": dj.get("updated_at")})
        ok(r.ok and r.json()["doc"].get("markup_amount") is None and sur_of(r.json()["doc"].get("totals"))[0]["total"] == 100,
           f"a percent from the agent clears the amount: {r.status_code} {r.text[:200]}")


run(Fr, "freelancer")
run(A, "organisation")
print(f"p6943_zuschlag_betrag: {OKS[0]} ok, {len(FAILS)} failed")
sys.exit(1 if FAILS else 0)
