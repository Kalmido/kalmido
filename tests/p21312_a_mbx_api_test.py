#!/usr/bin/env python3
# kalmido-suite: fresh
"""2.1312.0 part A (#6540): a workspace's own SMTP is no open relay, the mailbox settings no port scanner.
Own container (start.sh) with the stub mail server inside (stub_mail.py: IMAP 1143 + SMTP 1025, AUTH PLAIN password "secret").
No KALMIDO_CALENDAR_ALLOW_HOSTS: only the admin's list "mail" names internal hosts here.
 - a server for sending only with user name AND password (400 without, also a new password missing); a mailbox stored
   without a login sends nothing (compose: can_send false with the hint, send 409 code login, the test code login)
 - SMTP only on 465 / 587; 25 / another port only as host:port of the admin's list (400 code port; a stored one: 409)
 - the admin's list: an entry without a port opens the mail ports only (not 1143), and only for the workspaces of the
   server's admins (Alpha of bob, no server admin, reaches no internal host of the list)
 - outside only "network" / "auth": an internal host nobody allowed reads as network (no "blocked")
 - saving a connection, the test and "Fetch now" share one limit per person (429), the sender name alone is not counted
 - through the own SMTP at most 20 mails a day per person and recipient (the server's mail_budget is not used)
 - the whole delivery / test against a server answering drop by drop ends after its time (cal_until)
usage: p21312_a_mbx_api_test.py <datadir>
freelancer-matrix: hub"""
import os
import subprocess
import sys
import time

import requests

N = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, N)
import dbx as dbxm  # noqa: E402
from freelancer_fixture import freelancer  # noqa: E402
from kt import FAILS, OKS, check, sess  # noqa: E402

DATA = sys.argv[1]
B = "http://127.0.0.1:" + os.environ.get("KALMIDO_TEST_PORT", "3048")
CT = os.environ.get("KALMIDO_TEST_CONTAINER", "kalmido-test")
H = {"X-Requested-With": "kalmido"}
ENV = ["-e", "KALMIDO_IMAP_INTERVAL=600", "-e", "KALMIDO_SECRET_KEY=AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8="]
LOGIN_TXT = "Sending needs the user name and the password of the SMTP server"
PORT_TXT = "Sending only through port 465 or 587"


def dbx(sql, args=(), write=False):
    c = dbxm.connect(os.path.join(DATA, "tasks.db"), timeout=10)
    try:
        r = c.execute(sql, args).fetchall()
        if write:
            c.commit()
        return r
    finally:
        c.close()


def in_app(code):
    """Python inside the server container (the app loaded, c = a connection in the system context) -> stdout + stderr."""
    body = "\n".join("    " + x for x in code.split("\n"))
    out = subprocess.run(["docker", "exec", CT, "python", "-c",
                          "import app\nfrom kalmido.core.db import connect\nfrom kalmido.core.pg import system_ctx\nc = connect()\n"
                          "with system_ctx(c):\n" + body + "\nc.close()"], capture_output=True, text=True)
    return out.stdout + out.stderr


def sent():
    p = os.path.join(DATA, "mail", "out.jsonl")
    return [ln for ln in open(p)] if os.path.exists(p) else []


subprocess.run(["docker", "rm", "-f", CT], capture_output=True)
subprocess.run(["rm", "-rf", DATA])
os.makedirs(os.path.join(DATA, "mail", "in"), exist_ok=True)
subprocess.run(["cp", os.path.join(N, "stub_mail.py"), DATA])
r = subprocess.run(["bash", os.path.join(N, "start.sh"), DATA], env=dict(os.environ, KEEP="1", EXTRA=os.environ.get("EXTRA", "") + " " + " ".join(ENV)),
                   capture_output=True, text=True)
assert r.returncode == 0, r.stdout + r.stderr
subprocess.run(["docker", "exec", "-d", CT, "python", "/data/stub_mail.py"])
s0 = requests.Session()
s0.headers.update(H)
assert s0.post(B + "/api/auth/setup", json={"username": "alice", "display_name": "Alice", "password": "password123"}).ok
A = sess("alice")
A.post(B + "/api/admin/setup", json={"lang": "en", "collab_all": True})
ALICE = dbx("SELECT id FROM users WHERE username='alice'")[0][0]
r = A.post(B + "/api/users", json={"username": "bob", "display_name": "Bob", "password": "password123", "email": "bob@example.com"})
assert r.ok, r.text
BOB = r.json()["id"]
ERIN, Er = freelancer(B, A, "erin")
r = A.post(B + "/api/admin/orgs", json={"name": "Alpha", "admin_id": BOB})
ORG = r.json()["id"]
A.patch(B + f"/api/admin/orgs/{ORG}", json={"members": [BOB], "admins": [BOB]})
dbx("DELETE FROM org_members WHERE (org_id=? AND user_id<>?) OR user_id=?", (ORG, BOB, ERIN), write=True)
Bo = sess("bob")
for s in (A, Bo, Er):
    s.patch(B + "/api/settings", json={"lang": "en", "features": "collab,comments,clients,contacts", "tour": "done", "workspace": "all"})
# the admin's list "mail": the stubs by name with their ports, 127.0.0.1 without a port (= the mail ports only) + the drip port
r = A.patch(B + "/api/admin/settings", json={"allow_hosts_by_purpose": {"mail": "localhost:1025, localhost:1143, 127.0.0.1, 127.0.0.1:1029"}})
check(r.ok, f"the admin's list for mail saved ({r.status_code} {r.text[:200]})")
until_up = time.monotonic() + 20
while time.monotonic() < until_up and subprocess.run(["docker", "exec", CT, "python", "-c", "import socket;socket.create_connection(('127.0.0.1',1025),1)"],
                                                     capture_output=True).returncode:
    time.sleep(0.3)  # the stub's port (a real state, not a fixed time)

# ---- 1. a server for sending only with its login (alice: server admin, her private workspace)
BOX = {"ws": "private", "imap_host": "localhost", "imap_port": 1143, "imap_ssl": False, "imap_user": "kalmido", "imap_password": "secret",
       "smtp_host": "localhost", "smtp_port": 1025, "smtp_tls": "none", "smtp_user": "kalmido", "smtp_password": "secret",
       "from_addr": "office@example.test", "from_name": "Alice Office"}
r = A.put(B + "/api/hubmail/mailbox", json={**BOX, "smtp_user": ""})
check(r.status_code == 400 and LOGIN_TXT in r.text, f"SMTP without a user name: 400 ({r.status_code} {r.text[:200]})")
r = A.put(B + "/api/hubmail/mailbox", json={k: v for k, v in BOX.items() if k != "smtp_password"})
check(r.status_code == 400 and LOGIN_TXT in r.text, f"SMTP without a password: 400 ({r.status_code} {r.text[:200]})")
r = A.put(B + "/api/hubmail/mailbox", json={**BOX, "check": True})
ch = (r.json().get("check") or {}) if r.ok else {}
check(r.ok and ch.get("imap", {}).get("ok") and ch.get("smtp", {}).get("ok"), f"with the login: both log in ({r.status_code} {ch})")
r = A.put(B + "/api/hubmail/mailbox", json={"ws": "private", "from_name": "Alice GbR"})
check(r.ok, f"a stored password stays: another field alone saves ({r.status_code} {r.text[:200]})")

# ---- 2. the admin's list per workspace and with ports
r = A.put(B + "/api/hubmail/mailbox", json={"ws": "private", "imap_host": "127.0.0.1", "imap_password": "secret", "check": True})
c1 = ((r.json().get("check") or {}).get("imap") or {}) if r.ok else {}
check(r.ok and c1.get("code") == "network", f"127.0.0.1 without a port in the list: not port 1143 (network) ({r.status_code} {c1})")
A.put(B + "/api/hubmail/mailbox", json={"ws": "private", "imap_host": "localhost", "imap_password": "secret"})
r = Bo.put(B + "/api/hubmail/mailbox", json={**BOX, "ws": f"org:{ORG}"})
check(r.status_code == 400 and PORT_TXT in r.text, f"Alpha (no server admin among its admins): localhost:1025 of the list is not Alpha's ({r.status_code} {r.text[:200]})")
r = Bo.put(B + "/api/hubmail/mailbox", json={"ws": f"org:{ORG}", "imap_host": "localhost", "imap_port": 1143, "imap_ssl": False, "imap_user": "kalmido",
                                              "imap_password": "secret", "check": True})
c1 = ((r.json().get("check") or {}).get("imap") or {}) if r.ok else {}
check(r.ok and c1.get("code") == "network" and "local network" not in c1.get("text", ""),
      f"Alpha: the internal IMAP of the list is not reached, and only 'network' outside ({r.status_code} {c1})")

# ---- 3. ports of an outside SMTP (the freelancer, freelancer-matrix: hub)
EBOX = {"ws": "private", "smtp_host": "smtp.example.com", "smtp_tls": "starttls", "smtp_user": "erin", "smtp_password": "pw-erin", "from_addr": "erin@example.com"}
for port in (2525, 25):
    r = Er.put(B + "/api/hubmail/mailbox", json={**EBOX, "smtp_port": port})
    check(r.status_code == 400 and PORT_TXT in r.text, f"freelancer: SMTP port {port}: 400 ({r.status_code} {r.text[:200]})")
r = Er.put(B + "/api/hubmail/mailbox", json={**EBOX, "smtp_port": 587})
check(r.ok and (r.json().get("box") or {}).get("smtp_password_set"), f"freelancer: port 587 with the login is saved ({r.status_code} {r.text[:200]})")
r = Er.put(B + "/api/hubmail/mailbox", json={**EBOX, "smtp_port": 0, "smtp_tls": "ssl"})
check(r.ok, f"freelancer: SSL without a port (= 465) is saved ({r.status_code} {r.text[:200]})")

# ---- 4. sending through the own SMTP: 20 a day per person and recipient; a stored mailbox without a login sends nothing
ACME = A.post(B + "/api/clients", json={"name": "Acme", "org_id": None, "email": "acme@example.com"}).json()["id"]
MAIL = {"client_id": ACME, "to": "acme@example.com", "subject": "Hello", "text": "x"}
n0 = len(sent())
r = A.post(B + "/api/hubmail/send", json=MAIL)
check(r.status_code == 201 and r.json().get("via") == "workspace" and len(sent()) == n0 + 1, f"sent through the own SMTP with its login ({r.status_code} {r.text[:200]})")
row = dbx("SELECT n, day FROM mail_counts WHERE k=?", (f"o:{ALICE}:acme@example.com",))
check(row and row[0][0] == 1 and not dbx("SELECT 1 FROM mail_counts WHERE k IN ('r:acme@example.com', ?)", (f"s:{ALICE}",)),
      f"counted per person and recipient, not in the server's daily limit ({row})")
DAY = row[0][1] if row else ""
dbx("INSERT INTO mail_counts(k, day, n) VALUES(?, ?, 20)", (f"o:{ALICE}:lisa@example.com", DAY), write=True)
r = A.post(B + "/api/hubmail/send", json={**MAIL, "to": "Lisa <LISA@example.com>"})
check(r.status_code == 429 and len(sent()) == n0 + 1, f"the 21st mail of the day to the same recipient: 429 ({r.status_code} {r.text[:200]})")
r = A.post(B + "/api/hubmail/send", json={**MAIL, "to": "acme@example.com", "cc": "lisa@example.com"})
check(r.status_code == 429 and dbx("SELECT n FROM mail_counts WHERE k=?", (f"o:{ALICE}:acme@example.com",))[0][0] == 1,
      "one recipient over its limit: nothing sent, nothing counted")
dbx("UPDATE hub_mailboxes SET smtp_user='' WHERE ws=?", (f"u{ALICE}",), write=True)
j = A.get(B + f"/api/hubmail/compose?client_id={ACME}").json()
check(j.get("can_send") is False and LOGIN_TXT in (j.get("hint") or ""), f"stored without a login: the dialog says why, no Send ({j.get('can_send')} {j.get('hint')})")
r = A.post(B + "/api/hubmail/send", json=MAIL)
check(r.status_code == 409 and r.json().get("code") == "login" and len(sent()) == n0 + 1, f"stored without a login: 409 login, nothing sent ({r.status_code} {r.text[:200]})")
r = A.post(B + "/api/hubmail/mailbox/check", json={"ws": "private"})
check(r.ok and (r.json().get("check") or {}).get("smtp", {}).get("code") == "login", f"the test: code login ({r.status_code} {r.text[:200]})")
dbx("UPDATE hub_mailboxes SET smtp_user='kalmido', smtp_port=2526 WHERE ws=?", (f"u{ALICE}",), write=True)
r = A.post(B + "/api/hubmail/send", json=MAIL)
check(r.status_code == 409 and r.json().get("code") == "port" and len(sent()) == n0 + 1, f"stored on another port: 409 port, nothing sent ({r.status_code} {r.text[:200]})")

# ---- 5. saving a connection, the test and "Fetch now" share one limit per person
r = Er.put(B + "/api/hubmail/mailbox", json={"ws": "private", "imap_host": "127.0.0.1", "imap_port": 1027, "imap_ssl": False, "imap_user": "erin",
                                              "imap_password": "secret"})
check(r.ok, f"freelancer: an IMAP to fetch from ({r.status_code} {r.text[:200]})")
codes = [Er.post(B + "/api/hubmail/mailbox/poll", json={"ws": "private"}).status_code for _ in range(30)]
check(200 in codes and codes[-1] == 429, f"freelancer: Fetch now is limited ({codes})")
r = Er.post(B + "/api/hubmail/mailbox/check", json={"ws": "private"})
check(r.status_code == 429, f"the test shares the limit ({r.status_code})")
r = Er.put(B + "/api/hubmail/mailbox", json={"ws": "private", "imap_port": 1028, "imap_password": "secret"})
check(r.status_code == 429, f"saving another port shares the limit ({r.status_code})")
r = Er.put(B + "/api/hubmail/mailbox", json={"ws": "private", "from_name": "Erin"})
check(r.ok, f"the sender name alone is no connection: saved ({r.status_code} {r.text[:200]})")

# ---- 6. the whole time of a delivery / a test against a server answering drop by drop
out = in_app(f"""import socket, threading, time
from kalmido.integrations import mail as M
from kalmido.hub import mailbox as MB
srv = socket.socket()
srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
srv.bind(("127.0.0.1", 1029))
srv.listen(5)
def one(k):
    try:
        for _ in range(40):
            k.send(b"2")
            time.sleep(0.5)
    except OSError:
        pass
    k.close()
def drip():
    while True:
        k, _ = srv.accept()
        threading.Thread(target=one, args=(k,), daemon=True).start()
threading.Thread(target=drip, daemon=True).start()
M.SMTP_OWN_S = 3
MB.MBX_CHECK_S = 3
cfg = {{"host": "127.0.0.1", "port": 1029, "tls": "none", "user": "u", "password": "p", "from": "a@example.test", "allow": frozenset({{("127.0.0.1", 1029)}})}}
t = time.monotonic()
try:
    M.mail_deliver(M.mail_message("b@example.test", "s", "t", smtp=cfg), cfg)
    res = "sent"
except Exception as e:
    res = type(e).__name__
print("deliver", res, round(time.monotonic() - t, 1))
row = {{"imap_host": "", "smtp_host": "127.0.0.1", "smtp_port": 1029, "smtp_tls": "none", "smtp_user": "u", "from_addr": "a@example.test", "ws": "u{ALICE}"}}
t = time.monotonic()
print("check", MB.mbx_check(c, row, {{"smtp": "p"}}).get("smtp"), round(time.monotonic() - t, 1))""")
dl = [x.split() for x in out.splitlines() if x.startswith(("deliver ", "check "))]
d = {x[0]: x[1:] for x in dl if len(x) == 3}
check("deliver" in d and d["deliver"][0] != "sent" and float(d["deliver"][1]) < 10, f"a delivery drop by drop ends after its time ({out[-400:]})")
check("check" in d and d["check"][0] == "network" and float(d["check"][1]) < 10, f"a test drop by drop ends after its time ({out[-400:]})")

print(f"p21312_a_mbx_api: {OKS[0]} ok, {len(FAILS)} failed", flush=True)
sys.exit(1 if FAILS else 0)
