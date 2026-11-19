#!/usr/bin/env python3
# kalmido-suite: fresh
"""#6583: the account import's run in operation. Invented names only (example.com). A person without an organisation
(freelancer, P4) exports a project and imports the file again:
 - the result stays after the watchdog's clean-up (was: the folder of a finished run went at the next pass, about 10 minutes):
   state.json and the result stay UMZ_KEEP_H hours, the uploaded archive is gone at once; an old folder goes
 - every warning is kept in imports.warnings (the result names at most 50), the report file names them all; another person's
   import has no report for me (404); the list of imports counts them
 - a run that was interrupted (state "running", no queue row, the upload there) falls back to the preview and starts again;
   without the upload it says "interrupted" as before
 - an error after the commit says "imported, the follow-up work failed" with the import's id (undo), not "Nothing was imported"
 - the end of a run is a News item (kind umzdone, row "import" of the notification settings): finished / failed with the reason;
   the row switched off writes nothing
usage: p6583_import_flow_test.py <datadir>      (a fresh container; P6583_NOSTART=1 = the server already runs)"""
# freelancer-matrix: own
# tenant-matrix: own
import json
import os
import subprocess
import sys
import time

N = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, N)
from freelancer_fixture import freelancer  # noqa: E402
from kt import B, CT, check, dbx, done, fresh, setup, su_get, until  # noqa: E402

fresh({"KALMIDO_INSTANCE_MODE": "workspaces"}, prefix="P6583")
A = setup("alice", "Alice Admin")
A.patch(B + "/api/settings", json={"lang": "en", "tour": "done"})
FID, F = freelancer(B, A)
F.patch(B + "/api/settings", json={"lang": "en", "tour": "done"})


def py(code):
    """Runs code in a second process of the container -> the last line of its output as JSON."""
    r = {}
    for _try in range(3):  # the import may meet the running server's start-up DDL (deadlock): try again
        r = subprocess.run(["docker", "exec", "-w", "/app", "-e", "TASKS_WATCHDOG=0", "-e", "KALMIDO_ROLE=web", CT,
                            "python", "-c", "import app\n" + code], capture_output=True, text=True)
        if "DeadlockDetected" not in r.stdout + r.stderr:
            break
        time.sleep(2)
    try:
        return json.loads(r.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        print(r.stdout[-2000:], r.stderr[-3000:], flush=True)
        return {}


def export(s):
    check(s.post(B + "/api/account/export").status_code in (200, 202), "the export starts")
    st = until(lambda: (lambda j: j if j.get("state") != "running" else None)(s.get(B + "/api/account/export").json()), timeout=120)
    check((st or {}).get("state") == "done", f"the export is done {st}")
    return su_get(s, B + "/api/account/export/file").content


def wait(s, iid):
    return until(lambda: (lambda j: j if j.get("state") not in ("checking", "running", "upload") else None)(
        s.get(B + f"/api/account/import/{iid}").json()), timeout=120) or {}


def upload(s, data):
    r = s.post(B + "/api/account/import", json={"size": len(data), "name": "probe.kalmido-export"})
    assert r.ok, r.text
    iid, off = r.json()["id"], 0
    while off < len(data):
        part = data[off:off + (1 << 20)]
        assert s.put(B + f"/api/account/import/{iid}?offset={off}", data=part, headers={"Content-Type": "application/octet-stream"}).ok
        off += len(part)
    return iid, wait(s, iid)


def run(s, iid, again=False):
    r = s.post(B + f"/api/account/import/{iid}/run", json={"target": "private", "people": {}, **({"again": True} if again else {})})
    check(r.status_code == 202, f"the run starts {r.status_code} {r.text[:200]}")
    return wait(s, iid)


FOLDER = "import json, os\nfrom kalmido.admin import acctimport as ai\nd = ai._dir({uid}, {iid!r})\n"


def folder(iid, code):
    return py(FOLDER.format(uid=FID, iid=iid) + code)


def news(kind="umzdone"):
    return [json.loads(r[0]) if isinstance(r[0], str) else r[0] for r in dbx("SELECT data FROM notifications WHERE user_id=? AND kind=? ORDER BY id", (FID, kind))]


LID = F.post(B + "/api/lists", json={"name": "Umzug Bericht"}).json()["id"]
F.post(B + "/api/tasks", json={"title": "Kiste packen", "list_id": LID})
FILE = export(F)

# ---------------------------------------------------------------- the result stays after the clean-up, the archive goes
iid, j = upload(F, FILE)
check(j.get("state") == "preview", f"the upload is checked {j.get('state')} {j.get('error')}")
j = run(F, iid)
res = j.get("result") or {}
IMP = res.get("import_id")
check(j.get("state") == "done" and IMP and res.get("warn_more") == 0, f"the import is done {j}")
w = dbx("SELECT warnings FROM imports WHERE id=?", (IMP,))
check(w and isinstance(json.loads(w[0][0]) if isinstance(w[0][0], str) else w[0][0], list), f"the import's record has its warnings (a list) {w}")
n = news()
check(len(n) == 1 and "is finished" in (n[0].get("text") or "") and n[0].get("click") == "settings/data", f"the person hears the end of the run {n}")
st = folder(iid, "print(json.dumps({'up': os.path.exists(os.path.join(d, 'upload.bin')), 'n': ai.umz_import_cleanup(), 'st': os.path.exists(os.path.join(d, 'state.json'))}))")
check(st.get("up") is False and st.get("st") is True, f"the archive is gone at once, the state stays through the clean-up {st}")
j = F.get(B + f"/api/account/import/{iid}").json()
check(j.get("state") == "done" and (j.get("result") or {}).get("import_id") == IMP, f"#6583: the result is still there after the clean-up {j.get('state')}")
st = folder(iid, "import json, time\np = os.path.join(d, 'state.json')\nt = time.time() - (ai.UMZ_KEEP_H + 1) * 3600\nos.utime(p, (t, t))\n"
                 "ai.umz_import_cleanup()\nprint(json.dumps({'gone': not os.path.exists(d)}))")
check(st.get("gone") is True, f"a folder older than UMZ_KEEP_H hours goes {st}")
check(F.get(B + f"/api/account/import/{iid}").status_code == 404, "and its state with it")

# ---------------------------------------------------------------- every warning: the record, the report file, the list
cut = py("import json\nfrom kalmido.admin.acctimport import _Run\nr = _Run(1, 'x', 'e', None, 1)\n"
         "[r.warning('w {0}', i) for i in range(70)]\nr.warning('must', must=True)\n"
         "print(json.dumps({'cut': len(r.warnings()), 'full': len(r.warnings(full=True)), 'first': r.warnings()[0]['text']}))")
check(cut == {"cut": 51, "full": 71, "first": ["must"]}, f"the result names 50 plus the must ones, the record all of them {cut}")
WARN = [{"text": ["Assignment not imported (the person is not on this server or was not selected)"], "count": 2}] + \
       [{"text": ["Already here from an earlier import, skipped: {0} entries", i], "count": 1} for i in range(60)]
dbx("UPDATE imports SET warnings=? WHERE id=?", (json.dumps(WARN), IMP))
r = F.get(B + f"/api/imports/{IMP}/report")
txt = r.text
check(r.status_code == 200 and r.headers.get("Content-Type", "").startswith("text/plain") and "attachment" in r.headers.get("Content-Disposition", ""),
      f"the report is a text file to download {r.status_code} {r.headers}")
check("Warnings: 61" in txt and "Assignment not imported" in txt and "(2)" in txt and "skipped: 59 entries" in txt and "probe.kalmido-export" in txt,
      f"the report names every warning, uncut {txt[:400]}")
check(A.get(B + f"/api/imports/{IMP}/report").status_code == 404, "another person's import has no report for me")
rows = [x for x in F.get(B + "/api/imports").json().get("imports", []) if x["id"] == IMP]
check(rows and rows[0].get("warnings") == 61, f"the list of imports counts the warnings {rows}")

# ---------------------------------------------------------------- an interrupted run falls back to the preview
iid, j = upload(F, FILE)
check(j.get("state") == "preview" and j["preview"].get("again") is True, f"the same file again: preview {j.get('state')}")
folder(iid, "import json\nai._set(%d, %r, state='running', progress={'done': 3, 'total': 9}, target=None)\nprint('{}')" % (FID, iid))
j = F.get(B + f"/api/account/import/{iid}").json()
check(j.get("state") == "preview" and j.get("interrupted") is True and (j.get("preview") or {}).get("again") is True,
      f"#6583: an interrupted run is back at its preview (was: failed, upload again) {j.get('state')} {j.get('error')}")
check(F.get(B + f"/api/account/import/{iid}").json().get("state") == "preview", "it stays there (written, not only shown)")
j = run(F, iid, again=True)
check(j.get("state") == "done" and not j.get("interrupted"), f"and starts again {j.get('state')} {j.get('error')}")
iid, j = upload(F, FILE)
folder(iid, "import json\nai._set(%d, %r, state='running')\nos.remove(os.path.join(d, 'upload.bin'))\nprint('{}')" % (FID, iid))
j = F.get(B + f"/api/account/import/{iid}").json()
check(j.get("state") == "failed" and "interrupted" in (j.get("error") or ""), f"without the upload: interrupted as before {j}")
F.delete(B + f"/api/account/import/{iid}")

# ---------------------------------------------------------------- an error after the commit: imported, the follow-up failed
check(F.post(B + f"/api/imports/{IMP}/undo").ok, "the first import undone (the file counts as new)")
iid, j = upload(F, FILE)
check(j.get("state") == "preview", f"uploaded again {j.get('state')}")
before = len(news())
out = folder(iid, "import json\n"
                  "def boom(*a, **k):\n    raise RuntimeError('test: after the commit')\n"
                  "ai.umz_fix_people = boom\n"
                  "ai._set(%d, %r, state='running', progress={'done': 0, 'total': 1}, target=None)\n"
                  "ai.umz_run(%d, %r, {'org': None, 'people': {}, 'can_invite': False, 'invites': 0})\n"
                  "print(json.dumps(ai._st(%d, %r)))" % (FID, iid, FID, iid, FID, iid))
res = out.get("result") or {}
check(out.get("state") == "done" and res.get("import_id") and res.get("trouble"),
      f"#6583: an error after the commit says imported (was: failed, Nothing was imported) {out.get('state')} {out.get('error')}")
j = F.get(B + f"/api/account/import/{iid}").json()
check("follow-up work failed" in ((j.get("result") or {}).get("trouble") or "") and (j.get("result") or {}).get("undo_until"),
      f"the result names it, the undo is offered {j.get('result')}")
w = dbx("SELECT warnings FROM imports WHERE id=?", (res.get("import_id"),))
check(w and "follow-up work failed" in (w[0][0] if isinstance(w[0][0], str) else json.dumps(w[0][0])), f"the record keeps the warning {w}")
n = news()
check(len(n) == before + 1 and "follow-up work failed" in (n[-1].get("text") or ""), f"the person hears it {n[-1:]}")
check(F.post(B + f"/api/imports/{res.get('import_id')}/undo").ok, "that import can be undone")

# ---------------------------------------------------------------- a failed run: the reason; the row "import" switched off
iid, j = upload(F, FILE)
before = len(news())
out = folder(iid, "import json\n"
                  "def boom(*a, **k):\n    raise RuntimeError('test: before the commit')\n"
                  "ai.umz_write = boom\n"
                  "ai._set(%d, %r, state='running')\n"
                  "ai.umz_run(%d, %r, {'org': None, 'people': {}, 'can_invite': False, 'invites': 0})\n"
                  "print(json.dumps(ai._st(%d, %r)))" % (FID, iid, FID, iid, FID, iid))
check(out.get("state") == "failed", f"a run that fails before the commit: failed {out.get('state')}")
n = news()
check(len(n) == before + 1 and "failed" in (n[-1].get("text") or "") and "Nothing was imported" in (n[-1].get("text") or ""), f"the person hears the reason {n[-1:]}")
check("import" in (F.get(B + "/api/state").json().get("notify") or {}), "the row import is in the notification settings")
check(F.patch(B + "/api/settings", json={"notify": {"import": {"news": 0, "push": 0}}}).ok, "the row import switched off")
F.delete(B + f"/api/account/import/{iid}")
iid, j = upload(F, FILE)
before = len(news())
folder(iid, "import json\n"
            "def boom(*a, **k):\n    raise RuntimeError('test')\n"
            "ai.umz_write = boom\nai._set(%d, %r, state='running')\n"
            "ai.umz_run(%d, %r, {'org': None, 'people': {}, 'can_invite': False, 'invites': 0})\nprint('{}')" % (FID, iid, FID, iid))
check(len(news()) == before, "switched off: no News item")

sys.exit(done("p6583_import_flow"))
