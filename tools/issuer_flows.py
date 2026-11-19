#!/usr/bin/env python3
"""(#6702) The test organisation of the invoice issuer API on a TEST server, and the flows of an outside system through it.

Never against a live server, three locks before anything is written (review F1-F2 of job/5775):
 - --test-host HOST names the test server on purpose and must be the host of --url; the hosted service (kalmido.com and its
   subdomains) is always refused, because a server without KALMIDO_ISSUER_ENV reports "test" by default;
 - the server itself must say environment "test" (GET /api/office/issuers in the signed-in person's current office, before
   setup writes anything; GET /api/v1/issuer before run does);
 - https only (plain http only for a loopback or private address), and no redirect is followed: the key and the sign-in
   headers never go to another host.
Invented companies and figures only.

  issuer_flows.py setup --url URL --test-host HOST --key-file FILE [--login USER | --header "Name: value" ...]
      The organisation "Vertragstest" (the signed-in person must be an instance admin; it becomes the organisation's admin),
      its office with invented company data, the number range VT-{yyyy}-{seq} and one invoice issuer "Vertragstest" in the
      review mode. The key is written once into FILE (mode 0600, no symlink), never printed. Repeatable: what exists is kept; an issuer
      without a key file gets a new key. The sign-in confirmation of the issuer takes the password of KIS_CONFIRM_PASSWORD
      (default KIS_ADMIN_PASSWORD).
  issuer_flows.py run --url URL --test-host HOST --key-file FILE --out DIR [--login USER | --header ...] [--to ADDRESS] [--kosit]
      With the key: clients and drafts for Germany 19 % (with a unit price of 4 places), an EU business with reverse charge
      and a business in a third country; the same request again (200, the same draft), another content under the same
      client_ref (409 ref_conflict), a client's new e-mail (the hold mark: checked false, flag client_changed). With the
      session: each draft finalised in the office (the hold mark confirmed, as a person does), the German invoice mailed to
      --to (on a test server the mails stay in its catcher). With the key again: number VT-…, the archived PDF and e-invoice
      XML byte for byte (X-Content-SHA256), the mail state. --kosit validates the XML files with tools/einvoice_validate.sh
      (KoSIT, EN 16931). Writes DIR/summary.json; exit 0 = every step as expected, 1 = a finding, 2 = refused / setup.

The session: --login USER with the password in KIS_ADMIN_PASSWORD, or --header lines of a signing-in proxy in front of the
server. Python standard library only.
"""
import argparse
import hashlib
import http.cookiejar
import ipaddress
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from urllib.parse import urlsplit

ORG_NAME = "Vertragstest"
RANGE_CODE, RANGE_SCHEME = "VT", "VT-{yyyy}-{seq}"
ISSUER_NAME = "Vertragstest"
HOSTED = "kalmido.com"  # the hosted service: never a test server
COMPANY = {"name": "Vertragstest Studio", "street": "Probeweg 1", "zip": "20457", "city": "Hamburg", "country": "DE",
           "email": "buero@vertragstest.example", "tax_number": "12/345/67890", "vat_id": "DE123456789",
           "iban": "DE89370400440532013000", "bic": "COBADEFFXXX"}
CLIENTS = {
    "de": {"name": "Kundin Probe", "street": "Marktweg 5", "zip": "50667", "city": "Köln", "country": "DE",
           "email_invoice": "kunde-de@example.com"},
    "at": {"name": "Probe Handel GmbH", "street": "Ringstraße 3", "zip": "1010", "city": "Wien", "country": "AT",
           "vat_id": "ATU12345675", "email_invoice": "kunde-at@example.com"},
    "ch": {"name": "Probe Verlag AG", "street": "Seestrasse 9", "zip": "8002", "city": "Zürich", "country": "CH",
           "email_invoice": "kunde-ch@example.com"},
}


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """A redirect is an answer, never followed (the key and the sign-in headers stay with the named host)."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def guard(url, test_host):
    """Exit 2 unless url is the named test server: its host = test_host, not the hosted service, https or a local http."""
    u = urlsplit(url)
    host = (u.hostname or "").lower().rstrip(".")
    if not host or host != (test_host or "").lower().rstrip("."):
        print(f"REFUSED: --url's host {host!r} is not the --test-host {test_host!r}")
        sys.exit(2)
    if host == HOSTED or host.endswith("." + HOSTED):
        print(f"REFUSED: {host} is the hosted service, never a test server")
        sys.exit(2)
    if u.scheme != "https":
        try:
            local = host == "localhost" or ipaddress.ip_address(host).is_loopback or ipaddress.ip_address(host).is_private
        except ValueError:
            local = False
        if u.scheme != "http" or not local:
            print(f"REFUSED: {u.scheme}:// to {host} - https only (plain http only for a loopback or private address)")
            sys.exit(2)


class Http:
    """A session (cookies, X-Requested-With) or a key (Authorization: Bearer)."""

    def __init__(self, url, headers=None, key=None):
        self.url = url.rstrip("/")
        self.h = {"X-Requested-With": "kalmido", "Accept": "application/json", **(headers or {})}
        if key:
            self.h["Authorization"] = "Bearer " + key
        self.op = urllib.request.build_opener(_NoRedirect, urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))

    def req(self, method, path, body=None, raw=False):
        data = json.dumps(body).encode() if body is not None else None
        h = dict(self.h, **({"Content-Type": "application/json"} if data is not None else {}))
        rq = urllib.request.Request(self.url + path, data=data, method=method, headers=h)
        try:
            with self.op.open(rq, timeout=120) as r:
                status, hdr, content = r.status, dict(r.headers), r.read()
        except urllib.error.HTTPError as e:
            status, hdr, content = e.code, dict(e.headers), e.read()
        if raw:
            return status, hdr, content
        try:
            return status, json.loads(content or b"{}")
        except ValueError:
            return status, {"raw": content[:200].decode("utf-8", "replace")}


def err_code(j):
    e = j.get("error") if isinstance(j, dict) else None
    return e.get("code") if isinstance(e, dict) else e


def session(a):
    hdr = {}
    for line in a.header or ():
        k, _, v = line.partition(":")
        hdr[k.strip()] = v.strip()
    s = Http(a.url, hdr)
    if a.login:
        pw = os.environ.get("KIS_ADMIN_PASSWORD", "")
        st, j = s.req("POST", "/api/auth/login", {"username": a.login, "password": pw})
        if st != 200:
            sys.exit(f"sign-in of {a.login} failed: {st} {err_code(j)}")
    st, j = s.req("GET", "/api/state")
    if st != 200 or not (j.get("me") or {}).get("id"):
        sys.exit(f"no session ({st}): --login USER (KIS_ADMIN_PASSWORD) or --header of the signing-in proxy")
    return s, j["me"]


def test_only(env, where):
    if env != "test":
        print(f"REFUSED: {where} says environment {env!r} - this tool runs on a test server only (KALMIDO_ISSUER_ENV=test)")
        sys.exit(2)


def find_org(s):
    st, j = s.req("GET", "/api/admin/orgs")
    if st != 200:
        sys.exit(f"the organisations ({st}): the signed-in person must be an instance admin")
    return next((o for o in j.get("orgs") or [] if o.get("name") == ORG_NAME), None)


def to_org(s, org):
    st, j = s.req("PATCH", "/api/settings", {"workspace": f"org:{org['id']}"})
    if st != 200:
        sys.exit(f"switching to the organisation {ORG_NAME}: {st} {j}")


def setup(a):
    s, me = session(a)
    st, j = s.req("GET", "/api/office/issuers")  # the server's environment, before anything is written (review F1)
    if st != 200:
        print(f"REFUSED: the environment cannot be read ({st} {err_code(j)}): KALMIDO_ISSUER_KEYS=1 on the server, and the signed-in "
              "person's current workspace an office (switch it there once in the app)")
        return 2
    test_only(j.get("environment"), "GET /api/office/issuers")
    org = find_org(s)
    if org is None:
        st, j = s.req("POST", "/api/admin/orgs", {"name": ORG_NAME, "admin_id": me["id"]})
        if st not in (200, 201):
            sys.exit(f"the organisation {ORG_NAME}: {st} {j}")
        org = j
        print(f"organisation {ORG_NAME} set up (id {org['id']})")
    else:
        print(f"organisation {ORG_NAME} is there (id {org['id']})")
    to_org(s, org)
    st, iss = s.req("GET", "/api/office/issuers")
    if st != 200:
        sys.exit(f"invoice issuers are not available ({st} {err_code(iss)}): KALMIDO_ISSUER_KEYS=1 on the server, the office on")
    test_only(iss.get("environment"), "GET /api/office/issuers")
    st, j = s.req("PUT", "/api/office/settings", {"lang": "de", "company_fields": COMPANY})
    if st != 200:
        sys.exit(f"the office's company data: {st} {j}")
    st, j = s.req("GET", "/api/office/number-ranges")  # the additional ranges stand in "extra"
    rng = next((r for r in (j.get("extra") or []) if r.get("code") == RANGE_CODE), None) if isinstance(j, dict) else None
    if rng is None:
        st, rng = s.req("POST", "/api/office/num-ranges", {"code": RANGE_CODE, "scheme": RANGE_SCHEME})
        if st != 201:
            sys.exit(f"the number range {RANGE_CODE}: {st} {rng}")
        print(f"number range {RANGE_SCHEME} set up")
    pw = os.environ.get("KIS_CONFIRM_PASSWORD") or os.environ.get("KIS_ADMIN_PASSWORD", "")
    have = next((i for i in iss.get("issuers") or [] if i.get("name") == ISSUER_NAME and not i.get("revoked_at")), None)
    if have and os.path.exists(a.key_file):
        print(f"issuer {ISSUER_NAME} is there (id {have['id']}), the key file too - nothing to do")
        return 0
    if have:
        st, j = s.req("POST", f"/api/office/issuers/{have['id']}/keys", {"password": pw})
    else:
        st, j = s.req("POST", "/api/office/issuers", {"name": ISSUER_NAME, "range_id": rng["id"], "password": pw})
    key = j.get("key") if isinstance(j, dict) else None
    if st != 201 or not key:
        sys.exit(f"the issuer's key: {st} {err_code(j)} (the sign-in confirmation: KIS_CONFIRM_PASSWORD)")
    fd = os.open(a.key_file, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_NOFOLLOW", 0), 0o600)
    os.fchmod(fd, 0o600)  # review F3: also an older file of the key (a mode set only on creation)
    with os.fdopen(fd, "w") as f:
        f.write(key + "\n")
    print(f"issuer {ISSUER_NAME} in the review mode, its key written to {a.key_file} (shown nowhere else)")
    return 0


class Run:
    def __init__(self):
        self.steps = []

    def step(self, name, ok, detail=""):
        self.steps.append({"step": name, "ok": bool(ok), "detail": str(detail)[:400]})
        print(("ok   " if ok else "FUND ") + name + (f" - {detail}" if detail and not ok else ""), flush=True)
        return ok


def body(ref, ext, items, expect, **more):
    return {"client_ref": ref, "client": {"external_ref": ext}, "items": items, "expect": expect, **more}


def run(a):
    key = open(a.key_file, encoding="utf-8").read().strip()
    k = Http(a.url, key=key)
    st, me = k.req("GET", "/api/v1/issuer")
    if st != 200:
        print(f"the key does not work: {st} {err_code(me)}")
        return 2
    test_only(me.get("environment"), "GET /api/v1/issuer")
    s, _me = session(a)
    org = find_org(s)
    if org is None:
        sys.exit(f"no organisation {ORG_NAME}: run setup first")
    to_org(s, org)  # a person of the organisation finalises and mails
    os.makedirs(a.out, exist_ok=True)
    R = Run()
    R.step("the key's range is VT", (me.get("range") or {}).get("code") == RANGE_CODE, me.get("range"))
    R.step("the review mode", me.get("mode") == "review", me.get("mode"))
    now = datetime.now(timezone.utc)
    stamp, checked = now.strftime("%Y%m%d%H%M%S"), now.strftime("%Y-%m-%dT%H:%M:%SZ")
    today = datetime.now(timezone.utc).date().isoformat()

    # -- clients (external_ref with the environment's prefix, kept for good)
    upd = {}
    for c_, data in CLIENTS.items():
        ref = f"test:account:{c_}"
        st, j = k.req("GET", f"/api/v1/issuer/clients/by-ref/{ref}")
        if st == 200:
            st, j = k.req("PUT", f"/api/v1/issuer/clients/by-ref/{ref}", {**data, "expect_updated_at": j["updated_at"]})
            R.step(f"client {ref} as before", st == 200, f"{st} {err_code(j)}")
        else:
            st, j = k.req("PUT", f"/api/v1/issuer/clients/by-ref/{ref}", data)
            R.step(f"client {ref} set up", st == 201, f"{st} {err_code(j)}")
        upd[c_] = j.get("updated_at")

    # -- drafts
    flows = {
        "de": dict(items=[{"text": "Tarif Studio, Monat", "qty": 1, "unit": "flat", "rate": "100.00", "tax": "standard"},
                          {"text": "Speicher je Gigabyte", "qty": "3", "unit": "piece", "rate": "0.3333", "tax": "standard"}],
                   expect={"net": "101.00", "tax": "19.19", "gross": "120.19"}),
        "at": dict(items=[{"text": "Tarif Studio, Monat", "qty": 1, "unit": "flat", "rate": "250.00", "tax": "standard"}],
                   expect={"net": "250.00", "tax": "0.00", "gross": "250.00"}, vat_note="reverse",
                   vat_check={"source": "VIES", "checked_at": checked, "valid": True, "vat_id": CLIENTS["at"]["vat_id"]}),
        "ch": dict(items=[{"text": "Tarif Studio, Monat", "qty": 1, "unit": "flat", "rate": "300.00", "tax": "standard"}],
                   expect={"net": "300.00", "tax": "0.00", "gross": "300.00"}, vat_note="abroad",
                   business_check={"kind": "register", "source": "commercial register", "checked_at": checked}),
    }
    docs = {}
    for c_, f in flows.items():
        ref = f"test:order:{c_}-{stamp}"
        st, j = k.req("POST", "/api/v1/issuer/invoices", body(ref, f"test:account:{c_}", service_from=today, service_to=today, **f))
        if R.step(f"draft {c_}: 201, Kalmido's sums = expect", st == 201 and j.get("status") == "draft", f"{st} {err_code(j)} {j.get('error')}"):
            docs[c_] = {"ref": ref, "id": j["doc_id"], "body": body(ref, f"test:account:{c_}", service_from=today, service_to=today, **f)}
    if "de" in docs:
        d = docs["de"]
        st, j = k.req("POST", "/api/v1/issuer/invoices", d["body"])
        R.step("the same request again: 200, the same draft", st == 200 and j.get("doc_id") == d["id"], f"{st} {j.get('doc_id')}")
        st, j = k.req("POST", "/api/v1/issuer/invoices", {**d["body"], "order_ref": "andere Bestellung"})
        R.step("another content, same client_ref: 409 ref_conflict", st == 409 and err_code(j) == "ref_conflict", f"{st} {err_code(j)}")
        st, j = k.req("PUT", "/api/v1/issuer/clients/by-ref/test:account:de",
                      {"email_invoice": f"neu-{stamp}@example.com", "expect_updated_at": upd["de"]})
        R.step("a new e-mail of the client: checked false (hold mark)", st == 200 and j.get("checked") is False, f"{st} {err_code(j)}")
        st, j = k.req("GET", f"/api/v1/issuer/docs/{d['id']}")
        # a client no person checked yet carries its mark as client_new, a checked one that the key changed as client_changed
        R.step("the draft shows the hold mark (client_new / client_changed)",
               st == 200 and bool({"client_new", "client_changed"} & set(j.get("flags") or [])), j.get("flags"))

    # -- a person finalises (and confirms the hold mark), the German invoice is mailed
    for c_, d in docs.items():
        st, pv = s.req("GET", f"/api/office/docs/{d['id']}/number-preview")
        hold = (pv.get("client_hold") or {}) if isinstance(pv, dict) else {}
        st, j = s.req("POST", f"/api/office/docs/{d['id']}/finalize", {"client_hold_ok": hold.get("at")} if hold else {})
        d["final"] = R.step(f"{c_}: finalised by a person", st == 200, f"{st} {j.get('error') if isinstance(j, dict) else j}")
    if docs.get("de", {}).get("final"):
        st, j = s.req("POST", f"/api/office/docs/{docs['de']['id']}/send", {"to": a.to})
        R.step(f"de: mailed to {a.to}", st == 200, f"{st} {j.get('error') if isinstance(j, dict) else j}")

    # -- the key reads the result
    xmls = []
    for c_, d in docs.items():
        if not d.get("final"):
            continue
        st, j = k.req("GET", f"/api/v1/issuer/docs/{d['id']}")
        R.step(f"{c_}: number VT-yyyy-n", st == 200 and re.fullmatch(r"VT-\d{4}-\d+", j.get("number") or ""), j.get("number"))
        if c_ == "de":
            R.step("de: mail state sent", (j.get("mail") or {}).get("state") == "sent", j.get("mail"))
        for kind in ("pdf", "xml"):
            st, hdr, content = k.req("GET", f"/api/v1/issuer/docs/{d['id']}/file?kind={kind}", raw=True)
            sha = {h.lower(): v for h, v in hdr.items()}.get("x-content-sha256")
            ok = st == 200 and sha == hashlib.sha256(content).hexdigest()
            R.step(f"{c_}: the archived {kind} byte for byte", ok, f"{st}")
            if ok:
                p = os.path.join(a.out, f"{c_}-{d['id']}.{kind}")
                with open(p, "wb") as f:
                    f.write(content)
                if kind == "xml":
                    xmls.append(p)
    if a.kosit:
        tool = os.path.join(os.path.dirname(os.path.abspath(__file__)), "einvoice_validate.sh")
        rc = subprocess.run(["bash", tool, *xmls], check=False).returncode if xmls else 1
        R.step(f"KoSIT (EN 16931) on {len(xmls)} e-invoice(s)", rc == 0 and len(xmls) == len([d for d in docs.values() if d.get("final")]), f"rc {rc}")
    with open(os.path.join(a.out, "summary.json"), "w", encoding="utf-8") as f:
        json.dump({"at": stamp, "url": a.url, "steps": R.steps}, f, indent=1, ensure_ascii=False)
    bad = [x for x in R.steps if not x["ok"]]
    print(f"{len(R.steps) - len(bad)} ok, {len(bad)} finding(s); {os.path.join(a.out, 'summary.json')}")
    return 1 if bad else 0


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("command", choices=("setup", "run"))
    p.add_argument("--url", required=True)
    p.add_argument("--test-host", required=True, help="the host of --url, named on purpose: this is a test server")
    p.add_argument("--key-file", required=True)
    p.add_argument("--login")
    p.add_argument("--header", action="append")
    p.add_argument("--out", default="issuer-flows")
    p.add_argument("--to", default="kunde-de@example.com")
    p.add_argument("--kosit", action="store_true")
    a = p.parse_args()
    guard(a.url, a.test_host)
    return setup(a) if a.command == "setup" else run(a)


if __name__ == "__main__":
    sys.exit(main())
