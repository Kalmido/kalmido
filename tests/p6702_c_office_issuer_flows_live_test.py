#!/usr/bin/env python3
# kalmido-suite: fresh
"""(#6702, review F1 of job/5775) tools/issuer_flows.py against a server that gives out live keys (KALMIDO_ISSUER_ENV=live):
setup reads the environment before it writes anything and stops with exit 2 - no organisation "Vertragstest", no issuer,
no key file. Own container (start.sh, mode workspaces, KALMIDO_ISSUER_KEYS on, KALMIDO_ISSUER_ENV live).
usage: p6702_c_office_issuer_flows_live_test.py <datadir>"""
import os
import subprocess
import sys
import tempfile
from urllib.parse import urlsplit

N = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, N)
import kt  # noqa: E402
from kt import B, PASSWORD, check  # noqa: E402
from freelancer_fixture import FEATURES  # noqa: E402

kt.docker_logs_on_first_fail()
DATA = sys.argv[1] if len(sys.argv) > 1 else kt.DATA
TOOL = os.path.join(N, "..", "tools", "issuer_flows.py")
KEYF = os.path.join(tempfile.mkdtemp(prefix="kis-live-"), "key")

kt.fresh({"KALMIDO_INSTANCE_MODE": "workspaces", "KALMIDO_ISSUER_KEYS": "1", "KALMIDO_ISSUER_ENV": "live"}, data=DATA)
A = kt.setup()
A.patch(B + "/api/settings", json={"lang": "en", "features": FEATURES, "tour": "done"})
assert A.patch(B + "/api/settings", json={"workspace": "private"}).ok
r = A.get(B + "/api/office/issuers")
check(r.ok and r.json().get("environment") == "live", f"the server gives out live keys {r.status_code} {r.text[:120]}")

r = subprocess.run([sys.executable, TOOL, "setup", "--url", B, "--test-host", urlsplit(B).hostname, "--key-file", KEYF, "--login", "alice"],
                   env={**os.environ, "KIS_ADMIN_PASSWORD": PASSWORD}, capture_output=True, text=True, timeout=300)
print(r.stdout[-2000:], r.stderr[-2000:], flush=True)
check(r.returncode == 2 and "REFUSED" in r.stdout and "'live'" in r.stdout, f"setup on a live server: exit 2, refused {r.returncode}")
orgs = [o for o in A.get(B + "/api/admin/orgs").json().get("orgs") or [] if o.get("name") == "Vertragstest"]
check(not orgs and not os.path.exists(KEYF), f"nothing written: no organisation Vertragstest, no key file {orgs}")
check(not [i for i in A.get(B + "/api/office/issuers").json().get("issuers") or []], "no issuer")
r = subprocess.run([sys.executable, TOOL, "run", "--url", B, "--test-host", urlsplit(B).hostname, "--key-file", KEYF, "--login", "alice"],
                   env={**os.environ, "KIS_ADMIN_PASSWORD": PASSWORD}, capture_output=True, text=True, timeout=300)
check(r.returncode != 0, f"run without a key file does not run {r.returncode}")

sys.exit(kt.done("p6702_c_office_issuer_flows_live"))
