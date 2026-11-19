#!/usr/bin/env python3
# kalmido-suite:
"""#6587: the own formats come back as they went out (round trips that compare the content, not only the count).
Invented names only (@example.com).
 - list CSV (GET /api/lists/<id>/export.csv) in every language of the app -> POST /api/import/csv: the state (open / done /
   won't do) from the column "Status", not from the date column "Completed" / "Erledigt"; the subtask under its parent
   ("Parent task" / "Hauptaufgabe" / ...); title and priority (the words of every language); a real import keeps the parent
 - Markdown (GET /api/export/markdown.zip) -> POST /api/import/markdown: "Title (due 2026-12-01 09:30, high priority)" gives the
   title without the brackets, the date, the time and the priority; a title with its own brackets stays whole; [x] / [-] the
   state; "repeats" / "every week" the rule; subtasks and tags
 - vCard 3.0 (GET /api/books/<id>/export.vcf) -> import into another book: a company stays a company (X-ABShowAs:COMPANY /
   X-KIND:org), a person a person; the company's card lists its people again; a card of Apple Contacts with X-ABShowAs:COMPANY
   is a company; the export of the re-imported card carries the marker once
 - the same for a person without an organisation
usage: p6587_roundtrip_api_test.py <datadir>"""
import io
import os
import sys
import zipfile

N = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, N)
from freelancer_fixture import freelancer  # noqa: E402
from kt import B, check, dbx, done, fresh, setup  # noqa: E402

LANGS = ("en", "de", "es", "fr", "it", "nl")
fresh()
A = setup()
FID, Fr = freelancer(B, A)


def mk(s, lid, title, **kw):
    r = s.post(B + "/api/tasks", json={"list_id": lid, "title": title, **kw})
    assert r.ok, (title, r.text)
    return r.json()["id"]


def imp(s, src, name, data, dry=True):
    r = s.post(B + f"/api/import/{src}", files={"file": (name, data)}, data={"dry_run": "1"} if dry else {})
    assert r.ok, (src, name, r.status_code, r.text[:300])
    return r.json()


def samples(j):
    return {x["title"]: x for x in j["samples"]}


def tasks_fixture(s, who):
    lid = s.post(B + "/api/lists", json={"name": f"Trip {who}"}).json()["id"]
    p = mk(s, lid, "Pack bags", priority=5)
    mk(s, lid, "Socks", parent_id=p, priority=1)
    h = mk(s, lid, "Book hotel", priority=3)
    assert s.post(B + f"/api/tasks/{h}/complete", json={}).ok
    c = mk(s, lid, "Rent car", priority=7)
    assert s.post(B + f"/api/tasks/{c}/complete", json={"status": -1}).ok
    mk(s, lid, "Call Anna (office)", priority=5, due="2026-12-01", due_time="09:30", tags=["work"])
    mk(s, lid, "Weekly review", repeat="FREQ=WEEKLY", due="2026-11-03")
    return lid


WANT = {"Pack bags": (0, 5, False), "Socks": (0, 1, True), "Book hotel": (2, 3, False), "Rent car": (-1, 7, False)}


def csv_roundtrip(s, who, lid):
    for lg in LANGS:
        assert s.patch(B + "/api/settings", json={"lang": lg}).ok
        txt = s.get(B + f"/api/lists/{lid}/export.csv").content
        sm = samples(imp(s, "csv", f"trip-{lg}.csv", txt))
        got = {t: (sm[t]["status"], sm[t]["priority"], sm[t]["subtask"]) if t in sm else None for t in WANT}
        check(got == WANT, f"{who}: list CSV ({lg}) back with state, priority and parent {got}")
    # a real import (German): the subtask hangs under its parent again
    assert s.patch(B + "/api/settings", json={"lang": "de"}).ok
    txt = s.get(B + f"/api/lists/{lid}/export.csv").content
    j = imp(s, "csv", f"zurueck-{who}.csv", txt, dry=False)
    me = s.get(B + "/api/me").json()["id"]
    par = dbx("""SELECT p.title FROM tasks t JOIN tasks p ON p.id=t.parent_id JOIN lists l ON l.id=t.list_id WHERE t.title='Socks'
                 AND t.list_id<>? AND l.owner_id=? AND t.deleted_at IS NULL""", (lid, me))
    st = dbx("""SELECT t.status FROM tasks t JOIN lists l ON l.id=t.list_id WHERE t.title='Book hotel' AND t.list_id<>? AND l.owner_id=?
                AND t.deleted_at IS NULL""", (lid, me))
    check(j["created"]["subtasks"] >= 1 and [r[0] for r in par] == ["Pack bags"] and [r[0] for r in st] == [2],
          f"{who}: the German list CSV imported: Socks under Pack bags, Book hotel done ({par}, {st})")
    assert s.patch(B + "/api/settings", json={"lang": "en"}).ok


def md_roundtrip(s, who, lid):
    z = zipfile.ZipFile(io.BytesIO(s.get(B + "/api/export/markdown.zip").content))
    md = z.read(next(n for n in z.namelist() if n.startswith(f"Trip {who}")))
    check(b"Call Anna (office) (due 2026-12-01 09:30, high priority) #work" in md, f"{who}: the export line as expected {md[:400]!r}")
    sm = samples(imp(s, "markdown", "trip.md", md))
    got = {t: (sm[t]["status"], sm[t]["priority"], sm[t]["subtask"]) if t in sm else None for t in WANT}
    check(got == WANT, f"{who}: Markdown back with state, priority and parent {got} {sorted(sm)}")
    a = sm.get("Call Anna (office)") or {}
    check(a.get("due") == "2026-12-01" and a.get("due_time") == "09:30" and a.get("priority") == 5 and a.get("tags") == ["work"],
          f"{who}: Markdown: the title with its own brackets whole, date, time, priority, tag {a} {sorted(sm)}")
    w = sm.get("Weekly review") or {}
    check(w.get("repeat") == "FREQ=WEEKLY", f"{who}: Markdown: the repeat rule back {w}")


def vc_roundtrip(s, who):
    bk = s.post(B + "/api/books", json={"name": f"Firmen {who}"}).json()["id"]
    r1 = s.post(B + "/api/contacts", json={"book_id": bk, "kind": "org", "fn": "Bakery Ltd", "org": "Bakery Ltd"})
    r2 = s.post(B + "/api/contacts", json={"book_id": bk, "fn": "Jane Doe", "given": "Jane", "family": "Doe", "org": "Bakery Ltd",
                                           "emails": [{"value": f"jane.{who}@example.com", "type": ["work"]}]})
    assert r1.ok and r2.ok, (r1.text, r2.text)
    exp = s.get(B + f"/api/books/{bk}/export.vcf").text
    check("VERSION:3.0" in exp and "X-ABShowAs:COMPANY" in exp and "X-KIND:org" in exp, f"{who}: vCard 3.0 carries the kind {exp[:500]!r}")
    bk2 = s.post(B + "/api/books", json={"name": f"Zurueck {who}"}).json()["id"]
    r = s.post(B + f"/api/books/{bk2}/import", files={"file": ("k.vcf", exp.encode(), "text/vcard")})
    assert r.ok, r.text
    got = {x[0]: x[1] for x in dbx("SELECT fn, kind FROM contacts WHERE book_id=? AND deleted_at IS NULL", (bk2,))}
    check(got == {"Bakery Ltd": "org", "Jane Doe": "individual"}, f"{who}: vCard back: the company a company, the person a person {got}")
    items = s.get(B + "/api/contacts", params={"q": "Bakery", "limit": 200}).json()["items"]
    firm = [x for x in items if x["book_id"] == bk2 and x["kind"] == "org"]
    people = [x["fn"] for x in items if x["book_id"] == bk2 and x["kind"] != "org" and (x.get("org") or "") == "Bakery Ltd"]
    check(len(firm) == 1 and people == ["Jane Doe"], f"{who}: people of this company again {firm} {people}")
    exp2 = s.get(B + f"/api/books/{bk2}/export.vcf").text
    check(exp2.count("X-ABShowAs:COMPANY") == 1 and exp2.count("X-KIND:org") == 1, f"{who}: the marker once after the round trip {exp2!r}")
    apple = ("BEGIN:VCARD\r\nVERSION:3.0\r\nPRODID:-//Apple Inc.//iPhone OS 18.0//EN\r\nN:;;;;\r\nFN:Garden Corp\r\nORG:Garden Corp;\r\n"
             f"X-ABShowAs:COMPANY\r\nUID:apple-firm-{who}\r\nEND:VCARD\r\n")
    r = s.post(B + f"/api/books/{bk2}/import", files={"file": ("a.vcf", apple.encode(), "text/vcard")})
    k = dbx("SELECT kind FROM contacts WHERE uid=?", (f"apple-firm-{who}",))
    check(r.ok and [x[0] for x in k] == ["org"], f"{who}: Apple's X-ABShowAs:COMPANY is a company {k}")
    exp3 = s.get(B + f"/api/books/{bk2}/export.vcf").text
    card = exp3[exp3.index(f"UID:apple-firm-{who}") - 200:]
    check(exp3.count("X-ABShowAs:COMPANY") == 2, f"{who}: Apple's marker once per company, not doubled {card[:400]!r}")


for who, s in (("alice", A), ("frida", Fr)):
    lid = tasks_fixture(s, who)
    csv_roundtrip(s, who, lid)
    md_roundtrip(s, who, lid)
    vc_roundtrip(s, who)

sys.exit(done("p6587_roundtrip_api"))
