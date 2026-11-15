#!/usr/bin/env python3
# kalmido-suite: nodata
"""#6253 (decision 15.11.2026): the train's release push ("X.Y.Z: Live-Zug (...)") runs the stage "release" = Lint,
scanners, semgrep, e-invoice, ZAP + the hard test groups only (tests/hard_suites.txt); the soft suites run in the nightly
full run and by hand. Without a server (CI Lint):
- tests/stages.py: the release push on main = stage "release", its groups are the hard groups; [full], hotfix, nightly and
  by-hand runs stay full; a queue push keeps "none", a push on main keeps the push stage;
- ci.yml: the plan keeps the stage release and cuts it like the queue stage, every shard of it is "hart" (the name the live
  train waits for, kalmido-livezug.py SG_HART_NAME_RE);
- tools/ci_gate.py: a green release-stage run counts like a green full run for the image; a red one is soft when only soft
  suites are red inside its hard shards (judged by suite, like the merge queue gate), never when a hard suite is red or a
  hard shard was cut; release.yml waits at most 150 min (was 250)."""
import importlib.util
import os
import re
import subprocess
import sys
import tempfile

N = os.path.dirname(os.path.abspath(__file__))
R = os.path.join(N, "..")
sys.path.insert(0, N)
from kt import FAILS, OKS, check  # noqa: E402
import stages  # noqa: E402

spec = importlib.util.spec_from_file_location("ci_gate", os.path.join(R, "tools", "ci_gate.py"))
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)


def read(*p):
    with open(os.path.join(R, *p), encoding="utf-8") as f:
        return f.read()


KEYS = ("GITHUB_EVENT_NAME", "GITHUB_REF", "CI_BEFORE", "CI_MESSAGE", "CI_INPUT_STAGE", "CI_QUEUE_RUN", "CI_BASE_SHA")


def ci_base(env):
    keep = {k: os.environ.get(k) for k in KEYS}
    try:
        for k in KEYS:
            os.environ.pop(k, None)
        os.environ.update(env)
        return stages.ci_base()
    finally:
        for k, v in keep.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


# ---- 1. tests/stages.py
head = subprocess.run(["git", "-C", R, "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip() or "1" * 40
ZUG = "2.1226.0: Live-Zug (Paket 2.1198, Paket 2.1205, Paket 2.1210)"
push = {"GITHUB_EVENT_NAME": "push", "GITHUB_REF": "refs/heads/main", "CI_BEFORE": head, "CI_MESSAGE": ZUG}
st, why, base = ci_base(push)
check(st == "release" and base is None, "the train's release push = stage release (%s, %s)" % (st, why))
st, _, _ = ci_base(dict(push, CI_QUEUE_RUN="43560000001"))
check(st == "release", "a release push with a merge_group run of the same SHA stays release, never none (%s)" % st)
st, _, _ = ci_base(dict(push, CI_MESSAGE=ZUG + " [full]"))
check(st == "full", "[full] in the message still asks for the full run (%s)" % st)
st, _, _ = ci_base(dict(push, GITHUB_REF="refs/heads/hotfix/2.1226.1"))
check(st == "full", "a hotfix push with the train's message stays full (fast lane) (%s)" % st)
st, _, _ = ci_base(dict(push, GITHUB_EVENT_NAME="schedule"))
check(st == "full", "the nightly run stays full (%s)" % st)
st, _, _ = ci_base(dict(push, GITHUB_EVENT_NAME="workflow_dispatch"))
check(st == "full", "a run by hand stays full (%s)" % st)
st, _, _ = ci_base(dict(push, CI_MESSAGE="Merge zug/2.1226.0 back into main (#3507: Push v2.1226.0)"))
check(st is None, "the merge back of the train's branch is an ordinary push (%s)" % st)
st, _, _ = ci_base(dict(push, CI_MESSAGE="#6253: lean release push (job/4688)", CI_QUEUE_RUN="43560000002"))
check(st == "none", "a push from the merge queue keeps the stage none (%s)" % st)

repo = stages.Repo(stages.ROOT, os.path.join(N, "run_all.sh"))
hard = stages.hard_groups(repo)
check(len(hard) > 0 and len(hard) < len(repo.first), "the hard groups are a part of all groups (%d of %d)" % (len(hard), len(repo.first)))
env = {k: v for k, v in os.environ.items() if k not in KEYS}
env.update(push)
with tempfile.TemporaryDirectory() as td:
    gout = os.path.join(td, "groups.txt")
    out = subprocess.run([sys.executable, os.path.join(N, "stages.py"), "--ci", "--groups-out", gout],
                         capture_output=True, text=True, env=env, cwd=R).stdout
    check("stage=release" in out.splitlines(), "stages.py --ci prints stage=release for the release push (%s)" % out.strip()[:200])
    with open(gout, encoding="utf-8") as f:
        got = {ln.strip() for ln in f if ln.strip()}
    want = {repo.first[g] for g in hard}
    check(got == want, "--groups-out lists exactly the hard groups (%d, want %d)" % (len(got), len(want)))
    soft = [s for g, s, _ in repo.rows if g not in hard]
    check(soft and not (set(soft) & got), "no soft group in the release stage (e.g. %s)" % (soft[:1],))
    gout2 = os.path.join(td, "none.txt")
    out = subprocess.run([sys.executable, os.path.join(N, "stages.py"), "--ci", "--groups-out", gout2],
                         capture_output=True, text=True, env=dict(env, GITHUB_EVENT_NAME="schedule"), cwd=R).stdout
    check("stage=full" in out.splitlines() and os.path.getsize(gout2) == 0, "the nightly run: stage full, no group list")

# ---- 2. ci.yml
ci = read(".github", "workflows", "ci.yml")
check('[ "$stage" = release ] ||' in ci and "stage=full  # #5787" in ci, "ci.yml plan keeps the stage release")
check('if [ "$stage" = release ] && ! [ -s /tmp/push-groups.txt ]; then stage=full' in ci, "ci.yml: release without groups = the full run")
check('[ "$stage" = queue ] || [ "$stage" = release ]; then' in ci, "ci.yml: the release stage is cut like the queue stage (--only the groups)")
check('test "$h" -le "$n" || h=0' in ci and 'test "$h" -lt "$n" || h=0' not in ci,
      "ci.yml: all shards hard keeps the hard mark (\"release hart\" names)")
check('if [ "$stage" = full ]; then par=$FULL_PARALLEL; lim=60; else par=$n; lim=90; fi' in ci, "ci.yml: the release stage runs all its shards at once")
check("Test suites ${{ matrix.shard }}/${{ needs.plan.outputs.count }} ${{ needs.plan.outputs.stage }}${{ matrix.hart }}" in ci,
      "ci.yml: the shard name carries the stage and the hard mark")
for job in ("einvoice", "zap", "semgrep", "checks"):
    m = re.search(r"^  " + job + r":\n((?:    .*\n|\n)+)", ci, re.M)
    body = m.group(1) if m else ""
    ifl = re.search(r"^    if: (.*)$", body, re.M)
    check(m is not None and (ifl is None or ("schedule" not in ifl.group(1) and "Live-Zug" not in ifl.group(1))),
          "ci.yml: %s still runs on the release push (%s)" % (job, ifl.group(1) if ifl else "no if"))
# the shard plan of the release stage: every shard is hard (tools/shards.py --only the hard groups)
with tempfile.TemporaryDirectory() as td:
    gl = os.path.join(td, "g.txt")
    with open(gl, "w", encoding="utf-8") as f:
        f.writelines(repo.first[g] + "\n" for g in sorted(hard))
    plan = subprocess.run([sys.executable, os.path.join(R, "tools", "shards.py"), "--shards", "20", "--target-min", "15",
                           "--hard-target-min", "9", "--only", gl, "--assign"], capture_output=True, text=True, cwd=R).stdout
    n = max((int(ln.split()[1]) for ln in plan.splitlines() if ln and not ln.startswith("#") and len(ln.split()) > 1), default=0)
    hm = re.search(r"^# hard (\d+)$", plan, re.M)
    h = int(hm.group(1)) if hm else 0
    check(n >= 1 and h == n, "the release plan: every shard is a hard one (%d hard of %d)" % (h, n))

# ---- 3. tools/ci_gate.py (image / release)
REL = ["Shard plan (stage, suite times of the last runs)", "Test suites 1/8 release hart (API, UI, security)", "Lint, i18n, scanners"]
check(gate.stage(REL) == "release", "ci_gate.stage: a release-stage run (%s)" % gate.stage(REL))
check(gate.stage(["Test suites 1/20 full hart (API, UI, security)"]) == "full", "ci_gate.stage: full stays full")


def run(i, status="completed", conclusion="success"):
    return {"id": i, "status": status, "conclusion": conclusion if status == "completed" else None}


res, txt = gate.decide([run(1)], lambda rid: REL)
check(res == "green" and "release" in txt, "a green release-stage run = image (%s, %s)" % (res, txt))
res, txt = gate.decide([run(1)], lambda rid: ["Test suites 1/6 push (API, UI, security)"])
check(res == "red", "a green push-stage run is still no release (%s)" % res)
res, txt = gate.decide_tree("red", "x", [{"id": 5, "head_sha": "a" * 40}], lambda rid: REL)
check(res == "green", "a green release-stage run on the same tree counts (%s)" % res)

PATS = ["*invoice*", "*restore*", "*login*", "*bandit*", "*audit*", "*zap*", "*owasp*"]
GRP = {"p1_invoice_api": "p1_invoice_api", "p1_invoice_ui": "p1_invoice_api", "p2_restore_api": "p2_restore_api"}


def job(i, name, conclusion="success"):
    return {"id": i, "name": name, "status": "completed", "conclusion": conclusion, "steps": []}


def rel_jobs(c2="success", c3="success"):
    return [job(1, "Shard plan (stage, suite times of the last runs)"), job(2, "Test suites 1/2 release hart (API, UI, security)", c2),
            job(3, "Test suites 2/2 release hart (API, UI, security)", c3), job(4, "Lint, i18n, scanners"),
            job(5, "Test suites (API, UI, security)", "failure" if "failure" in (c2, c3) else "success")]


def suites(m):
    return lambda j: m.get(j["id"], [])


ok, txt, info = gate.judge_soft(rel_jobs(c2="failure"), suites({2: ["p1_invoice_ui"]}), ["*invoice_api*"], GRP)
check(ok and info["suites"] == ["p1_invoice_ui"], "release: a soft suite red in a hard shard (hard group, soft name) = soft go (%s)" % txt)
ok, txt, _ = gate.judge_soft(rel_jobs(c2="failure"), suites({2: ["p1_invoice_api"]}), PATS, GRP)
check(not ok and "p1_invoice_api" in txt, "release: a hard suite red = no image (%s)" % txt)
ok, txt, _ = gate.judge_soft(rel_jobs(c3="cancelled"), suites({}), PATS, GRP)
check(not ok and "hard shard" in txt, "release: a hard shard cut before its end = no image (%s)" % txt)
ok, txt, _ = gate.judge_soft(rel_jobs(c2="failure"), suites({}), PATS, GRP)
check(not ok and "without a named suite" in txt, "release: a red hard shard without a named suite = hard (%s)" % txt)
ok, txt, _ = gate.judge_soft(rel_jobs(c2="failure"), suites({2: ["p1_invoice_ui", gate.STOPPED]}), ["*invoice_api*"], GRP)
check(not ok and "red streak" in txt, "release: a hard shard stopped after a red streak = hard (%s)" % txt)
ok, txt, _ = gate.judge_soft(rel_jobs(c2="failure"), suites({2: ["p1_invoice_ui"] * gate.ANN_MAX}), ["*invoice_api*"], GRP)
check(not ok and "maybe more" in txt, "release: as many red suites as GitHub names = unknown = hard (%s)" % txt)
mixed = rel_jobs() + [job(9, "Test suites 3/3 full (API, UI, security)", "failure")]
ok, txt, _ = gate.judge_soft(mixed, suites({9: ["x_ui"]}), PATS, GRP)
check(not ok and "stage" in txt, "a run with two stages is unknown = hard (%s)" % txt)
# the full stage keeps its rule: a red hard shard = no image, whatever suite
full = [dict(j, name=j["name"].replace(" release ", " full ")) for j in rel_jobs(c2="failure")]
ok, txt, _ = gate.judge_soft(full, suites({2: ["p1_invoice_ui"]}), ["*invoice_api*"], GRP)
check(not ok and "hard shard" in txt, "full stage: a red hard shard stays no image (%s)" % txt)

rel = read(".github", "workflows", "release.yml")
g = re.search(r"^  ci-gate:\n((?:    .*\n|\n)+)", rel, re.M)
gtxt = g.group(1) if g else ""
check(re.search(r"^    timeout-minutes: 150$", gtxt, re.M) is not None, "release.yml: ci-gate holds its runner at most 150 min")
check("--timeout-min 120" in gtxt and "--timeout-min 240" not in gtxt, "release.yml: ci_gate.py waits at most 120 min")

print("p6253_release_stage: %d ok, %d failed" % (OKS[0], len(FAILS)))
sys.exit(1 if FAILS else 0)
