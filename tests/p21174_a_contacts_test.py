#!/usr/bin/env python3
# kalmido-suite: fresh
"""2.1174.0 A (#6119, #6120): the contacts' server side of the editor and the card. Invented people only (@example.com).
freelancer-matrix: pim
 - #6120 a phone number written through the app / the API holds only digits, spaces, + - / ( ) (the editor checks the same):
   "abc" -> 400 naming the field (Phone), "+49 (0)171 123-45/6" goes; a website without a scheme is refused naming the
   field (Website, was "url"); a contact already holding an old number (imported) can still be changed in other fields
 - #6119 a company (kind org) is saved with its kind; the contact history no longer lists the contact's events (the card's
   block "Events" has them), the card itself still does
 - the same for a person without an organisation (private address book)
usage: p21174_a_contacts_test.py <datadir>   (P21174A_NOSTART=1: a running server on KALMIDO_TEST_PORT)"""
import os
import sys

N = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, N)
import kt  # noqa: E402
from kt import B, check  # noqa: E402
from freelancer_fixture import freelancer  # noqa: E402

kt.fresh(prefix="P21174A")
kt.docker_logs_on_first_fail()
A = kt.setup()
A.patch(B + "/api/settings", json={"lang": "en", "tour": "done", "features": "cal,events,contacts"})
_FID, FR = freelancer(B, A)
D = "2026-09-14"


def run(s, who):
    bk = s.post(B + "/api/books", json={"name": "People", "org_id": None})
    check(bk.ok, f"{who}: an address book ({bk.status_code} {bk.text[:160]})")
    bid = bk.json()["id"]
    # ---- #6120 the phone number
    r = s.post(B + "/api/contacts", json={"book_id": bid, "given": "Kurt", "family": "Broken", "phones": [{"value": "abc", "type": ["cell"]}]})
    check(r.status_code == 400 and "Phone" in r.json().get("error", ""), f"{who}: #6120 phone 'abc' is refused, naming the field ({r.status_code} {r.text[:160]})")
    r = s.post(B + "/api/contacts", json={"book_id": bid, "given": "Kurt", "family": "Fine", "phones": [{"value": "+49 (0)171 123-45/6", "type": ["cell"]}]})
    check(r.ok and r.json()["phones"][0]["value"] == "+49 (0)171 123-45/6", f"{who}: #6120 digits, spaces, + - / ( ) go ({r.status_code} {r.text[:160]})")
    kid = r.json().get("id")
    r = s.patch(B + f"/api/contacts/{kid}", json={"phones": [{"value": "call me", "type": ["cell"]}]})
    check(r.status_code == 400 and "Phone" in r.json().get("error", ""), f"{who}: #6120 the same on a change ({r.status_code})")
    r = s.post(B + "/api/contacts", json={"book_id": bid, "given": "Wanda", "urls": [{"value": "www.example.org"}]})
    check(r.status_code == 400 and "Website" in r.json().get("error", ""), f"{who}: #6120 a website without its scheme names the field ({r.status_code} {r.text[:160]})")
    r = s.post(B + "/api/contacts", json={"book_id": bid, "given": "Kurt", "emails": [{"value": "kurt@@broken"}]})
    check(r.status_code == 400 and "E-mail" in r.json().get("error", ""), f"{who}: an e-mail with two @ is refused ({r.status_code})")
    # an old number (as an import brings it) stays; another field of the contact still saves
    old = s.post(B + "/api/contacts", json={"book_id": bid, "given": "Olga", "family": "Old"}).json()["id"]
    kt.dbx(f"""UPDATE contacts SET phones='[{{"value": "ext. 12", "type": ["work"]}}]' WHERE id={int(old)}""")  # an untyped literal: TEXT or JSONB
    r = s.patch(B + f"/api/contacts/{old}", json={"title": "Buyer"})
    check(r.ok and r.json()["phones"][0]["value"] == "ext. 12", f"{who}: #6120 an old number stays, other fields save ({r.status_code} {r.text[:160]})")
    # review 2.1174.0: the whole list written back (a new number added) does not fail on the untouched old one; a new wrong one does
    r = s.patch(B + f"/api/contacts/{old}", json={"phones": [{"value": "ext. 12", "type": ["work"]}, {"value": "+49 40 123", "type": ["cell"]}]})
    check(r.ok and [x["value"] for x in r.json()["phones"]] == ["ext. 12", "+49 40 123"], f"{who}: #6120 an old number kept in the whole list ({r.status_code} {r.text[:160]})")
    r = s.patch(B + f"/api/contacts/{old}", json={"phones": [{"value": "ext. 12", "type": ["work"]}, {"value": "ext. 13", "type": ["cell"]}]})
    check(r.status_code == 400 and "Phone" in r.json().get("error", ""), f"{who}: #6120 a new wrong number beside it is refused ({r.status_code})")

    # ---- #6119 a company with its kind; the history without events
    r = s.post(B + "/api/contacts", json={"book_id": bid, "kind": "org", "org": "Harbor Works Ltd", "fn": "Harbor Works Ltd"})
    check(r.ok and r.json()["kind"] == "org" and r.json()["fn"] == "Harbor Works Ltd", f"{who}: #6119 a company ({r.status_code} {r.text[:160]})")
    jana = s.post(B + "/api/contacts", json={"book_id": bid, "given": "Jana", "family": "Kruse", "org": "Harbor Works Ltd",
                                             "emails": [{"value": f"jana.{who}@example.com", "type": ["work"]}]}).json()["id"]
    r = s.get(B + "/api/contacts", params={"q": "Harbor Works Ltd", "limit": 200})
    names = sorted((x["fn"], x["kind"]) for x in r.json().get("items", []))
    check(("Harbor Works Ltd", "org") in names and ("Jana Kruse", "individual") in names, f"{who}: #6119 the search by the company finds both {names}")
    ev = s.post(B + "/api/events", json={"title": "Site visit", "start": f"{D}T10:00", "attendees": [{"contact_id": jana}]})
    check(ev.status_code in (200, 201), f"{who}: an event with jana ({ev.status_code} {ev.text[:160]})")
    h = s.get(B + f"/api/contacts/{jana}/history")
    check(h.ok and not any(x["kind"] == "event" for x in h.json()["items"]), f"{who}: #6119 no event in the history {h.text[:200]}")
    c = s.get(B + f"/api/contacts/{jana}").json()
    check([e["title"] for e in c.get("events", [])] == ["Site visit"], f"{who}: #6119 the card still lists the event {c.get('events')}")


run(A, "alice")
run(FR, "frida")
sys.exit(kt.done("p21174_a_contacts_test"))
