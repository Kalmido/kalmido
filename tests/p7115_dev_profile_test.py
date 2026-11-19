#!/usr/bin/env python3
# kalmido-suite: nodata
"""2.1400 (#7115): a third rights profile "Programming agent" (dev) next to hardened and standard, chosen in the
one-command setup (setup.sh --profile, setup.ps1 -RightsProfile, the dialog's "Rights profile").
 - mcp/agent_profiles.json (a starter file) has hardened / standard / dev; dev allows the project folder, git without
   pushing main, build and test commands, and denies force-push, tags, prune, sudo, ssh, curl, the secret paths, .env*,
   the Claude Code settings and the agent's control files; no rule is allowed and denied at once
 - the harden step of setup.sh writes allow / deny / defaultMode into .claude/settings.local.json (twice = nothing twice),
   adds KALMIDO_BLOCK_EXTRA to the env file only when it has none, and stops cleanly without the profile file
 - setup.sh refuses an unknown profile and names the profile in a dry run; setup.ps1 and agentsetup.js offer the same
 - the dialog's texts are translated
Temporary folders only, no server.
usage: p7115_dev_profile_test.py"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

from kt import check, done  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")


def rd(*p):
    with open(os.path.join(ROOT, *p), encoding="utf-8") as f:
        return f.read()


prof = json.loads(rd("mcp", "agent_profiles.json"))["profiles"]
check(set(prof) == {"hardened", "standard", "dev"}, f"three profiles: {sorted(prof)}")
check("agent_profiles.json" in rd("mcp", "starter_files.txt").split(), "agent_profiles.json is a starter file")
dev = prof["dev"]
check(dev["defaultMode"] == "default" and prof["hardened"]["defaultMode"] == "dontAsk", "modes")
for r in ("Edit(./**)", "Read(./**)", "{job}", "Bash(git commit:*)", "Bash(make:*)",
          "Bash(npm test:*)", "Bash(pytest:*)", "mcp__kalmido"):
    check(r in dev["allow"], f"dev allows {r}")
# reader F1 / F2 of 2.1400: no push is allowed without asking (a prefix rule job/... also let job/1:main through), and no
# general program starter or git command that runs another program (npx, pnpm / yarn of anything, bundle exec of anything,
# git fetch --upload-pack, git rebase --exec, git grep -O)
check(not [a for a in dev["allow"] if "git push" in a], f"F1: dev allows no git push without asking {[a for a in dev['allow'] if 'push' in a]}")
for r in ("Bash(npx:*)", "Bash(pnpm:*)", "Bash(yarn:*)", "Bash(bundle exec:*)", "Bash(composer:*)", "Bash(mvn:*)", "Bash(gradle:*)",
          "Bash(./gradlew:*)", "Bash(git fetch:*)", "Bash(git rebase:*)", "Bash(git grep:*)"):
    check(r not in dev["allow"], f"F2: dev does not allow the general starter {r}")
for r in ("Bash(find:*)", "Bash(rg:*)"):  # reader F10: find -exec, rg --pre
    check(r not in dev["allow"], f"F10: dev does not allow {r}")
check({"Edit(./.git/**)", "Edit(**/.git/hooks/**)", "Edit(**/.git/config)"} <= set(dev["deny"]), "F10: dev never edits .git (hooks, config)")
# reader round 3 F4: every secret place the dev profile closes to Read is in its block list too (grep / head / tail in Bash)
home_reads = {re.sub(r"/\*\*$", "", r[5:-1]) for r in dev["deny"] if r.startswith("Read(~/")}
listed = {x.strip()[5:] for x in dev["block_extra"].split(",") if x.strip().startswith("path:")}
check(home_reads <= listed, f"F4: block_extra covers every Read-denied secret place: missing {sorted(home_reads - listed)}")
for r in ("Bash(git push --force:*)", "Bash(git push -f:*)", "Bash(git push origin main:*)", "Bash(git tag:*)",
          "Bash(docker system prune:*)", "Bash(sudo:*)", "Bash(reboot:*)", "Bash(ssh:*)", "Bash(curl:*)", "Read(~/.ssh/**)",
          "Read(~/.aws/**)", "Read(~/.config/gh/**)", "Read(**/.env*)", "Edit(**/.claude/settings*.json)",
          "Edit(**/KALMIDO-DISPATCH.json)", "Edit(**/KALMIDO-DISPATCH-STOP)", "Edit({inst}/*.*)", "Edit({inst}/state/*.*)"):
    check(r in dev["deny"], f"dev denies {r}")
for name, p in prof.items():
    both = set(p.get("allow") or []) & set(p.get("deny") or [])
    check(not both, f"{name}: no rule allowed and denied at once {both}")
    check(not any(re.search(r"push (-f|--force)|git tag|sudo|ssh", a) for a in p.get("allow") or []), f"{name}: nothing dangerous allowed")
check(all(a.startswith(("mcp__", "Read(", "Edit(", "Bash(", "{job}")) for a in dev["allow"]), "allow rules are rule strings")
check("path:~/.ssh" in dev["block_extra"] and "path:.env*" in dev["block_extra"], "dev brings a block list with the secret paths")

# ---- the harden step of setup.sh, run as it is
sh = rd("static", "agent", "setup.sh")
m = re.search(r"# kalmido-setup-step: harden.*?<<'PYEOF'\n(.*?)\nPYEOF", sh, re.S)
check(m is not None, "setup.sh: harden step found")
code = m.group(1) if m else ""
tmp = tempfile.mkdtemp(prefix="k7115-")
inst, proj = os.path.join(tmp, "inst"), os.path.join(tmp, "proj")
os.makedirs(inst)
os.makedirs(proj)
shutil.copy(os.path.join(ROOT, "mcp", "agent_profiles.json"), inst)
envf = os.path.join(inst, "kalmido-agent.env")
with open(envf, "w", encoding="utf-8") as f:
    f.write("KALMIDO_URL=https://k.example.com\n")
hset = os.path.join(proj, ".claude", "settings.local.json")


def harden(profile, inst_dir=inst):
    return subprocess.run([sys.executable, "-c", code, hset, envf, profile, inst_dir, "/usr/bin/python3"],
                          capture_output=True, text=True, timeout=60).returncode


check(harden("dev") == 0, "harden with dev")
d = json.load(open(hset, encoding="utf-8"))
perm = d["permissions"]
check(perm.get("defaultMode") == "default", f"defaultMode set: {perm.get('defaultMode')}")
check("Bash(git commit:*)" in perm["allow"] and "Edit(./**)" in perm["allow"], "allow rules written")
check(f'Bash("/usr/bin/python3" "{os.path.abspath(inst)}/agent_job.py":*)' in perm["allow"], f"the job tool with this instance's path: {perm['allow'][:5]}")
check("Bash(git push --force:*)" in perm["deny"] and "WebFetch" in perm["deny"] and f"Edit(/{os.path.abspath(envf)})" in perm["deny"],
      "deny rules: the profile's and the env file's")
check(f"Edit(/{os.path.abspath(inst)}/*.*)" in perm["deny"], "{inst} filled in as a rule path")
check(not any("{" in r for r in perm["allow"] + perm["deny"]), "no placeholder left")
env1 = open(envf, encoding="utf-8").read()
check(env1.count("KALMIDO_BLOCK_EXTRA=") == 1 and "path:~/.ssh" in env1, f"env file got the block list: {env1}")
n = (len(perm["allow"]), len(perm["deny"]))
check(harden("dev") == 0, "a second run")
perm2 = json.load(open(hset, encoding="utf-8"))["permissions"]
check((len(perm2["allow"]), len(perm2["deny"])) == n and open(envf, encoding="utf-8").read() == env1, "a second run adds nothing twice")

with open(envf, "w", encoding="utf-8") as f:
    f.write("KALMIDO_URL=https://k.example.com\nKALMIDO_BLOCK_EXTRA='host:shop-live'\n")
check(harden("dev") == 0 and "path:~/.ssh" not in open(envf, encoding="utf-8").read(), "the person's own KALMIDO_BLOCK_EXTRA is never replaced")
os.remove(hset)
check(harden("") == 0, "no profile: only the deny rules")
perm3 = json.load(open(hset, encoding="utf-8"))["permissions"]
check("allow" not in perm3 and "defaultMode" not in perm3 and "WebFetch" in perm3["deny"], f"no profile: as before {perm3}")
os.remove(hset)
check(harden("dev", os.path.join(tmp, "nowhere")) == 4, "no profile file: exit 4 (told)")
perm4 = json.load(open(hset, encoding="utf-8"))["permissions"]
check("WebFetch" in perm4["deny"] and "allow" not in perm4, f"reader F12: without the profile file the basic deny rules are written all the same {perm4}")
with open(hset, "w", encoding="utf-8") as f:
    f.write("{not json")
check(harden("dev") == 3, "invalid settings file: exit 3")

# ---- setup.sh options
SETUP = os.path.join(ROOT, "static", "agent", "setup.sh")
cp = subprocess.run(["bash", SETUP, "--dry-run", "--url", "https://k.example.com", "--dir", proj, "--tool", "claude", "--cmd", "true",
                     "--profile", "bogus", "--lang", "en"], capture_output=True, text=True, timeout=120)
check(cp.returncode != 0 and "unknown rights profile bogus" in cp.stdout + cp.stderr, f"unknown profile refused: {cp.returncode} {cp.stderr[-300:]}")
cp = subprocess.run(["bash", SETUP, "--dry-run", "--url", "https://k.example.com", "--dir", proj, "--tool", "claude", "--cmd", "true",
                     "--profile", "dev", "--lang", "en", "--no-autostart"], capture_output=True, text=True, timeout=120)
check("write rights profile dev into" in cp.stdout + cp.stderr, f"dry run names the profile: {(cp.stdout + cp.stderr)[-600:]}")
for lang in ("de", "en", "es", "fr", "it", "nl"):
    body = sh[sh.index(f"msg_{lang}() {{"):]
    body = body[:body.index("\n}\n")]
    for k in ("badprof", "prof_ok", "dry_prof", "prof_nofile", "prof_codex"):
        check(f"    {k}) echo" in body, f"setup.sh {lang}: {k}")

# ---- setup.ps1 and the dialog
ps = rd("static", "agent", "setup.ps1")
check("[string]$RightsProfile = ''" in ps and "'agent_profiles.json'" in ps and "KALMIDO_BLOCK_EXTRA=" in ps, "setup.ps1: -RightsProfile, the profile file, the block list")
for var in ("MsgEn", "MsgDe", "MsgEs", "MsgFr", "MsgIt", "MsgNl"):
    body = ps[ps.index(f"${var} = @{{"):]
    body = body[:body.index("\n}")]
    for k in ("badprof", "prof_ok", "dry_prof", "prof_nofile", "prof_codex"):
        check(f"  {k} = '" in body, f"setup.ps1 {var}: {k}")
js = rd("static", "js", "agentsetup.js")
check("['dev', N_('Programming agent')]" in js and "' --profile ' + pf" in js and "' -RightsProfile ' + pf" in js,
      "agentsetup.js: the dialog offers the profile and puts it into the command")
TEXTS = ["Rights profile", "Deny rules only", "Hardened (Kalmido tools only)", "Standard (+ notes and jobs)", "Programming agent"]
for code_ in ("de", "es", "fr", "it", "nl"):
    tr = json.loads(rd("static", "i18n", f"{code_}.json"))
    check(all(tr.get(t) for t in TEXTS), f"{code_}: the dialog's texts translated")
check("--profile hardened|standard|dev" in rd("docs", "AGENT-SETUP.md") and "agent_profiles.json" in rd("docs", "AGENT-SETUP.md"), "AGENT-SETUP.md documents it")

shutil.rmtree(tmp, ignore_errors=True)
sys.exit(done("p7115_dev_profile"))
