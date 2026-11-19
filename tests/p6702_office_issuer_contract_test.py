#!/usr/bin/env python3
# kalmido-suite: fresh
"""(#6702) The contract test of the invoice issuer API: the running server and the code against docs/api/issuer-contract.json.
A hard suite (tests/hard_suites.txt, pattern *office*): a Kalmido release cannot change what an outside system relies on
without changing that file, and a change of that file is named in docs/API.md (notice of 90 days). Own container (start.sh,
mode workspaces, KALMIDO_ISSUER_KEYS on). Invented companies, people and figures only.
tenant-matrix: office  freelancer-matrix: office
The code, read as text (no import of the app):
 - the routes of the key (@app.* "/api/v1/issuer...") = the contract's routes; each one in the OpenAPI description
 - every error the issuer modules raise (status + name) is in the contract with that status, every name of the contract is raised
 - the request fields, the lists of values and the fixed limits = the constants of the code
 - docs/API.md names every route and every error name, the file and the rule of changes (90 days)
The running server (an organisation's office and the personal office of a person without an organisation):
 - every answer has exactly the contract's fields (the key's view, a client, a draft, a finalised invoice, a page of changes,
   a withdrawn draft: by its ref status withdrawn while in the office's trash, 410 withdrawn once purged); every value of a
   list is one of the contract's
 - every error answer: the status and the class of its name as in the contract, the name allowed for its route, the body's
   fields (code, message and the named extras), Retry-After where the contract names it
 - the refused fields of an invoice (date, number, finalize ...) each 400 unknown_field
 - the OpenAPI description: the same routes and the same lists of values
usage: p6702_office_issuer_contract_test.py <datadir>"""
import json
import os
import re
import sys

import requests

N = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, N)
import kt  # noqa: E402
from kt import B, check  # noqa: E402
import dbx as dbxm  # noqa: E402
from freelancer_fixture import FEATURES, PASSWORD, freelancer  # noqa: E402

kt.docker_logs_on_first_fail()
DATA = sys.argv[1] if len(sys.argv) > 1 else kt.DATA
ROOT = os.path.join(N, "..")
C = json.load(open(os.path.join(ROOT, "docs", "api", "issuer-contract.json"), encoding="utf-8"))
ERR, ROUTES, OBJ, ENUM, REQ, LIM = C["errors"], C["routes"], C["objects"], C["enums"], C["requests"], C["limits"]
ISS_FILES = ("issuers.py", "issclients.py", "issdocs.py")


def src(*p):
    with open(os.path.join(ROOT, *p), encoding="utf-8") as f:
        return f.read()


def tup(text, name):
    """The string items of the tuple / list / dict literal NAME = (...) in text (dict: its keys)."""
    m = re.search(rf"^{name}\s*=\s*([(\[{{])", text, re.M)
    if not m:
        return None
    close = {"(": ")", "[": "]", "{": "}"}[m.group(1)]
    body = text[m.end():text.index(close, m.end())] if close != "}" else text[m.end():text.index("}\n", m.end())]
    if close == "}":
        return re.findall(r'"([a-z_]+)"\s*:', body)
    return re.findall(r'"([^"]+)"', body)


def num(text, name):
    m = re.search(rf"^{name}\s*=\s*(\d+)\b", text, re.M)
    if m:
        return int(m.group(1))
    m = re.search(rf"^([A-Z_, ]*\b{name}\b[A-Z_, ]*)=\s*([\d, ]+)$", text, re.M)  # A, B = 1, 2
    if m:
        names = [x.strip() for x in m.group(1).split(",")]
        return int(m.group(2).split(",")[names.index(name)])
    return None


def norm_route(method, path):
    return method.upper() + " " + re.sub(r"<[^>]+>|\{[^}]+\}", "{}", path.replace(C["base"], "", 1))


# ================================================================ the code against the contract (static)
SRC = {f: src("kalmido", "office", f) for f in ISS_FILES}
ALL = "\n".join(SRC.values())

# -- routes
code_routes = set()
for dirpath, _d, files in os.walk(os.path.join(ROOT, "kalmido")):
    for fn in files:
        if fn.endswith(".py"):
            t = open(os.path.join(dirpath, fn), encoding="utf-8").read()
            for m in re.finditer(r'@app\.(get|put|post|patch|delete)\("(/api/v1/issuer[^"]*)"', t):
                code_routes.add(norm_route(m.group(1), m.group(2)))
contract_routes = {norm_route(*k.split(" ", 1)) for k in ROUTES}
check(code_routes == contract_routes, f"the key's routes in the code = the contract's: only code {sorted(code_routes - contract_routes)}, "
                                      f"only contract {sorted(contract_routes - code_routes)}")
spec_paths = set(re.findall(r'paths\["(/issuer[^"]*)"\]', ALL))
check({k.split(" ", 1)[1] for k in ROUTES} <= spec_paths, f"every route of the contract in the OpenAPI description {sorted(spec_paths)}")

# -- errors: (status, name) raised in the issuer modules
DEFAULT = {400: "invalid", 401: "unauthorized", 403: "forbidden", 404: "not_found", 409: "conflict", 413: "too_large",
           429: "rate_limited", 503: "unavailable"}  # api/common.py V1_CODES: an error without its own name
raised = set()
for t in SRC.values():
    lines = t.splitlines()
    for i, ln in enumerate(lines):
        s = re.sub(r'tr\((?:"(?:[^"\\]|\\.)*"|[^()])*?\)', "", ln)  # the messages out
        for m in re.finditer(r'\b(?:IsdErr|_fail|_iss_refuse\(c, iss, (?:g\.issuer_)?key,)\(?\s*(\d{3}),[^"]*?(?:"[^"]*"[^"]*?)*?"([a-z_]+)"', s):
            raised.add((int(m.group(1)), m.group(2)))
        for m in re.finditer(r'\bv1_err\((\d{3}),(.*)', s):
            n = re.search(r'name="([a-z_]+)"', m.group(2))
            raised.add((int(m.group(1)), n.group(1) if n else DEFAULT[int(m.group(1))]))
        m = re.search(r'\bDenied\((\d{3})(?:\)|,)', s)
        if m:
            nxt = " ".join(lines[i + 1:i + 3])
            n = re.search(r'e\.v1_name(?:, e\.v1_extra)? = "([a-z_]+)"', nxt)
            raised.add((int(m.group(1)), n.group(1) if n else DEFAULT[int(m.group(1))]))
if re.search(r"\b_bad\(", ALL):
    raised.add((400, "invalid_field"))
if re.search(r"\bUnknownFields\(", ALL):
    raised.add((400, "unknown_field"))
if re.search(r"\bBadInput\(", ALL):
    raised.add((400, "invalid"))
if re.search(r"\bConflict\b|\bow_write\(", ALL):
    raised.add((409, "conflict"))  # ow_write's version check (office/owrite.py OwConflict)
named = {(v["status"], k) for k, v in ERR.items()}
check(raised - named == set(), f"every error the issuer modules raise is in the contract with its status: missing {sorted(raised - named)}")
check(named - raised == set(), f"every error name of the contract is raised by the issuer modules: never raised {sorted(named - raised)}")
check(all(v["class"] in C["error_classes"] for v in ERR.values()), "every error has a class the contract explains")
every = set(C["every_route_errors"])
check(every <= set(ERR) and all(set(r["errors"]) <= set(ERR) for r in ROUTES.values()), "the routes name only errors of the contract")

# -- request fields, lists of values, limits
DOCS_SRC, CALC, MODEL = SRC["issdocs.py"], src("kalmido", "office", "calc.py"), src("kalmido", "office", "model.py")
for key, (text, name) in {"invoice": (DOCS_SRC, "ISD_KEYS"), "invoice.items[]": (DOCS_SRC, "ISD_ITEM_KEYS"),
                          "invoice.wish": (DOCS_SRC, "ISD_WISH_KEYS"), "invoice.wish.paid": (DOCS_SRC, "ISD_PAID_KEYS"),
                          "invoice.vat_check": (DOCS_SRC, "ISD_VAT_CHECK_KEYS"), "invoice.business_check": (DOCS_SRC, "ISD_BUSINESS_KEYS")}.items():
    check(tup(text, name) == REQ[key], f"request {key} = {name} {tup(text, name)} {REQ[key]}")
isc_fields = tup(SRC["issclients.py"], "ISC_FIELDS")
check(isc_fields and isc_fields + ["expect_updated_at"] == REQ["client_put"], f"request client_put = ISC_FIELDS + expect_updated_at {isc_fields}")
check(isc_fields and ["external_ref"] + isc_fields + ["updated_at", "checked"] == OBJ["client"], f"the client's fields = external_ref + ISC_FIELDS {isc_fields}")
for key, (text, name) in {"paid_method": (DOCS_SRC, "ISD_METHODS"), "tax": (CALC, "TAX_KEYS"), "vat_note": (CALC, "INV_VAT_NOTES"),
                          "client_flags": (SRC["issclients.py"], "ISC_KEY_FLAGS"), "file_kind": (DOCS_SRC, "ISD_FILE_MIME")}.items():
    check(tup(text, name) == ENUM[key], f"values {key} = {name} {tup(text, name)} {ENUM[key]}")
units = tup(MODEL, "UNITS")
check(units and [u for u in units if u != "percent"] == ENUM["unit"], f"values unit = office units but percent {units}")
check(tup(SRC["issuers.py"], "ISS_LIMITS") == OBJ["issuer.limits"], f"the key's limits = ISS_LIMITS {tup(SRC['issuers.py'], 'ISS_LIMITS')}")
for key, (text, name) in {"items": (DOCS_SRC, "ISD_ITEMS_MAX"), "item_text": (DOCS_SRC, "ISD_TITLE_MAX"), "item_detail": (DOCS_SRC, "ISD_DETAIL_MAX"),
                          "order_ref": (DOCS_SRC, "ISD_ORDER_REF_MAX"), "calls_a_minute": (SRC["issuers.py"], "ISS_RATE"),
                          "previews_a_minute": (DOCS_SRC, "ISD_PDF_RATE"), "files_a_minute": (DOCS_SRC, "ISD_FILE_RATE"),
                          "client_changes_a_day": (SRC["issclients.py"], "ISC_DAY_CHANGES"), "docs_page_max": (DOCS_SRC, "ISD_PAGE_MAX"),
                          "key_days_max": (SRC["issuers.py"], "ISS_DAYS"), "due_min_days": (DOCS_SRC, "ISD_DUE_MIN_DAYS"),
                          "self_pause_targets_an_hour": (SRC["issuers.py"], "ISS_SELF_PAUSE")}.items():
    check(num(text, name) == LIM[key], f"limit {key} = {name} {num(text, name)} {LIM[key]}")
check(re.search(r"^ISC_BODY_MAX = 64 \* 1024\b", SRC["issclients.py"], re.M) and LIM["body_bytes"] == 65536, "limit body_bytes = ISC_BODY_MAX")
check(f'ISC_REF_RE = re.compile(r"{LIM["ref_pattern"][1:-1]}")' in SRC["issclients.py"], "the ref pattern = ISC_REF_RE")
check(f'ISD_REF_RE = re.compile(r"{LIM["reference_pattern"][1:-1]}")' in DOCS_SRC, "the reference pattern = ISD_REF_RE")
for k in ("status", "origin", "kind"):
    check(re.search(rf'"{k}": \{{"type": "string", "enum": {re.escape(json.dumps(ENUM[k]))}', DOCS_SRC), f"OpenAPI {k} = the contract's values")
check(json.dumps(ENUM["doc_flags"]) in DOCS_SRC and json.dumps(ENUM["mail_state"]) in DOCS_SRC, "OpenAPI flags and mail states = the contract's")
check(not set(C["refused_invoice_fields"]) & set(REQ["invoice"]), "no refused field is a field of the request")

# -- the documentation
api = src("docs", "API.md")
sect = api[api.index("## Invoice issuer keys"):]
sect = sect[:sect.index("\n## ", 5)]
check("docs/api/issuer-contract.json" in sect and "90 days" in sect and "### Changes of the contract" in sect,
      "docs/API.md: the contract file, the notice of 90 days, the rule of changes")
check(all(f"`{k}`" in sect or f" {k}`" in sect or f"{k} (" in sect for k in ERR), f"docs/API.md names every error name {[k for k in ERR if k not in sect]}")
check(all(k.split(" ", 1)[1] in sect for k in ROUTES), f"docs/API.md names every route {[k for k in ROUTES if k.split(' ', 1)[1] not in sect]}")
check(all(f"`{f}`" in sect for f in C["refused_invoice_fields"]), f"docs/API.md lists every refused field {[f for f in C['refused_invoice_fields'] if f'`{f}`' not in sect]}")
for cls in C["error_classes"]:
    check(f"**{cls}**" in sect, f"docs/API.md explains the error class {cls}")

# ================================================================ the running server against the contract
OF = "/api/office"
D = OF + "/docs"
V = B + "/api/v1"
TODAY = __import__("datetime").date.today()
COMPANY = {"name": "Studio Nordlicht", "street": "Hafenstraße 12", "zip": "20457", "city": "Hamburg", "country": "DE",
           "email": "hallo@nordlicht.example", "phone": "+49 40 1234567", "tax_number": "12/345/67890", "iban": "DE02120300000000202051", "bic": "BYLADEM1001"}
ADDR = {"street": "Marktweg 5", "zip": "50667", "city": "Köln", "country": "DE"}
SEEN = set()


def sql(q, args=()):
    c = dbxm.connect(os.path.join(DATA, "tasks.db"), timeout=10)
    try:
        return c.execute(q, args).fetchall()
    finally:
        c.close()


def hk(key):
    return {"Authorization": "Bearer " + key}


def call(key, method, path, route, **kw):
    """One call of the key; an error answer is checked against the contract (status, class, route, body, headers)."""
    r = requests.request(method, V + path, headers={**hk(key), **kw.pop("headers", {})}, timeout=60, **kw)
    if r.status_code >= 400:
        try:
            e = r.json().get("error")
        except ValueError:
            e = None
        name = e.get("code") if isinstance(e, dict) else None
        spec = ERR.get(name) or {}
        SEEN.add(name)
        allowed = set(ROUTES[route]["errors"]) | set(C["every_route_errors"])
        check(spec.get("status") == r.status_code and name in allowed,
              f"{route}: error {r.status_code} {name} is in the contract for this route {r.text[:200]}")
        check(isinstance(e, dict) and set(C["error_body"]) <= set(e) and set(spec.get("extra", ())) <= set(e),
              f"{route}: the error body has {C['error_body'] + spec.get('extra', [])} {sorted(e) if isinstance(e, dict) else e}")
        for h in spec.get("headers", ()):
            check(r.headers.get(h), f"{route}: {name} carries the header {h}")
    else:
        check(r.status_code in ROUTES[route]["ok"], f"{route}: {r.status_code} is one of its statuses {ROUTES[route]['ok']}")
    return r


def code(r):
    try:
        e = r.json().get("error")
        return e.get("code") if isinstance(e, dict) else None
    except ValueError:
        return None


def fields(what, d, key):
    check(isinstance(d, dict) and sorted(d) == sorted(key), f"{what}: exactly the contract's fields: only answer "
          f"{sorted(set(d or {}) - set(key))}, missing {sorted(set(key) - set(d or {}))}")


def doc_ok(what, d, draft=None, listed=False):
    """A document as the contract says: its fields (a draft of the key + missing / flags, a page + changed_at) and values."""
    want = OBJ["doc"] + (OBJ["doc_draft"] if draft else []) + (OBJ["doc_in_list"] if listed else [])
    fields(what, d, want)
    if not isinstance(d, dict):
        return
    fields(what + ".totals", d.get("totals"), OBJ["doc.totals"])
    fields(what + ".mail", d.get("mail"), OBJ["doc.mail"])
    for p in d.get("payments") or []:
        fields(what + ".payments[]", p, OBJ["doc.payments[]"])
    for k, e in (("origin", "origin"), ("kind", "kind"), ("status", "status")):
        check(d.get(k) in ENUM[e], f"{what}: {k} {d.get(k)} is one of {ENUM[e]}")
    check(d.get("mail", {}).get("state") in ENUM["mail_state"], f"{what}: mail.state {d.get('mail')}")
    check(set(d.get("flags") or []) <= set(ENUM["doc_flags"]), f"{what}: flags {d.get('flags')}")


def setup_area(S, code_):
    assert S.put(B + OF + "/settings", json={"lang": "de", "company_fields": COMPANY}).ok
    r = S.post(B + OF + "/num-ranges", json={"code": code_, "scheme": code_ + "-{yyyy}-{seq:03}"})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def issuer(S, rg, name, limits=None):
    r = S.post(B + OF + "/issuers", json={"name": name, "range_id": rg, "password": PASSWORD, **({"limits": limits} if limits else {})})
    assert r.status_code == 201, r.text
    return r.json()["issuer"]["id"], r.json()["key"]


def body(ref, ext="acc:1", **more):
    return {"client_ref": ref, "client": {"external_ref": ext}, "service_from": TODAY.isoformat(), "service_to": TODAY.isoformat(),
            "items": [{"text": "Tarif Studio, Dezember", "qty": 1, "unit": "flat", "rate": "150.00", "tax": "standard"}],
            "expect": {"net": "150.00", "tax": "28.50", "gross": "178.50"}, **more}


def finalise(S, did):
    hold = S.get(B + D + f"/{did}/number-preview").json().get("client_hold") or {}
    r = S.post(B + D + f"/{did}/finalize", json={"client_hold_ok": hold.get("at")} if hold else {})
    assert r.ok, f"finalise {did}: {r.status_code} {r.text[:300]}"


kt.fresh({"KALMIDO_INSTANCE_MODE": "workspaces", "KALMIDO_ISSUER_KEYS": "1", "TASKS_WATCHDOG_INTERVAL": "3600"}, data=DATA)
A = kt.setup()
A.patch(B + "/api/settings", json={"lang": "en", "features": FEATURES, "tour": "done"})
ALICE = A.get(B + "/api/state").json()["me"]["id"]
ORG = A.post(B + "/api/admin/orgs", json={"name": "Alpha", "admin_id": ALICE}).json()["id"]
assert A.patch(B + "/api/settings", json={"workspace": f"org:{ORG}"}).ok
FID, Fr = freelancer(B, A)
Fr.patch(B + "/api/settings", json={"workspace": "private"})
RG = setup_area(A, "GT")
IID, KEY = issuer(A, RG, "Shop")
IID2, KEY2 = issuer(A, RG, "Kasse", {"day_docs": 1})
IID3, KEY3 = issuer(A, RG, "Pausen")
IID4, KEY4 = issuer(A, RG, "Felder")  # the many 400s on a key of their own (60 calls a minute each)
FRG = setup_area(Fr, "WEB")
FI, FK = issuer(Fr, FRG, "Own script")

# ---------------------------------------------------------------- the key's own view
for who, key in (("organisation", KEY), ("personal office", FK)):
    r = call(key, "GET", "/issuer", "GET /issuer")
    j = r.json() if r.ok else {}
    fields(f"GET /issuer ({who})", j, OBJ["issuer"])
    for part in ("range", "key", "limits", "tax_profile"):
        fields(f"GET /issuer.{part} ({who})", j.get(part), OBJ["issuer." + part])
    check(j.get("environment") in ENUM["environment"] and j.get("mode") in ENUM["mode"], f"environment / mode values {j.get('environment')} {j.get('mode')}")
call(KEY, "GET", "/issuer?x=1", "GET /issuer")
r = call("kis_test_" + "x" * 43, "GET", "/issuer", "GET /issuer")
check(r.status_code == 401 and code(r) == "unauthorized", f"an unknown key: 401 unauthorized {r.status_code} {r.text[:120]}")
r = requests.get(V + "/tasks", headers=hk(KEY), timeout=30)
check(r.status_code == 403 and code(r) == "forbidden" and ERR["forbidden"]["status"] == 403, f"a route outside the list: 403 forbidden {r.status_code}")

# ---------------------------------------------------------------- clients
for who, key in (("organisation", KEY), ("personal office", FK)):
    r = call(key, "PUT", "/issuer/clients/by-ref/acc:1", "PUT /issuer/clients/by-ref/{ref}",
             json={"name": "Kundin Eins", **ADDR, "email_invoice": "rechnung@kunde.example"})
    check(r.status_code == 201, f"a client set up ({who}): 201 {r.status_code} {r.text[:200]}")
    fields(f"PUT client ({who})", r.json() if r.ok else None, OBJ["client"] + OBJ["client_after_put"])
    check(set((r.json() if r.ok else {}).get("flags") or []) <= set(ENUM["client_flags"]), "client flags values")
    r = call(key, "GET", "/issuer/clients/by-ref/acc:1", "GET /issuer/clients/by-ref/{ref}")
    fields(f"GET client ({who})", r.json() if r.ok else None, OBJ["client"])
CL = call(KEY, "GET", "/issuer/clients/by-ref/acc:1", "GET /issuer/clients/by-ref/{ref}").json()
r = call(KEY, "PUT", "/issuer/clients/by-ref/acc:1", "PUT /issuer/clients/by-ref/{ref}", json={"city": "Bonn"})
check(code(r) == "version_required", f"a change without the version: version_required {r.text[:160]}")
CID = sql("SELECT id FROM clients WHERE issuer_id=? AND external_ref='acc:1'", (IID,))[0][0]
assert A.patch(B + f"/api/clients/{CID}", json={"phone": "+49 221 1234567"}).ok
r = call(KEY, "PUT", "/issuer/clients/by-ref/acc:1", "PUT /issuer/clients/by-ref/{ref}", json={"city": "Bonn", "expect_updated_at": CL["updated_at"]})
check(code(r) == "conflict", f"a person's change in between: 409 conflict {r.text[:160]}")
r = call(KEY, "PUT", "/issuer/clients/by-ref/a%2Fb", "PUT /issuer/clients/by-ref/{ref}", json={"name": "X"})
check(code(r) == "invalid_field", f"a slash in the ref: invalid_field {r.status_code} {r.text[:160]}")
r = call(KEY, "PUT", "/issuer/clients/by-ref/acc:9", "PUT /issuer/clients/by-ref/{ref}", json={"name": "X", "notes": "y"})
check(code(r) == "unknown_field", f"an unknown field: unknown_field {r.text[:160]}")
r = call(KEY, "PUT", "/issuer/clients/by-ref/acc:9", "PUT /issuer/clients/by-ref/{ref}", data='{"name": "X", "name": "Y"}',
         headers={"Content-Type": "application/json"})
check(r.status_code == 400 and code(r) == "invalid", f"a key twice: 400 invalid {r.text[:160]}")
r = call(KEY, "PUT", "/issuer/clients/by-ref/acc:9", "PUT /issuer/clients/by-ref/{ref}", json={"name": "X" * (LIM["body_bytes"] + 10)})
check(r.status_code == 413 and code(r) == "too_large", f"over body_bytes: 413 too_large {r.status_code}")
r = call(KEY, "GET", "/issuer/clients/by-ref/acc:404", "GET /issuer/clients/by-ref/{ref}")
check(r.status_code == 404 and code(r) == "not_found", f"an unknown client: 404 not_found {r.status_code}")

# ---------------------------------------------------------------- drafts
r = call(KEY, "POST", "/issuer/invoices", "POST /issuer/invoices", json=body("kauf:1", order_ref="Kauf 4711"))
check(r.status_code == 201, f"a draft: 201 {r.status_code} {r.text[:200]}")
DR = r.json() if r.status_code == 201 else {}
doc_ok("POST /issuer/invoices", DR, draft=True)
DID = DR.get("doc_id")
r = call(KEY, "POST", "/issuer/invoices", "POST /issuer/invoices", json=body("kauf:1", order_ref="Kauf 4711"))
check(r.status_code == 200, f"the same again: 200 {r.status_code}")
doc_ok("POST again", r.json() if r.ok else None, draft=True)
r = call(KEY, "POST", "/issuer/invoices", "POST /issuer/invoices", json=body("kauf:1", order_ref="Kauf 4712"))
check(code(r) == "ref_conflict", f"another content: ref_conflict {r.text[:160]}")
r = call(KEY, "POST", "/issuer/invoices", "POST /issuer/invoices", json=body("kauf:2", expect={"net": "150.00", "tax": "28.50", "gross": "178.51"}))
check(code(r) == "totals_mismatch" and set(r.json()["error"].get("totals") or {}) >= {"net", "tax", "gross"}, f"totals_mismatch with totals {r.text[:200]}")
r = call(KEY, "POST", "/issuer/invoices", "POST /issuer/invoices", json=body("kauf:3", ext="acc:none"))
check(code(r) == "client_unknown", f"an unknown client: client_unknown {r.text[:160]}")
r = call(KEY, "POST", "/issuer/invoices", "POST /issuer/invoices", json=body("kauf:4", wish={"payee": 999999, "payee_check": "0000"}))
check(code(r) == "payee_unknown", f"an unknown account: payee_unknown {r.text[:160]}")
r = call(KEY, "POST", "/issuer/invoices", "POST /issuer/invoices",
         json=body("kauf:5", items=[{"text": "Zahle an DE89 3704 0044 0532 0130 00", "rate": "10.00"}], expect={"net": "10.00", "tax": "1.90", "gross": "11.90"}))
check(code(r) == "invalid_field" and r.json()["error"].get("field", "").startswith("items"), f"an IBAN in a position: invalid_field {r.text[:160]}")
assert call(KEY4, "PUT", "/issuer/clients/by-ref/acc:1", "PUT /issuer/clients/by-ref/{ref}", json={"name": "Kundin Vier", **ADDR}).status_code == 201
for f in C["refused_invoice_fields"]:
    r = call(KEY4, "POST", "/issuer/invoices", "POST /issuer/invoices", json=body(f"kauf:f-{f}", **{f: "1"}))
    check(r.status_code == 400 and code(r) == "unknown_field" and f in (r.json()["error"].get("fields") or []),
          f"the refused field {f}: 400 unknown_field {r.status_code} {r.text[:160]}")
for u in ENUM["unit"]:
    r = call(KEY4, "POST", "/issuer/invoices", "POST /issuer/invoices",
             json=body(f"kauf:u-{u}", items=[{"text": "Leistung", "qty": 1, "unit": u, "rate": "150.00", "tax": "standard"}]))
    check(r.status_code == 201, f"the unit {u} is taken {r.status_code} {r.text[:160]}")
r = call(KEY4, "POST", "/issuer/invoices", "POST /issuer/invoices",
         json=body("kauf:u-percent", items=[{"text": "Leistung", "qty": 1, "unit": "percent", "rate": "150.00"}]))
check(code(r) == "invalid_field", f"a unit outside the list: invalid_field {r.text[:160]}")
r = call(KEY2, "POST", "/issuer/invoices", "POST /issuer/invoices", json=body("k2:1", ext="acc:1"))
check(code(r) == "client_unknown", f"another issuer never sees this issuer's client {r.text[:120]}")
assert call(KEY2, "PUT", "/issuer/clients/by-ref/acc:1", "PUT /issuer/clients/by-ref/{ref}", json={"name": "Kundin Zwei", **ADDR}).status_code == 201
assert call(KEY2, "POST", "/issuer/invoices", "POST /issuer/invoices", json=body("k2:1")).status_code == 201
r = call(KEY2, "POST", "/issuer/invoices", "POST /issuer/invoices", json=body("k2:2"))
check(r.status_code == 429 and code(r) == "limit_reached", f"day_docs 1: the second 429 limit_reached {r.status_code} {r.text[:160]}")

# ---------------------------------------------------------------- reads
r = call(KEY, "GET", f"/issuer/docs/{DID}", "GET /issuer/docs/{id}")
doc_ok("GET /issuer/docs/{id}", r.json() if r.ok else None, draft=True)
r = call(KEY, "GET", "/issuer/docs/by-ref/kauf:1", "GET /issuer/docs/by-ref/{ref}")
doc_ok("GET /issuer/docs/by-ref/{ref}", r.json() if r.ok else None, draft=True)
r = call(KEY4, "GET", "/issuer/docs?changed_since=2000-01-01T00:00:00Z&limit=2", "GET /issuer/docs")  # KEY4: 5 drafts
pg = r.json() if r.ok else {}
fields("GET /issuer/docs", pg, OBJ["docs_page"])
for d in pg.get("docs") or []:
    doc_ok("GET /issuer/docs[]", d, draft=d.get("status") == "draft", listed=True)
check(pg.get("next_cursor"), "a page of 2 with more: next_cursor")
call(KEY, "GET", "/issuer/docs?changed_since=gestern", "GET /issuer/docs")
call(KEY, "GET", "/issuer/docs?since=1", "GET /issuer/docs")
r = call(KEY, "GET", f"/issuer/docs/{DID + 100000}", "GET /issuer/docs/{id}")
check(r.status_code == 404 and code(r) == "not_found", f"an id that is not its own: 404 not_found {r.status_code}")
r = call(KEY, "GET", f"/issuer/docs/{DID}/pdf", "GET /issuer/docs/{id}/pdf")
check(r.status_code == 200 and r.headers.get("Content-Type", "").startswith("application/pdf"), f"the preview: a PDF {r.status_code}")
r = call(KEY, "GET", f"/issuer/docs/{DID}/file?kind=pdf", "GET /issuer/docs/{id}/file")
check(code(r) == "not_final", f"the file of a draft: not_final {r.text[:120]}")
call(KEY, "GET", f"/issuer/docs/{DID}/file?kind=zip", "GET /issuer/docs/{id}/file")

# a person's change ends the preview; finalising gives the file
cur = A.get(B + D + f"/{DID}").json()
assert A.patch(B + D + f"/{DID}", json={"project_title": "Studio Dezember", "expect_updated_at": cur.get("updated_at")}).ok
r = call(KEY, "GET", f"/issuer/docs/{DID}/pdf", "GET /issuer/docs/{id}/pdf")
check(code(r) == "edited_by_human", f"after a person's change: edited_by_human {r.text[:120]}")
finalise(A, DID)
r = call(KEY, "GET", f"/issuer/docs/{DID}", "GET /issuer/docs/{id}")
FD = r.json() if r.ok else {}
doc_ok("a finalised invoice", FD, draft=False)
check(FD.get("number") and FD.get("date") and FD.get("status") != "draft", f"finalised: number and date {FD.get('number')} {FD.get('date')}")
for kind in ENUM["file_kind"]:
    r = call(KEY, "GET", f"/issuer/docs/{DID}/file?kind={kind}", "GET /issuer/docs/{id}/file")
    check(r.status_code == 200 and r.headers.get("X-Content-SHA256") or (kind == "xml" and code(r) == "not_final"),
          f"the file {kind}: 200 with X-Content-SHA256 (or no e-invoice: not_final) {r.status_code}")
r = call(KEY, "GET", f"/issuer/docs/{DID}/pdf", "GET /issuer/docs/{id}/pdf")
check(code(r) == "not_draft", f"the preview of a finalised invoice: not_draft {r.text[:120]}")
r = call(KEY, "POST", f"/issuer/docs/{DID}/withdraw", "POST /issuer/docs/{id}/withdraw")
check(code(r) == "not_draft", f"withdrawing a finalised invoice: not_draft {r.text[:120]}")

# ---------------------------------------------------------------- withdraw
W = call(KEY, "POST", "/issuer/invoices", "POST /issuer/invoices", json=body("kauf:w")).json()["doc_id"]
r = call(KEY, "POST", f"/issuer/docs/{W}/withdraw", "POST /issuer/docs/{id}/withdraw")
doc_ok("a withdrawn draft", r.json() if r.ok else None, draft=False)
check(r.ok and r.json().get("status") == "withdrawn", f"withdrawn {r.status_code} {r.text[:160]}")
r = call(KEY, "GET", "/issuer/docs/by-ref/kauf:w", "GET /issuer/docs/by-ref/{ref}")
check(r.status_code == 200 and r.json().get("status") == "withdrawn", f"its ref while in the office's trash: 200 status withdrawn {r.status_code}")
doc_ok("a withdrawn draft by its ref", r.json() if r.ok else None, draft=False)
r = call(KEY, "POST", "/issuer/invoices", "POST /issuer/invoices", json=body("kauf:w"))
check(r.status_code == 410 and code(r) == "withdrawn", f"the ref again: 410 withdrawn, never a new draft {r.status_code}")
dbxm_c = dbxm.connect(os.path.join(DATA, "tasks.db"), timeout=10)
try:  # as the purge of the trash does
    dbxm_c.execute("DELETE FROM office_doc_items WHERE doc_id=?", (W,))
    dbxm_c.execute("DELETE FROM office_docs WHERE id=?", (W,))
    dbxm_c.commit()
finally:
    dbxm_c.close()
r = call(KEY, "GET", "/issuer/docs/by-ref/kauf:w", "GET /issuer/docs/by-ref/{ref}")
check(r.status_code == 410 and code(r) == "withdrawn", f"its ref once the trash is purged: 410 withdrawn {r.status_code}")

# ---------------------------------------------------------------- pause (another issuer, it would stop the others)
assert A.post(B + f"/api/office/issuers/{IID3}/pause").ok
r = call(KEY3, "GET", "/issuer", "GET /issuer")
check(r.status_code == 403 and code(r) == "issuer_paused", f"paused: 403 issuer_paused with Retry-After {r.status_code}")

# ---------------------------------------------------------------- the personal office
r = call(FK, "POST", "/issuer/invoices", "POST /issuer/invoices", json=body("f:1"))
doc_ok("Frida's draft", r.json() if r.status_code == 201 else None, draft=True)
r = call(FK, "GET", f"/issuer/docs/{DID}", "GET /issuer/docs/{id}")
# tenant: GET /api/v1/issuer/docs/{}
check(r.status_code == 404, f"the personal office's key never reaches the organisation's document: 404 {r.status_code}")

# ---------------------------------------------------------------- the OpenAPI description
spec = requests.get(V + "/openapi.json", timeout=30).json()
sp = {norm_route(m, "/api/v1" + p) for p, ops in (spec.get("paths") or {}).items() if p.startswith("/issuer") for m in ops}
check(sp == contract_routes, f"OpenAPI: the key's routes = the contract's {sorted(sp ^ contract_routes)}")
props = (((spec["paths"].get("/issuer/docs/{id}") or {}).get("get") or {}).get("responses", {}).get("200", {}).get("content", {})
         .get("application/json", {}).get("schema", {}).get("properties", {}))
check(sorted(props) == sorted(OBJ["doc"] + OBJ["doc_draft"]), f"OpenAPI: the document's fields = the contract's {sorted(props)}")

print("error names seen:", ", ".join(sorted(n for n in SEEN if n)), flush=True)
sys.exit(kt.done("p6702_office_issuer_contract"))
