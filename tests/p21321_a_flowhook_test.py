#!/usr/bin/env python3
# kalmido-suite: fresh
"""2.1321.0 API tests (#6555): the webhook of a document flow follows the rules of the organisation's webhooks
(integrations/docflowhook.py, docs/flows.py fl_hook_*). A webhook stub inside the container (stub_webhook.py, 127.0.0.1:8097:
/ok 200, /fail 500); invented names only, generated PDFs with a text layer.
 - delivered: carol (admin) sets up a flow with a webhook, a new document calls it, no failure is counted
 - failures: bob's flow calls /fail; every failed attempt is counted at the flow (hook_fails, hook_error with the status);
   after the last retry the webhook switches off (hook_state failures), both admins get the News "integfail", the flow's
   other action (a tag) runs on for the next document but no call goes out; saving the flow again switches it on
 - rights lost: carol becomes a member -- the next call of her flow does not go out, the flow pauses (off, hook_state
   admin), the admin bob hears it; bob switches it on again and is its author from then on, the call goes out again
 - a person without an organisation (freelancer-matrix: files): frida's private flow switches off after failures, she
   hears it herself
freelancer-matrix: files
tenant-matrix: document
usage: p21321_a_flowhook_test.py <datadir>      (a fresh container; KMT_NOSTART=1: it runs already, with the stub)"""
import base64
import json
import os
import shutil
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kt  # noqa: E402
from kt import B, CT, DATA, N, check, dbx, sess, until  # noqa: E402
from freelancer_fixture import FEATURES, freelancer, org_join  # noqa: E402

STUB = "http://127.0.0.1:8097"
KEY = base64.b64encode(os.urandom(32)).decode()  # #6560: the flow's webhook secret is sealed, refused without a server key
kt.fresh(env={"KALMIDO_SECRET_KEY": KEY, "KALMIDO_DOCFLOW_TICK_S": "1", "KALMIDO_WEBHOOK_ALLOW_HOSTS": "127.0.0.1:8097", "KALMIDO_WEBHOOK_BACKOFF": "1,1"},
         prefix="P21321A")
if not kt.nostart("P21321A"):
    shutil.copy(os.path.join(N, "stub_webhook.py"), DATA)
    subprocess.run(["docker", "exec", "-d", CT, "python", "/data/stub_webhook.py"])
    time.sleep(0.8)
A = kt.setup()


def text_pdf(lines):
    """A one-page PDF with a text layer (hand-written, no library)."""
    def esc(s):
        return s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    stream = ("BT /F1 12 Tf 60 740 Td 16 TL " + " ".join(f"({esc(x)}) '" for x in lines) + " ET").encode("latin-1")
    objs = [b"<< /Type /Catalog /Pages 2 0 R >>", b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
            b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream",
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>"]
    out, offs = b"%PDF-1.4\n", []
    for i, o in enumerate(objs, 1):
        offs.append(len(out))
        out += b"%d 0 obj\n" % i + o + b"\nendobj\n"
    x = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1) + b"".join(b"%010d 00000 n \n" % o for o in offs)
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objs) + 1, x)
    return out


def upload(s, name, lines, ws="private"):
    r = s.post(B + "/api/docs", data={"ws": ws}, files=[("files", (name, text_pdf(lines), "application/pdf"))])
    assert r.status_code == 201, r.text
    nid = r.json()["ids"][0]
    until(lambda: (lambda d: d if d and d["state"] in ("done", "failed") else None)(s.get(B + f"/api/docs/{nid}").json()), 90)
    return nid


def calls(path):
    """The calls the stub got on path."""
    p = os.path.join(DATA, "wh.log")
    if not os.path.exists(p):
        return []
    out = []
    for ln in open(p, encoding="utf-8"):
        try:
            x = json.loads(ln)
        except ValueError:
            continue
        if x.get("path") == path:
            out.append(x)
    return out


def rule(s, ws, name):
    rs = s.get(B + f"/api/docs/settings?ws={ws}").json()["rules"]
    return next((x for x in rs if x.get("name") == name), None)


def patch(s, r, **kw):
    """Saves flow r again (as the list's switch does: the whole flow with its version)."""
    body = {k: v for k, v in r.items() if k not in ("id",)}
    body.update(expect_updated_at=r.get("updated_at"), **kw)
    body.pop("updated_at", None)
    return s.patch(B + f"/api/docs/rules/{r['id']}", json=body)


def integfail(s, what):
    return [x for x in s.get(B + "/api/news").json()["items"] if x["kind"] == "integfail" and (x.get("data") or {}).get("what") == what]


def tags(s, nid):
    return sorted(t["name"] for t in (s.get(B + f"/api/docs/{nid}").json() or {}).get("tags") or [])


# ---- setup: Alpha = bob + carol (both admins); frida without an organisation
FR, Fr = freelancer(B, A, "frida")
ids = {}
for u in ("bob", "carol"):
    r = A.post(B + "/api/users", json={"username": u, "display_name": u.title(), "password": "password123", "email": f"{u}@example.com"})
    assert r.ok, r.text
    ids[u] = r.json()["id"]
r = A.post(B + "/api/admin/orgs", json={"name": "Alpha", "admin_id": ids["bob"]})
assert r.status_code == 201, r.text
ORG = r.json()["id"]
OWS = f"org:{ORG}"
Bo = sess("bob")
kt.proved()
check(Bo.put(B + f"/api/orgs/{ORG}/members", json={"email": "carol@example.com"}).ok and org_join(B, "carol", ORG), "setup: carol joins Alpha")
check(Bo.put(B + f"/api/orgs/{ORG}/members", json={"user_id": ids["carol"], "role": "admin"}).ok, "setup: carol is an admin")
Ca = sess("carol")
for s in (Bo, Ca, Fr):
    s.patch(B + "/api/settings", json={"lang": "en", "features": FEATURES, "tour": "done"})

# ---- delivered: carol's flow calls /ok, nothing counted
r = Ca.post(B + "/api/docs/rules", json={"ws": OWS, "name": "Carol", "kind": "any", "match": "Carolfall", "webhook": STUB + "/ok"})
check(r.status_code == 201, f"setup: carol's flow with a webhook {r.status_code} {r.text[:200]}")
upload(Ca, "carol1.pdf", ["Carolfall eins", "Seite 1"], ws=OWS)
check(until(lambda: len(calls("/ok")) == 1, 30), f"delivered: the call went out {len(calls('/ok'))}")
f = rule(Bo, OWS, "Carol")
check(f and f.get("hook_state") == "" and f.get("hook_fails") == 0, f"delivered: nothing counted at the flow {f}")

# ---- failures: counted, switched off after the last retry, the admins hear it, the other action runs on
r = Bo.post(B + "/api/docs/rules", json={"ws": OWS, "name": "Tot", "kind": "any", "match": "Totfall", "tags": ["Totgelesen"], "webhook": STUB + "/fail"})
check(r.status_code == 201, f"setup: bob's flow to a dead target {r.status_code} {r.text[:200]}")
upload(Bo, "tot1.pdf", ["Totfall eins", "Seite 1"], ws=OWS)
f = until(lambda: (lambda x: x if x and x.get("hook_state") == "failures" else None)(rule(Bo, OWS, "Tot")), 60)
check(f and f["hook_fails"] == 3 and "500" in f["hook_error"] and f["hook_error_at"], f"failures: counted and switched off after the last retry {f}")
check(len(calls("/fail")) == 3, f"failures: the first try + 2 retries {len(calls('/fail'))}")
nb, nc = until(lambda: integfail(Bo, "docflow_hook"), 15), until(lambda: integfail(Ca, "docflow_hook"), 15)
check(nb and nc and "Tot" in nb[0]["data"]["text"] and "500" in nb[0]["data"]["text"], f"failures: both admins hear it, with the last error {nb} {nc}")
check(not (f or {}).get("off"), "failures: the flow itself stays on")
d2 = upload(Bo, "tot2.pdf", ["Totfall zwei", "Seite 1"], ws=OWS)
check(until(lambda: "Totgelesen" in tags(Bo, d2), 30), "failures: the flow's other action runs on")
time.sleep(3)  # a few ticks of the webhook loop (1 s backoff): nothing may go out
check(len(calls("/fail")) == 3, f"failures: no call goes out while the webhook is off {len(calls('/fail'))}")
check(dbx("SELECT hook FROM doc_flow_runs WHERE node_id=?", (d2,))[0][0] == "off", "failures: the run's call is marked off")
check(Ca.patch(B + f"/api/docs/rules/{f['id']}", json={"hook_state": "", "hook_fails": 0}).status_code == 200 and
      rule(Bo, OWS, "Tot").get("hook_state") == "failures", "failures: the state cannot be set from outside")
r = patch(Bo, rule(Bo, OWS, "Tot"))
check(r.ok and rule(Bo, OWS, "Tot").get("hook_state") == "" and rule(Bo, OWS, "Tot").get("hook_fails") == 0,
      f"failures: saving the flow again switches the webhook on {r.status_code} {r.text[:200]}")

# ---- rights lost: carol becomes a member -> her flow's call does not go out, the flow pauses, bob hears it
check(Bo.put(B + f"/api/orgs/{ORG}/members", json={"user_id": ids["carol"], "role": "member"}).ok, "setup: carol is a member now")
n_ok = len(calls("/ok"))
upload(Bo, "carol2.pdf", ["Carolfall zwei", "Seite 1"], ws=OWS)
f = until(lambda: (lambda x: x if x and x.get("hook_state") == "admin" else None)(rule(Bo, OWS, "Carol")), 30)
check(f and f.get("off"), f"rights lost: the flow paused {f}")
time.sleep(2)
check(len(calls("/ok")) == n_ok, f"rights lost: the call did not go out to the former admin's target {len(calls('/ok'))} {n_ok}")
nb = until(lambda: integfail(Bo, "docflow_admin"), 15)
check(nb and "Carol" in nb[0]["data"]["text"], f"rights lost: the admin hears it {nb}")
check(not integfail(Ca, "docflow_admin"), "rights lost: the former admin is not told (no admin any more)")
r = patch(Bo, rule(Bo, OWS, "Carol"), off=False)
check(r.ok and dbx("SELECT created_by, hook_state FROM doc_rules WHERE id=?", (f["id"],))[0] == (ids["bob"], ""),
      f"rights lost: switched on again by bob, he is its author now {r.status_code} {r.text[:200]}")
upload(Bo, "carol3.pdf", ["Carolfall drei", "Seite 1"], ws=OWS)
check(until(lambda: len(calls("/ok")) == n_ok + 1, 30), "rights lost: after the new author's switch the call goes out again")

# ---- a person without an organisation: her own flow switches off, she hears it
r = Fr.post(B + "/api/docs/rules", json={"ws": "private", "name": "Frida tot", "kind": "any", "match": "Fridafall", "webhook": STUB + "/fail-frida"})
check(r.status_code == 201, f"freelancer: a flow with a webhook {r.status_code} {r.text[:200]}")
upload(Fr, "frida1.pdf", ["Fridafall eins", "Seite 1"])
f = until(lambda: (lambda x: x if x and x.get("hook_state") == "failures" else None)(rule(Fr, "private", "Frida tot")), 60)
check(f and f["hook_fails"] == 3, f"freelancer: switched off after the last retry {f}")
check(until(lambda: integfail(Fr, "docflow_hook"), 15), "freelancer: she hears it herself")

sys.exit(kt.done("p21321_a_flowhook"))
