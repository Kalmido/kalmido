#!/usr/bin/env python3
# kalmido-suite: fresh
"""2.1185.0 (#6150): the steps of a quotation without an answer (office/offerexp.py) follow the editor's rules.
Invented companies, people and figures only.
freelancer-matrix: office
 - the editor's answer (offer_exp) carries subject and text of "Follow up" in the QUOTATION's language: a German quotation
   gets the German text although the person reads English; past its date the text says "was valid until"
 - "Extend validity" can be undone: {valid_until: <the date before>, undo: true} writes exactly that date back, also a past
   one; any other past date is refused with undo too (400); the bell does not ring the old date a second time after the undo
 - the same for a person without an organisation (her private office, she is its admin)
usage: p6150_offer_steps_test.py <datadir>"""
import os
import subprocess
import sys
from datetime import date, timedelta

N = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, N)
from freelancer_fixture import freelancer  # noqa: E402
from kt import B, check, dbx, done, fresh, setup  # noqa: E402

CT = os.environ.get("KALMIDO_TEST_CONTAINER", "kalmido-test")
OFF = "/api/office"
D = OFF + "/docs"
FEAT = "cal,comments,collab,clients,office,docs,files,contacts"
COMPANY = {"name": "Beispiel Film GmbH", "street": "Musterweg 1", "zip": "12345", "city": "Musterstadt", "country": "DE",
           "email": "hallo@beispiel.example", "vat_id": "DE123456789", "iban": "DE02120300000000202051", "bic": "BYLADEM1001",
           "bank_name": "Beispielbank"}
TODAY = date.today()


def day(n):
    return (TODAY + timedelta(days=n)).isoformat()


def de_date(iso):
    y, m, d = iso.split("-")
    return f"{d}.{m}.{y}"


fresh({"KALMIDO_INSTANCE_MODE": "workspaces"}, prefix="P6150")
A = setup()
A.patch(B + "/api/settings", json={"tour": "done", "lang": "en", "features": FEAT})
ALICE = A.get(B + "/api/me").json()["id"]
ORG = A.post(B + "/api/admin/orgs", json={"name": "Alpha", "admin_id": ALICE}).json()["id"]
assert A.patch(B + "/api/settings", json={"workspace": f"org:{ORG}"}).ok


def tick():
    code = ("import app\nfrom kalmido.core.db import connect\nfrom kalmido.office import offerexp as x\n"
            "x._OFE_LAST['at'] = -1e12\nc = connect()\nx.ofe_tick(c)\nc.close()")
    r = subprocess.run(["docker", "exec", CT, "python3", "-c", code], capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stdout + r.stderr


def news(s, did):
    j = s.get(B + "/api/news").json()
    return [x for x in j["items"] if x["kind"] == "offerexp" and (x.get("data") or {}).get("doc") == did]


def office(s, client):
    assert s.put(B + OFF + "/settings", json={"lang": "de", "company_fields": COMPANY}).ok
    r = s.post(B + "/api/clients", json={"name": client, "street": "Marktweg 5", "zip": "50667", "city": "Koeln", "country": "DE"})
    assert r.status_code in (200, 201), r.text
    return r.json()["id"]


def sent_offer(s, cl, title, lang):
    r = s.post(B + D, json={"kind": "offer", "lang": lang, "client_id": cl, "project_title": title,
                            "items": [{"kind": "service", "title": "Dreh", "qty": 1, "unit": "day", "rate": 900, "tax": "standard"}]})
    assert r.status_code == 201, r.text
    did = r.json()["id"]
    assert s.post(B + f"{D}/{did}/finalize").ok
    r = s.post(B + f"{D}/{did}/status", json={"status": "sent"})
    assert r.ok and r.json().get("status") == "sent", r.text
    return did


def run(s, who, cl):
    # ---- "Follow up" in the quotation's language (the person reads English)
    did = sent_offer(s, cl, "Imagefilm " + who, "de")
    dbx("UPDATE office_docs SET valid_until=? WHERE id=?", (day(2), did))
    x = s.get(B + f"{D}/{did}").json().get("offer_exp") or {}
    num = s.get(B + f"{D}/{did}").json().get("number")
    check(x.get("state") == "soon" and "Angebot" in (x.get("subject") or "") and num in (x.get("subject") or ""),
          f"{who}: the subject of a German quotation is German {x.get('subject')!r}")
    check("Guten Tag" in (x.get("text") or "") and f"Es gilt bis {de_date(day(2))}" in (x.get("text") or ""),
          f"{who}: the text is German with the German date {x.get('text')!r}")
    dbx("UPDATE office_docs SET valid_until=? WHERE id=?", (day(-1), did))
    x = s.get(B + f"{D}/{did}").json().get("offer_exp") or {}
    check(x.get("state") == "gone" and f"bis {de_date(day(-1))} gültig war" in (x.get("text") or ""),
          f"{who}: past its date the text says 'was valid until' {x.get('text')!r}")
    en = sent_offer(s, cl, "Spot " + who, "en")
    dbx("UPDATE office_docs SET valid_until=? WHERE id=?", (day(-1), en))
    x = s.get(B + f"{D}/{en}").json().get("offer_exp") or {}
    check("which was valid until" in (x.get("text") or "") and (x.get("subject") or "").startswith("Our quotation"),
          f"{who}: an English quotation gets the English text {x.get('subject')!r} {x.get('text')!r}")

    # ---- "Extend validity" and its undo
    tick()
    check([n["data"].get("state") for n in news(s, did)] == ["gone"], f"{who}: the expired quotation rings once {news(s, did)}")
    r = s.post(B + f"{D}/{did}/valid-until", json={"valid_until": day(-3), "undo": True})
    check(r.status_code == 400, f"{who}: undo without an extension before: a past date stays refused {r.status_code}")
    r = s.post(B + f"{D}/{did}/valid-until", json={"valid_until": day(14)})
    check(r.ok and r.json().get("valid_until") == day(14), f"{who}: extended {r.status_code} {r.text[:200]}")
    r = s.post(B + f"{D}/{did}/valid-until", json={"valid_until": day(-3), "undo": True})
    check(r.status_code == 400, f"{who}: undo writes back only the date before, not any past one {r.status_code}")
    r = s.post(B + f"{D}/{did}/valid-until", json={"valid_until": day(-1), "undo": True})
    j = r.json() if r.ok else {}
    check(r.ok and j.get("valid_until") == day(-1) and j.get("status") == "sent" and (j.get("offer_exp") or {}).get("state") == "gone",
          f"{who}: undo -> the old date (in the past) is back {r.status_code} {r.text[:300]}")
    tick()
    check(len(news(s, did)) == 1, f"{who}: after the undo the bell shows the old entry once, not a second one {news(s, did)}")
    r = s.post(B + f"{D}/{did}/valid-until", json={"valid_until": day(14)})
    check(r.ok and r.json().get("valid_until") == day(14), f"{who}: redo = the new date again {r.status_code}")
    r = s.get(B + f"{D}/{did}/pdf")
    check(r.status_code == 200 and r.content[:4] == b"%PDF", f"{who}: the stored PDF is served after undo / redo {r.status_code}")
    return did


A_DOC = run(A, "org", office(A, "Kunde Alpha GmbH"))

# ---------------------------------------------------------------- a person without an organisation
# freelancer-matrix: office
FID, Fr = freelancer(B, A)
Fr.patch(B + "/api/settings", json={"lang": "en"})
run(Fr, "freelancer", office(Fr, "Privatkunde GmbH"))

# ---------------------------------------------------------------- the boundary: another person cannot undo it
r = Fr.post(B + f"{D}/{A_DOC}/valid-until", json={"valid_until": day(-1), "undo": True})
check(r.status_code in (403, 404), f"another person: the organisation's quotation is not hers to set back {r.status_code}")
check(dbx("SELECT valid_until FROM office_docs WHERE id=?", (A_DOC,))[0][0] == day(14), "another person: the date stays as it was")

sys.exit(done("p6150_offer_steps"))
