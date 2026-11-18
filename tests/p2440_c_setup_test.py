#!/usr/bin/env python3
"""2.44.0 part C (#962 agent_launcher.sh on macOS, #1517 setup with one command) against a stub API, no container.
 - lint: mcp/agent_launcher.sh and static/agent/setup.sh use no GNU-only tool or option and nothing newer than bash 3.2
   (macOS ships bash 3.2 and BSD tools)
 - agent_launcher.sh: the nightly time comes from python3 (no GNU date -d) and matches zoneinfo; without util-linux setsid
   on PATH the command still gets its own process group (python3 os.setsid), is reported with its host name
   (PUT /api/v1/agent/status {host}) and ends with the launcher; a missing agent command is reported as error
 - static/agent/setup.sh: --dry-run writes nothing and shows the LaunchAgent (macOS) / systemd --user unit (Linux); a real
   run with --no-autostart redeems the code, keeps the token out of the output in a file with mode 600, takes the starter
   files of mcp/starter_files.txt and writes mcp.json; --uninstall revokes the token and removes the instance folder
 - static/agent/setup.ps1 -DryRun with pwsh when there is one (else SKIP for that part)
Every shell part runs with /bin/bash (bash 3.2 on a Mac) and, when different, with the bash on PATH."""
import json
import os
import re
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import threading
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from zoneinfo import ZoneInfo

from kt import check, done, until  # 2.206.0 B (#2762): shared helpers (tests/kt.py)

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
LAUNCHER = os.path.join(ROOT, "mcp", "agent_launcher.sh")
SETUP_SH = os.path.join(ROOT, "static", "agent", "setup.sh")
SETUP_PS1 = os.path.join(ROOT, "static", "agent", "setup.ps1")
MCP = os.path.join(ROOT, "mcp")


def read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


# ---- lint: GNU-only / bash 4+ constructs (comment lines skipped)
BAD = [(r"\bsed\s+-i\b", "sed -i"), (r"\breadlink\s+-f\b", "readlink -f"), (r"\bdate\s+-d\b", "date -d"), (r"\bgrep\s+-\w*P", "grep -P"),
       (r"(^|[;&|(]\s*)timeout\s", "timeout"), (r"\bmapfile\b|\breadarray\b", "mapfile"), (r"\bdeclare\s+-A\b|\blocal\s+-A\b", "associative array"),
       (r"\$\{\w+(,,|\^\^)", "${x,,}"), (r"\|&", "|&"), (r"&>>", "&>>"), (r"\bwait\s+-n\b", "wait -n"), (r"\bcoproc\b", "coproc"),
       (r"\bstat\s+-c\b", "stat -c"), (r"-printf\b", "find -printf"), (r"\bxargs\s+-r\b", "xargs -r"), (r"\bsort\s+-V\b", "sort -V"),
       (r"\bbase64\s+-w\b", "base64 -w"), (r"\$\{\w+@[QEPAa]\}", "${x@Q}"), (r";;&|;&", "case fallthrough")]
for path in (LAUNCHER, SETUP_SH):
    code = "\n".join(ln for ln in read(path).split("\n") if not ln.lstrip().startswith("#"))
    for pat, name in BAD:
        hits = [m.group(0) for m in re.finditer(pat, code, re.M)]
        check(not hits, f"{os.path.basename(path)}: no {name} (macOS / bash 3.2): {hits}")
    check(not re.search(r"(^|[^\w-])setsid\s+\"", code), f"{os.path.basename(path)}: setsid only through the portable NEWSESS")
src = read(LAUNCHER)
# 2.1394.0 (#4068): the launcher only loads the env file and starts agent_run.py --launch; the time of the nightly restart and the
# process group are Python's (mcp/agent_run.py nightly_at, start_new_session), the same for agent_launcher.ps1
check("date -d" not in src.replace("GNU date -d", "") and "--launch" in src and "exec " in src, "launcher: python3 for time and process group")

BASHES = []
for b in ("/bin/bash", shutil.which("bash")):
    if b and os.path.exists(b) and os.path.realpath(b) not in [os.path.realpath(x) for x in BASHES]:
        BASHES.append(b)
for b in BASHES:
    v = subprocess.run([b, "-c", "echo $BASH_VERSION"], capture_output=True, text=True).stdout.strip()
    print(f"bash: {b} {v}")
    for path in (LAUNCHER, SETUP_SH):
        r = subprocess.run([b, "-n", path], capture_output=True, text=True)
        check(r.returncode == 0, f"{b} -n {os.path.basename(path)}: {r.stderr[:200]}")

# ---- the launcher core's time function = zoneinfo (2.1394.0, #4068: mcp/agent_run.py nightly_at)
import importlib.util  # noqa: E402
_spec = importlib.util.spec_from_file_location("agent_run_p2440c", os.path.join(ROOT, "mcp", "agent_run.py"))
ar = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ar)
for day, hm, tz in (("2026-10-15", "03:00", "Europe/Berlin"), ("2026-01-15", "23:30", "America/New_York"), ("2026-07-01", "00:00", "UTC")):
    y, m, d = map(int, day.split("-"))
    hh, mm = map(int, hm.split(":"))
    want = int(datetime(y, m, d, hh, mm, tzinfo=ZoneInfo(tz)).timestamp())
    noon = datetime(y, m, d, 12, 0, tzinfo=ZoneInfo(tz)).timestamp()
    got = ar.nightly_at(hm, tz, now=noon)
    check(got is not None and int(got) == want, f"nightly_at {day} {hm} {tz} = {want}, got {got!r}")
check(ar.nightly_at("25:00", "UTC") is None and ar.nightly_at("", "UTC") is None, "no such time: no restart")

# ---- a stub Kalmido
TOKEN = "abk_stub_secret_token_4711"
ST = {"status": [], "redeem": [], "remove": [], "enabled": True, "remove_code": 200, "base": None,  # 2.360.0: base = another starter address  # 2.47.3 (#1729): remove_code 401 = the key is already revoked
      "revoked": False,  # 2.157.0 (#1517): GET /api/v1/agent answers 401 (computer removed in Kalmido)
      "polls": 0,  # 2.206.0 B (#2513): GET /api/v1/agent count: "nothing happens for N polls" instead of a fixed sleep
      "sha": None}  # 2.380 G (#3390): the checksums the redeem answer sends (None: none, like an older Kalmido)


class Stub(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _json(self, code, obj):
        b = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b)

    def _body(self):
        n = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(n) or b"{}")

    def do_GET(self):
        if self.path == "/api/v1/agent":
            ST["polls"] += 1
        if self.path == "/api/v1/agent" and ST["revoked"]:
            return self._json(401, {"error": "invalid token"})
        if self.path == "/api/v1/agent" and self.headers.get("Authorization") == "Bearer " + TOKEN:
            return self._json(200, {"id": 9, "enabled": ST["enabled"], "runtime": {"model": None, "autocompact": True, "autocompact_pct": None,
                                                                                    "nightly_reset": "04:00", "reset_seq": 0, "timezone": "Europe/Berlin"}})
        if self.path.startswith("/mcp/"):
            p = os.path.join(MCP, os.path.basename(self.path))
            if os.path.isfile(p):
                self.send_response(200)
                self.end_headers()
                self.wfile.write(open(p, "rb").read())
                return
        self._json(404, {"error": "not found"})

    def do_PUT(self):
        if self.path == "/api/v1/agent/status":
            ST["status"].append((self.headers.get("Authorization"), self._body()))
            return self._json(200, {"ok": True})
        self._json(404, {})

    def do_POST(self):
        if self.path == "/api/agent-setup/redeem":
            b = self._body()
            ST["redeem"].append((self.headers.get("X-Requested-With"), b))
            if b.get("code") != "ks_good_code":
                return self._json(400, {"error": "This setup code is invalid, used or expired. Create a new one in Kalmido."})
            ips = {"allowed_ips": ["203.0.113.7/32"], "allowed_ips_applied": True} if b.get("allowed_ips") == "current" else {}  # 2.1367.0 (#6457)
            return self._json(200, {**ips, "token": TOKEN, "url": "https://ignored.example", "version": "2.44.0",
                                    "agent": {"id": 9, "name": "Helper", "username": "helper"}, "starter_base": ST["base"] or f"{URL}/mcp/",
                                    **({"starter_sha256": ST["sha"]} if ST["sha"] is not None else {})})
        if self.path == "/api/agent-setup/remove":
            ST["remove"].append(self.headers.get("Authorization"))
            if ST["remove_code"] != 200:
                return self._json(ST["remove_code"], {"error": "Missing or invalid API token"})
            return self._json(200, {"ok": True})
        self._json(404, {})


srv = ThreadingHTTPServer(("127.0.0.1", 0), Stub)
threading.Thread(target=srv.serve_forever, daemon=True).start()
URL = f"http://127.0.0.1:{srv.server_address[1]}"

def alive_pid(pid):
    try:
        os.kill(pid, 0)
        return True
    except (OSError, TypeError):
        return False


# ---- the launcher without setsid on PATH: own process group, host reported, ends with the launcher
tmp = tempfile.mkdtemp(prefix="kalmido-p2440c-")
nobin = os.path.join(tmp, "bin")
os.makedirs(nobin)
for t in ("bash", "env", "curl", "python3", "sleep", "seq", "date", "hostname", "sed", "dirname", "cat", "uname", "id", "tr", "cut", "cksum", "basename", "mkdir", "chmod", "cp", "mv", "rm", "pwd", "ls"):
    w = shutil.which(t)
    if w:
        os.symlink(w, os.path.join(nobin, t))
fake = os.path.join(nobin, "fakeagent")
with open(fake, "w") as f:
    f.write("#!/usr/bin/env python3\nimport os, sys, time\nopen(os.environ['FAKE_OUT'], 'w').write('%d %d %s %s %s' % (os.getpid(), os.getpgid(0), os.environ.get('KALMIDO_LAUNCHER_PID', '-'), 'T' if 'KALMIDO_TOKEN' in os.environ else '-', os.environ.get('KALMIDO_ENV_FILE', '-')))\ntime.sleep(120)\n")
os.chmod(fake, 0o755)
envf = os.path.join(tmp, "agent.env")
with open(envf, "w") as f:
    f.write(f"KALMIDO_URL={URL}\nKALMIDO_TOKEN={TOKEN}\nKALMIDO_POLL=1\nKALMIDO_HOST=desk-07.example.lan\n")
os.chmod(envf, 0o600)
check(not shutil.which("setsid", path=nobin), "test PATH has no setsid")
for b in BASHES:
    ST["status"].clear()
    out_f = os.path.join(tmp, "fake.out")
    if os.path.exists(out_f):
        os.remove(out_f)
    env = {"PATH": nobin, "HOME": tmp, "FAKE_OUT": out_f}
    r = subprocess.run([b, LAUNCHER, "-e", envf, "--once", "--", "fakeagent", "--x"], env=env, capture_output=True, text=True, timeout=60)
    check(r.returncode == 0 and "fakeagent --x" in r.stdout and TOKEN not in r.stdout + r.stderr, f"{b}: --once dry run: {r.stdout!r} {r.stderr[-300:]!r}")
    p = subprocess.Popen([b, LAUNCHER, "-e", envf, "--", "fakeagent"], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
    until(lambda: os.path.exists(out_f) and os.path.getsize(out_f), 30)  # 2.206.0 B (#2513): generous state waits (CI load)
    pid = pgid = None
    lpid = tokf = envp = "-"
    if os.path.exists(out_f) and os.path.getsize(out_f):
        pid, pgid, lpid, tokf, envp = read(out_f).split()
        pid, pgid = int(pid), int(pgid)
    # 2.1367.0 (#6457): without --events the command is the model itself: no token, only the env file's path
    check(tokf == "-" and envp in (envf, os.path.realpath(envf)), f"{b}: #6457: the command gets KALMIDO_ENV_FILE, never KALMIDO_TOKEN ({tokf}, {envp})")
    check(pid and pid == pgid and pgid != os.getpgid(0), f"{b}: the command runs in its own process group without setsid ({pid}, {pgid})")
    check(lpid == str(p.pid), f"{b}: 2.157.0 (#1517): the command gets KALMIDO_LAUNCHER_PID = the launcher's pid ({lpid} vs {p.pid})")
    until(lambda: ST["status"], 30)
    st = ST["status"][0] if ST["status"] else (None, {})
    check(st[0] == "Bearer " + TOKEN and st[1].get("host") == "desk-07" and st[1].get("status") == "idle", f"{b}: host reported once at start: {st}")
    p.send_signal(signal.SIGTERM)
    try:
        p.wait(timeout=40)
    except subprocess.TimeoutExpired:
        p.kill()
    gone = until(lambda: not alive_pid(pid), 30)
    check(gone, f"{b}: the command ends with the launcher")
    # a missing agent command -> error status
    ST["status"].clear()
    p = subprocess.Popen([b, LAUNCHER, "-e", envf, "--", "no-such-agent-cmd"], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    until(lambda: ST["status"], 30)
    p.send_signal(signal.SIGTERM)
    try:
        p.wait(timeout=40)
    except subprocess.TimeoutExpired:
        p.kill()
    st = ST["status"][0][1] if ST["status"] else {}
    check(st.get("status") == "error" and "no-such-agent-cmd" in st.get("text", ""), f"{b}: a missing agent command is the agent's error: {st}")
    # 2.157.0 (#1517): the token is revoked while the agent runs -> the command stops, ONE log line, the launcher stays
    if os.path.exists(out_f):
        os.remove(out_f)
    p = subprocess.Popen([b, LAUNCHER, "-e", envf, "--", "fakeagent"], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
    until(lambda: os.path.exists(out_f) and os.path.getsize(out_f), 30)  # 2.206.0 B (#2513): generous state waits (CI load)
    pid = int(read(out_f).split()[0]) if os.path.exists(out_f) and os.path.getsize(out_f) else None
    ST["revoked"] = True
    gone = until(lambda: not alive_pid(pid), 30)
    polls = ST["polls"]  # 2.206.0 B (#2513): three more polls (KALMIDO_POLL=1) instead of a fixed 3 s: still one line, launcher there
    until(lambda: ST["polls"] >= polls + 3, 30)
    alive = p.poll() is None
    p.send_signal(signal.SIGTERM)
    try:
        _, err = p.communicate(timeout=40)
    except subprocess.TimeoutExpired:
        p.kill()
        _, err = p.communicate()
    check(gone and alive and err.count("no longer works") == 1 and "not reachable" not in err,
          f"{b}: revoked while running: command stopped ({gone}), launcher stays ({alive}), one log line: {err[-400:]!r}")
    # ... and already revoked at the start: no command, the launcher waits quietly instead of exiting (no restart loop)
    if os.path.exists(out_f):
        os.remove(out_f)
    polls = ST["polls"]
    p = subprocess.Popen([b, LAUNCHER, "-e", envf, "--", "fakeagent"], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
    until(lambda: ST["polls"] >= polls + 3 or p.poll() is not None, 30)  # 2.206.0 B (#2513): three polls instead of a fixed 3 s
    alive = p.poll() is None
    ST["revoked"] = False
    # works again (a test only: a revoked token never comes back) -> it starts the command
    until(lambda: os.path.exists(out_f) and os.path.getsize(out_f), 30)
    started = os.path.exists(out_f) and os.path.getsize(out_f) > 0
    p.send_signal(signal.SIGTERM)
    try:
        _, err = p.communicate(timeout=40)
    except subprocess.TimeoutExpired:
        p.kill()
        _, err = p.communicate()
    check(alive and started and err.count("no longer works") == 1, f"{b}: revoked at the start: waits quietly, starts once the key works: {alive} {started} {err[-400:]!r}")

# ---- setup.sh
check(os.path.isfile(SETUP_SH), "static/agent/setup.sh exists")
OSN = "mac" if sys.platform == "darwin" else "linux"
for b in BASHES:
    home = tempfile.mkdtemp(prefix="kalmido-p2440c-home-")
    env = {"PATH": nobin, "HOME": home}
    proj = os.path.join(home, "my project")
    r = subprocess.run([b, SETUP_SH, "--dry-run", "--url", URL, "--code", "ks_good_code", "--dir", "~/my project", "--cmd", "fakeagent"],
                       env=env, capture_output=True, text=True, timeout=60)
    o = r.stdout
    check(r.returncode == 0, f"{b}: dry run exit 0: {r.stderr[-400:]}")
    check(all(x in o for x in ("Checking what is needed", "Connecting to Kalmido", "Fetching the starter files", "Starting it at every login", "Done")), f"{b}: dry run shows every step")
    # 2.46.6 (#1713): --lang de gives the German messages, anything else English; commands and paths stay as they are
    rd = subprocess.run([b, SETUP_SH, "--dry-run", "--lang", "de-DE", "--url", URL, "--code", "ks_good_code", "--dir", "~/my project", "--cmd", "fakeagent"],
                        env=env, capture_output=True, text=True, timeout=60)
    check(rd.returncode == 0 and all(x in rd.stdout for x in ("Prüfe, was gebraucht wird", "Verbinde mit Kalmido", "Lade die Starter-Dateien", "Fertig", "(Probelauf)")), f"{b}: --lang de: German messages: {rd.stdout[:300]!r} {rd.stderr[-200:]!r}")
    check("Checking what is needed" not in rd.stdout and (OSN != "linux" or "Restart=always" in rd.stdout), f"{b}: --lang de: no English step lines, the unit text is unchanged")
    # 2.574.0 (#3759): fr is French now (was: English); a language without a table (pt) stays English
    rf = subprocess.run([b, SETUP_SH, "--dry-run", "--lang", "fr", "--url", URL, "--code", "ks_good_code", "--dir", "~/my project", "--cmd", "fakeagent"],
                        env=env, capture_output=True, text=True, timeout=60)
    check(rf.returncode == 0 and "Vérification de ce qui est nécessaire" in rf.stdout and "Checking what is needed" not in rf.stdout, f"{b}: --lang fr: French messages: {rf.stdout[:200]!r}")
    rp = subprocess.run([b, SETUP_SH, "--dry-run", "--lang", "pt", "--url", URL, "--code", "ks_good_code", "--dir", "~/my project", "--cmd", "fakeagent"],
                        env=env, capture_output=True, text=True, timeout=60)
    check(rp.returncode == 0 and "Checking what is needed" in rp.stdout, f"{b}: --lang pt falls back to English")
    if OSN == "mac":
        check("<key>KeepAlive</key><true/>" in o and "<key>RunAtLoad</key><true/>" in o and "/bin/bash" in o and "--events" in o, f"{b}: LaunchAgent with KeepAlive / RunAtLoad")
    else:
        check("Restart=always" in o and "WantedBy=default.target" in o and "--events" in o and "--mcp-config" in o, f"{b}: systemd --user unit")
    # (on macOS /usr/bin/python3, a developer-tools shim, may create ~/Library/Caches itself: only our files count)
    left = [x for x in os.listdir(home) if x != "Library"] + (["Library/LaunchAgents"] if os.path.exists(os.path.join(home, "Library", "LaunchAgents")) else [])
    check(not ST["redeem"] and not left, f"{b}: the dry run redeems nothing and writes nothing: {left}")
    # real run without autostart
    r = subprocess.run([b, SETUP_SH, "--url", URL, "--code", "ks_good_code", "--dir", "~/my project", "--cmd", "fakeagent", "--no-autostart"],
                       env=env, capture_output=True, text=True, timeout=120)
    check(r.returncode == 0, f"{b}: setup exit 0: {r.stdout[-300:]} {r.stderr[-300:]}")
    check(TOKEN not in r.stdout + r.stderr and "ks_good_code" not in r.stdout + r.stderr, f"{b}: neither token nor code in the output")
    red = ST["redeem"][-1] if ST["redeem"] else (None, {})
    check(red[0] == "kalmido" and red[1].get("os") == OSN and red[1].get("folder") == proj and red[1].get("host"), f"{b}: redeem with os / folder / host: {red}")
    insts = os.listdir(os.path.join(home, ".kalmido", "agents")) if os.path.isdir(os.path.join(home, ".kalmido", "agents")) else []
    check(len(insts) == 1 and insts[0].startswith("my-project-"), f"{b}: one instance per folder: {insts}")
    inst = os.path.join(home, ".kalmido", "agents", insts[0]) if insts else home
    ef = os.path.join(inst, "kalmido-agent.env")
    check(os.path.isfile(ef) and stat.S_IMODE(os.stat(ef).st_mode) == 0o600 and f"KALMIDO_TOKEN={TOKEN}" in read(ef) and f"KALMIDO_URL={URL}" in read(ef),
          f"{b}: env file mode 600 with the token and the address that worked")
    check(f"KALMIDO_STATE_DIR={os.path.join(inst, 'state')}" in read(ef), f"{b}: a state folder of its own per instance")
    # 2.443.0 (#2940): the launcher reads the env file as shell: a space in the home folder
    sp = os.path.join(home, "with space")
    os.makedirs(sp)
    r = subprocess.run([b, SETUP_SH, "--url", URL, "--code", "ks_good_code", "--dir", "~/proj", "--cmd", "fakeagent", "--no-autostart"],
                       env={**env, "HOME": sp, "KALMIDO_PYTHON": sys.executable}, capture_output=True, text=True, timeout=120)
    spi = os.path.join(sp, ".kalmido", "agents")
    spe = os.path.join(spi, os.listdir(spi)[0], "kalmido-agent.env") if os.path.isdir(spi) else ""
    v = subprocess.run(["bash", "-c", '. "$1"; printf "%s|%s" "$KALMIDO_STATE_DIR" "$KALMIDO_PYTHON"', "_", spe], capture_output=True, text=True).stdout
    check(r.returncode == 0 and v == os.path.join(os.path.dirname(spe), "state") + "|" + sys.executable, f"{b}: the env file reads back with a space in the home folder: {v!r} {r.stderr[-200:]}")
    shutil.rmtree(sp, ignore_errors=True)
    for need in ("agent_launcher.sh", "agent_run.py", "kalmido_mcp.py", "starter_files.txt", "mcp.json"):
        check(os.path.isfile(os.path.join(inst, need)), f"{b}: {need} in the instance folder")
    mj = json.loads(read(os.path.join(inst, "mcp.json"))) if os.path.isfile(os.path.join(inst, "mcp.json")) else {}
    check(mj.get("mcpServers", {}).get("kalmido", {}).get("args") == [os.path.join(inst, "kalmido_mcp.py")] and TOKEN not in json.dumps(mj), f"{b}: mcp.json without the token")
    check(os.path.isdir(proj), f"{b}: the project folder is created")
    # 2.1367.0 (#6457): the MCP server finds the env file through mcp.json; the deny rules land in .claude/settings.local.json
    check(mj.get("mcpServers", {}).get("kalmido", {}).get("env") == {"KALMIDO_ENV_FILE": ef}, f"{b}: #6457: mcp.json names the env file (path only): {mj}")
    hs = os.path.join(proj, ".claude", "settings.local.json")
    deny = (json.loads(read(hs)).get("permissions") or {}).get("deny") if os.path.isfile(hs) else None
    want = ["WebFetch", "WebSearch", "Read(~/.kalmido/*.env)", "Read(~/.kalmido/**/*.env)", f"Read(/{ef})", f"Edit(/{ef})"]
    check(deny == want, f"{b}: #6457: the setup writes the deny rules: {deny}")
    with open(hs, "w") as f:
        json.dump({"permissions": {"allow": ["Bash(ls:*)"], "deny": ["Bash(rm:*)", "WebFetch"]}, "model": "x"}, f)
    n = len(ST["redeem"])
    r = subprocess.run([b, SETUP_SH, "--url", URL, "--code", "ks_good_code", "--dir", "~/my project", "--cmd", "fakeagent", "--no-autostart", "--ip-rule", "current"],
                       env=env, capture_output=True, text=True, timeout=120)
    hj = json.loads(read(hs)) if os.path.isfile(hs) else {}
    check(r.returncode == 0 and hj.get("model") == "x" and hj.get("permissions", {}).get("allow") == ["Bash(ls:*)"]
          and hj.get("permissions", {}).get("deny") == ["Bash(rm:*)"] + want, f"{b}: #6457: a second setup keeps the entries there and adds nothing twice: {hj}")
    check(len(ST["redeem"]) == n + 1 and ST["redeem"][-1][1].get("allowed_ips") == "current" and "203.0.113.7/32" in r.stdout,
          f"{b}: #6457: --ip-rule current asks Kalmido for the address rule and names it: {ST['redeem'][-1][1].get('allowed_ips')} {r.stdout[-300:]!r}")
    check("allowed_ips" not in ST["redeem"][-2][1], f"{b}: #6457: no rule without --ip-rule and without a terminal")
    r = subprocess.run([b, SETUP_SH, "--url", URL, "--code", "ks_good_code", "--dir", "~/my project", "--cmd", "fakeagent", "--no-autostart", "--ip-rule", "x;rm"],
                       env=env, capture_output=True, text=True, timeout=60)
    check(r.returncode != 0 and len(ST["redeem"]) == n + 1, f"{b}: #6457: a wrong --ip-rule stops before the code goes out")
    # 2.1367.0 (#2700): the template "Software development": rules in a new CLAUDE.md + BRIEF-TEMPLATE.md; nothing overwritten
    sw = os.path.join(home, "sw")
    r = subprocess.run([b, SETUP_SH, "--url", URL, "--code", "ks_good_code", "--dir", "~/sw", "--cmd", "fakeagent", "--no-autostart", "--template", "software"],
                       env=env, capture_output=True, text=True, timeout=120)
    cm = read(os.path.join(sw, "CLAUDE.md")) if os.path.isfile(os.path.join(sw, "CLAUDE.md")) else ""
    br = read(os.path.join(sw, "BRIEF-TEMPLATE.md")) if os.path.isfile(os.path.join(sw, "BRIEF-TEMPLATE.md")) else ""
    check(r.returncode == 0 and "kalmido-agent-rules:start" in cm and "## Building software" in cm and "One working copy per order" in cm
          and "kalmido-template-brief" not in cm, f"{b}: #2700: a new CLAUDE.md with the general rules and the software block: {r.stdout[-300:]!r}")
    check(br.startswith("# Brief: TITLE (#TASK)") and "## Done when" in br and "<!--" not in br and not os.path.exists(os.path.join(sw, "CLAUDE.software.md")),
          f"{b}: #2700: BRIEF-TEMPLATE.md without the markers, no proposal file next to a new CLAUDE.md")
    with open(os.path.join(sw, "BRIEF-TEMPLATE.md"), "w") as f:
        f.write("my own brief\n")
    r = subprocess.run([b, SETUP_SH, "--url", URL, "--code", "ks_good_code", "--dir", "~/sw", "--cmd", "fakeagent", "--no-autostart", "--template", "software"],
                       env=env, capture_output=True, text=True, timeout=120)
    prop = os.path.join(sw, "CLAUDE.software.md")
    check(r.returncode == 0 and read(os.path.join(sw, "CLAUDE.md")) == cm and read(os.path.join(sw, "BRIEF-TEMPLATE.md")) == "my own brief\n"
          and os.path.isfile(prop) and "## Building software" in read(prop) and "kalmido-agent-rules:start" not in read(prop) and "CLAUDE.software.md" in r.stdout,
          f"{b}: #2700: an existing CLAUDE.md / brief stay, the rules come next to it as a proposal: {r.stdout[-300:]!r}")
    with open(prop, "w") as f:
        f.write("edited\n")
    r = subprocess.run([b, SETUP_SH, "--url", URL, "--code", "ks_good_code", "--dir", "~/sw", "--cmd", "fakeagent", "--no-autostart", "--template", "software"],
                       env=env, capture_output=True, text=True, timeout=120)
    check(r.returncode == 0 and read(prop) == "edited\n", f"{b}: #2700: a proposal there already is never overwritten")
    check(not os.path.exists(os.path.join(proj, "BRIEF-TEMPLATE.md")) and "## Building software" not in (read(os.path.join(proj, "CLAUDE.md")) if os.path.isfile(os.path.join(proj, "CLAUDE.md")) else ""),
          f"{b}: #2700: without --template only the general rules, no brief template")
    n = len(ST["redeem"])
    r = subprocess.run([b, SETUP_SH, "--url", URL, "--code", "ks_good_code", "--dir", "~/sw2", "--cmd", "fakeagent", "--no-autostart", "--template", "games"],
                       env=env, capture_output=True, text=True, timeout=60)
    check(r.returncode != 0 and len(ST["redeem"]) == n and "games" in r.stderr, f"{b}: #2700: an unknown template stops before the code goes out")
    # a wrong code: nothing stays behind
    n = len(ST["redeem"])
    r = subprocess.run([b, SETUP_SH, "--url", URL, "--code", "ks_bad", "--dir", "~/other", "--cmd", "fakeagent", "--no-autostart"],
                       env=env, capture_output=True, text=True, timeout=60)
    check(r.returncode != 0 and "invalid, used or expired" in r.stderr and len(ST["redeem"]) == n + 1, f"{b}: a refused code stops with the reason: {r.stderr[-300:]}")
    # uninstall
    ST["remove"].clear()
    r = subprocess.run([b, SETUP_SH, "--uninstall", "--dir", "~/my project"], env=env, capture_output=True, text=True, timeout=60)
    check(r.returncode == 0 and ST["remove"] == ["Bearer " + TOKEN] and not os.path.exists(inst) and os.path.isdir(proj),
          f"{b}: --uninstall revokes the token, removes the instance, keeps the project: {ST['remove']} {r.stderr[-300:]}")
    # 2.47.3 (#1729): --uninstall after the key was revoked (agent deleted): a hint, the cleanup still runs through (dry run + real)
    r = subprocess.run([b, SETUP_SH, "--url", URL, "--code", "ks_good_code", "--dir", "~/my project", "--cmd", "fakeagent", "--no-autostart"], env=env, capture_output=True, text=True, timeout=120)
    insts = os.listdir(os.path.join(home, ".kalmido", "agents")) if os.path.isdir(os.path.join(home, ".kalmido", "agents")) else []
    # the folder of "~/other" from above is there too: take the one of "my project" (os.listdir has no fixed order)
    insts = [x for x in insts if x.startswith("my-project-")]
    inst = os.path.join(home, ".kalmido", "agents", insts[0]) if insts else home
    ST["remove_code"] = 401
    ST["remove"].clear()
    r = subprocess.run([b, SETUP_SH, "--uninstall", "--lang", "en", "--dir", "~/my project"], env=env, capture_output=True, text=True, timeout=60)
    ST["remove_code"] = 200
    check(r.returncode == 0 and len(ST["remove"]) == 1 and not os.path.exists(inst) and os.path.isdir(proj) and "already revoked" in r.stdout and "Done" in r.stdout,
          f"{b}: --uninstall with a revoked key: hint only, files removed, project kept: {r.returncode} {r.stdout[-300:]} {r.stderr[-200:]}")
    # missing prerequisites are named
    r = subprocess.run([b, SETUP_SH, "--url", URL, "--code", "x", "--dir", "/tmp/x", "--cmd", "claude-not-here"], env=env, capture_output=True, text=True, timeout=60)
    check(r.returncode == 1 and "missing on this computer" in r.stderr and "claude-not-here" in r.stderr, f"{b}: a missing agent command is named: {r.stderr[-300:]}")
    # 2.360.0 C (#2496): the code from the environment (not on the command line); http:// only for localhost or --allow-http;
    # starter files only over https or from the Kalmido itself
    n = len(ST["redeem"])
    r = subprocess.run([b, SETUP_SH, "--url", URL, "--dir", "~/envcode", "--cmd", "fakeagent", "--no-autostart"],
                       env={**env, "KALMIDO_SETUP_CODE": "ks_good_code"}, capture_output=True, text=True, timeout=120)
    check(r.returncode == 0 and len(ST["redeem"]) == n + 1 and ST["redeem"][-1][1].get("code") == "ks_good_code" and "ks_good_code" not in r.stdout + r.stderr,
          f"{b}: the code from KALMIDO_SETUP_CODE: {r.returncode} {r.stderr[-300:]}")
    n = len(ST["redeem"])
    r = subprocess.run([b, SETUP_SH, "--url", "http://kalmido.example.invalid", "--code", "ks_good_code", "--dir", "~/http", "--cmd", "fakeagent", "--no-autostart"],
                       env=env, capture_output=True, text=True, timeout=60)
    check(r.returncode != 0 and "is an http:// address" in r.stderr and len(ST["redeem"]) == n, f"{b}: http:// to another computer is refused before the code goes out: {r.stderr[-300:]}")
    r = subprocess.run([b, SETUP_SH, "--allow-http", "--url", "http://kalmido.example.invalid", "--code", "ks_good_code", "--dir", "~/http", "--cmd", "fakeagent", "--no-autostart"],
                       env=env, capture_output=True, text=True, timeout=90)
    check(r.returncode != 0 and "is an http:// address" not in r.stderr, f"{b}: --allow-http takes it (then the address is not reachable): {r.stderr[-300:]}")
    ST["base"] = "http://starter.example.invalid/mcp/"
    r = subprocess.run([b, SETUP_SH, "--url", URL, "--code", "ks_good_code", "--dir", "~/plainbase", "--cmd", "fakeagent", "--no-autostart"],
                       env=env, capture_output=True, text=True, timeout=120)
    ST["base"] = None
    check(r.returncode != 0 and "without https://" in r.stderr, f"{b}: starter files from a plain http address are refused: {r.stderr[-300:]}")
    # 2.380 G (#3390): the checksums of the redeem answer (mcp/starter_sha256.txt): matching -> installed; one file differs -> the
    # setup stops before that file is installed
    # #6887: the sums are computed (tools/starter_sha.py), the file is no longer checked in
    _ss = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "starter_sha.py"), "--print"], capture_output=True, text=True)
    SHA = {ln.split()[1]: ln.split()[0] for ln in _ss.stdout.splitlines() if ln.strip() and not ln.startswith("#")}
    check("starter_files.txt" in SHA and "agent_run.py" in SHA, f"starter_sha256.txt lists the list and the files: {sorted(SHA)}")
    agents = os.path.join(home, ".kalmido", "agents")
    ST["sha"] = SHA
    r = subprocess.run([b, SETUP_SH, "--url", URL, "--code", "ks_good_code", "--dir", "~/shaok", "--cmd", "fakeagent", "--no-autostart"],
                       env=env, capture_output=True, text=True, timeout=120)
    inst = [os.path.join(agents, d) for d in os.listdir(agents) if d.startswith("shaok-")]
    check(r.returncode == 0 and inst and os.path.isfile(os.path.join(inst[0], "agent_run.py")) and os.path.isfile(os.path.join(inst[0], "starter_sha256.txt")),
          f"{b}: #3390 matching checksums: installed: {r.returncode} {r.stderr[-300:]}")
    ST["sha"] = {**SHA, "agent_run.py": "0" * 64}
    r = subprocess.run([b, SETUP_SH, "--url", URL, "--code", "ks_good_code", "--dir", "~/shabad", "--cmd", "fakeagent", "--no-autostart"],
                       env=env, capture_output=True, text=True, timeout=120)
    inst = [os.path.join(agents, d) for d in os.listdir(agents) if d.startswith("shabad-")]
    # the stop undoes the setup (token revoked, the instance folder gone), so nothing of it runs
    check(r.returncode != 0 and "does not match the checksum" in r.stderr and not any(os.path.exists(os.path.join(i, "agent_run.py")) for i in inst),
          f"{b}: #3390 a differing file stops the setup, not installed: {r.returncode} {inst} {r.stderr[-300:]}")
    ST["sha"] = {k: v for k, v in SHA.items() if k != "agent_job.py"}
    r = subprocess.run([b, SETUP_SH, "--url", URL, "--code", "ks_good_code", "--dir", "~/shamiss", "--cmd", "fakeagent", "--no-autostart"],
                       env=env, capture_output=True, text=True, timeout=120)
    check(r.returncode != 0 and "agent_job.py does not match" in r.stderr, f"{b}: #3390 a file without a checksum is refused too: {r.stderr[-300:]}")
    ST["sha"] = None
    shutil.rmtree(home, ignore_errors=True)

# ---- setup.ps1 (dry run with pwsh when there is one)
src = read(SETUP_PS1)
check("param(" in src and "-AtLogOn" in src and "RunLevel Limited" in src and "SetAccessRuleProtection" in src, "setup.ps1: task at logon without admin, file only for the user")
# 2.380 G (#3390): setup.ps1 checks the same checksums (Get-FileHash) before a starter file is moved into place
check("$r.starter_sha256" in src and "Get-FileHash" in src and "ShaOk $name $tmp" in src and "Move-Item -LiteralPath $tmp" in src,
      "setup.ps1: starter files checked against starter_sha256 before they are installed")
PWSH = os.environ.get("PWSH") or shutil.which("pwsh")
if PWSH:
    home = tempfile.mkdtemp(prefix="kalmido-p2440c-ps-")
    r = subprocess.run([PWSH, "-NoProfile", "-File", SETUP_PS1, "-DryRun", "-Url", URL, "-Dir", os.path.join(home, "proj"), "-Cmd", "fakeagent"],
                       env={**os.environ, "PATH": nobin + os.pathsep + os.path.dirname(PWSH), "HOME": home}, capture_output=True, text=True, timeout=120)
    o = r.stdout + r.stderr
    check(r.returncode == 0 and "Connecting to Kalmido" in o and "Starting it at every login" in o and "\\Kalmido\\" in o, f"setup.ps1 -DryRun: {o[-500:]}")
    check(not ST["redeem"] or all(x[1].get("os") != "windows" for x in ST["redeem"]), "setup.ps1 dry run redeems nothing")
    shutil.rmtree(home, ignore_errors=True)
else:
    print("p2440_c_setup: setup.ps1 dry run SKIP (no pwsh)")

srv.shutdown()
shutil.rmtree(tmp, ignore_errors=True)
sys.exit(done("p2440_c_setup"))
