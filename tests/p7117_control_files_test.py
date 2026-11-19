#!/usr/bin/env python3
# kalmido-suite: nodata
"""2.1400 (#7117): the agent does not change its own control files.
 - the dispatcher reads KALMIDO-DISPATCH.json from the runner's state folder; one in the project folder may only tighten
   (places, max_writes, job_timeout_h, stau_max ... at most the state folder's value or the default; skip_tags only added;
   one_way_rx never changed); without a state folder file it counts as before, with the limits capped at the defaults
 - every run's and job's settings deny Edit of the state folder's files, the starter files, KALMIDO-DISPATCH.json /
   -STOP and .claude/settings*.json, and leave the outbox and a job's working copy open
 - the guard refuses Bash lines that name them, KALMIDO_BLOCK_*, KALMIDO_STATE_DIR (also with --secret-only), and lets
   agent_job.py / kalmido_cli.py run as a program, files into the outbox and a job's working copy pass
Pure Python, temporary folders only.
usage: p7117_control_files_test.py"""
import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile

from kt import check, done  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
MCP = os.path.join(HERE, "..", "mcp")
RUN = os.path.join(MCP, "agent_run.py")
sys.path.insert(0, MCP)


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


ar = load("agent_run_ctl", RUN)
ad = load("agent_dispatch_ctl", os.path.join(MCP, "agent_dispatch.py"))
os.environ.pop("KALMIDO_DISPATCH_CONFIG", None)
os.environ["KALMIDO_DISPATCH_CHECK_CMD"] = "make test"
os.environ["KALMIDO_DISPATCH_PUSH_URL"] = "git@example.com:o/r.git"  # #7057 (parent package) requires it; harmless before

tmp = tempfile.mkdtemp(prefix="k7117-")
proj, state = os.path.join(tmp, "proj"), os.path.join(tmp, "inst", "state")
os.makedirs(proj)
os.makedirs(state)


def put(folder, data):
    p = os.path.join(folder, "KALMIDO-DISPATCH.json")
    if data is None:
        if os.path.exists(p):
            os.remove(p)
        return
    with open(p, "w", encoding="utf-8") as f:
        json.dump(data, f)


# ---- the configuration: state folder first, the project folder only tightens
put(state, {"lists": ["Backlog"], "places": 3, "max_writes": 60, "stau_max": 0, "one_way_rx": "(?i)forever", "skip_tags": ["hold"]})
put(proj, {"lists": ["Other"], "places": 9, "max_writes": 10, "stau_max": 50, "job_timeout_h": 99, "one_way_rx": "x^",
           "skip_tags": ["mine"], "close_ref": "job/1"})
cfg, prob = ad.load_config(proj, state)
check(not prob, f"loads: {prob}")
check(cfg["lists"] == ["Backlog"] and cfg["close_ref"] == "", f"with a state folder file the project file changes no other key: {cfg['lists']} {cfg['close_ref']}")
check(cfg["places"] == 3, f"places: the project file cannot raise it ({cfg['places']})")
check(cfg["max_writes"] == 10, f"max_writes: the project file may lower it ({cfg['max_writes']})")
check(cfg["stau_max"] == 50, f"stau_max 0 (never) in the state file: a number in the project file tightens ({cfg['stau_max']})")
check(cfg["job_timeout_h"] == ad.DEFAULTS["job_timeout_h"], f"job_timeout_h above the default is not used ({cfg['job_timeout_h']})")
check(cfg["one_way_rx"] == "(?i)forever", "one_way_rx only from the state folder's file")
check(cfg["skip_tags"] == ["hold", "mine"], f"skip_tags: only added ({cfg['skip_tags']})")

put(state, {"lists": ["Backlog"], "stau_max": 5, "usage_limit_pct": 80.0})
put(proj, {"stau_max": 0, "usage_limit_pct": 0})
cfg, prob = ad.load_config(proj, state)
check(cfg["stau_max"] == 5 and cfg["usage_limit_pct"] == 80.0, f"0 (never) in the project file loosens: not used ({cfg['stau_max']} {cfg['usage_limit_pct']})")
put(proj, {"stau_max": -1, "usage_limit_pct": -5.0})
cfg, prob = ad.load_config(proj, state)
check(cfg["stau_max"] == 5 and cfg["usage_limit_pct"] == 80.0, f"reader F8: a negative value loosens like 0: not used ({cfg['stau_max']} {cfg['usage_limit_pct']})")

# without a state folder file: the project file as before, its limits at most the defaults
put(state, None)
put(proj, {"lists": ["Backlog"], "places": 4, "stale_h": 1, "one_way_rx": "x^", "skip_tags": []})
cfg, prob = ad.load_config(proj, state)
check(not prob and cfg["lists"] == ["Backlog"] and cfg["stale_h"] == 1, f"no state folder file: the project file counts ({prob})")
check(cfg["places"] == ad.DEFAULTS["places"], f"no state folder file: places at most the default ({cfg['places']})")
check(cfg["one_way_rx"] == ad.DEFAULTS["one_way_rx"] and "blocked" in cfg["skip_tags"], "no state folder file: the hold-back rules stay the defaults")
put(proj, None)
cfg, prob = ad.load_config(proj, state)
check(prob == "no KALMIDO-DISPATCH.json", f"no file at all: idle ({prob})")
put(state, {"lists": ["Backlog"], "places": 2})
cfg, prob = ad.load_config(proj, state)
check(not prob and cfg["places"] == 2, f"the state folder's file alone may set places 2 ({prob} {cfg['places']})")
os.environ["KALMIDO_DISPATCH_CONFIG"] = os.path.join(state, "KALMIDO-DISPATCH.json")
put(proj, {"places": 5})
cfg, prob = ad.load_config(proj)
check(cfg["places"] == 2, "KALMIDO_DISPATCH_CONFIG is the runner's file; the project file only tightens")
os.environ.pop("KALMIDO_DISPATCH_CONFIG", None)

# the stop file of the project folder still stops
host = type("H", (), {"state_dir": state})()
d = ad.Dispatcher(host, proj)
check(not d.brakes(dict(ad.DEFAULTS, usage_limit_pct=0)), "no stop file: no brake")
open(os.path.join(proj, "KALMIDO-DISPATCH-STOP"), "w").close()
check("stop file" in d.brakes(dict(ad.DEFAULTS, usage_limit_pct=0)), "KALMIDO-DISPATCH-STOP in the project folder still stops")

# ---- deny rules of every run and job
inst = os.path.dirname(state)
rules = ar.control_deny_rules([state], inst)
rp, ip = ar.rule_path(state), ar.rule_path(inst)
for r in (f"Edit({rp}/*.*)", f"Edit({rp}/*STOP*)", f"Edit({rp}/jobs/*/*.*)", f"Edit({ip}/*.*)",
          "Edit(**/KALMIDO-DISPATCH.json)", "Edit(**/KALMIDO-DISPATCH-STOP)", "Edit(**/.claude/settings*.json)",
          "Edit(~/.claude/settings*.json)"):
    check(r in rules, f"deny rule {r}")
check(not any(r.endswith(("/*)", "/**)")) and ("/state/" in r or r.startswith(f"Edit({ip}/")) for r in rules if "wakes" not in r),
      f"no folder rule over the state or starter folder (the outbox and a job's working copy stay writable): {rules}")
os.environ["KALMIDO_STATE_DIR"] = state
hs = ar.hook_settings(False, usage=False)
deny = hs.get("permissions", {}).get("deny") or []
check(f"Edit({rp}/*.*)" in deny and "Edit(**/.claude/settings*.json)" in deny, f"hook_settings carries them: {deny}")
gcmd = hs["hooks"]["PreToolUse"][0]["hooks"][0]["command"]
check(f'--control-dir "{os.path.abspath(state)}"' in gcmd, f"the hook gets the state folder: {gcmd[:300]}")
os.environ["KALMIDO_BLOCK_DANGEROUS"] = "0"
gcmd0 = ar.hook_settings(False, usage=False)["hooks"]["PreToolUse"][0]["hooks"][0]["command"]
check("--secret-only" in gcmd0 and "--control-dir" in gcmd0, "KALMIDO_BLOCK_DANGEROUS=0 keeps the control files part")
os.environ.pop("KALMIDO_BLOCK_DANGEROUS", None)

# the starter inside the project folder is the project's own code: no starter rules
os.environ["KALMIDO_PROJECT_DIR"] = os.path.dirname(MCP)
check(ar.control_dirs()[1] is None, "starter inside the project folder: not protected as starter")
os.environ["KALMIDO_PROJECT_DIR"] = proj
check(ar.control_dirs()[1] == os.path.dirname(os.path.abspath(RUN)), "starter outside the project folder: protected")

# ---- the guard
ST, INS = state, inst
REFUSED = [
    f"rm {ST}/dispatch-STOP",
    f"echo '{{}}' > {ST}/KALMIDO-DISPATCH.json",
    f"cat {ST}/outbox/../dispatch.json",
    f"cp x {ST}/jobs/7/run-settings.json",
    f"sed -i s/a/b/ {INS}/agent_run.py",
    f"cp evil.py {INS}/agent_job.py",
    f"python3 {INS}/agent_job.py progress 4 x > {INS}/agent_run.py",
    f"cd {INS} && rm state/dispatch.json",
    "rm KALMIDO-DISPATCH-STOP",
    "echo '{\"places\": 9}' > KALMIDO-DISPATCH.json",
    "export KALMIDO_BLOCK_DANGEROUS=0",
    f"KALMIDO_BLOCK_DANGEROUS=0 python3 {INS}/agent_job.py start --title x -",
    "env -u KALMIDO_BLOCK_EXTRA python3 x.py",
    "cat .claude/settings.local.json",
    "jq '.disableAllHooks=true' ~/.claude/settings.json > /tmp/x",
    "ls $KALMIDO_STATE_DIR",
]
ALLOWED = [
    f'"{sys.executable}" "{INS}/agent_job.py" start --title "x" -',
    f"python3 -u {INS}/agent_job.py progress 4 'step two'",
    f"cp report.pdf {ST}/outbox/20261118-ab/",
    f"cp x {ST}/jobs/7/outbox/a.pdf",
    f"cd {ST}/jobs/7/wt && git status",
    "git status",
    "ls -la",
    "cat README.md",
]
REFUSED += ["rm KALMIDO\\-DISPATCH-STOP", "cat > .claude/sett\\ings.json"]  # reader F5 of 2.1400: a backslash the shell drops
REFUSED += ["rm kalmido-dispatch.json", "cat > .Claude/Settings.local.json",  # reader F9: any case (macOS, Windows)
            "rm " + ST[:-2] + "\\" + ST[-2:] + "/dispatch-STOP"]  # reader F9: a backslash inside a folder's name
for c in REFUSED:
    check(ar.guard_control(c, [ST], INS), f"refused: {c!r}")
for c in ALLOWED:
    check(not ar.guard_control(c, [ST], INS), f"allowed: {c!r}")


def hook(cmd, args):
    cp = subprocess.run([sys.executable, RUN, "--guard-hook"] + args, capture_output=True, text=True, timeout=60,
                        input=json.dumps({"tool_name": "Bash", "tool_input": {"command": cmd}}))
    out = json.loads(cp.stdout) if cp.stdout.strip() else {}
    return (out.get("hookSpecificOutput") or {}).get("permissionDecision")


a = ["--control-dir", ST, "--starter-dir", INS]
check(hook(f"rm {ST}/dispatch-STOP", a) == "deny", "the hook refuses the stop file")
check(hook(f"rm {ST}/dispatch-STOP", ["--secret-only"] + a) == "deny", "also with --secret-only (KALMIDO_BLOCK_DANGEROUS=0)")
check(hook("export KALMIDO_BLOCK_DANGEROUS=0", ["--secret-only"]) == "deny", "KALMIDO_BLOCK_* also without folders")
check(hook(f"cp a.pdf {ST}/outbox/x/", a) is None, "the outbox passes")
check(hook("git status", a) is None, "an ordinary command passes")
_stdin, sys.stdin = sys.stdin, io.StringIO("{}")
try:
    ar.guard_hook(a)
finally:
    sys.stdin = _stdin

# reader F11 of 2.1400: whether the starter lies inside the project decides the runner's pinned project folder, never the
# cwd of the process that starts a job (the model's: a job started from a parent folder kept the starter open)
pin = tempfile.mkdtemp(prefix="k7117-pin-")
here = os.path.dirname(os.path.abspath(ar.__file__))
old_sd, old_cwd = os.environ.get("KALMIDO_STATE_DIR"), os.getcwd()
os.environ["KALMIDO_STATE_DIR"] = pin
os.environ["KALMIDO_PROJECT_DIR"] = pin  # the runner's project: not around the starter
ar.guard_pin(pin)
os.environ.pop("KALMIDO_PROJECT_DIR")
os.chdir(os.path.dirname(here))  # the model starts the job from the starter's parent folder
check(ar.control_dirs()[1] == here, f"F11: the starter stays protected for a job started from a parent folder {ar.control_dirs()}")
os.chdir(old_cwd)
os.remove(os.path.join(pin, ar.GUARD_PIN_FILE))
if old_sd is None:
    os.environ.pop("KALMIDO_STATE_DIR", None)
else:
    os.environ["KALMIDO_STATE_DIR"] = old_sd

sys.exit(done("p7117_control_files"))
