#!/usr/bin/env python3
# kalmido-suite: fresh
"""#7445: a new one-shot of the start is a fragment kalmido/core/oncesteps.d/<task>.py (its function + a list STEPS), loaded in
name order behind the fixed STEPS of its phase -- never a line at the end of oncesteps.STEPS (case F114: two packages appending
there collided in the merge queue). Own container for the run, the lint part is static.
 - the lint (tools/check_migrations.py) on a copy: the repository's folder passes; a good fragment passes; a key twice (fixed +
   fragment, two fragments), an unknown phase, a key of RETIRED, a migr_ flag of another key, a function not in the file, a
   bad file name and a file without STEPS are findings
 - the run (core/oncesteps.py once_frag_load + run_phase): a fragment with a once step and relative imports runs in its phase
   behind the fixed steps, exactly once over two runs (the runner writes its flag); a step of another phase does not run there
 - the folder is in the image (the README keeps it; once_frag_load of the app's folder = [] without fragments)
usage: p7445_oncefrag_test.py <datadir>"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

N = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(N, "..")
sys.path.insert(0, N)
sys.path.insert(0, os.path.join(ROOT, "tools"))
import check_migrations as cm  # noqa: E402
import kt  # noqa: E402
from kt import CT, check  # noqa: E402

GOOD = '''"""(#9001): a probe."""
from .db import gset, gsetting


def migr_probe9001(c):
    gset(c, "p7445_runs", str(int(gsetting(c, "p7445_runs") or 0) + 1))


def migr_late9001(c):
    gset(c, "p7445_late", "1")


STEPS = [("cdn_backfill", "migr_probe9001", True, migr_probe9001), ("later_phase", "migr_late9001", True, migr_late9001)]
'''

# ================================================================ the lint, static
tmp = tempfile.mkdtemp()
try:
    core = os.path.join(tmp, "kalmido", "core")
    shutil.copytree(os.path.join(ROOT, "kalmido", "core", "oncesteps.d"), os.path.join(core, "oncesteps.d"))
    for f in ("oncesteps.py", "db.py"):
        shutil.copy(os.path.join(ROOT, "kalmido", "core", f), core)
    D = os.path.join(core, "oncesteps.d")
    check(cm.once_findings(ROOT) == [], f"the repository passes {cm.once_findings(ROOT)[:5]}")
    check(cm.once_findings(tmp) == [], f"the copy with the folder's README only passes {cm.once_findings(tmp)}")

    def frag(name, src):
        with open(os.path.join(D, name), "w", encoding="utf-8") as f:
            f.write(src)

    def lint(*names):
        out = cm.once_findings(tmp)
        for n in names:
            os.remove(os.path.join(D, n))
        return out

    frag("9001.py", GOOD.replace('"later_phase"', '"cdn_backfill"'))
    check(lint("9001.py") == [], "a good fragment passes")
    frag("9001.py", GOOD.replace("migr_probe9001", "migr_upg2103"))
    out = lint("9001.py")
    check(any("key migr_upg2103 already in kalmido/core/oncesteps.py" in x for x in out), f"a key of the fixed STEPS again is a finding {out}")
    frag("9001.py", GOOD.replace('"later_phase"', '"cdn_backfill"'))
    frag("9002_b.py", 'def f(c):\n    pass\n\n\nSTEPS = [("cdn_backfill", "migr_probe9001", True, f)]\n')
    out = lint("9001.py", "9002_b.py")
    check(any("9002_b.py" in x and "key migr_probe9001 already in kalmido/core/oncesteps.d/9001.py" in x for x in out),
          f"a key twice over two fragments is a finding {out}")
    frag("9001.py", GOOD)
    out = lint("9001.py")
    check(len(out) == 1 and "phase later_phase is none of" in out[0], f"an unknown phase is a finding (init_db never runs it) {out}")
    frag("9001.py", GOOD.replace('"later_phase"', '"cdn_backfill"').replace("migr_late9001", "migr_kind"))
    out = lint("9001.py")
    check(any("migr_kind is in RETIRED" in x for x in out), f"a retired key is a finding {out}")
    frag("9001.py", GOOD.replace('"later_phase"', '"cdn_backfill"').replace('gset(c, "p7445_late", "1")', 'gset(c, "migr_other", "1")'))
    out = lint("9001.py")
    check(any("migr_other is not a key of this fragment" in x for x in out), f"a flag of another key is a finding {out}")
    frag("9001.py", GOOD.replace('"later_phase"', '"cdn_backfill"').replace("True, migr_late9001)", "True, missing)"))
    out = lint("9001.py")
    check(any("missing is no function of this file" in x for x in out), f"a function from elsewhere is a finding {out}")
    frag("probe.py", GOOD.replace('"later_phase"', '"cdn_backfill"'))
    out = lint("probe.py")
    check(any("probe.py: name must be" in x for x in out), f"a name without the task id is a finding {out}")
    frag("9003.py", "X = 1\n")
    out = lint("9003.py")
    check(any("needs one list STEPS" in x for x in out), f"a file without STEPS is a finding {out}")
    frag("9004.py", 'from .db import gset\n\n\ndef f(c):\n    gset(c, "migr_x9004", "1")\n\n\nSTEPS = [("cdn_backfill", "migr_x9004", True, f)]\n')
    with open(os.path.join(core, "late.py"), "w", encoding="utf-8") as f:
        f.write('def g(c):\n    gsetting(c, "migr_x9004")\n')
    out = lint("9004.py")
    check(any("late.py" in x and "outside" in x for x in out), f"the flag outside its fragment (another module) stays a finding {out}")
finally:
    shutil.rmtree(tmp, ignore_errors=True)

# ================================================================ the run, in the container
kt.fresh(prefix="P7445")
kt.docker_logs_on_first_fail()
RUN = f"""
import json, os, tempfile
import app
import kalmido.core.oncesteps as O
from kalmido.core.db import connect, gsetting
from kalmido.core.pg import system_ctx
here = O.once_frag_load()
d = tempfile.mkdtemp()
with open(os.path.join(d, "9001.py"), "w") as f:
    f.write({GOOD!r})
O.FRAG_STEPS = O.once_frag_load(d)
c = connect()
logs = []
with system_ctx(c):
    for _ in range(2):
        log = []
        O.run_phase(c, log.append, "cdn_backfill")
        c.commit()
        logs.append(log)
    out = {{"here": here, "folder": os.path.isdir(O.ONCE_D), "readme": os.path.isfile(os.path.join(O.ONCE_D, "README.md")),
           "steps": [x[:3] for x in O.FRAG_STEPS], "logs": logs, "runs": gsetting(c, "p7445_runs"),
           "flag": gsetting(c, "migr_probe9001"), "late": gsetting(c, "p7445_late"), "late_flag": gsetting(c, "migr_late9001"),
           "fixed": [k for p, k, o, f in O.STEPS if p == "cdn_backfill" and not o]}}
print("OUT" + json.dumps(out))
"""
r = subprocess.run(["docker", "exec", "-w", "/app", "-e", "TASKS_WATCHDOG=0", CT, "python", "-c", RUN], capture_output=True, text=True, timeout=200)
out = next((json.loads(x[3:]) for x in r.stdout.splitlines() if x.startswith("OUT")), None)
check(out is not None, "the run inside the app: " + r.stdout[-400:] + r.stderr[-1500:])
out = out or {"here": None, "folder": False, "readme": False, "steps": [], "logs": [[], []], "runs": "", "flag": "", "late": "", "late_flag": "", "fixed": []}
check(out["folder"] and out["readme"] and out["here"] == [], f"the folder is in the image, without fragments nothing loads {out['here']}")
check(out["steps"] == [["cdn_backfill", "migr_probe9001", True], ["later_phase", "migr_late9001", True]], f"the fragment's STEPS load {out['steps']}")
first, second = out["logs"]
check("migr_probe9001" in first and first.index("migr_probe9001") > max(first.index(k) for k in out["fixed"]),
      f"the fragment's step runs in its phase, behind the fixed steps {first}")
check(out["runs"] == "1" and out["flag"] == "1", f"it ran exactly once over two runs, the runner wrote its flag {out['runs']} {out['flag']}")
check("migr_probe9001" not in second, f"the second run skips it {second}")
check(out["late"] == "" and out["late_flag"] in ("", "0") and "migr_late9001" not in first + second,
      f"a step of another phase does not run in this one {out['late']} {out['late_flag']}")

sys.exit(kt.done("p7445_oncefrag"))
