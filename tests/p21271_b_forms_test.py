#!/usr/bin/env python3
# kalmido-suite: fresh
"""2.1271.0 (#6424): an answer with many line breaks in a public questionnaire no longer holds the server up. Own container
(start.sh). Invented accounts only (example.com).
 - fq_md (team/formq.py) runs in linear time: 8,000 and 80,000 line breaks (also \\r\\n, blanks between) take well under a second
   (before: \\s* after (?m)^ ran over every following break, seconds to minutes)
 - it still disarms a heading / list of the sender's own after blanks, tabs, \\r, \\r\\n and form feeds
 - fq_lines: at most 200 lines per answer, the rest joins the last line (no typed word is lost)
 - the public route: a sender without an account sends a long answer with 7,980 breaks to a form of a person without an
   organisation; it arrives quickly as a task with at most 200 lines of the answer, its last words included
freelancer-matrix: own
usage: p21271_b_forms_test.py <datadir>"""
import os
import re
import subprocess
import sys
import time

import requests

import kt
from kt import B, CT, check, sess

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from freelancer_fixture import freelancer  # noqa: E402

H = {"X-Requested-With": "kalmido"}
kt.fresh()


def py(code):
    r = subprocess.run(["docker", "exec", "-i", CT, "python", "-c", code], capture_output=True, text=True, timeout=300)
    return (r.stdout.strip().splitlines() or [""])[-1], r.stderr[-600:]


# ---- fq_md in linear time (the attack input of the audit: 'a' + 7,998 breaks; and ten times that)
out, er = py("""
import time
from kalmido.team.formq import fq_md
worst = 0.0
for v in ("a" + "\\n" * 7998, "a" + "\\n" * 79998, "a" + "\\r\\n" * 40000, "a" + "\\n \\t" * 30000, "1" + "\\n" * 80000 + "1."):
    t = time.monotonic()
    fq_md(v)
    worst = max(worst, time.monotonic() - t)
print(round(worst, 3))
""")
check(out and float(out) < 1.0, f"fq_md: 8,000 / 80,000 line breaks (also \\r\\n, blanks between) in well under a second: {out} s {er}")

# ---- the protection stays: no heading / list of the sender's own, also after blanks, tabs, \r, \r\n and form feeds
out, er = py(r"""
import json
from kalmido.team.formq import fq_md
cases = ["\n  # x", "\n\t- x", "\n 1. x", "# x", "+ x", "\r# x", "a\r\n- x", "a\n\r# x", "a\n\x0c# x", "a\n \t 2) x", "a\n\n\n   + x"]
print(json.dumps([fq_md(v) for v in cases]))
""")
try:
    import json
    got = json.loads(out)
except ValueError:
    got = []
mark = re.compile(r"(?m)^[ \t\x0c]*(#|[+\-](?=\s|$)|\d+[.)](?=\s|$))")
check(len(got) == 11 and not any(mark.search(v) for v in got) and all("\r" not in v for v in got),
      f"fq_md still disarms headings and lists after blanks, tabs, \\r, \\r\\n, form feeds: {got} {er}")
check(got[:3] == ["\n  \\# x", "\n\t\\- x", "\n 1\\. x"], f"... the indentation stays, the mark is escaped {got[:3]}")

# ---- fq_lines: at most 200 lines, the rest joins the last one
out, er = py(r"""
import json
from kalmido.team.formq import fq_lines, FQ_LINES_MAX
v = "\n".join(f"w{i}" for i in range(300))
x = fq_lines(v)
print(json.dumps([FQ_LINES_MAX, x.count("\n") + 1, x.split("\n")[-1][:20], x.split("\n")[-1][-9:], fq_lines("a\nb") == "a\nb",
                  fq_lines("a" + "\r\n" * 500 + "end")]))
""")
try:
    got = json.loads(out)
except ValueError:
    got = []
check(got[:5] == [200, 200, "w199 w200 w201 w202 ", "w298 w299", True], f"fq_lines: 200 lines, the rest in the last line, short answers unchanged {got} {er}")
check(len(got) == 6 and got[5].count("\n") == 199 and got[5].endswith("\nend") and "\r" not in got[5],
      f"fq_lines: \\r\\n counts as a break, the surplus empty lines go {repr(got[5][-20:]) if len(got) == 6 else got} {er}")

# ---- the public route (a form of a person without an organisation)
A = kt.sess(None)
assert A.post(B + "/api/auth/setup", json={"username": "alice", "display_name": "Alice", "password": "password123"}).ok
A = sess("alice")
A.post(B + "/api/admin/setup", json={"org_name": "Alpha", "lang": "en", "collab_all": True, "modules": ["comments"]})
A = sess("alice")
A.patch(B + "/api/admin/settings", json={"public_links": True})
FID, Fr = freelancer(B, A)
FL = Fr.post(B + "/api/lists", json={"name": "Requests", "org_id": None}).json()["id"]
r = Fr.post(B + f"/api/lists/{FL}/forms", json={"title": "Questionnaire", "access": "public",
                                                "questions": [{"kind": "long", "label": "Your story", "required": True}]})
check(r.status_code == 201, "frida makes a public questionnaire " + r.text[:160])
FQ = r.json()
QID, TOK = FQ["questions"][0]["id"], FQ["url"].rsplit("/", 1)[1]
anon = requests.Session()
anon.headers.update(H)
page = anon.get(B + "/f/" + TOK).text
m = re.search(r'name="stamp" value="([^"]+)"', page)
ST = m.group(1) if m else ""
kt.until(lambda: time.time() - int(ST.split(".")[0] or 0) > 3.2, 10)  # the stamp's least age (FRM_MIN_S): a real state
ans = "start" + "\n" * 7980 + "the last words"  # 7,999 characters: within FQ_LONG_MAX (8,000), cut before
t = time.monotonic()
r = anon.post(B + "/f/" + TOK, data={f"q_{QID}": ans, "name": "Eve", "email": "eve@example.com", "stamp": ST})
took = time.monotonic() - t
check(r.ok and "Your request has been sent." in r.text, f"the send with 7,980 breaks arrives {r.status_code} {r.text[-200:]}")
check(took < 5, f"... quickly ({took:.2f} s)")
row = kt.dbx("SELECT content FROM tasks WHERE list_id=? ORDER BY id DESC LIMIT 1", (FL,))
body = row[0][0] if row else ""
part = body.split("### Your story\n", 1)[-1].split("\n\n— ", 1)[0]
check(row and "start" in part and "the last words" in part and part.count("\n") + 1 <= 200,
      f"the task holds the answer in at most 200 lines, its last words included ({part.count(chr(10)) + 1} lines)")
sys.exit(kt.done("p21271_b_forms"))
