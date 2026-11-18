#!/usr/bin/env python3
# kalmido-suite: fresh
"""2.1385.0 B2 (#6435, audit #4780): hardening of foreign input. Own container (start.sh), invented data; a person without an
organisation (tests/freelancer_fixture.py).
 - 7 the hub inbox (and so the workspace mailbox, the same import hub/hubmail.py _import): one sender files at most
   HBM_IN_SENDER_HOUR (30) mails per workspace and hour, the next one waits (MAIL_LATER, the mail stays in the mailbox);
   another sender still gets through; a double is no new count. A text over HBM_IN_BODY_MAX (50,000) characters is kept
   shortened in the database with the note "The text was shortened" (the whole mail stays in its .eml file)
 - 6 a file name loses its invisible format characters (Unicode Cf: the direction override U+202E, U+2066-2069, U+200E/F,
   zero widths): "rechnung<U+202E>fdp.exe" is stored as "rechnungfdp.exe" (it showed itself as "...exe.pdf"); letters, umlauts
   and emoji stay
usage: p21385_b2_harden_test.py <datadir>"""
import email.message
import os
import subprocess
import sys

N = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, N)
from freelancer_fixture import freelancer  # noqa: E402
import kt  # noqa: E402
from kt import B, CT, check, dbx, done  # noqa: E402

MAILENV = {"KALMIDO_MAIL_ADDRESS": "tasks@example.test", "KALMIDO_IMAP_HOST": "127.0.0.1", "KALMIDO_IMAP_PORT": "1143",
           "KALMIDO_IMAP_SSL": "0", "KALMIDO_IMAP_USER": "kalmido", "KALMIDO_IMAP_PASSWORD": "secret", "KALMIDO_IMAP_INTERVAL": "600"}
kt.fresh(MAILENV)
A = kt.setup()
FU, Fr = freelancer(B, A, "frida")


def box(code):
    """Python code inside the app container (a fresh process with the server's settings)."""
    r = subprocess.run(["docker", "exec", CT, "python", "-c", "import app\nfrom kalmido.core.db import connect\nc = connect()\n" + code
                        + "\nc.commit()\nc.close()"], capture_output=True, text=True, timeout=300)
    return (r.stdout + r.stderr).strip()


def raw_mail(frm, to, subject, text, mid):
    m = email.message.EmailMessage()
    m["From"], m["To"], m["Subject"], m["Message-ID"] = frm, to, subject, mid
    m.set_content(text)
    return m.as_bytes()


IMPORT = ("import email, email.policy\nfrom kalmido.hub import hubmail as H\nfrom kalmido.integrations.mail import MAIL_LATER\n"
          "def one(raw):\n    out = H.hbm_mail_import(c, email.message_from_bytes(raw, policy=email.policy.default), raw)\n"
          "    return 'LATER' if out is MAIL_LATER else out\n")

# ---- 7: the hub inbox, a limit per sender and hour, a shortened text
IN = Fr.post(B + "/api/hubmail/address", json={"ws": "private"}).json().get("address") or ""
check("+" in IN, f"setup: Frida's hub inbox address {IN!r}")
flood = [raw_mail("Nora Sender <nora@example.com>", IN, f"Flood {i}", f"Mail {i}", f"<p21385b2-flood-{i}@example.com>") for i in range(31)]
other = raw_mail("Otto Other <otto@example.com>", IN, "Other", "Another sender", "<p21385b2-other@example.com>")
again = flood[0]
out = box(IMPORT + f"FLOOD = {flood!r}\nprint('res', [one(r) for r in FLOOD])\nprint('again', one({again!r}))\n"
          f"print('other', one({other!r}))")
res = next((ln for ln in out.splitlines() if ln.startswith("res ")), "")
vals = eval(res[4:]) if res else []  # noqa: S307 - our own print of a list of ints / 'LATER'
check(len(vals) == 31 and all(isinstance(v, int) and v > 0 for v in vals[:30]), f"#6435 7: 30 mails of one sender are filed {out[-600:]}")
check(vals[30:] == ["LATER"], f"#6435 7: the 31st mail of the same sender in the hour waits (MAIL_LATER) {vals[30:]}")
check("again 0" in out, f"#6435 7: the same mail again is a double (no new count, not filed twice) {out[-300:]}")
other_id = next((ln.split()[1] for ln in out.splitlines() if ln.startswith("other ")), "")
check(other_id.isdigit() and int(other_id) > 0, f"#6435 7: another sender is still filed {out[-300:]}")
n = dbx("SELECT count(*) FROM hub_mails WHERE owner_id=? AND message_id LIKE ?", (FU, "<p21385b2-flood-%"))[0][0]
check(n == 30, f"#6435 7: exactly 30 of the flood are in the database ({n})")

long_raw = raw_mail("Lena Long <lena@example.com>", IN, "Long one", "word " * 11000, "<p21385b2-long@example.com>")
out = box(IMPORT + f"print('long', one({long_raw!r}))")
lid = next((ln.split()[1] for ln in out.splitlines() if ln.startswith("long ")), "")
check(lid.isdigit(), f"setup: the long mail is filed {out[-400:]}")
r = Fr.get(B + f"/api/hubmail/mails/{lid}")
j = r.json() if r.ok else {}
check(r.ok and len(j.get("body") or "") == 50000, f"#6435 7: the text is kept shortened to 50,000 characters ({len(j.get('body') or '')})")
check("The text was shortened" in (j.get("note") or ""), f"#6435 7: the mail notes the shortened text {j.get('note')!r}")
check(bool(j.get("eml_id")), "#6435 7: the whole mail stays in its .eml file")
short_raw = raw_mail("Lena Long <lena@example.com>", IN, "Short one", "A short text", "<p21385b2-short@example.com>")
out = box(IMPORT + f"print('short', one({short_raw!r}))")
sid = next((ln.split()[1] for ln in out.splitlines() if ln.startswith("short ")), "")
j = Fr.get(B + f"/api/hubmail/mails/{sid}").json() if sid.isdigit() else {}
check(j.get("body") == "A short text" and "shortened" not in (j.get("note") or ""), f"#6435 7: a short text stays whole, no note {j.get('note')!r}")

# ---- 6: invisible direction / format characters leave a file name
out = box("from kalmido.tasks.attachments import safe_name\n"
          "print('names', [safe_name(x) for x in ('rechnung\\u202efdp.exe', 'a\\u2066b\\u2069\\u200ec\\u200f\\u200b.pdf', "
          "'\\u00c4rger \\U0001f600.pdf', '\\u202a\\u202c')])")
check("names ['rechnungfdp.exe', 'abc.pdf', '\u00c4rger \U0001f600.pdf', 'datei']" in out, f"#6435 6: safe_name drops the Cf characters {out[-300:]}")
lid = Fr.post(B + "/api/lists", json={"name": "Film", "kind": "project"}).json()["id"]
tid = Fr.post(B + "/api/tasks", json={"title": "Invoice", "list_id": lid}).json()["id"]
r = Fr.post(B + f"/api/tasks/{tid}/attachments", files={"file": ("rechnung\u202efdp.exe", b"MZ not really\n", "application/octet-stream")})
check(r.ok, f"setup: the file on the task {r.status_code} {r.text[:200]}")
names = [a.get("name") for a in (r.json().get("attachments") or [])] if r.ok else []
check(names == ["rechnungfdp.exe"], f"#6435 6: the task file is stored without the direction override {names!r}")

sys.exit(done("p21385_b2_harden"))
