#!/usr/bin/env python3
# kalmido-suite: fresh
"""(#6616, audit #4817): an update across many versions.
 - a SQLite install from before 2.37 (data/tasks.db with content) next to an empty Postgres: the start ends with its own FATAL
   line naming 2.37.0 with the command and the stop at 2.1001.0 (not "point DATABASE_URL"); a missing DATABASE_URL next to
   such a file adds the way; an empty or missing tasks.db changes nothing (the old line about the data dir)
 - the update hint: more than one minor ahead = update_jump (and the link to docs/UPGRADING.md), one minor ahead or none = not
 - docs/UPGRADING.md: the short "how far back" and "from 2.763 on, back only through a backup"; no row per one-way step
Starts its OWN container (start.sh).
freelancer-matrix: admin (server start and the update hint of Administration > Server; nothing per person)
usage: p21508_6616_upgrade_jump_test.py <datadir>"""
import json
import os
import subprocess
import sys

N = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, N)
import kt  # noqa: E402
from kt import B, CT, check  # noqa: E402

SRC = os.environ.get("KALMIDO_SRC") or os.path.join(N, "..")


def in_app(code):
    r = subprocess.run(["docker", "exec", "-w", "/app", "-e", "TASKS_WATCHDOG=0", CT, "python", "-c", "import app, json\n" + code],
                       capture_output=True, text=True, timeout=120)
    out = r.stdout.strip().splitlines()
    return out[-1] if out else "ERR " + r.stderr[-800:]


kt.fresh(prefix="P6616")
A = kt.setup()

# ---- the start of an install from before 2.37
GUARD = """import contextlib, io, os, tempfile
from kalmido.core import db as D
d = tempfile.mkdtemp()
p = os.path.join(d, 'tasks.db')
out = {}
open(p, 'wb').close()
out['empty_file'] = D.sqlite_way(p)
out['missing'] = D.sqlite_way(os.path.join(d, 'nothing.db'))
with open(p, 'wb') as f:
    f.write(b'SQLite format 3\\x00' + b'x' * 100)
out['way'] = D.sqlite_way(p)
D.DB = p
D.table_exists = lambda c, t: False  # stands in for an empty Postgres database
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    try:
        D.startup_guard()
        out['guard_rc'] = None
    except D.DataDirError as e:
        out['guard_rc'] = e.args[0] if e.args else 3
out['guard'] = buf.getvalue()
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    out['no_url_rc'] = D._no_url()
out['no_url'] = buf.getvalue()
D.DB = os.path.join(d, 'nothing.db')
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    try:
        D.startup_guard()
    except D.DataDirError:
        pass
out['guard_plain'] = buf.getvalue()
print(json.dumps(out))"""
raw = in_app(GUARD)
try:
    g = json.loads(raw)
except ValueError:
    g = {}
check(g, f"the start check ran in the container {raw[-600:]}")
check(g.get("empty_file") == "" and g.get("missing") == "", f"an empty or missing tasks.db is no SQLite install {g.get('empty_file')!r}")
way = g.get("way") or ""
check("2.37.0" in way and "KALMIDO_VERSION=v2.37.0 ~/kalmido/update.sh" in way and "2.1001.0" in way, f"the way names 2.37.0 with the command and the stop {way!r}")
gd = g.get("guard") or ""
check(gd.startswith("FATAL: the Postgres database is empty and the data dir holds") and "2.37.0" in gd and "DATABASE_URL" not in gd,
      f"empty Postgres next to tasks.db: its own FATAL line with the way {gd[:300]!r}")
check(g.get("guard_rc") is not None, f"... and the start stops {g.get('guard_rc')}")
nu = g.get("no_url") or ""
check(g.get("no_url_rc") == 3 and "DATABASE_URL is not set" in nu and "If this install still runs on SQLite" in nu and "2.37.0" in nu,
      f"no DATABASE_URL next to tasks.db: the way is added {nu[-300:]!r}")
gp = g.get("guard_plain") or ""
check("2.37.0" not in gp and ("holds Kalmido data" in gp or gp == ""), f"without tasks.db: the line as before {gp[:300]!r}")

# ---- the update hint
check(in_app("from kalmido.core.instance import update_jump as J\n"
             "print(json.dumps([J((2, 1458, 0), (2, 1456, 0)), J((2, 1457, 0), (2, 1456, 0)), J((3, 0, 0), (2, 1456, 9)), J((2, 1456, 3), (2, 1456, 0)), J(None, (2, 1, 0))]))")
      == "[true, false, true, false, false]", "update_jump: more than one minor or a major ahead, not one minor or a patch")
VER = A.get(B + "/api/about").json().get("version") or "0.0.0"
major, minor, _p = (int(x) for x in VER.split("."))


def about_with(latest):
    kt.dbx("INSERT INTO settings(key,value) VALUES('update_info', ?) ON CONFLICT (key) DO UPDATE SET value=excluded.value",
           (json.dumps({"checked_at": "2026-11-20T03:00:00Z", "for": VER, "latest": latest, "url": "https://example.com/r"}),))
    return A.get(B + "/api/about").json()


a = about_with(f"{major}.{minor + 2}.0")
check(a.get("update_jump") is True and (a.get("upgrading_url") or "").endswith("docs/UPGRADING.md"), f"two minors ahead: the hint points to UPGRADING.md {a.get('update_jump')} {a.get('upgrading_url')}")
a = about_with(f"{major}.{minor + 1}.0")
check(a.get("update_jump") is False, f"one minor ahead: no jump {a.get('update_jump')}")
js = open(os.path.join(SRC, "static", "js", "settings.js"), encoding="utf-8").read()
check("a.update_jump && a.upgrading_url ?" in js, "Administration > Server shows the hint with the link")

# ---- docs/UPGRADING.md
up = open(os.path.join(SRC, "docs", "UPGRADING.md"), encoding="utf-8").read()
check("from 2.763 on, back only through a backup" in up and "directly from 2.1000" in up and "2.1001.0 and 2.1380.0" in up,
      "UPGRADING.md: the short rules and the tested starting points")
check("**Never go back before the release with package" not in up, "UPGRADING.md: no paragraph per one-way step any more")
sys.exit(kt.done("p21508_6616_upgrade_jump"))
