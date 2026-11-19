#!/usr/bin/env python3
# kalmido-suite: nodata
"""2.1400 (#7116): the project's own block list of the starter's guard (KALMIDO_BLOCK_EXTRA in the runner's env file).
 - hosts (ssh / scp / rsync / sftp / mosh targets, user@host, host:path, host.domain, -J host), commands (a program and its
   words in order) and paths are refused, with the same parsing as the fixed list (sh -c, $( ), sudo in front)
 - echo / grep text and git messages that only name a host stay allowed; other hosts and commands stay allowed
 - the per-run settings carry the list on the hook's command line (--block-extra) and the paths as Read / Edit deny
 - the hook reads the list only from its command line, never from the environment of the model's process
 - the list holds also with KALMIDO_BLOCK_DANGEROUS=0 (--secret-only): only the fixed list is off then
Pure Python, invented names only.
usage: p7116_block_extra_test.py"""
import importlib.util
import io
import json
import os
import subprocess
import sys

from kt import check, done  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
RUN = os.path.join(HERE, "..", "mcp", "agent_run.py")
spec = importlib.util.spec_from_file_location("agent_run_block", RUN)
ar = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ar)

LIST = "host:shop-live, host:db?.example.net, cmd:deploy.sh, cmd:git push origin production, cmd:make release, path:~/.ssh, path:.env*"
os.environ["KALMIDO_BLOCK_EXTRA"] = LIST
os.environ.pop("KALMIDO_BLOCK_DANGEROUS", None)

REFUSED = [
    "ssh shop-live uptime",
    "ssh -p 2222 admin@shop-live 'systemctl status app'",
    "scp dump.sql root@shop-live:/tmp/",
    "rsync -az ./dist/ deploy@shop-live.example.com:/srv/app",
    "sftp shop-live",
    "mosh shop-live",
    "ssh -J shop-live inner ls",
    "ssh -o ProxyJump=shop-live inner ls",
    "psql -h db1.example.net app",
    "git clone shop-live:repo.git",
    "./deploy.sh",
    "bash scripts/deploy.sh --now",
    "sudo -u web ./deploy.sh",
    "git push origin production",
    "git push -u origin production",
    "make release",
    "echo ok && make release",
    "echo $(ssh shop-live id)",
    "sh -c 'ssh shop-live reboot-app'",
    "timeout 60 ssh shop-live true",
    "cat ~/.ssh/id_ed25519",
    "cat $HOME/.ssh/config",
    "grep KEY .env.production",
    "cp config/.env ./x",
]
ALLOWED = [
    "echo shop-live",
    "git commit -m 'deploy fix for shop-live'",
    "grep -r shop-live docs/",
    "ssh staging-box uptime",
    "git push origin main",
    "git push -u origin job/12",
    "make test",
    "./build.sh",
    "node -e 'console.log(process.env.HOME)'",
    "ls src/",
    "cat README.md",
]


def why(cmd):
    return ar.guard_reason(cmd) or ar.block_path(cmd)


for c in REFUSED:
    check(why(c), f"refused: {c!r}")
for c in ALLOWED:
    check(not why(c), f"allowed: {c!r} ({why(c)})")

p = ar.block_extra_parse("shop-live, deploy now, ./secrets, ~/.aws")
check(p == {"host": ["shop-live"], "cmd": [["deploy", "now"]], "path": ["./secrets", "~/.aws"]}, f"items without a prefix: {p}")

# ---- the per-run settings: the list on the hook's command line, the paths as deny rules
hs = ar.hook_settings(False, usage=False)
gcmd = hs["hooks"]["PreToolUse"][0]["hooks"][0]["command"]
check("--block-extra " + LIST.encode().hex() in gcmd, f"the hook gets the list on its command line: {gcmd[:200]}")
deny = hs.get("permissions", {}).get("deny") or []
check({"Read(~/.ssh)", "Read(~/.ssh/**)", "Edit(~/.ssh/**)", "Read(**/.env*)", "Edit(**/.env*)"} <= set(deny), f"paths as deny rules: {deny}")
os.environ["KALMIDO_BLOCK_DANGEROUS"] = "0"
gcmd0 = ar.hook_settings(False, usage=False)["hooks"]["PreToolUse"][0]["hooks"][0]["command"]
check("--secret-only" in gcmd0 and "--block-extra" in gcmd0, f"KALMIDO_BLOCK_DANGEROUS=0 keeps the project's list: {gcmd0[:200]}")
os.environ.pop("KALMIDO_BLOCK_DANGEROUS", None)

# reader F4 of 2.1400: a job the agent starts itself reads the runner's pinned switches, never only the environment its
# model's process left (unset KALMIDO_BLOCK_EXTRA, KALMIDO_BLOCK_DANGEROUS=0)
import tempfile  # noqa: E402
pin_dir = tempfile.mkdtemp(prefix="kalmido-pin-")
os.environ["KALMIDO_BLOCK_EXTRA"] = LIST
ar.guard_pin(pin_dir)
old_sd = os.environ.get("KALMIDO_STATE_DIR")
os.environ["KALMIDO_STATE_DIR"] = pin_dir
os.environ.pop("KALMIDO_BLOCK_EXTRA", None)
os.environ["KALMIDO_BLOCK_DANGEROUS"] = "0"
gcmdj = ar.hook_settings(False, usage=False)["hooks"]["PreToolUse"][0]["hooks"][0]["command"]
check("--block-extra " + LIST.encode().hex() in gcmdj and "--secret-only" not in gcmdj,
      f"F4: the runner's pinned list and guard hold for a job whose environment dropped them: {gcmdj[:200]}")
check(ar.block_extra()["path"], "F4: the pinned paths count for the deny rules too")
os.environ.pop("KALMIDO_BLOCK_DANGEROUS", None)
os.remove(os.path.join(pin_dir, ar.GUARD_PIN_FILE))
if old_sd is None:
    os.environ.pop("KALMIDO_STATE_DIR", None)
else:
    os.environ["KALMIDO_STATE_DIR"] = old_sd
os.environ["KALMIDO_BLOCK_EXTRA"] = LIST


# ---- the hook as Claude Code starts it: the list only from its command line
def hook(cmd, args, env_extra=None):
    env = dict(os.environ)
    env.pop("KALMIDO_BLOCK_EXTRA", None)
    if env_extra is not None:
        env["KALMIDO_BLOCK_EXTRA"] = env_extra
    cp = subprocess.run([sys.executable, RUN, "--guard-hook"] + args, env=env, capture_output=True, text=True, timeout=60,
                        input=json.dumps({"tool_name": "Bash", "tool_input": {"command": cmd}}))
    out = json.loads(cp.stdout) if cp.stdout.strip() else {}
    return (out.get("hookSpecificOutput") or {}).get("permissionDecision")


hx = ["--block-extra", LIST.encode().hex()]
check(hook("ssh shop-live ls", hx) == "deny", "the hook refuses a host of its list")
check(hook("ssh shop-live ls", ["--secret-only"] + hx) == "deny", "the list holds with --secret-only (KALMIDO_BLOCK_DANGEROUS=0)")
check(hook("git push -f", ["--secret-only"] + hx) is None, "--secret-only: the fixed list is off")
check(hook("git push -f", hx) == "deny", "without --secret-only the fixed list is on next to the project's list")
check(hook("cat ~/.ssh/id_rsa", ["--secret-only"] + hx) == "deny", "a path of the list, also with --secret-only")
check(hook("ssh shop-live ls", [], env_extra="host:shop-live") is None,
      "the hook never takes the list from the environment (the model's process could set or clear it)")
check(hook("ssh anything ls", ["--block-extra", "zz"]) == "deny", "a damaged list refuses (fail closed)")
check(hook("ssh other ls", hx) is None, "a host not on the list passes")

# guard_reason itself is unchanged after a hook call in the same process (globals restored)
_stdin, sys.stdin = sys.stdin, io.StringIO("{}")
try:
    ar.guard_hook(["--secret-only", "--block-extra", "00"])
finally:
    sys.stdin = _stdin
check(ar.GUARD_FIXED is True and ar.GUARD_EXTRA is None, "guard_hook restores its globals")

sys.exit(done("p7116_block_extra"))
