#!/usr/bin/env python3
# kalmido-suite: fresh
"""#7325: the general input keeps the office it was brought in for ON THE DOCUMENT (doc_meta.area_to, docs/ingest.py) and the
queue only reads it (docs/area.py ar_sort_queued) -- it never works an office out of the setting of the moment.
Invented companies and figures only.
freelancer-matrix: files
 - two organisations under "All workspaces", an invoice uploaded in the file store with sorting and nothing named: it is not
   lost -- it stays visible in the own documents (area_sort 'ask'), "New in the office" of both offices offers it, taking it
   over in Alpha's office moves it there (and Beta no longer offers it)
 - a mail to the person's own document address with two offices: the same ('ask', visible), never the setting
 - the setting changes between the upload and the recognition: the target named at the upload stays (own office), the new
   setting (Alpha) does not move it
 - "Also private" off with one organisation: an invoice uploaded in Private stays in the file store ('ask', offered in the
   organisation's office), never area 'office' behind the switch; what lay in the own office before shows in the file store
 - a second member of the organisation never sees the person's offered document
usage: p7325_a_area_to_test.py <datadir>"""
import email.message
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kt  # noqa: E402
from kt import B, FAILS, OKS, check, until  # noqa: E402
from freelancer_fixture import freelancer  # noqa: E402

HS = "X-Kalmido-Office-Space"
FEAT = "docs,files,office"
MAILENV = {"KALMIDO_MAIL_ADDRESS": "tasks@example.test", "KALMIDO_IMAP_HOST": "127.0.0.1", "KALMIDO_IMAP_PORT": "1143", "KALMIDO_IMAP_SSL": "0",
           "KALMIDO_IMAP_USER": "kalmido", "KALMIDO_IMAP_PASSWORD": "secret", "KALMIDO_IMAP_INTERVAL": "600"}
if not kt.nostart("P7325A"):
    subprocess.run(["rm", "-rf", kt.DATA])
    os.makedirs(os.path.join(kt.DATA, "mail", "in"), exist_ok=True)
    subprocess.run(["cp", os.path.join(kt.N, "stub_mail.py"), kt.DATA])
    kt.fresh(env=MAILENV, prefix="P7325A", keep=True)
    subprocess.run(["docker", "exec", "-d", kt.CT, "python", "/data/stub_mail.py"])
os.makedirs(os.path.join(kt.DATA, "mail", "in"), exist_ok=True)
A = kt.setup()
ALICE = A.get(B + "/api/state").json()["me"]["id"]

INVOICE = ("Beispiel Papier GmbH\nUSt-IdNr. DE123456789\n\nRechnung Nr. ER-2026-{n}\nDatum 05.03.2026\n\n"
           "Papier 100,00 EUR\nNetto 100,00 EUR\nUSt 19 % 19,00 EUR\nGesamt 119,00 EUR\n")


def upload(s, name, hdr=None):
    # the name in the text: the same content again would be a duplicate (dups), no new document
    r = s.post(B + "/api/docs", data={"ws": "private", "sort": "1"},
               files=[("files", (name, INVOICE.format(n=sum(map(ord, name)) * 7 % 9000 + 1000).encode() + f"Ablage {name}\n".encode(), "text/plain"))],
               headers=hdr or {})
    assert r.ok and r.json().get("ids"), r.text
    return r.json()["ids"][0]


def row(nid):
    x = kt.dbx("SELECT area, area_sort, ws, area_to FROM doc_meta WHERE node_id=?", (nid,))
    return tuple(x[0]) if x else None


def settled(s, nid, secs=90):
    def one():
        if (row(nid) or ("", "pending"))[1] in ("pending", "sorting"):
            return None
        r = s.get(B + f"/api/docs/{nid}")
        if not r.ok or r.json()["state"] not in ("done", "failed"):
            return None
        return r.json() if (row(nid) or ("", "pending"))[1] not in ("pending", "sorting") else None
    return until(one, secs)


def ids(s, hdr=None, **q):
    r = s.get(B + "/api/docs", params={"ws": "all", "facets": "0", "limit": "200", **q}, headers=hdr or {})
    assert r.ok, r.text
    return [d["id"] for d in r.json()["docs"]]


def put(s, **kw):
    r = s.patch(B + "/api/settings", json=kw)
    assert r.ok, r.text


MAILNO = [0]


def mail_in(addr, text, att):
    """One mail to addr through the stub mailbox -> the new document's node id (None: none came)."""
    MAILNO[0] += 1
    mid = f"<p7325-mail-{MAILNO[0]}@example.com>"
    m = email.message.EmailMessage()
    m["From"], m["To"], m["Subject"], m["Message-ID"] = "post@example.com", addr, "Fwd: Rechnung", mid
    m.set_content(text)
    m.add_attachment(att[1], maintype=att[2], subtype=att[3], filename=att[0])
    open(os.path.join(kt.DATA, "mail", "in", f"{MAILNO[0]}.eml"), "wb").write(bytes(m))

    def got():
        A.post(B + "/api/admin/mail/poll")
        x = kt.dbx("SELECT node_id FROM doc_meta WHERE source='mail' AND ext_id LIKE ?", (f"mail:{mid}:%",))
        return x[0][0] if x else None
    return until(got, 40)


# ==== two organisations, "All workspaces"
put(A, lang="en", features=FEAT, tour="done")
ALPHA = A.post(B + "/api/admin/orgs", json={"name": "Alpha", "admin_id": ALICE}).json()["id"]
BETA = A.post(B + "/api/admin/orgs", json={"name": "Beta", "admin_id": ALICE}).json()["id"]
for oid, name in ((ALPHA, "Alpha Studio GmbH"), (BETA, "Beta Werkstatt GmbH")):
    put(A, workspace=f"org:{oid}")
    r = A.put(B + "/api/office/settings", json={"company_fields": {"name": name, "vat_id": "DE999888777"}})
    check(r.ok, f"setup: the office of {name} " + r.text[:160])
put(A, workspace="all")
HA, HB = {HS: f"org:{ALPHA}"}, {HS: f"org:{BETA}"}

d1 = upload(A, "rechnung-alle.txt")
check(row(d1)[3] == "", f"#7325: nothing named under 'All' with two offices: no target kept {row(d1)}")
d = settled(A, d1)
check(d is not None and row(d1)[:3] == ("", "ask", f"u{ALICE}"), f"#7325: not sorted, not lost: offered ('ask') {row(d1)}")
check(d1 in ids(A) and d1 in ids(A, area="private"), "#7325: visible in the file store")
check(d1 in ids(A, HA, area="office", unbooked="1") and d1 in ids(A, HB, area="office", unbooked="1"),
      "#7325: 'New in the office' of both offices offers it")
check(d and d.get("area_ask") is True, f"#7325: the list / sheet marks it as offered {d and d.get('area_ask')}")

# a second member of Alpha never sees Alice's offered document
r = A.post(B + "/api/users", json={"orgs": [{"id": ALPHA, "role": "member"}], "username": "bert", "display_name": "Bert",
                                   "password": "password123", "email": "bert@example.com"})
check(r.ok, "setup: bert, a member of Alpha " + r.text[:160])
Be = kt.sess("bert")
put(Be, tour="done", lang="en", features=FEAT, workspace=f"org:{ALPHA}")
check(d1 not in ids(Be, HA, area="office", unbooked="1") and d1 not in ids(Be), "#7325: another member of Alpha does not see it")
check(Be.get(B + f"/api/docs/{d1}").status_code in (403, 404), "#7325: nor its sheet")

# taking it over in Alpha's office (the existing POST /api/docs/<id>/area in that office's request)
r = A.post(B + f"/api/docs/{d1}/area", json={"to": "office"}, headers=HA)
check(r.ok and r.json().get("org_id") == ALPHA and row(d1)[:3] == ("office", "person", f"o{ALPHA}"),
      f"#7325: taken over into Alpha {r.status_code} {r.text[:200]} {row(d1)}")
check(d1 not in ids(A, HB, area="office", unbooked="1"), "#7325: Beta no longer offers it")

# ---- a mail to her own document address with two offices: never the setting, offered
put(A, workspace=f"org:{BETA}")  # the setting names Beta -- a mail is no request: it must not decide
r = A.post(B + "/api/docs/mail", json={"ws": "private"})
check(r.ok and r.json().get("address"), "her document address " + r.text[:160])
if r.ok and r.json().get("address"):
    m1 = mail_in(r.json()["address"], "siehe Anhang", ("mail-rechnung.txt", INVOICE.format(n=7101).encode(), "text", "plain"))
    check(m1 and row(m1)[3] == "", f"#7325: a mail with two offices keeps no target {m1 and row(m1)}")
    check(m1 and settled(A, m1) is not None and row(m1)[:3] == ("", "ask", f"u{ALICE}") and m1 in ids(A),
          f"#7325: the mail's invoice stays visible, offered -- not in Beta of the setting {m1 and row(m1)}")

# ---- the setting changes between the upload and the recognition: the target of the upload stays
put(A, workspace="private")
d2 = upload(A, "rechnung-privat.txt", {HS: "private"})
check(row(d2)[3] == "private", f"#7325: the upload in Private keeps its target {row(d2)}")
settled(A, d2)
check(row(d2)[:3] == ("office", "auto", f"u{ALICE}"), f"setup: sorted into her own office {row(d2)}")
# the recognition once more with the setting on Alpha now (as if it had changed before the first recognition)
kt.dbx("UPDATE doc_meta SET area='', area_sort='pending' WHERE node_id=?", (d2,))
put(A, workspace=f"org:{ALPHA}")
r = A.post(B + f"/api/docs/{d2}/redo")
check(r.ok, "recognise again " + r.text[:160])
settled(A, d2)
check(row(d2)[:3] == ("office", "auto", f"u{ALICE}"), f"#7325: the setting Alpha does not move it, the target of the upload stays {row(d2)}")

# ==== "Also private" off, one organisation (freelancer-matrix: files -- a person who is first alone)
CARLA, Ca = freelancer(B, A, "carla", features=FEAT)
check(Ca.put(B + "/api/office/settings", json={"company_fields": {"name": "Carla Grafik", "vat_id": "DE111222333"}}).ok,
      "setup: her personal office")
c1 = upload(Ca, "rechnung-carla-1.txt")
check(row(c1)[3] == "private", f"#7325: alone: her own office is the target {row(c1)}")
settled(Ca, c1)
check(row(c1)[:2] == ("office", "auto"), f"alone: sorted into her own office {row(c1)}")
GAMMA = A.post(B + "/api/admin/orgs", json={"name": "Gamma", "admin_id": CARLA}).json()["id"]
HG = {HS: f"org:{GAMMA}"}
put(Ca, workspace=f"org:{GAMMA}")
check(Ca.put(B + "/api/office/settings", json={"company_fields": {"name": "Gamma Film GmbH", "vat_id": "DE444555666"}}).ok,
      "setup: Gamma's office")
put(Ca, workspace="private", ws_areas_off={"private": ["office"]}, ws_mods_off={})
c2 = upload(Ca, "rechnung-carla-2.txt", {HS: "private"})
check(row(c2)[3] == "", f"#7325: 'Also private' off: her own office is no target {row(c2)}")
d = settled(Ca, c2)
check(d is not None and row(c2)[:3] == ("", "ask", f"u{CARLA}"), f"#7325: never area 'office' behind the switch, offered {row(c2)}")
hp = {HS: "private"}
check(c2 in ids(Ca, hp, area="private") and c2 in ids(Ca), "#7325: it stays in the file store")
check(c2 in ids(Ca, HG, area="office", unbooked="1"), "#7325: Gamma's office offers it")
check(c1 in ids(Ca, hp, area="private") and Ca.get(B + f"/api/docs/{c1}", headers=hp).ok,
      "#7325: what lay in her own office before shows in the file store (no data run)")

print(f"p7325_a_area_to: {OKS[0]} ok, {len(FAILS)} failed")
sys.exit(1 if FAILS else 0)
