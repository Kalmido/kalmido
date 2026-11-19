#!/usr/bin/env python3
# kalmido-suite: fresh
"""2.1437.0 C (#6615): self-hosting: clear start messages instead of a traceback in the restart loop.
 - unit (kalmido/core/env.py, no app): env_int / env_float with a value that is no number = the default and ONE warning line
   naming the variable; env_port: a value that is no port ends with a FATAL line naming PORT (exit 2); env_unknown names the
   KALMIDO_* variables nobody reads (from the registry tools/env_check.py checks), never a known one
 - tools/env_check.py: no number read with int()/float() straight from os.environ (its rule finds a planted one)
 - in the container: TZ that is no time zone and PORT=abc end importing the config with one FATAL line (exit 2, no traceback);
   TASKS_MAX_FILE_MB=50MB starts with a warning and the default
 - the start log names KALMIDO_SMTP_HOSTT (a typo) once, and says that KALMIDO_SMTP_HOST without a sender leaves mail off
 - pg_requirements: the test database (PostgreSQL 17, both extensions) passes; an old major version, a missing extension and a
   user without the right to create one each give a clear line (a stand-in connection)
 - the virus scanner set but not answering: no alert at once, one storage alert "clamd" after KALMIDO_CLAMD_ALERT_S
 - the small ones: the test mail's error in words (smtp_why), a full disk while storing a task file = 507 with words, an
   authenticator code that fits a clock minutes off gets that hint (and is never accepted)
freelancer-matrix: admin (server start and admin alerts; nothing per person)
usage: p21437_c_startmsg_test.py <datadir>"""
import contextlib
import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile

N = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, N)
SRC = os.environ.get("KALMIDO_SRC") or os.path.join(N, "..")
DATA = sys.argv[1] if len(sys.argv) > 1 else os.path.join(N, ".data")
CT = os.environ.get("KALMIDO_TEST_CONTAINER", "kalmido-test")
from kt import check, done  # noqa: E402

# ---- unit: kalmido/core/env.py
spec = importlib.util.spec_from_file_location("p21437c_env", os.path.join(SRC, "kalmido", "core", "env.py"))
E = importlib.util.module_from_spec(spec)
spec.loader.exec_module(E)


def warned(fn, *a, **kw):
    buf = io.StringIO()
    with contextlib.redirect_stderr(buf):
        v = fn(*a, **kw)
    return v, buf.getvalue()


os.environ["P21437C_N"] = "50MB"
v, out = warned(E.env_int, "P21437C_N", 50)
check(v == 50 and "P21437C_N" in out and "'50MB'" in out and "(50)" in out, f"env_int: not a number = default + a line with the name {out!r}")
v, out = warned(E.env_int, "P21437C_N", 50)
check(v == 50 and out == "", "env_int: the warning comes once per process")
os.environ["P21437C_F"] = "1,5"
v, out = warned(E.env_float, "P21437C_F", 2.5)
check(v == 2.5 and "P21437C_F" in out, f"env_float: not a number = default + a line with the name {out!r}")
os.environ["P21437C_F"] = "0.25"
check(E.env_float("P21437C_F", 2.5) == 0.25 and E.env_float("P21437C_UNSET", 3) == 3.0, "env_float: a value, unset = default")
os.environ["P21437C_I"] = " 7 "
check(E.env_int("P21437C_I", 3) == 7 and E.env_int("P21437C_UNSET", "30") == 30, "env_int: a value with blanks, a default given as text")
for raw, want in (("", 3040), ("8080", 8080), ("abc", None), ("0", None), ("70000", None), ("-1", None)):
    os.environ["P21437C_PORT"] = raw
    buf = io.StringIO()
    try:
        with contextlib.redirect_stderr(buf):
            got = E.env_port("P21437C_PORT", 3040)
    except SystemExit as x:
        got = ("exit", x.code)
    if want is None:
        check(got == ("exit", 2) and "FATAL: P21437C_PORT=" in buf.getvalue(), f"env_port({raw!r}): FATAL with the name, exit 2 ({got} {buf.getvalue()!r})")
    else:
        check(got == want, f"env_port({raw!r}) = {want} ({got})")
known = [v[0] for v in E.VARS if v[0].startswith("KALMIDO_")][:3]
unk = E.env_unknown({"KALMIDO_SMTP_HOSTT": "x", "KALMIDO_CLAMDD": "y", "PATH": "/bin", **{k: "1" for k in known}})
check(unk == ["KALMIDO_CLAMDD", "KALMIDO_SMTP_HOSTT"], f"env_unknown: only the unknown KALMIDO_* names, sorted ({unk})")
for k in ("P21437C_N", "P21437C_F", "P21437C_I", "P21437C_PORT"):
    os.environ.pop(k, None)

# ---- tools/env_check.py: the rule against int(os.environ ...)
r = subprocess.run([sys.executable, os.path.join(SRC, "tools", "env_check.py")], capture_output=True, text=True)
check(r.returncode == 0, f"env_check passes on the code: {r.stdout[-400:]}")
spec = importlib.util.spec_from_file_location("p21437c_envcheck", os.path.join(SRC, "tools", "env_check.py"))
EC = importlib.util.module_from_spec(spec)
spec.loader.exec_module(EC)
check(EC.RAW_NUM.search('X = int(os.environ.get("KALMIDO_FOO", "3"))') and EC.RAW_NUM.search("y = float( os.getenv('A') or 1)")
      and not EC.RAW_NUM.search('X = env_int("KALMIDO_FOO", 3)'), "env_check: the pattern finds a raw number read, not env_int")
with tempfile.TemporaryDirectory() as td:
    os.makedirs(os.path.join(td, "kalmido", "core"))
    open(os.path.join(td, "app.py"), "w").write("")
    with open(os.path.join(SRC, "kalmido", "core", "env.py"), encoding="utf-8") as f:
        open(os.path.join(td, "kalmido", "core", "env.py"), "w").write(f.read())
    open(os.path.join(td, "kalmido", "x.py"), "w").write('import os\nN = int(os.environ.get("KALMIDO_DB_WAIT", "60"))\n')
    r = subprocess.run([sys.executable, os.path.join(SRC, "tools", "env_check.py"), "--root", td], capture_output=True, text=True)
    check(r.returncode == 1 and "kalmido/x.py:2" in r.stdout and "env_int" in r.stdout, f"env_check: a planted raw read is red {r.stdout[-300:]}")


# ---- in the container
def start(extra=()):
    e = dict(os.environ, EXTRA=" ".join(extra))
    e.pop("KEEP", None)
    r = subprocess.run(["bash", os.path.join(N, "start.sh"), DATA], env=e, capture_output=True, text=True)
    return r.returncode == 0


def logs():
    r = subprocess.run(["docker", "logs", CT], capture_output=True, text=True)
    return r.stdout + r.stderr


def run_in(code, env=()):
    args = ["docker", "exec", "-w", "/app", "-e", "TASKS_WATCHDOG=0"]
    for kv in env:
        args += ["-e", kv]
    return subprocess.run(args + [CT, "python", "-c", code], capture_output=True, text=True, timeout=120)


def in_app(code):
    r = run_in("import app, json\n" + code)
    return r.stdout.strip().splitlines()[-1] if r.stdout.strip() else "ERR " + r.stderr[-600:]


subprocess.run(["docker", "rm", "-f", CT], capture_output=True)
ok = start(extra=("-e KALMIDO_SMTP_HOSTT=mail.example.com", "-e KALMIDO_SMTP_HOST=mail.example.com", "-e TASKS_MAX_FILE_MB=50MB"))
lg = logs()
check(ok, "the server starts with a typo, a mail host without sender and a wrong number " + lg[-800:])
check(lg.count("Kalmido does not know") == 1 and "KALMIDO_SMTP_HOSTT" in lg, "the start names the unknown variable once " + lg[-600:])
check("KALMIDO_SMTP_HOST is set but neither KALMIDO_MAIL_FROM" in lg, "a mail host without sender: one line")
check("TASKS_MAX_FILE_MB='50MB' is not a whole number" in lg and "Traceback" not in lg, "TASKS_MAX_FILE_MB=50MB: a warning, no traceback")
check(in_app("from kalmido.core.config import MAX_FILE_MB\nprint(MAX_FILE_MB)") == "50", "TASKS_MAX_FILE_MB=50MB: the default 50")

r = run_in("import kalmido.core.config", env=("TZ=Mars/Phobos",))
check(r.returncode == 2 and "FATAL: TZ='Mars/Phobos' is not a time zone" in r.stderr and "Traceback" not in r.stderr,
      f"TZ that is no time zone: FATAL with the name, exit 2 ({r.returncode} {r.stderr[-300:]})")
r = run_in("import kalmido.core.config", env=("PORT=abc",))
check(r.returncode == 2 and "FATAL: PORT='abc' is not a port number" in r.stderr and "Traceback" not in r.stderr,
      f"PORT=abc: FATAL with the name, exit 2 ({r.returncode} {r.stderr[-300:]})")
r = run_in("from kalmido.core.config import PORT, TZ\nprint(PORT, TZ)", env=("PORT=4000", "TZ=UTC"))
check(r.returncode == 0 and r.stdout.strip() == "4000 UTC", f"PORT and TZ with good values ({r.stdout} {r.stderr[-200:]})")

# ---- PostgreSQL version and extensions
got = in_app("from kalmido.core.db import pg_requirements, connect_direct, DATABASE_URL\nc = connect_direct(DATABASE_URL)\n"
             "print(json.dumps(pg_requirements(c)))\nc.close()")
check(got == "[]", f"the test database (PostgreSQL 17, unaccent, pg_trgm) passes ({got})")
FAKE = """from kalmido.core.db import pg_requirements
class R:
    def __init__(self, rows): self.rows = rows
    def fetchone(self): return self.rows[0]
    def fetchall(self): return self.rows
class C:
    def __init__(self, num, have, avail, may): self.num, self.have, self.avail, self.may = num, have, avail, may
    def execute(self, q, a=()):
        if 'server_version_num' in q: return R([(str(self.num),)])
        if 'pg_extension' in q: return R([(x,) for x in self.have])
        if 'pg_available_extensions' in q: return R([(x,) for x in self.avail])
        if 'has_database_privilege' in q: return R([(self.may,)])
        raise AssertionError(q)
out = {"old": pg_requirements(C(160004, [], [], False)), "noext": pg_requirements(C(170012, ['unaccent'], ['unaccent'], True)),
       "norights": pg_requirements(C(170012, [], ['unaccent', 'pg_trgm'], False)), "ok": pg_requirements(C(170012, [], ['unaccent', 'pg_trgm'], True)),
       "newer": pg_requirements(C(180001, ['unaccent', 'pg_trgm'], [], False))}
print(json.dumps(out))"""
got = in_app(FAKE)
try:
    P = json.loads(got)
except ValueError:
    P = {}
check(P.get("old") and "PostgreSQL 16 is too old" in P["old"][0] and "PostgreSQL 17" in P["old"][0], f"PostgreSQL 16: too old, in words {got[:300]}")
check(P.get("noext") and len(P["noext"]) == 1 and "pg_trgm is not available" in P["noext"][0], f"a missing extension: named {P.get('noext')}")
check(P.get("norights") and len(P["norights"]) == 2 and "may not create" in P["norights"][0] and "CREATE EXTENSION unaccent" in P["norights"][0],
      f"no right to create: the command to run {P.get('norights')}")
check(P.get("ok") == [] and P.get("newer") == [], "installable extensions and a newer PostgreSQL: no FATAL")
check("Database integrity" not in got, "no stray output")

# ---- the virus scanner does not answer
SCAN = """import time
os = __import__('os'); os.environ['KALMIDO_CLAMD'] = '127.0.0.1:9'; os.environ['KALMIDO_CLAMD_DOWN_S'] = '0'
from kalmido.notify import alerts as A
from kalmido.core.db import connect
c = connect()
cfg = {**A.aa_cfg(c), 'on': True, 'kinds': list(A.AA_KINDS)}
n = lambda: c.execute("SELECT COUNT(*) FROM admin_alerts WHERE kind='storage' AND key='clamd'").fetchone()[0]
t = time.time()
A._aa_scanner(c, cfg, t); a = n()
A._aa_scanner(c, cfg, t + 30); b = n()
A._aa_scanner(c, cfg, t + A.AA_SCAN_DOWN_S + 61); d = n()
m = c.execute("SELECT message FROM admin_alerts WHERE key='clamd' ORDER BY id DESC LIMIT 1").fetchone()
os.environ['KALMIDO_CLAMD'] = ''
A._AA['scan_at'] = 0; A._aa_scanner(c, cfg, t + 2000); off = A._AA['scan_down']
print(json.dumps([a, b, d, m[0] if m else '', off]))"""
got = in_app(SCAN)
try:
    a, b, d, msg, off = json.loads(got)
except ValueError:
    a = b = d = off = None
    msg = got
check(a == 0 and b == 0 and d == 1, f"scanner down: no alert at once, one after {300} s ({got[:300]})")
check("127.0.0.1:9" in msg and "COMPOSE_PROFILES" in msg and "KALMIDO_CLAMD=" in msg, f"the alert names the address and both ways ({msg[:200]})")
check(off == 0.0, "scanner switched off: no down time kept")

# ---- the small ones
SMALL = """import errno, smtplib, socket
from kalmido.core.config import app as F
from kalmido.integrations.mail import smtp_why
from kalmido.accounts.login import totp_wrong, totp_code, totp_match, TOTP_STEP
from kalmido.tasks.attachments import _att_full
from kalmido.core.access import Denied
import base64, time
out = {}
with F.test_request_context():
    out['auth'] = smtp_why(smtplib.SMTPAuthenticationError(535, b'no'))
    out['net'] = smtp_why(ConnectionRefusedError(111, 'refused'))
    out['other'] = smtp_why(ValueError('x'))
    sec = base64.b32encode(b'0123456789abcdefghij').decode().rstrip('=')
    key = base64.b32decode(sec + '=' * (-len(sec) % 8))
    now = int(time.time() // TOTP_STEP)
    far = totp_code(key, now + 6)
    out['skew'] = totp_wrong(sec, far)
    out['skew_ok'] = totp_match(sec, far)
    out['plain'] = totp_wrong(sec, '000000' if totp_code(key, now) != '000000' else '111111')
    try:
        _att_full(OSError(errno.ENOSPC, 'No space left on device'))
        out['full'] = None
    except Denied as e:
        out['full'] = [e.code, e.text()]
    try:
        _att_full(OSError(errno.EACCES, 'denied'))
        out['other_os'] = 'passed'
    except Denied:
        out['other_os'] = 'denied'
print(json.dumps(out))"""
got = in_app(SMALL)
try:
    S = json.loads(got)
except ValueError:
    S = {}
check("refused the sign-in" in S.get("auth", ""), f"test mail: a refused login in words {got[:300]}")
check("cannot be reached" in S.get("net", "") and S.get("other") == "ValueError", f"test mail: not reachable in words, else the class name {S}")
check("3 minutes off" in S.get("skew", "") and S.get("skew_ok") is None, f"2FA: a code 3 min off is said, never accepted {S.get('skew')}")
check(S.get("plain") == "Wrong code", f"2FA: a wrong code stays 'Wrong code' {S.get('plain')}")
check(S.get("full") and S["full"][0] == 507 and "not enough space" in S["full"][1] and S.get("other_os") == "passed",
      f"a full disk while storing a task file: 507 with words; another file error stays {S.get('full')} {S.get('other_os')}")

subprocess.run(["docker", "rm", "-f", CT], capture_output=True)
sys.exit(done("p21437_c_startmsg"))
