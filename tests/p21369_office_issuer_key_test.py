#!/usr/bin/env python3
# kalmido-suite: fresh
"""2.1369.0 API tests (#6699): invoice issuer keys (office/issuers.py). Own container (start.sh, mode workspaces, the operator
interface with a token file). Invented companies, people and figures only.
tenant-matrix: office  freelancer-matrix: office
In an organisation's office (Alice its admin, Bob a member) and in the personal office of a person without an organisation:
 - management: only the organisation's admin sets up an issuer (member 403 for reading and writing), setting up asks for the
   password (password_needed, a wrong one 403); the key "kis_test_" + 43 characters is shown once, never stored (only its hash,
   never in api_tokens)
 - the key: GET /api/v1/issuer = name, environment, range, mode review, key prefix / end, limits, tax profile (from the company
   data and the office settings: ISS_REUSED, each function checked with the issuer's context); never the address rule or bank
   accounts; any other /api/v1 route 403, /api/office with the key 403, the replay header 401, an invalid key 401, a key of the
   other environment 401, an unknown query field 400
 - pause by an admin (403 issuer_paused, resume without password), 20 refused routes = self-pause (resume asks for the
   password), 20 x 400 = no pause; the rate limit 60 a minute (429)
 - keys: overlap 15 days 400, at most two valid keys (409), a new key with overlap 0 ends the old one at once, ending a key
   works at once; revoking the issuer ends every key
 - address rule: tightening needs no password and refuses another address (403 address_refused), loosening asks for it;
   limits: lowering free, raising asks for the password, out of range / unknown 400
 - bank accounts: only with the password, never readable with the key; log lines by the issuer and by the admin
 - alarms reach the owner of a personal office (News "integfail")
 - moving the personal office into an organisation revokes its issuers (the preview names them)
 - KALMIDO_ISSUER_KEYS=0: management 404, the key 403 issuer_keys_off; KALMIDO_HOSTED=1: off until the operator unlocks the
   area (PUT /api/operator/accounts/<id> issuer_keys), locking again pauses; KALMIDO_ISSUER_ENV=live: a test key 401, a new
   issuer needs addresses, its key starts with kis_live_
usage: p21369_office_issuer_key_test.py <datadir>"""
import os
import re
import secrets
import shutil
import subprocess
import sys

import requests

N = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, N)
import kt  # noqa: E402
from kt import B, check  # noqa: E402
import dbx as dbxm  # noqa: E402
from freelancer_fixture import FEATURES, PASSWORD, freelancer, login, org_join  # noqa: E402

kt.docker_logs_on_first_fail()
DATA = sys.argv[1] if len(sys.argv) > 1 else kt.DATA
OF = "/api/office"
IS = OF + "/issuers"
V = B + "/api/v1"
OPDIR = os.path.abspath(DATA.rstrip("/")) + "-op"
TOKEN = secrets.token_urlsafe(40)
os.environ["EXTRA"] = (os.environ.get("EXTRA", "") + f" -v {OPDIR}:/run/kop:ro -e KALMIDO_OPERATOR_TOKEN_FILE=/run/kop/token").strip()
COMPANY = {"name": "Studio Nordlicht", "street": "Hafenstraße 12", "zip": "20457", "city": "Hamburg", "country": "AT",
           "email": "hallo@nordlicht.example", "tax_number": "12/345/67890", "iban": "DE02120300000000202051", "bic": "BYLADEM1001"}
IBAN2 = "DE89370400440532013000"
KEY_RE = re.compile(r"kis_test_[A-Za-z0-9_-]{43}")
# the office functions an issuer route calls without a person (office/issuers.py ISS_REUSED): each checked below
REUSED_CHECKED = ("office.ledger.ofx_company", "office.model.office_settings")


def sql(q, args=(), write=False):
    c = dbxm.connect(os.path.join(DATA, "tasks.db"), timeout=10)
    try:
        r = c.execute(q, args)
        if write:
            c.commit()
            return None
        return r.fetchall()
    finally:
        c.close()


def ws(s, v):
    r = s.patch(B + "/api/settings", json={"workspace": v})
    assert r.ok, r.text


def key_get(key, path="/issuer", **kw):
    h = {"Authorization": "Bearer " + key, **kw.pop("headers", {})}
    return requests.get(V + path, headers=h, timeout=30, **kw)


def op(method, path, **kw):
    return requests.request(method, B + "/api/operator/" + path, headers={"Authorization": "Bearer " + TOKEN}, timeout=60, **kw)


def code(r):
    try:
        return (r.json().get("error") or {}).get("code") if isinstance(r.json().get("error"), dict) else None
    except ValueError:
        return None


def news(uid, what):
    return sql("SELECT data FROM notifications WHERE user_id=? AND kind='integfail' AND data LIKE ?", (uid, f'%"what": "{what}"%'))


# ---------------------------------------------------------------- the container
shutil.rmtree(OPDIR, ignore_errors=True)
os.makedirs(OPDIR)
with open(os.path.join(OPDIR, "token"), "w") as f:
    f.write(TOKEN + "\n")
os.chmod(OPDIR, 0o755)
os.chmod(os.path.join(OPDIR, "token"), 0o644)
kt.fresh({"KALMIDO_INSTANCE_MODE": "workspaces"}, data=DATA)
A = kt.setup()
A.patch(B + "/api/settings", json={"lang": "en", "features": FEATURES, "tour": "done"})
ALICE = A.get(B + "/api/state").json()["me"]["id"]
r = A.post(B + "/api/users", json={"username": "bob", "display_name": "Bob Member", "password": PASSWORD, "email": "bob@example.com"})
assert r.ok, r.text
ORG = A.post(B + "/api/admin/orgs", json={"name": "Alpha", "admin_id": ALICE}).json()["id"]
assert A.put(B + f"/api/orgs/{ORG}/members", json={"email": "bob@example.com", "role": "member"}).ok
org_join(B, "bob", ORG)
ws(A, f"org:{ORG}")
Bo = login(B, "bob")
Bo.patch(B + "/api/settings", json={"lang": "en", "features": FEATURES, "tour": "done", "workspace": f"org:{ORG}"})
FID, Fr = freelancer(B, A)
ws(Fr, "private")


def setup_area(S, label, code_):
    """A number range and the company data of the office S works in -> the range id."""
    assert S.put(B + OF + "/settings", json={"company_fields": COMPANY, "small_business": True}).ok
    r = S.post(B + OF + "/num-ranges", json={"code": code_, "scheme": code_ + "-{yyyy}-{seq:03}"})
    assert r.status_code == 201, r.text
    return r.json()["id"]


RG = setup_area(A, "org", "GT")

# ---------------------------------------------------------------- management rights and the password
r = Bo.get(B + IS)
check(r.status_code == 403, f"a member does not read the issuers {r.status_code}")
r = Bo.post(B + IS, json={"name": "Shop", "range_id": RG, "password": PASSWORD})
check(r.status_code == 403 and not sql("SELECT 1 FROM office_issuers"), f"a member sets up no issuer {r.status_code}")
r = A.get(B + IS)
check(r.ok and r.json().get("admin") is True and r.json().get("environment") == "test" and any(x["id"] == RG for x in r.json().get("ranges") or []),
      f"the admin reads the issuers and the open ranges {r.text[:200]}")
r = A.post(B + IS, json={"name": "Shop", "range_id": RG})
check(r.status_code == 403 and r.json().get("password_needed") is True and not sql("SELECT 1 FROM office_issuers"), f"setting up asks for the password {r.text[:160]}")
r = A.post(B + IS, json={"name": "Shop", "range_id": RG, "password": "wrong-one"})
check(r.status_code == 403 and not sql("SELECT 1 FROM office_issuers"), f"a wrong password sets up nothing {r.status_code}")
r = A.post(B + IS, json={"name": "Shop", "range_id": RG, "password": PASSWORD, "mode": "auto"})
check(r.status_code == 400 and not sql("SELECT 1 FROM office_issuers"), f"no mode field (only review exists) {r.status_code}")
TOK0 = sql("SELECT COUNT(*) FROM api_tokens")[0][0]
r = A.post(B + IS, json={"name": "Shop", "range_id": RG, "password": PASSWORD})
check(r.status_code == 201, f"the admin sets up an issuer {r.status_code} {r.text[:200]}")
IID, KEY = r.json()["issuer"]["id"], r.json().get("key") or ""
check(bool(KEY_RE.fullmatch(KEY)), f"the key: kis_test_ + 43 characters {KEY[:14]}")
check(not sql("SELECT 1 FROM office_issuer_keys WHERE token_hash=? OR prefix=?", (KEY, KEY)) and sql("SELECT COUNT(*) FROM api_tokens")[0][0] == TOK0,
      "only the hash is stored, nothing in api_tokens")
check("key" not in A.get(B + IS).json()["issuers"][0] and all("token" not in k and "hash" not in k for k in A.get(B + IS).json()["issuers"][0]["keys"][0]),
      "the list never shows the key again")
check(r.json()["issuer"]["mode"] == "review" and r.json()["issuer"]["limits"]["day_docs"] == 50 and r.json()["issuer"]["limits"]["max_gross"] == "2000.00",
      f"review mode, careful default limits {r.json()['issuer']['limits']}")

# ---------------------------------------------------------------- the key's own view (ISS_REUSED with the issuer's context)
r = key_get(KEY)
j = r.json() if r.ok else {}
check(r.ok and j.get("name") == "Shop" and j.get("environment") == "test" and j.get("mode") == "review" and j.get("range", {}).get("code") == "GT",
      f"GET /issuer with the key {r.status_code} {r.text[:200]}")
check(j.get("tax_profile") == {"country": "AT", "small_business": True}, f"tax profile from the company data (ofx_company) and settings (office_settings) {j.get('tax_profile')}")
check(j.get("key", {}).get("prefix", "").startswith("kis_test_") and j.get("key", {}).get("expires_at"), f"the key's prefix and end {j.get('key')}")
check(not ({"allowed_ips", "payees", "keys", "addresses", "created_by"} & set(j)), f"no address rule, accounts or admins in the key's view {sorted(j)}")
src = open(os.path.join(N, "..", "kalmido", "office", "issuers.py")).read()
m = re.search(r"ISS_REUSED = \(([^)]*)\)", src)
check(m and sorted(re.findall(r'"([^"]+)"', m.group(1))) == sorted(REUSED_CHECKED), f"ISS_REUSED is exactly what this suite checks {m.group(1) if m else None}")
check(key_get(KEY, params={"x": "1"}).status_code == 400, "an unknown query field 400")
check(key_get(KEY, "/tasks").status_code == 403, "another /api/v1 route with the key: 403")
r = requests.get(B + IS, headers={"Authorization": "Bearer " + KEY, "X-Requested-With": "kalmido"}, timeout=30)
check(r.status_code == 403, f"/api/office with the key: 403 {r.status_code}")
check(key_get(KEY, headers={"X-Kalmido-Replay": "x" * 40}).status_code == 401, "the key with the replay header: 401")
check(key_get(KEY[:-3] + "abc").status_code == 401, "an invalid key: 401")
check(key_get("kis_live_" + KEY[len("kis_test_"):]).status_code == 401, "the same key as a live key on a test server: 401")
lg = A.get(B + IS + f"/{IID}/log").json().get("log") or []
check(any(x["action"] == "issuer_created" and x["by"] == "person" for x in lg) and any(x["action"] == "issuer_read" and x["by"] == "issuer" for x in lg)
      and any(x["action"] == "issuer_refused" for x in lg), f"the log: set up by a person, read and refused by the issuer {[x['action'] for x in lg]}")

# ---------------------------------------------------------------- pause, self-pause, rate
r = A.post(B + IS + f"/{IID}/pause")
check(r.ok and r.json()["issuer"]["paused"] and r.json()["issuer"]["paused_reason"] == "admin", f"pause {r.text[:160]}")
r = key_get(KEY)
check(r.status_code == 403 and code(r) == "issuer_paused" and r.headers.get("Retry-After"), f"a paused issuer: 403 issuer_paused {r.text[:160]}")
r = A.post(B + IS + f"/{IID}/resume")
check(r.ok and not r.json()["issuer"]["paused"] and key_get(KEY).ok, f"resume after an admin's pause, without the password {r.text[:160]}")
for i in range(20):
    key_get(KEY, params={"bad": str(i)})
check(not A.get(B + IS).json()["issuers"][0]["paused"] and key_get(KEY).ok, "20 x 400 pause nothing")
for i in range(20):
    key_get(KEY, f"/tasks/{i + 1}")
x = A.get(B + IS).json()["issuers"][0]
check(x["paused"] and x["paused_reason"] == "refused", f"20 refused routes: self-pause {x['paused_reason']}")
check(bool(news(ALICE, "issuer_paused")), "the admins hear of the self-pause")
r = A.post(B + IS + f"/{IID}/resume")
check(r.status_code == 403 and r.json().get("password_needed"), f"resume after a self-pause asks for the password {r.status_code}")
r = A.post(B + IS + f"/{IID}/resume", json={"password": PASSWORD})
check(r.ok and not r.json()["issuer"]["paused"], f"resume with the password {r.text[:120]}")

# ---------------------------------------------------------------- limits and the address rule
r = A.patch(B + IS + f"/{IID}", json={"limits": {"day_docs": 10, "max_gross": "1000"}})
check(r.ok and r.json()["issuer"]["limits"]["day_docs"] == 10, f"lowering a limit needs no password {r.text[:160]}")
r = A.patch(B + IS + f"/{IID}", json={"limits": {"day_docs": 100}})
check(r.status_code == 403 and r.json().get("password_needed"), f"raising a limit asks for the password {r.status_code}")
r = A.patch(B + IS + f"/{IID}", json={"limits": {"day_docs": 100}, "password": PASSWORD})
check(r.ok and r.json()["issuer"]["limits"]["day_docs"] == 100, f"raised with the password {r.status_code}")
check(A.patch(B + IS + f"/{IID}", json={"limits": {"day_docs": 10001}}).status_code == 400, "a limit above its highest value: 400")
check(A.patch(B + IS + f"/{IID}", json={"limits": {"unlimited": 1}}).status_code == 400, "an unknown limit: 400")
check(A.patch(B + IS + f"/{IID}", json={"limits": {"day_docs": -1}}).status_code == 400, "a negative limit: 400")
r = A.patch(B + IS + f"/{IID}", json={"allowed_ips": ["192.0.2.10/32"]})
check(r.ok and r.json()["issuer"]["allowed_ips"] == ["192.0.2.10/32"], f"tightening the address rule needs no password {r.text[:160]}")
r = key_get(KEY)
check(r.status_code == 403 and code(r) == "address_refused", f"a call from another address: 403 {r.text[:160]}")
r = A.patch(B + IS + f"/{IID}", json={"allowed_ips": []})
check(r.status_code == 403 and r.json().get("password_needed"), f"removing the address rule asks for the password {r.status_code}")
r = A.patch(B + IS + f"/{IID}", json={"allowed_ips": [], "password": PASSWORD})
check(r.ok and r.json()["issuer"]["allowed_ips"] == [] and key_get(KEY).ok, f"removed with the password, the key works again {r.status_code}")
x = A.get(B + IS).json()["issuers"][0]
check(len(x["addresses"]) >= 1 and x["addresses"][0]["calls"] >= 1, f"the addresses the key was used from {x['addresses']}")
check(bool(news(ALICE, "issuer_ip")), "first call from a new address: the admins hear it")

# ---------------------------------------------------------------- bank accounts
r = A.post(B + IS + f"/{IID}/payees", json={"label": "Main", "holder": "Studio Nordlicht GmbH", "iban": IBAN2, "ref_only": True})
check(r.status_code == 403 and r.json().get("password_needed"), f"a bank account asks for the password {r.status_code}")
check(A.post(B + IS + f"/{IID}/payees", json={"label": "x", "holder": "y", "iban": "DE00123", "password": PASSWORD}).status_code == 400, "an invalid IBAN: 400")
r = A.post(B + IS + f"/{IID}/payees", json={"label": "Main", "holder": "Studio Nordlicht GmbH", "iban": IBAN2, "ref_only": True, "password": PASSWORD})
check(r.status_code == 201 and r.json()["payee"]["iban"] == IBAN2 and r.json()["payee"]["ref_only"] is True, f"bank account added {r.text[:200]}")
PID = r.json()["payee"]["id"] if r.status_code == 201 else 0
check(IBAN2 not in key_get(KEY).text, "the key never reads the bank accounts")
check(Bo.get(B + IS + f"/{IID}/payees").status_code == 403, "a member does not read the bank accounts")
r = A.delete(B + IS + f"/{IID}/payees/{PID}")
check(r.ok and not A.get(B + IS + f"/{IID}/payees").json()["payees"], f"bank account removed {r.status_code}")

# ---------------------------------------------------------------- keys: overlap, at most two, end at once
check(A.post(B + IS + f"/{IID}/keys", json={"overlap_days": 15, "password": PASSWORD}).status_code == 400, "an overlap of 15 days: 400")
r = A.post(B + IS + f"/{IID}/keys", json={"overlap_days": 7})
check(r.status_code == 403 and r.json().get("password_needed"), f"a new key asks for the password {r.status_code}")
r = A.post(B + IS + f"/{IID}/keys", json={"overlap_days": 7, "password": PASSWORD})
KEY2 = r.json().get("key", "") if r.status_code == 201 else ""
check(r.status_code == 201 and KEY_RE.fullmatch(KEY2) and key_get(KEY).ok and key_get(KEY2).ok, f"a new key, the old one still works in the overlap {r.status_code}")
r = A.post(B + IS + f"/{IID}/keys", json={"overlap_days": 7, "password": PASSWORD})
check(r.status_code == 409, f"at most two valid keys: 409 {r.status_code}")
k2 = next(k for k in A.get(B + IS).json()["issuers"][0]["keys"] if KEY2.startswith(k["prefix"]))
r = A.delete(B + IS + f"/{IID}/keys/{k2['id']}")
check(r.ok and key_get(KEY2).status_code == 401 and key_get(KEY).ok, f"a key ended at once: 401, the other works {r.status_code}")
r = A.post(B + IS + f"/{IID}/keys", json={"overlap_days": 0, "password": PASSWORD})
KEY3 = r.json().get("key", "") if r.status_code == 201 else ""
check(r.status_code == 201 and key_get(KEY3).ok and key_get(KEY).status_code == 401, f"overlap 0: the old key ends now {r.status_code}")
check(bool(news(ALICE, "issuer_key")), "a new key: the admins hear of it")

# ---------------------------------------------------------------- revoke
r = A.post(B + IS, json={"name": "Second", "range_id": RG, "password": PASSWORD})
I2, K2 = (r.json()["issuer"]["id"], r.json()["key"]) if r.status_code == 201 else (0, "")
codes = [key_get(K2).status_code for _ in range(62)]
check(codes[0] == 200 and codes[-1] == 429, f"the rate limit: 60 a minute, then 429 {codes[-5:]}")
check(not next(x for x in A.get(B + IS).json()["issuers"] if x["id"] == I2)["paused"], "429 never pauses")
r = A.delete(B + IS + f"/{I2}")
check(r.ok and key_get(K2).status_code == 401 and all(x["id"] != I2 for x in A.get(B + IS).json()["issuers"]), f"revoked: its key 401, gone from the list {r.status_code}")
check(A.patch(B + IS + f"/{I2}", json={"name": "again"}).status_code == 404, "a revoked issuer cannot be changed (404)")

# ---------------------------------------------------------------- the personal office of a person without an organisation  # freelancer-matrix: office
FRG = setup_area(Fr, "private", "WEB")
r = Fr.post(B + IS, json={"name": "Own script", "range_id": FRG, "password": PASSWORD})
check(r.status_code == 201, f"private office: the owner sets up an issuer {r.status_code} {r.text[:200]}")
FI, FK = (r.json()["issuer"]["id"], r.json()["key"]) if r.status_code == 201 else (0, "")
r = key_get(FK)
check(r.ok and r.json().get("range", {}).get("code") == "WEB" and r.json().get("tax_profile", {}).get("country") == "AT", f"private office: the key's view {r.text[:200]}")
check(A.get(B + IS + f"/{FI}/log").status_code == 404, "another office's issuer: 404")
check(Fr.get(B + IS + f"/{IID}/log").status_code == 404 and Fr.post(B + IS + f"/{IID}/pause").status_code == 404, "the organisation's issuer from the private office: 404")
for i in range(20):
    key_get(FK, f"/lists/{i + 1}")
check(bool(news(FID, "issuer_paused")), "private office: the alarm of the self-pause reaches the owner")
r = Fr.post(B + IS + f"/{FI}/resume", json={"password": PASSWORD})
check(r.ok and key_get(FK).ok, f"private office: resumed {r.status_code}")
# the move into an organisation revokes it
BETA = A.post(B + "/api/admin/orgs", json={"name": "Beta", "admin_id": FID}).json()["id"]
r = Fr.get(B + OF + f"/move/check?org={BETA}")
check(r.ok and any("invoice issuer" in x for x in r.json().get("notes") or []), f"move preview names the issuer {r.text[:300]}")
r = Fr.post(B + OF + "/move/org", json={"org": BETA, "confirm": True})
check(r.ok, f"move: the personal office moves {r.status_code} {r.text[:200]}")
check(key_get(FK).status_code == 401 and sql("SELECT revoked_at IS NOT NULL FROM office_issuers WHERE id=?", (FI,))[0][0],
      "move: the issuer is revoked, its key 401")

# ---------------------------------------------------------------- server switches (the same data, restarted)
kt.fresh({"KALMIDO_INSTANCE_MODE": "workspaces", "KALMIDO_ISSUER_KEYS": "0"}, keep=True, data=DATA)
A = kt.sess("alice")
r = key_get(KEY3)
check(r.status_code == 403 and code(r) == "issuer_keys_off", f"KALMIDO_ISSUER_KEYS=0: the key 403 {r.text[:160]}")
check(A.get(B + IS).status_code == 404, "KALMIDO_ISSUER_KEYS=0: the management 404")

kt.fresh({"KALMIDO_INSTANCE_MODE": "workspaces", "KALMIDO_HOSTED": "1"}, keep=True, data=DATA)
A = kt.sess("alice")
check(key_get(KEY3).status_code == 403 and A.get(B + IS).status_code == 404, "hosted: off until the operator unlocks the organisation")
acc = op("GET", f"accounts/{ALICE}").json().get("account") or {}
check(any(o["id"] == ORG and o["on"] is False for o in (acc.get("issuer_keys") or {}).get("orgs") or []), f"the operator sees the switch {acc.get('issuer_keys')}")
check(op("PUT", f"accounts/{ALICE}", json={"issuer_keys": {"area": 999999, "on": True}}).status_code == 404, "the operator: an area the account is no admin of 404")
r = op("PUT", f"accounts/{ALICE}", json={"issuer_keys": {"area": ORG, "on": True}})
check(r.ok and key_get(KEY3).ok and A.get(B + IS).ok, f"hosted: the operator unlocks, the key works {r.status_code} {r.text[:160]}")
r = op("PUT", f"accounts/{ALICE}", json={"issuer_keys": {"area": ORG, "on": False}})
check(r.ok and sql("SELECT paused_reason FROM office_issuers WHERE id=?", (IID,))[0][0] == "operator", "hosted: locking again pauses the issuers")

kt.fresh({"KALMIDO_INSTANCE_MODE": "workspaces", "KALMIDO_ISSUER_ENV": "live"}, keep=True, data=DATA)
A = kt.sess("alice")
check(key_get(KEY3).status_code == 401, "a live server takes no test key")
r = A.post(B + IS, json={"name": "Live", "range_id": RG, "password": PASSWORD})
check(r.status_code == 400, f"a live issuer needs addresses {r.status_code}")
r = A.post(B + IS, json={"name": "Live", "range_id": RG, "allowed_ips": ["198.51.100.0/24"], "password": PASSWORD})
check(r.status_code == 201 and str(r.json().get("key", "")).startswith("kis_live_") and len(r.json()["key"]) == len("kis_live_") + 43,
      f"a live server gives out kis_live_ keys {r.status_code}")

sys.exit(kt.done("p21369_office_issuer_key"))
