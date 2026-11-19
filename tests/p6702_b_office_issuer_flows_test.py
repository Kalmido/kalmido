#!/usr/bin/env python3
# kalmido-suite: after=p6702_office_issuer_contract
"""(#6702) tools/issuer_flows.py - the test organisation "Vertragstest" and the flows of an outside system - run against the
test container of p6702_office_issuer_contract (KALMIDO_ISSUER_KEYS on, a test server), as it runs on the staging server:
 - setup: the organisation Vertragstest, the range VT-{yyyy}-{seq}, the issuer in the review mode, the key only in the key
   file (mode 0600, never in the output); a second setup keeps all of it
 - run: Germany 19 % with a unit price of 4 places, EU reverse charge, a third country, the same request again, the
   conflict, the hold mark, finalised by the person, numbers VT-..., the archived PDF / XML byte for byte; every step ok
   except the mail (the test container has no mail server; on staging the catcher takes it)
 - the locks before anything is written (review F1-F3 of job/5775): --test-host other than the URL's host, the hosted
   service, plain http to a public host: exit 2; a key file left with a wider mode gets 0600 again with the new key; a key
   the server does not know: exit 2 (the live server's own refusal: p6702_c_office_issuer_flows_live)
Invented companies and figures only.
usage: p6702_b_office_issuer_flows_test.py <datadir>"""
import json
import os
import stat
import subprocess
import sys
import tempfile
from urllib.parse import urlsplit

N = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, N)
import kt  # noqa: E402
from kt import B, PASSWORD, check  # noqa: E402

TOOL = os.path.join(N, "..", "tools", "issuer_flows.py")
TMP = tempfile.mkdtemp(prefix="kis-flows-")
KEYF = os.path.join(TMP, "key")
ENV = {**os.environ, "KIS_ADMIN_PASSWORD": PASSWORD}


HOST = urlsplit(B).hostname


def tool(*args, url=B, host=HOST):
    r = subprocess.run([sys.executable, TOOL, *args, "--url", url, "--test-host", host, "--key-file", KEYF, "--login", "alice"], env=ENV,
                       capture_output=True, text=True, timeout=600)
    print(r.stdout[-3000:], r.stderr[-2000:], flush=True)
    return r


for url, host, why in ((B, "127.0.0.2", "another --test-host"), ("https://app.kalmido.com", "app.kalmido.com", "the hosted service"),
                       ("http://test.example.org", "test.example.org", "plain http to a public host")):
    r = tool("setup", url=url, host=host)
    check(r.returncode == 2 and "REFUSED" in r.stdout and not os.path.exists(KEYF), f"{why}: exit 2, nothing done {r.returncode}")
r = tool("setup")
key = open(KEYF, encoding="utf-8").read().strip() if os.path.exists(KEYF) else ""
check(r.returncode == 0 and key.startswith("kis_test_"), f"setup: exit 0, a test key in the key file {r.returncode}")
check(os.path.exists(KEYF) and stat.S_IMODE(os.stat(KEYF).st_mode) == 0o600, "the key file has mode 0600")
check(key and key not in r.stdout + r.stderr, "the key is never printed")
S = kt.sess("alice")
orgs = [o for o in S.get(B + "/api/admin/orgs").json().get("orgs") or [] if o.get("name") == "Vertragstest"]
check(len(orgs) == 1, f"the organisation Vertragstest {orgs}")
r = tool("setup")
check(r.returncode == 0 and open(KEYF, encoding="utf-8").read().strip() == key, "a second setup keeps the organisation, the issuer and the key")
check(len([o for o in S.get(B + "/api/admin/orgs").json().get("orgs") or [] if o.get("name") == "Vertragstest"]) == 1, "still one organisation")

# review F3: the issuer revoked, the old key file left readable for others -> the new key, the file 0600 again
iid = [i for i in S.get(B + "/api/office/issuers").json().get("issuers") or [] if i.get("name") == "Vertragstest" and not i.get("revoked_at")]
r = S.delete(B + f"/api/office/issuers/{iid[0]['id']}", json={"password": PASSWORD}) if iid else None
check(r is not None and r.ok, f"the issuer revoked {r.status_code if r is not None else None}")
os.chmod(KEYF, 0o644)
r = tool("setup")
key2 = open(KEYF, encoding="utf-8").read().strip()
check(r.returncode == 0 and key2.startswith("kis_test_") and key2 != key and stat.S_IMODE(os.stat(KEYF).st_mode) == 0o600,
      f"a new issuer, its key in the old file with mode 0600 again {r.returncode} {oct(stat.S_IMODE(os.stat(KEYF).st_mode))}")

out = os.path.join(TMP, "out")
r = tool("run", "--out", out)
summary = json.load(open(os.path.join(out, "summary.json"), encoding="utf-8")) if os.path.exists(os.path.join(out, "summary.json")) else {}
steps = summary.get("steps") or []
bad = [s_ for s_ in steps if not s_["ok"] and "mail" not in s_["step"]]
check(steps and not bad, f"run: every step ok but the mail (no mail server in the container) {bad}")
for want in ("draft de", "draft at", "draft ch", "the same request again", "409 ref_conflict", "hold mark", "shows the hold mark",
             "de: finalised", "at: finalised", "ch: finalised", "de: number VT", "de: the archived pdf"):
    check(any(want in s_["step"] and s_["ok"] for s_ in steps), f"run: the step {want!r}")
check(any(f.endswith(".pdf") for f in os.listdir(out)), "the archived PDFs are written")
r2 = tool("run", "--out", out + "2")
check(r2.returncode in (0, 1) and "client test:account:de as before" in r2.stdout,
      "a second run takes the clients as they are (expect_updated_at); its files may meet the key's 10 a minute")

# a live key never runs: the tool reads the environment from the server, a forged file changes nothing
with open(KEYF, "w", encoding="utf-8") as f:
    f.write("kis_live_" + "x" * 43 + "\n")
r = tool("run", "--out", out + "3")
check(r.returncode == 2 and not os.path.exists(os.path.join(out + "3", "summary.json")), f"a key the test server does not know: exit 2, nothing done {r.returncode}")

sys.exit(kt.done("p6702_b_office_issuer_flows"))
