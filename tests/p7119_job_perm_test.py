#!/usr/bin/env python3
# kalmido-suite: after=launcher_ps1 nodata
"""2.1407.0 (#7119, audit F6): a job of the reference starter (agent_job.py) asks a permission question in the chat like a
run, over a second local channel of the runner. Without a server: a stub API, the real hook as a subprocess.
 - the runner opens the jobs' channel and hands it down in its environment (KALMIDO_JOB_PERM_*), a key of its own
 - job_settings: the job's settings file carries the PermissionRequest hook only with that channel
 - the job's question: asked of the job's person with the label "job #N"; allow / deny reach the job's hook
 - no answer in time = denied; never an automatic yes
 - a job that ended / a job this host does not know: denied at once, nobody asked
 - a job of a person who is not the operator: denied with the operator note
 - the key of a chat run does not open the jobs' channel and the other way round
 - #7190: a bare ok / ja in the chat never answers a job's question, a reply to the question does
 - the job's model process gets the hook's names, never KALMIDO_JOB_PERM_* or an inherited run channel
"""
import importlib.util
import json
import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kt  # noqa: E402
from kt import check, until  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
MCP = os.path.join(HERE, "..", "mcp")
RUNNER = os.path.join(MCP, "agent_run.py")
sys.path.insert(0, MCP)
os.environ.update(KALMIDO_URL="http://127.0.0.1:9", KALMIDO_TOKEN="abk_" + "z" * 30)
for k in [k for k in os.environ if k.startswith(("KALMIDO_PERM_", "KALMIDO_JOB_PERM_"))]:
    del os.environ[k]
os.environ.pop("KALMIDO_PERM_RELAY", None)
spec = importlib.util.spec_from_file_location("agent_run", RUNNER)
ar = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ar)
import agent_job as aj  # noqa: E402  the module the runner imports itself (perm_request_job)

TMP = tempfile.mkdtemp(prefix="kalmido-p7119-")


class StubApi:
    def __init__(self):
        self.posts, self.perms, self.withdrawn = [], [], []

    def chat(self, uid, body, approval=None, reply_to=None, task_id=None, suggest=None):
        self.posts.append({"uid": uid, "body": body})
        return {"id": 100 + len(self.posts)}

    def perm_question(self, uid, body, timeout_s):
        self.perms.append((uid, body))
        return {"id": 900 + len(self.perms)}

    def withdraw(self, uid, mid, why=""):
        self.withdrawn.append((uid, mid, why))
        return True


# without a runner: no channel, no hook in the job's settings (as before: the step is denied without a question)
base = ar.profile_args("claude", ["claude"])
d0 = os.path.join(TMP, "job0")
os.makedirs(d0)
check(aj.job_perm_env(ar, {"id": 1, "chat_user": 7}) == {}, "no runner: no channel for the job")
s0 = aj.job_settings(ar, {"cmd": ["claude"]}, base, d0)
h0 = json.load(open(s0[1], encoding="utf-8")) if s0[:1] == ["--settings"] else {}
check("PermissionRequest" not in (h0.get("hooks") or {}), f"no runner: no permission hook in the job's settings {h0}")

r = ar.Runner(["claude"], os.path.join(TMP, "state"))
r.api = r.usage.api = StubApi()
r.agent = {"owner_id": 7}
r.ensure_perm_watch()
check(r.perm_jobs is not None and os.path.exists(r.perm_jobs.address), "the runner opened the jobs' channel")
check(r.perm_jobs.address != r.perm_chan.address, "a channel of its own, not the runs' one")
check(os.environ.get("KALMIDO_JOB_PERM_SOCK") == r.perm_jobs.address and os.environ.get("KALMIDO_JOB_PERM_PID") == str(os.getpid())
      and len(os.environ.get("KALMIDO_JOB_PERM_KEY") or "") == 64, "the runner hands the channel down in its environment")
run_env = r.child_env(7, None)
check(run_env.get("KALMIDO_JOB_PERM_SOCK") == r.perm_jobs.address, "a run inherits it (agent_job.py start of a run)")
check(run_env["KALMIDO_PERM_KEY"] != os.environ["KALMIDO_JOB_PERM_KEY"], "the run's key is not the jobs' key")
check(os.environ["KALMIDO_JOB_PERM_KEY"] == r.child_env(7, None).get("KALMIDO_JOB_PERM_KEY"),
      "the jobs' key stays from run to run (a job outlives the run that started it)")

aj.STATE_DIR = r.state_dir


def job(jid, state="running", user=7):
    j = {"id": jid, "state": state, "chat_user": user, "title": f"Job {jid}", "cmd": ["claude"], "cwd": TMP}
    aj.save(j)
    return j


j = job(55)
je = aj.job_perm_env(ar, j)
check(je.get("KALMIDO_PERM_SOCK") == r.perm_jobs.address and je.get("KALMIDO_PERM_KEY") == os.environ["KALMIDO_JOB_PERM_KEY"]
      and je.get("KALMIDO_JOB_ID") == "55" and je.get("KALMIDO_PERM_UID") == "7" and je.get("KALMIDO_RUN_LABEL") == "job #55",
      f"the job's hook environment: the jobs' channel, the job, its person {je}")
s1 = aj.job_settings(ar, {"cmd": ["claude"], "id": 55, "chat_user": 7}, base, d0)
h1 = json.load(open(s1[1], encoding="utf-8")) if s1[:1] == ["--settings"] else {}
check("--perm-hook" in json.dumps((h1.get("hooks") or {}).get("PermissionRequest")), f"with the channel: the job's settings carry the permission hook {h1}")
check("--guard-hook" in json.dumps((h1.get("hooks") or {}).get("PreToolUse")), "the guard against dangerous commands stays")
os.environ["KALMIDO_PERM_RELAY"] = "0"
ar.PERM_RELAY = False
check(aj.job_perm_env(ar, j) == {}, "KALMIDO_PERM_RELAY=0: no channel for the job")
ar.PERM_RELAY = True
os.environ.pop("KALMIDO_PERM_RELAY")


def hook(env, timeout="30"):
    e = {k: v for k, v in os.environ.items() if not k.startswith(("KALMIDO_PERM_", "KALMIDO_JOB_PERM_"))}
    e.pop("KALMIDO_JOB_ID", None)
    e.update(env)
    e["KALMIDO_PERM_TIMEOUT"] = timeout
    p = subprocess.Popen([sys.executable, RUNNER, "--perm-hook"], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, env=e)
    p.stdin.write('{"tool_name": "Bash", "tool_input": {"command": "npm publish"}}')
    p.stdin.close()
    return p


def result(p):
    out = p.stdout.read()
    p.wait(60)
    return json.loads(out)["hookSpecificOutput"]["decision"]


def asked(n):
    return bool(until(lambda: len(r.api.perms) >= n, 30, 0.1))


# the job asks: the question goes to the job's person, labelled with the job; allow and deny reach the job's hook
p = hook(je)
check(asked(1), "the job's request became a question in the chat")
uid, body = r.api.perms[0]
check(uid == 7 and "job #55" in body and "npm publish" in body, f"asked of the job's person, named by the job: {uid} {body!r}")
mid = next(iter(r.state.data["perms"]))
r.intercept([{"event": "chat_choice", "data": {"message_id": int(mid), "permission": True, "approval": "approved", "choice_ids": ["allow"]}}])
check(result(p)["behavior"] == "allow", "allow reaches the job's hook")
p = hook(je)
check(asked(2), "second question of the job")
mid = next(iter(r.state.data["perms"]))
r.intercept([{"event": "chat_choice", "data": {"message_id": int(mid), "permission": True, "approval": "rejected", "choice_ids": ["deny"]}}])
dd = result(p)
check(dd["behavior"] == "deny" and "denied by the person" in dd["message"], f"deny reaches the job's hook: {dd}")

# #7190 (F3 of the review of job/5545): a bare "ok" / "ja" in the chat never answers a job's question (it comes unasked in
# the middle of a talk); a reply to the question does
p = hook(je)
check(asked(3), "the job asks again")
mid = next(iter(r.state.data["perms"]))


def say(body, reply_to=None, n=[0]):
    n[0] += 1
    m = {"id": int(mid) + n[0], "body": body, **({"reply_to": int(reply_to)} if reply_to else {})}
    return r.intercept([{"event": "chat", "data": {"message": m, "user": {"id": 7}}}])


left = say("ok")
check(mid in r.state.data["perms"] and len(left) == 1, "#7190: a bare ok does not answer the job's question (a normal message)")
say("ja")
check(mid in r.state.data["perms"], "#7190: a bare ja neither")
say("ja", reply_to=mid)
check(result(p)["behavior"] == "allow", "#7190: a yes as a reply to the job's question answers it")

# no answer in time = no
p = hook(je, timeout="3")
check(asked(4), "fourth question, nobody answers")
dd = result(p)
check(dd["behavior"] == "deny" and "in time" in dd["message"], f"no answer in time: denied, never yes: {dd}")
for q in r.state.data["perms"].values():
    q["at"] = 0
r.perm_expire()

# the request names another person and label: the runner takes both from the job's record
p = hook(dict(je, KALMIDO_PERM_UID="99", KALMIDO_RUN_LABEL="chat"))
check(asked(5), "fifth question")
uid, body = r.api.perms[4]
check(uid == 7 and "job #55" in body, f"person and label from the job's record, not the request: {uid} {body!r}")
for q in r.state.data["perms"].values():
    q["at"] = 0
r.perm_expire()
result(p)

# an ended job, an unknown job, no job id: denied at once, nobody asked
n = len(r.api.perms)
job(56, state="done")
for env, why in ((dict(je, KALMIDO_JOB_ID="56"), "an ended job"), (dict(je, KALMIDO_JOB_ID="4711"), "a job this host does not know"),
                 ({k: v for k, v in je.items() if k != "KALMIDO_JOB_ID"}, "no job named")):
    dd = result(hook(env))
    check(dd["behavior"] == "deny", f"{why}: denied: {dd}")
check(len(r.api.perms) == n, "none of them became a question in the chat")

# a job of a person who is not the operator: denied, that person gets the note
job(57, user=9)
dd = result(hook(dict(je, KALMIDO_JOB_ID="57")))
check(dd["behavior"] == "deny" and "operator" in dd["message"], f"a job of someone who is not the operator: denied {dd}")
check(len(r.api.perms) == n and any(x["uid"] == 9 for x in r.api.posts), "nobody asked, the job's person told")

# the keys do not cross: a run's key on the jobs' channel, the jobs' key on the runs' channel
dd = result(hook(dict(je, KALMIDO_PERM_KEY=run_env["KALMIDO_PERM_KEY"])))
check(dd["behavior"] == "deny", f"a run's key on the jobs' channel: denied {dd}")
dd = result(hook(dict(je, KALMIDO_PERM_SOCK=r.perm_chan.address)))
check(dd["behavior"] == "deny", f"the jobs' key on the runs' channel: denied {dd}")
check(len(r.api.perms) == n, "neither asked anybody")

# the job's model process: the hook's names, never KALMIDO_JOB_PERM_* nor the run channel it was started from
src = open(os.path.join(MCP, "agent_job.py"), encoding="utf-8").read()
check("env.update(job_perm_env(ar, j))" in src and '"KALMIDO_PERM_SOCK", "KALMIDO_PERM_KEY", "KALMIDO_PERM_PID") + tuple(getattr(ar, "JOB_PERM_KEYS"' in src,
      "cmd_run drops the inherited channels and sets the jobs' channel under the hook's names")

r.perm_chan.close()
r.perm_jobs.close()
sys.exit(kt.done("p7119_job_perm"))
