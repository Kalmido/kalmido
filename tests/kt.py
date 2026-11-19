"""kt.py - shared helpers for the Python suites (2.149.0 E, #2513 #2514). New suites import these instead of copying them;
the older suites keep their own copies (they keep working, nothing has to move).

    import kt
    from kt import B, DATA, check, sess, until
    kt.fresh(env={"KALMIDO_DOCS_SCAN_S": "2"})      # (re)start the container unless <PREFIX>_NOSTART / KMT_NOSTART is set
    A = kt.setup()                                     # first admin "alice" + instance setup, logged in
    s = sess("bob")                                    # a logged-in session (password123)
    row = until(lambda: kt.dbx("SELECT ..."), 20)      # wait for a state instead of a fixed sleep
    check(cond, "what")  ...  sys.exit(kt.done("p2149_e_api"))

Settings come from the environment like in start.sh (KALMIDO_TEST_PORT, KALMIDO_TEST_CONTAINER, KALMIDO_TEST_DATA / argv[1]).
The test time: testclock.now() / today() (KALMIDO_TEST_NOW, run_all.sh `now <instant>; fresh`) - re-exported here."""
import os
import subprocess
import sys
import time

N = os.path.dirname(os.path.abspath(__file__))
if N not in sys.path:
    sys.path.insert(0, N)
import dbx as _dbx  # noqa: E402
from testclock import now, today  # noqa: E402,F401  (re-exported)

DATA = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("-") else os.environ.get("KALMIDO_TEST_DATA") or os.path.join(N, ".data")
PORT = os.environ.get("KALMIDO_TEST_PORT", "3048")
B = "http://127.0.0.1:" + PORT
CT = os.environ.get("KALMIDO_TEST_CONTAINER", "kalmido-test")
H = {"X-Requested-With": "kalmido"}
PASSWORD = "password123"
FAILS, OKS = [], [0]


def state_file(name):
    """2.609.0 (#4512): a state file that one suite writes for the suites after it in its group (ids.json of api_test.py,
    cal_ids.json of calendars_test.py, news_ids.json): in the test data folder DATA, not in tests/ - two runs in one work
    tree (two Mac places, a hand run beside a shard) never overwrite each other's; start.sh removes it with the folder at
    the next fresh group. The JS side: stateFile / readState in tests/boot.js."""
    return os.path.join(DATA, name)


def me_id(s):
    """2.609.0 (#4512): the user id of session s (GET /api/me), for "myself" instead of a fixed /api/users/1."""
    r = s.get(B + "/api/me")
    assert r.ok, ("/api/me", r.status_code, r.text[:200])
    return r.json()["id"]


FIRST_FAIL = []


def on_first_fail(fn):
    """2.358.0 D (#2783): call fn() once, right after the first failed check (e.g. print the container's log)."""
    FIRST_FAIL.append(fn)


def docker_logs_on_first_fail(tail=60, chars=6000):
    """2.358.0 D (#2783): the server's side of the first failure (a traceback of a background thread) into the output."""
    def show():
        r = subprocess.run(["docker", "logs", "--tail", str(tail), CT], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        print(r.stdout[-chars:], flush=True)
    on_first_fail(show)


STEPS = []  # 2.625 D (#4005): the open steps file of KALMIDO_JUNIT_STEPS (tests/run_all.sh -> tests/junit.py), once


def _step(ok, what):
    """2.625 D (#4005): one line per check into the steps file run_all.sh names (KALMIDO_JUNIT_STEPS) - a JUnit case each."""
    p = os.environ.get("KALMIDO_JUNIT_STEPS")
    if not p:
        return
    try:
        if not STEPS:
            STEPS.append(open(p, "a", encoding="utf-8"))
        STEPS[0].write(("ok" if ok else "fail") + "\t" + " ".join(str(what).split())[:300] + "\n")
        STEPS[0].flush()
    except OSError:
        pass


def check(cond, what):
    """Count a passed check or print and remember a failed one (the suite ends with sys.exit(done(name)))."""
    _step(cond, what)
    if cond:
        OKS[0] += 1
    else:
        FAILS.append(what)
        print("FAIL:", what, flush=True)
        if len(FAILS) == 1:
            for fn in FIRST_FAIL:
                fn()
    return bool(cond)


def lang(code):
    """(#7239) A language as the app serves it: static/i18n/<code>.json + the fragments static/i18n/neu/<KID>.json the merge
    queue moves a package's new texts into until the train folds them in (kalmido/core/i18nfrag.py, the one reader). A test
    that read the big file alone was red on main in that window (p7115_dev_profile, night run 19.11.2026)."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("i18nfrag", os.path.join(N, "..", "kalmido", "core", "i18nfrag.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.load_lang(os.path.join(N, "..", "static", "i18n"), code)


def done(name):
    """Print the summary line run_all.sh greps for; -> the exit code."""
    print(f"{name}: {OKS[0]} ok, {len(FAILS)} failed", flush=True)
    return 1 if FAILS else 0


def sess(user=None, pw=PASSWORD, ip=None, ua=None, headers=None, session_cls=None, hooks=(), soft=False, json_ok=False):
    """A logged-in session with the X-Requested-With header (user None: a session that is not logged in, 2.206.0 #2762).
    2.358.0 D (#2783), all optional: ip = X-Forwarded-For on the login request only; headers = extra headers of the whole
    session (ua = its User-Agent); session_cls = a requests.Session subclass; hooks = response hooks; json_ok = the login
    answer must carry ok=true too; soft = -> None instead of an assert error when the login fails."""
    import requests  # here, not at the top: the lint job runs i18n/mcp suites without requests installed (CI of 2.168.4)
    s = (session_cls or requests.Session)()
    s.headers.update(H)
    if ua:
        s.headers["User-Agent"] = ua
    if headers:
        s.headers.update(headers)
    for h in hooks:
        s.hooks["response"].append(h)
    if user is None:
        return s
    r = s.post(B + "/api/auth/login", json={"username": user, "password": pw}, headers={"X-Forwarded-For": ip} if ip else {})
    good = r.ok and (not json_ok or r.json().get("ok"))
    if soft:
        return s if good else None
    assert good, (user, r.text)
    return s


def until(fn, timeout=30, step=0.25, secs=None):
    """Call fn until it returns something truthy (-> that value) or timeout seconds are over (-> fn's last value).
    The one way to wait for a state: no fixed sleeps for things the server does in the background.
    secs = timeout (the name of the older suites' own copies, 2.206.0 #2762)."""
    end = time.monotonic() + (timeout if secs is None else secs)
    while True:
        x = fn()
        if x or time.monotonic() >= end:
            return x
        time.sleep(step)


def apv_body(s, base, src, ids=("yes",), url=None, **kw):
    """2.1386.0 (#6623): the body of an answer to an approval card as the web card sends it: a Yes on a card with a bound step
    carries the proof of the server's description (GET /api/approvals/diff -> proof). base = the suite's B; src = chat:<message id> | comment:<id>;
    url = the description's address of a token (V + "/approvals/diff"), kw = its headers."""
    ids = list(ids) if isinstance(ids, (list, tuple)) else [ids]
    k, i = src.split(":", 1)
    r = s.get((url or base + "/api/approvals/diff") + f"?{k}={i}", **kw)
    p = (r.json() or {}).get("proof") if r.ok else None
    return {"choice_ids": ids, **({"desc_proof": p} if p and "yes" in ids else {})}


def circle_yes(r, h, aid, s, v, to, base=B):
    """2.1433.0 (#7142, decision of #6863): an agent without a chosen control level counts as "free" for the circle rule
    (agents/circle.py): its write into a wider / public circle answers 409 approval_required with circle. For a suite whose
    agent (token headers h, id aid) really writes across circles: the card to person `to` (session s; must read every place
    of the agent), their Yes, the step run from the card (POST /agent/approvals/ID/run) -> the step's own answer. Any other
    answer r comes back unchanged; a card that cannot be made fails loudly (never a silent pass)."""
    import requests  # here, not at the top (see sess)
    try:
        e = (r.json() or {}).get("error") or {}
    except ValueError:
        return r
    if r.status_code != 409 or not isinstance(e, dict) or e.get("code") != "approval_required" or not e.get("circle"):
        return r
    ap = e.get("approval") or {}
    st = {k: ap[k] for k in ("method", "path", "body", "if_match") if k in ap}
    m = requests.post(v + f"/agent/chats/{to}", headers=h, json={"approval": {"title": "Write there", "what": "Write there", "step": st}})
    assert m.status_code == 201, f"circle_yes: the card {m.status_code} {m.text[:300]}"
    mid = m.json()["id"]
    y = s.post(base + f"/api/agents/{aid}/chat/{mid}/choice", json=apv_body(s, base, f"chat:{mid}", "yes"))
    assert y.ok, f"circle_yes: the Yes {y.status_code} {y.text[:300]}"
    return requests.post(v + f"/agent/approvals/{mid}/run", headers=h)


def dbx(sql, args=(), data=None):
    """Rows of a query in the suite's database (tests/dbx.py, the data dir names it)."""
    c = _dbx.connect(os.path.join(data or DATA, "tasks.db"))
    try:
        return c.execute(sql, args).fetchall()
    finally:
        c.close()


def proved(data=None):
    """2.1021.0 (#5775): the suite's accounts proved their addresses (users.email_proved, as a mailed link / OIDC / a confirmed
    sign-up does) -- an organisation admin's invitation by address, a mail sender and a mailed reply bind only a proved address."""
    dbx("UPDATE users SET email_proved=lower(COALESCE(email, '')) WHERE email_proved='' AND COALESCE(email, '')<>''", data=data)


def nostart(prefix=""):
    """True when the container runs already: <PREFIX>_NOSTART=1 (e.g. P2149E_NOSTART) or KMT_NOSTART=1."""
    return bool((prefix and os.environ.get(prefix + "_NOSTART")) or os.environ.get("KMT_NOSTART"))


def fresh(env=None, prefix="", keep=False, data=None):
    """(Re)start the test container through start.sh with extra container settings (env: {name: value} -> docker -e), unless
    nostart(prefix). keep=True keeps the data dir and database (KEEP=1). Waits until /api/health answers (start.sh does)."""
    if nostart(prefix):
        return False
    extra = os.environ.get("EXTRA", "")
    for k, v in (env or {}).items():
        extra += f" -e {k}={v}"
    e = dict(os.environ, EXTRA=extra.strip())
    if keep:
        e["KEEP"] = "1"
    else:
        e.pop("KEEP", None)
    r = subprocess.run(["bash", os.path.join(N, "start.sh"), data or DATA], env=e, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    return True


def setup(user="alice", name="Alice Admin", lang="en", collab_all=True):
    """The first account (instance admin) on an empty server plus the instance setup -> its logged-in session."""
    import requests
    s0 = requests.Session()
    s0.headers.update(H)
    r = s0.post(B + "/api/auth/setup", json={"username": user, "display_name": name, "password": PASSWORD})
    assert r.ok, r.text
    a = sess(user)
    a.post(B + "/api/admin/setup", json={"lang": lang, "collab_all": collab_all})
    return a


def container_env(name):
    """The value of an environment variable inside the running test container ('' when unset)."""
    r = subprocess.run(["docker", "exec", CT, "printenv", name], capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else ""


def su_get(s, url, pw=PASSWORD, **kw):
    """2.223.2 C (#2871): a download behind the step-up (retention exports, the own office's export): POST with the password
    -> a one-time ticket, then GET with it. -> the GET response (or the refused POST's one)."""
    r = s.post(url, json={"password": pw})
    if not r.ok:
        return r
    return s.get(url, params={"t": r.json().get("ticket", "")}, **kw)
