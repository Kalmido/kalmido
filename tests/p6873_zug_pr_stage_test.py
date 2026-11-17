#!/usr/bin/env python3
# kalmido-suite: nodata
"""#6873 (decision 17.11.2026 10:43, mark zug-pr-6853): the train's version commit ("X.Y.Z: Live-Zug (...)") comes as its own
pull request through the merge queue. Without a server (CI Lint):
- tests/stages.py: its merge_group entry runs the stage "release" (the hard groups) - only when the head commit's subject
  starts with "X.Y.Z: Live-Zug (", never for an entry that names it elsewhere; the landing push of that commit (CI_QUEUE_RUN
  found) runs "none"; without CI_QUEUE_RUN (API, direct push) the release push keeps "release" (the fallback);
- tools/ci_gate.py judge_queue: shards "Test suites N/M release hart" count as the entry's shards (green / hard red / missing);
- tools/ci_gate.py decide: on the tagged SHA a green push run of stage none + a green merge_group run of stage release = the
  image; the none run alone = no image;
- ci.yml: the comments say the version commit goes through the queue."""
import importlib.util
import os
import subprocess
import sys
import tempfile

N = os.path.dirname(os.path.abspath(__file__))
R = os.path.abspath(os.path.join(N, ".."))
sys.path.insert(0, N)
from kt import check, done  # noqa: E402
import stages  # noqa: E402

spec = importlib.util.spec_from_file_location("ci_gate", os.path.join(R, "tools", "ci_gate.py"))
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)

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
ZUG = "2.1352.0: Live-Zug (Paket 2.1352, Paket 2.1340)"
mg = {"GITHUB_EVENT_NAME": "merge_group", "CI_BASE_SHA": head, "CI_MESSAGE": ZUG + "\n\nversion + cache"}
st, why, base = ci_base(mg)
check(st == "release" and base is None,
      "the version pull request in the queue = stage release (%s, %s)" % (st, why))
st, why, base = ci_base(dict(mg, CI_MESSAGE="#6873: build the train's 2.1352.0: Live-Zug (Paket 2.1352) path"))
check(st is None and base == head, "an entry that names 'X.Y.Z: Live-Zug (' inside its subject stays an ordinary entry (%s, %s)" % (st, why))
st, _, _ = ci_base(dict(mg, CI_MESSAGE="#6873: tests\n\n2.1352.0: Live-Zug (Paket 2.1352)"))
check(st is None, "the words on a later line of the message do not make it release (%s)" % st)
st, _, _ = ci_base(dict(mg, CI_MESSAGE="README for the live train (5134, 5110)"))
check(st is None, "the train's README commit at the head is an ordinary entry (%s)" % st)
st, _, _ = ci_base(dict(mg, CI_MESSAGE=ZUG + " [full]"))
check(st == "full", "[full] still asks for the full run (%s)" % st)

push = {"GITHUB_EVENT_NAME": "push", "GITHUB_REF": "refs/heads/main", "CI_BEFORE": head, "CI_MESSAGE": ZUG}
st, why, _ = ci_base(dict(push, CI_QUEUE_RUN="43560000001"))
check(st == "none" and "43560000001" in why, "the landing push of the version commit the queue checked = none (%s, %s)" % (st, why))
st, _, _ = ci_base(push)
check(st == "release", "no merge_group run found (API, a direct push) = the release push keeps release (fallback) (%s)" % st)
st, _, _ = ci_base(dict(push, CI_MESSAGE="#6873: x", CI_QUEUE_RUN="43560000002"))
check(st == "none", "an ordinary push from the queue keeps none (%s)" % st)

repo = stages.Repo(stages.ROOT, os.path.join(N, "run_all.sh"))
hard = stages.hard_groups(repo)
env = {k: v for k, v in os.environ.items() if k not in KEYS and not k.startswith("GITHUB_")}
env.update(mg)
with tempfile.TemporaryDirectory() as td:
    gout = os.path.join(td, "groups.txt")
    p = subprocess.run([sys.executable, os.path.join(N, "stages.py"), "--ci", "--groups-out", gout], capture_output=True, text=True,
                       env=env, cwd=R, timeout=600)
    got = set(open(gout, encoding="utf-8").read().split()) if os.path.exists(gout) else set()
    check("stage=release" in p.stdout.splitlines() and got == {repo.first[g] for g in hard},
          "--ci with the version entry: stage=release, exactly the hard groups (%s %s)" % (p.stdout.strip()[:200], p.stderr[-200:]))

# ---- 2. tools/ci_gate.py judge_queue with release shards
OK = {"result": "success"}
NEEDS = {"plan": OK, "checks": OK, "pr-lint": OK, "semgrep": OK, "einvoice": OK, "zap": OK, "tests": OK}
pats = gate.patterns(R)
grp = gate.groups(R)


def job(i, name, concl="success", status="completed"):
    return {"id": i, "name": name, "conclusion": concl, "status": status, "steps": []}


def shard(i, n, concl="success"):
    return job(i, f"Test suites {i}/{n} release hart (API, UI, security)", concl)


base_jobs = [job(100, "Lint"), job(101, "PR lint"), job(102, "plan"), job(103, "semgrep"), job(104, "E-invoice validators"),
             job(105, "ZAP baseline"), job(106, gate.QUEUE_GATE, None, "in_progress")]
ok, txt, soft = gate.judge_queue("merge_group", NEEDS, base_jobs + [shard(1, 3), shard(2, 3), shard(3, 3)], lambda j: [], pats, grp)
check(ok and not soft, "judge_queue: three green release shards = green (%s)" % txt)
hard_suite = next((s for g, s, _ in repo.rows if gate.hard_suite(s, pats, grp)), None)
red = dict(NEEDS, tests={"result": "failure"})
ok, txt, _ = gate.judge_queue("merge_group", red, base_jobs + [shard(1, 2), shard(2, 2, "failure")], lambda j: [hard_suite], pats, grp)
check(hard_suite and not ok and "hard suite red" in txt, "judge_queue: a hard suite red in a release shard = red (%s)" % txt)
ok, txt, _ = gate.judge_queue("merge_group", NEEDS, base_jobs + [shard(1, 3), shard(3, 3)], lambda j: [], pats, grp)
check(not ok and "missing" in txt, "judge_queue: a release shard missing from the list = red (%s)" % txt)
ok, txt, _ = gate.judge_queue("merge_group", NEEDS, base_jobs, lambda j: [], pats, grp)
check(not ok and "no test shard" in txt, "judge_queue: no shard at all = red (%s)" % txt)

# ---- 3. tools/ci_gate.py decide on the tagged SHA
SHA = "a" * 40
none_run = {"id": 1, "status": "completed", "conclusion": "success", "event": "push", "head_sha": SHA}
mg_run = {"id": 2, "status": "completed", "conclusion": "success", "event": "merge_group", "head_sha": SHA}
JOBS = {1: ["plan", "Lint", "Test suites 1/1 none (API, UI, security)", "tests-done"],  # the none stage: the shard job is skipped
        2: ["plan", "Lint", "Test suites 1/2 release hart (API, UI, security)", "Test suites 2/2 release hart (API, UI, security)",
            gate.QUEUE_GATE]}
res, txt = gate.decide([none_run, mg_run], lambda rid: JOBS[rid])
check(res == "green" and "release" in txt, "decide: push run (none) + merge_group run (release), both green = the image (%s, %s)" % (res, txt))
res, txt = gate.decide([mg_run, none_run], lambda rid: JOBS[rid])
check(res == "green", "decide: the order of the runs does not matter (%s)" % res)
res, txt = gate.decide([none_run], lambda rid: JOBS[rid])
check(res == "red", "decide: the none run alone = no image (%s, %s)" % (res, txt))
res, txt = gate.decide([none_run, dict(mg_run, status="in_progress", conclusion=None)], lambda rid: JOBS[rid])
check(res == "wait", "decide: the merge_group run still running = wait (%s, %s)" % (res, txt))

# ---- 4. ci.yml
with open(os.path.join(R, ".github", "workflows", "ci.yml"), encoding="utf-8") as f:
    ci = f.read()
check("the release commit does not go through the queue" not in ci and "#6873" in ci, "ci.yml: the comments say the version commit goes through the queue")
with open(os.path.join(N, "stages.py"), encoding="utf-8") as f:
    check("zug-pr-6853" in f.read(), "tests/stages.py carries the mark zug-pr-6853 (the train reads it; dispatcher.json zug_pr decides)")

sys.exit(done("p6873_zug_pr_stage"))
