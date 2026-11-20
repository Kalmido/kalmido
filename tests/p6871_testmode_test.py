#!/usr/bin/env python3
# kalmido-suite: fresh nodata
"""(#6871): KALMIDO_TEST=1 opens test routes that bypass the separation of accounts (core/objlight.py /api/test/objrole ?as=).
The server does not refuse to start (the test containers run it together with KALMIDO_HOSTED=1), but names it:
 - every start writes one loud line "WARNING test mode: KALMIDO_TEST=1 ..." into the log (app.py, core/db.py test_mode_warn)
 - GET /api/about gives an instance admin test_mode=true (Settings > Server shows the lasting warning, settings.js
   shTestWarn); a person without an organisation (freelancer) gets no such field
freelancer-matrix: own
usage: p6871_testmode_test.py <datadir>      (P6871_NOSTART=1 / KMT_NOSTART=1: a running server)"""
import subprocess
import sys

import kt
from kt import B, CT, check, until
from freelancer_fixture import freelancer

kt.fresh(prefix="P6871")
kt.docker_logs_on_first_fail()
A = kt.setup()

check(kt.container_env("KALMIDO_TEST") == "1", "setup: the test container runs with KALMIDO_TEST=1")


def logs():
    r = subprocess.run(["docker", "logs", CT], capture_output=True, text=True)
    return r.stdout + r.stderr


check(until(lambda: "WARNING test mode: KALMIDO_TEST=1 is set" in logs(), 20),
      "#6871: the start names the test mode loudly in the log")
check(sum(1 for ln in logs().splitlines() if "WARNING test mode" in ln) == 1,
      "#6871: once per start (the first web process), not once per process")

a = A.get(B + "/api/about").json()
check(a.get("test_mode") is True, f"#6871: an instance admin reads test_mode=true in GET /api/about ({a.get('test_mode')!r})")

_, Fr = freelancer(B, A)
f = Fr.get(B + "/api/about").json()
check("test_mode" not in f, "#6871: a person without an organisation (no admin) gets no test_mode field")

sys.exit(kt.done("p6871_testmode"))
