#!/usr/bin/env python3
# kalmido-suite: fresh
"""2.1188.0 B API tests (#6152): the central recipes of the receipt fetcher and the helper's download. Invented recipes only,
written into a test folder of the container's data (KALMIDO_FETCHER_RECIPES), never into the repo.
 - GET /api/v1/fetcher/recipes?api=N only with a receipt fetcher key (kbh_): a web session 401, an ordinary token and an agent
   token 403, an unknown fetcher key 401; without api / a bad api / an unknown parameter 400
 - an empty or missing folder: recipes []
 - only complete pairs <id>.py + <id>.sig.json of the asked api, with the id of the file and the sha256 of the file; a pair
   with a wrong sha256, another id, a missing signature, a bad file name (upper case, a hyphen) is left out;
   the fields are the ones the helper reads (id, version, api, sha256, key, sig, source)
 - the settings name the helper's download (/static/downloads/kalmido-belegabholer-<version>.zip); it loads as a zip
freelancer-matrix: files (frida has no organisation: her own office, her own fetcher key)
usage: p21188_b_fetcherrecipes_test.py <datadir>      (a fresh container; P21188B_NOSTART=1 / KMT_NOSTART=1: it runs already)"""
import base64
import hashlib
import json
import os
import shutil
import sys

import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kt  # noqa: E402
from kt import B, check  # noqa: E402
from freelancer_fixture import freelancer  # noqa: E402

V = B + "/api/v1"
kt.fresh(env={"KALMIDO_FETCHER_RECIPES": "/data/fx-recipes"}, prefix="P21188B")
A = kt.setup()
REC = os.path.join(kt.DATA, "fx-recipes")  # /data of the container
shutil.rmtree(REC, ignore_errors=True)


def bearer(tok):
    return {"Authorization": "Bearer " + tok}


def decode(code):
    raw = code[len("kalmido-fetch:1:"):]
    return json.loads(base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4)))


def put(rid, src, api=1, sig_id=None, sha=None, version="1.1.0", name=None, sig=True):
    """An invented recipe pair in the test folder (the signature value is made up: the server never checks it)."""
    os.makedirs(REC, exist_ok=True)
    data = src.encode()
    with open(os.path.join(REC, (name or rid) + ".py"), "wb") as f:
        f.write(data)
    if sig:
        doc = {"id": sig_id or rid, "version": version, "api": api, "sha256": sha or hashlib.sha256(data).hexdigest(),
               "key": "test-1", "sig": base64.b64encode(b"x" * 64).decode()}
        with open(os.path.join(REC, (name or rid) + ".sig.json"), "w", encoding="utf-8") as f:
            json.dump(doc, f)


def recipes(key, q="?api=1"):
    return requests.get(V + "/fetcher/recipes" + q, headers=bearer(key))


# ---- frida without an organisation connects a fetcher (her own office)
FRIDA, Fr = freelancer(B, A, features="files,docs,comments,collab,office")
r = Fr.post(B + "/api/docs/fetchers", json={"ws": "private", "name": "Mac Studio"})
check(r.status_code == 201, f"frida connects a fetcher {r.status_code} {r.text[:200]}")
K = decode(r.json().get("code", "kalmido-fetch:1:")).get("key", "") if r.ok else ""
check(K.startswith("kbh_"), "the setup code carries a kbh_ key")

# ---- an empty / missing folder
r = recipes(K)
check(r.status_code == 200 and r.json() == {"recipes": []}, f"no folder: recipes [] {r.status_code} {r.text[:200]}")
os.makedirs(REC, exist_ok=True)
check(recipes(K).json() == {"recipes": []}, "an empty folder: recipes []")

# ---- who reaches it: only a fetcher key
r = Fr.get(V + "/fetcher/recipes?api=1", headers={"X-Requested-With": "kalmido"})
check(r.status_code in (401, 403), f"frida's web session: 401 / 403 {r.status_code}")
r = Fr.post(B + "/api/me/tokens", json={"name": "files", "scopes": ["read", "files:write"]})
PT = r.json().get("token", "") if r.ok else ""
check(PT and recipes(PT).status_code == 403, "an ordinary API token of frida: 403")
r = Fr.post(B + "/api/my/agents", json={"username": "fridabot", "display_name": "Fridabot", "scopes": ["read", "files:read"]})
AT = r.json().get("token", "") if r.ok else ""
check(AT and recipes(AT).status_code == 403, f"frida's agent token: 403 ({r.status_code})")
check(recipes("kbh_" + "x" * 43).status_code == 401, "an unknown fetcher key: 401")
check(requests.get(V + "/fetcher/recipes?api=1").status_code == 401, "no key: 401")

# ---- the parameter
check(recipes(K, "").status_code == 400, "without api: 400")
check(recipes(K, "?api=eins").status_code == 400, "api not a number: 400")
check(recipes(K, "?api=1&path=../x").status_code == 400, "an unknown parameter: 400")

# ---- the pairs: only complete, matching ones of the asked api
put("amazon", "class Rezept:\n    ID = 'amazon'\n    VERSION = '1.1.0'\n")
put("klarmobil", "class Rezept:\n    ID = 'klarmobil'\n", version="2.0.0")
put("google", "class Rezept:\n    ID = 'google'\n", api=2)
put("wrongsha", "class Rezept:\n    ID = 'wrongsha'\n", sha="0" * 64)            # changed after signing
put("otherid", "class Rezept:\n    ID = 'otherid'\n", sig_id="amazon")           # the signature of another portal
put("nosig", "class Rezept:\n    ID = 'nosig'\n", sig=False)                     # no signature document
put("Upper", "class Rezept:\n    pass\n")                                         # not a recipe id
put("with-dash", "class Rezept:\n    pass\n")                                     # the helper's ids have no hyphen
with open(os.path.join(REC, "broken.py"), "w") as f:
    f.write("x = 1\n")
with open(os.path.join(REC, "broken.sig.json"), "w") as f:
    f.write("{not json")                                                           # an unreadable signature document
put("halfsig", "x = 2\n")
with open(os.path.join(REC, "halfsig.sig.json"), "w") as f:
    json.dump({"id": "halfsig", "version": "1.0.0", "api": 1}, f)                 # incomplete: no sha256 / key / sig
# review 2.1188: a symlinked recipe is never followed, a deeply nested signature document skips its pair (no 500)
_am = open(os.path.join(REC, "amazon.py"), "rb").read()
put("linked", _am.decode(), sha=hashlib.sha256(_am).hexdigest())
os.remove(os.path.join(REC, "linked.py"))
os.symlink("amazon.py", os.path.join(REC, "linked.py"))                         # a link to a signed file of another id
put("deep", "x = 3\n")
with open(os.path.join(REC, "deep.sig.json"), "w") as f:
    f.write("[" * 2000 + "]" * 2000)                                              # RecursionError in json, not a 500
r = recipes(K)
got = r.json().get("recipes", []) if r.ok else []
ids = sorted(x.get("id") for x in got)
check(r.ok and ids == ["amazon", "klarmobil"], f"api 1: only the two complete matching pairs {ids} {r.text[:300]}")
am = next((x for x in got if x.get("id") == "amazon"), {})
check(sorted(am) == ["api", "id", "key", "sha256", "sig", "source", "version"], f"the fields the helper reads {sorted(am)}")
check(am.get("source", "").startswith("class Rezept:") and am.get("api") == 1 and am.get("version") == "1.1.0"
      and am.get("sha256") == hashlib.sha256(am.get("source", "").encode()).hexdigest() and am.get("key") == "test-1",
      f"amazon: source, api, version, sha256 of the source, key {json.dumps(am)[:300]}")
r = recipes(K, "?api=2")
check(r.ok and [x["id"] for x in r.json()["recipes"]] == ["google"], f"api 2: only google {r.text[:200]}")
check(recipes(K, "?api=3").json() == {"recipes": []}, "api 3: none")
# a pair changed later (the .py replaced after signing) disappears at once
with open(os.path.join(REC, "klarmobil.py"), "a") as f:
    f.write("# changed\n")
check([x["id"] for x in recipes(K).json()["recipes"]] == ["amazon"], "klarmobil changed after signing: left out")

# ---- the helper's download in the settings: the newest zip of static/downloads, it loads
j = Fr.get(B + "/api/docs/fetchers?ws=private").json()
dl = j.get("download") or {}
check(dl.get("url", "").startswith("/static/downloads/kalmido-belegabholer-") and dl["url"].endswith(f"-{dl.get('version')}.zip"),
      f"the settings name the download {dl}")
r = requests.get(B + dl.get("url", "/static/downloads/none.zip"))
check(r.status_code == 200 and r.content[:4] == b"PK\x03\x04" and len(r.content) > 10000, f"the zip loads {r.status_code} {len(r.content)}")
check(b"Einrichten.command" in r.content and b"Einrichten.cmd" in r.content, "it holds the setup files for Mac and Windows")

shutil.rmtree(REC, ignore_errors=True)
sys.exit(kt.done("p21188_b_fetcherrecipes"))
