#!/usr/bin/env python3
# kalmido-suite: fresh
"""2.1386.0 (#6668, rest of #6454 F5): a TEAM agent with its own token (its own starter, its own program) works per request for
ONE person: POST /api/v1/agent/request-token gives a short-lived token of the agent cut to the rights of the person the events
come from (kalmido/agents/reqtoken.py, the same cut as the server's run: agents/srvteam.py srv_run_cut); from the first ask on
the agent's own token reaches only its channel (api/runfor.py req_main_gate).
freelancer-matrix: agents (the person without an organisation: her personal agent gets token null -- its own token is hers --
  and keeps its whole reach after asking)
tenant-matrix: agent (only the agent's own events; the token reaches only what the person reaches themselves)
 (a) member carl (project one only) mentions the agent: his request token reads the task of project one, the task of project two
     is 404 (also not listed); without the fix (no cut) it would be 200
 (b) reader rita (view in project one) asks in the chat: with her request token the agent (role edit) writes no comment, the
     answer is 409 approval_required; carl's token writes it
 (c) an event without a person (the project's own automation): only its project, nothing outside, and every change is a card
     (409 approval_required) -- also with no control level chosen
 (d) an expired request token is refused (401); a request token cannot ask for another one (403 request_token_main); events of
     two people in one call 400 several_people; an unknown event 404 event_gone; no operator chosen 409 no_operator
 (e) the agent's own token after the first ask: content routes 403 request_token_needed, its channel (events, chats, status)
     stays; review F1: also /search, /news, /time, /office, /briefing, /me/waiting, /layouts (the classes mine / pin); a card a person answered still runs with it (the replay of an approved request)
 (f) static: the reference starter asks before every run and gives only the request token to the run (child_env), the
     dispatcher works with the chosen person's token; both launchers name the capability
 (i) review F3: the step of a card run with the agent's own token always checks the card and the rights of the person who
     said Yes (a reader's Yes changes nothing)
 (c) review F4: an event older than 24 hours gives no request token any more (404 event_gone)
 (h) review F2: removing a computer of the agent (its long-lived token) ends the request tokens too (401)
 (g) review F1, no server: no request token for a team agent (403 no_order, 400, 404 event_gone, the network) = the run, the
     dispatcher round and their children never start / never get the agent's own token; 2.1386.0 (F1): also a plain 404 /
     405 of the route -- only a server whose GET /agent does not report request_token (and a personal agent) keeps it,
     nothing is remembered; a job's wake asks with the person's last events
 (k) F2: one valid request token per agent and person -- a new one ends the older one (401)
 (l) F4: a locked person's account gets no request token (403 no_order); review F3: her request token stops while she is locked
 (n) review F4: the list work's token has its own place (a chat run of the same person keeps it); a 401 of a request
     token's client asks once anew (no server part)
 (m) review F2: the guard hook (also with KALMIDO_BLOCK_DANGEROUS=0) and the deny rules keep the run from the env file and
     the starter's environment (no server)
 (p) #6978 F5: the step of an answered card with the long-lived token holds the route classes (org / closed / pin) of the
     person who said Yes -- 403 run_closed as with her request token, the card stays unused
 #6978 F6: locking a person or a role in the organisation that gives no orders (guest) deletes her request tokens at once
 #6978 F7: request tokens are known by asked_by + req_slot, never by their name (a token named "Agent request" is listed)
 (q) #6808: after KALMIDO_REQ_MAIN_FROM every team agent's own token is its channel, also one that never asked; GET
     /agent/chats needs the request token (before: the channel); the admin list names the day until then
 (o) merged with #6457: a team agent's run, a job of the run, a woken job and the dispatcher's job read only a request
     token through an env file of their own -- MCP server, kalmido_cli.py, agent_job.py never the long-lived one (no server)
usage: p6668_ext_team_agent_test.py <datadir>      (KMT_NOSTART=1 / P6668_NOSTART=1: a running server)"""
import json
import os
import uuid

import requests

from kt import B, apv_body, check, dbx, docker_logs_on_first_fail, done, fresh, sess
# 2.1386.0 (#6623): a Yes on an approval card with a bound step carries the proof of the description (kt.apv_body)
from freelancer_fixture import freelancer

N = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(N, "..")
V = B + "/api/v1"
SCOPES = ["read", "tasks:write", "comments", "structure"]


def read(*p):
    with open(os.path.join(ROOT, *p), encoding="utf-8") as f:
        return f.read()


# ---------------------------------------------------------------- (f) static: the starter and both launchers
RUN, DISP = read("mcp", "agent_run.py"), read("mcp", "agent_dispatch.py")
check("def run_request" in RUN and "self.run_request(evs, uid)" in RUN, "(f) agent_run.py asks for the request token of every run")
# 2.1386.0 (#6668 with #6457): the request token goes to the run through an env file of its own (token_file), never in the environment
check('env["KALMIDO_ENV_FILE"] = self.run_env_file' in RUN and "def token_file" in RUN, "(f) agent_run.py: the run's env file carries only the request token")
check("self.run_api = self.api" in RUN, "(f) agent_run.py: the request token is forgotten after the run")
check("def data_api" in DISP and "api = self.data_api()" in DISP and "read_tasks(api, cfg)" in DISP and 'env["KALMIDO_ENV_FILE"] = self.host.op_env_file' in DISP and "if api is not self.host.api" in DISP,
      "(f) agent_dispatch.py: the list work and its jobs with the chosen person's token")
# 2.1394.0 (#4068): the thin launchers only start agent_run.py --launch; every capability marker sits in the core
check("kalmido-capability: request_token" in read("mcp", "agent_run.py"), "(f) the launch core agent_run.py names request_token")


def _starter_env():
    import tempfile
    d = tempfile.mkdtemp(prefix="kalmido-p6668-starter-")
    f = os.path.join(d, "kalmido-agent.env")
    with open(f, "w", encoding="utf-8") as fh:
        fh.write("KALMIDO_URL=http://127.0.0.1:9\nKALMIDO_TOKEN=abk_" + "m" * 30 + "\n")
    return f


STARTER_ENV = _starter_env()  # the starter's env file with the agent's long-lived token (abk_mmm...)


# ---------------------------------------------------------------- (g) review F1: the starter fails closed (no server)
# Without the fix a refused request token (403 no_order, 400 several_people, 409 no_operator, the network) let the run go on with
# the agent's own long-lived token: the model could fetch any person's reach with it. Only an older server (plain 404) keeps it.
def _f1():
    import importlib.util
    import sys
    import tempfile
    os.environ.update(KALMIDO_URL="http://127.0.0.1:9", KALMIDO_TOKEN="abk_" + "m" * 30, KALMIDO_ENV_FILE=STARTER_ENV)
    # 2.1400.0 (#7057): a configured dispatcher -- check_cmd (2.1368.0) and push_url are required, else the round stops at
    # the configuration before the token question this part is about (red since 2.1368.0)
    os.environ.update(KALMIDO_DISPATCH_CHECK_CMD="exit 0", KALMIDO_DISPATCH_PUSH_URL="/nowhere")
    sys.path.insert(0, os.path.join(ROOT, "mcp"))
    for nm in ("agent_run", "agent_dispatch", "kalmido_mcp", "agent_job"):
        spec = importlib.util.spec_from_file_location(nm, os.path.join(ROOT, "mcp", nm + ".py"))
        m = importlib.util.module_from_spec(spec)
        sys.modules[nm] = m
        spec.loader.exec_module(m)
    ar, ad = sys.modules["agent_run"], sys.modules["agent_dispatch"]
    tmp = tempfile.mkdtemp(prefix="kalmido-p6668f1-")

    TEAM = {"owner_id": None, "request_token": True, "runtime": {"dispatch": "on"}}

    def runner(name, answer, agent=None):
        r = ar.Runner(["claude"], os.path.join(tmp, name))
        r.extras = None
        r.calls, r.started, r.said = [], [], []
        r.agent = dict(TEAM if agent is None else agent)

        def req(method, path, body=None, query=None, timeout=30, retry=True):
            r.calls.append((path, body, r.api.token))
            if isinstance(answer, Exception):
                raise answer
            return answer
        r.api.req = req
        r.api.status = lambda *a, **k: r.said.append(k.get("key"))
        r.attempt_runs = lambda *a, **k: (r.started.append(1), (None, 1, "stub"))[1]
        return r

    def asks(r):
        return [c for c in r.calls if c[0] == "/agent/request-token"]

    ev = [{"event": "chat", "seq": 41, "data": {"user": {"id": 5}, "message": {"id": 1, "body": "hi"}}}]
    # 2.1386.0 (#6668, F1): a plain 404 / 405 of the route is no reason for the own token any more (only GET /agent decides)
    for name, answer in (("no_order", ar.ApiError(403, '{"error": {"code": "no_order"}}')),
                         ("several_people", ar.ApiError(400, '{"error": {"code": "several_people"}}')),
                         ("event_gone", ar.ApiError(404, '{"error": {"code": "event_gone"}}')),
                         ("plain404", ar.ApiError(404, '{"error": "Not found"}')),
                         ("plain405", ar.ApiError(405, '{"error": "Method not allowed"}')),
                         ("no_token_key", {"ok": True}),
                         ("network", OSError("unreachable"))):
        r = runner(name, answer)
        check(r.run_request(ev, 5) is False and r.run_api is r.api, f"(g) F1 {name}: no request token = the run may not start")
        check(r.run_request(ev, 5) is False and len(asks(r)) == 2, f"(g) F1 {name}: nothing remembered, the next request asks again")
        r = runner(name + "-run", answer)
        r.run(5, [dict(e) for e in ev])
        check(not r.started and "status_no_request" in r.said, f"(g) F1 {name}: the run is skipped with a status line {r.said}")
        ce = r.child_env(5, None)  # 2.1386.0 (with #6457): nor the path of the starter's env file
        check("KALMIDO_TOKEN" not in ce and "KALMIDO_ENV_FILE" not in ce, f"(g) F1 {name}: a child of the team agent never gets its own token")
        r = runner(name + "-op", answer)
        check(r.op_api() is None, f"(g) F1 {name}: the dispatcher gets no client for the chosen person")
        proj = os.path.join(tmp, name + "-proj")
        os.makedirs(proj)
        with open(os.path.join(proj, "KALMIDO-DISPATCH.json"), "w", encoding="utf-8") as f:
            json.dump({"lists": [1]}, f)
        # 2.1398.0 (#7138): since #7028 a round without the project's check stays idle before it asks for anything; the
        # runner's env file of this stand-in names one, so the round reaches the request token
        old_check = os.environ.get("KALMIDO_DISPATCH_CHECK_CMD")
        os.environ["KALMIDO_DISPATCH_CHECK_CMD"] = "exit 0"
        try:
            res = ad.Dispatcher(r, proj).tick(force=True, dry=False) or {}
        finally:
            if old_check is None:
                os.environ.pop("KALMIDO_DISPATCH_CHECK_CMD", None)
            else:
                os.environ["KALMIDO_DISPATCH_CHECK_CMD"] = old_check
        check("no request token" in str(res.get("problem")) and all(c[0] == "/agent/request-token" for c in r.calls),
              f"(g) F1 {name}: the dispatcher round reads nothing with the agent's own token {res.get('problem')} {r.calls}")
    r = runner("old-server", ar.ApiError(404, '{"error": "Not found"}'), agent={"owner_id": None, "runtime": {}})
    check(r.run_request(ev, 5) is True and not asks(r) and r.child_env(5, None).get("KALMIDO_ENV_FILE") == STARTER_ENV and r.op_api() is r.api,
          "(g) F1: a server whose GET /agent does not report request_token keeps the agent's own token, as before (never asked)")
    r = runner("unknown", ar.ApiError(503, "{}"), agent={})
    check(r.run_request(ev, 5) is False and not asks(r) and r.op_api() is None and "KALMIDO_ENV_FILE" not in r.child_env(5, None),
          "(g) F1: GET /agent not read (unknown) = nothing starts, no own token for a child")
    r = runner("personal", {"token": None}, agent={"owner_id": 5, "request_token": True, "runtime": {}})
    check(r.run_request(ev, 5) is True and not asks(r) and r.child_env(5, None).get("KALMIDO_ENV_FILE") == STARTER_ENV,
          "(g) F1: a personal agent keeps its own token (the starter's env file, #6457)")
    r = runner("server-personal", {"token": None, "expires_at": None, "asked_by": 5, "list_ids": None})
    check(r.run_request(ev, 5) is True and r.run_api is r.api, "(g) the server says a personal agent (token null + asked_by): its own token")
    r = runner("ok", {"token": "abk_" + "r" * 30, "expires_at": "2099-01-01T00:00:00Z", "asked_by": 5, "list_ids": [1]})
    check(r.run_request(ev, 5) is True, "(g) F1: the run gets its request token")
    ce = r.child_env(5, None)
    check("KALMIDO_TOKEN" not in ce and ce.get("KALMIDO_ENV_FILE") == r.run_env_file and r.run_env_file != STARTER_ENV
          and sys.modules["kalmido_mcp"].env_credentials(ce) == ("http://127.0.0.1:9", "abk_" + "r" * 30),
          f"(g) F1: the run gets the request token only, through its own env file {ce.get('KALMIDO_ENV_FILE')}")
    r.run_api = r.api
    wake = [{"event": "job_wake", "seq": "wake-9", "data": {"user": {"id": 5}}}]
    check(r.run_request(wake, 5) is True and r.calls[-1][1] == {"seqs": [41]}, f"(g) F1: a job's wake asks with the person's last events {r.calls[-1]}")
    r.run_api = r.api  # after the run (Runner.handle)
    r.run_env_file = None
    ce = r.child_env(5, None)
    check("KALMIDO_TOKEN" not in ce and "KALMIDO_ENV_FILE" not in ce, "(g) F1: outside a request the team agent's children get no token")


_f1()



# ---------------------------------------------------------------- review R3 F5: a tick by hand (CliHost) never hands on the long-lived token
# Without the fix the dispatcher run from the command line (agent_dispatch.py --once) gave a job of the chosen person the
# starter's environment: KALMIDO_TOKEN (the agent's long-lived token) and no env file of the person's request token.
def _f5():
    import sys
    import tempfile
    import time as _t
    ar, ad, km = sys.modules["agent_run"], sys.modules["agent_dispatch"], sys.modules["kalmido_mcp"]
    tmp = tempfile.mkdtemp(prefix="kalmido-p6668f5-")
    os.environ["KALMIDO_TOKEN"] = "abk_" + "m" * 30  # the starter's environment of a tick by hand
    h = ad.CliHost.__new__(ad.CliHost)
    h.api = ar.Api("http://127.0.0.1:9", "abk_" + "m" * 30)
    h.state_dir, h._say, h._write, h.op_env_file = tmp, ar.say, ar.write_token_file, None
    h.agent = {"owner_id": None, "request_token": True, "perm_user_id": 9, "runtime": {"dispatch": "on"}}
    h.api.request_token = lambda operator=False: ("abk_op" + "o" * 26, _t.time() + 3600, True)
    api = h.op_api()
    check(api is not None and api is not h.api and api.token == "abk_op" + "o" * 26, "(p) R3 F5: the tick by hand works the lists with the chosen person's token")
    check(h.op_env_file and km.env_credentials({"KALMIDO_ENV_FILE": h.op_env_file}) == ("http://127.0.0.1:9", "abk_op" + "o" * 26),
          f"(p) R3 F5: ... and writes it to op.env {h.op_env_file}")
    proj = os.path.join(tmp, "proj")
    os.makedirs(proj)
    with open(os.path.join(proj, "KALMIDO-DISPATCH.json"), "w", encoding="utf-8") as f:
        json.dump({"lists": [1]}, f)
    env = ad.Dispatcher(h, proj).job_env(api)
    check("KALMIDO_TOKEN" not in env and env.get("KALMIDO_ENV_FILE") == h.op_env_file,
          f"(p) R3 F5: the job of a tick by hand gets op.env, never KALMIDO_TOKEN {sorted(k for k in env if k.startswith('KALMIDO'))}")
    h.op_env_file = None
    env = ad.Dispatcher(h, proj).job_env(api)
    check("KALMIDO_TOKEN" not in env and "KALMIDO_ENV_FILE" not in env, "(p) R3 F5: without op.env neither the token nor the starter's file")


_f5()



# ---------------------------------------------------------------- review R3 F6: a job whose request token ran out says so
# Without the fix a job after 8 h (401, no newer token in its env file) failed silently: its result, progress and state never
# reached Kalmido and nobody saw why. Renewing is a later task (#7106); here only the clear status.
def _f6():
    import sys
    import tempfile
    ar, aj = sys.modules["agent_run"], sys.modules["agent_job"]
    tmp = tempfile.mkdtemp(prefix="kalmido-p6668f6-")
    envf = os.path.join(tmp, "p5.env")
    ar.write_token_file(envf, "http://127.0.0.1:9", "abk_old" + "x" * 24)
    saved = {k: os.environ.get(k) for k in ("KALMIDO_TOKEN", "KALMIDO_ENV_FILE", "KALMIDO_STATE_DIR")}
    os.environ.pop("KALMIDO_TOKEN", None)
    os.environ.update(KALMIDO_ENV_FILE=envf, KALMIDO_STATE_DIR=os.path.join(tmp, "state"))
    old_sd, aj.STATE_DIR = aj.STATE_DIR, None
    try:
        api = aj.Api()
        api.job_id = 31

        def dead(*a, **k):  # #7151: the shared transport (agent_common.Api) raises ApiError; agent_job.Api.req turns it into RuntimeError
            raise aj.ApiError(401, "Missing or invalid API token")
        api._req = dead
        try:
            api.req("GET", "/agent")
            raised = False
        except RuntimeError:
            raised = True
        marks = aj.take_req_expired()
        check(raised and [m.get("job") for m in marks] == [31], f"(q) R3 F6: a 401 without a fresh env file leaves the job's mark {marks}")
        check(aj.take_req_expired() == [], "(q) R3 F6: a mark is taken once")
        # the starter's job watch turns the mark into the status (its own channel)
        aj.mark_req_expired(32)
        os.environ["KALMIDO_TOKEN"] = "abk_" + "m" * 30  # the starter's own environment
        r = ar.Runner(["claude"], os.path.join(tmp, "state"))
        os.environ.pop("KALMIDO_TOKEN", None)
        r.extras = None
        r.agent = {"owner_id": None, "request_token": True, "runtime": {}, "lang": "de"}
        said = []
        r.api.status = lambda *a, **k: said.append((a, k))
        r.req_mode = lambda: "team"
        aj.revive_lost, keep = (lambda api=None: []), aj.revive_lost
        try:
            r.job_watch()
        finally:
            aj.revive_lost = keep
        check(any(k.get("key") == "status_req_expired" for _, k in said) and any("Anfrage-Token abgelaufen" in a[1] for a, _ in said),
              f"(q) R3 F6: the starter shows 'Anfrage-Token abgelaufen' in the agent's status {said}")
    finally:
        aj.STATE_DIR = old_sd
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


_f6()



# ---------------------------------------------------------------- review R3 F8: collected task events are cut per person
# Without the fix the events of the gather window went as ONE bundle into one run, whoever made them: with two people the
# server answered 400 several_people, the run was skipped and the events were gone from the queue.
def _f8():
    import sys
    import tempfile
    ar = sys.modules["agent_run"]
    sys.path.insert(0, os.path.join(ROOT, "mcp"))
    import agent_extras
    tmp = tempfile.mkdtemp(prefix="kalmido-p6668f8-")

    def ev(seq, who, kind="task_added"):
        return {"event": kind, "seq": seq, "actor": {"kind": "person", "id": who} if who else None,
                "data": {"task": {"id": 100 + seq, "title": f"t{seq}"}, "list_id": 1}}
    ex = agent_extras.Extras(None, os.path.join(tmp, "st"), ["claude"])
    ex.gather_s = 0
    ex.owners = set()
    got = ex.intake([ev(1, 5), ev(2, 7), ev(3, 5), ev(4, None, "tidy"), ev(5, 7)])
    check(got == [] and len(ex.pending) == 5, f"(r) R3 F8: five task events wait in the gather window {len(ex.pending)}")
    bs = ex.take_bundle()
    who = [sorted({agent_extras.Extras.ev_person(e) for e in b["data"]["events"]}, key=str) for b in bs]
    seqs = sorted(e["seq"] for b in bs for e in b["data"]["events"])
    check(len(bs) == 3 and who == [[5], [7], [None]] and seqs == [1, 2, 3, 4, 5] and [b["seq"] for b in bs] == [3, 5, 4],
          f"(r) R3 F8: one bundle per person (and one for the automation), no event lost {who} {seqs} {[b['seq'] for b in bs]}")
    # each bundle asks the request token for its one person: never 400 several_people
    r = ar.Runner(["claude"], os.path.join(tmp, "run"))
    r.extras = None
    r.agent = {"owner_id": None, "request_token": True, "runtime": {}}
    asked = []

    def rt(seqs=None, operator=False):
        asked.append(sorted(set(seqs or [])))  # as Api.request_token sends them (the bundle's seq is one of its events)
        return "abk_rq" + "z" * 26, 0, True
    r.api.request_token = rt
    for b in bs:
        check(r.run_request([b], None) is True, "(r) R3 F8: the bundle's run gets its token")
    check(asked == [[1, 3], [2, 5], [4]], f"(r) R3 F8: each ask names one person's events only {asked}")


_f8()


# ---------------------------------------------------------------- (m) review F2: no run reads the long-lived token
# Without the fix a team agent's run could read kalmido-agent.env (or the starter's /proc/<pid>/environ) and ask request
# tokens for anybody with the agent's own token. 2.1386.0 (merged with #6457): the guard hook of #6457 carries it -- its
# env file part (also /proc/<pid>/environ, ps e, the starter's file named with --secret-file) holds also with
# KALMIDO_BLOCK_DANGEROUS=0 (--secret-only); Read / Grep of the files and of /proc/*/environ are deny rules of every run.
def _f2():
    import subprocess
    import sys
    ar = sys.modules["agent_run"]
    os.environ["KALMIDO_BLOCK_DANGEROUS"] = "0"
    try:
        hs = ar.hook_settings(False, usage=False, env_files=["/srv/bot/state/run-env/p5.env"])
    finally:
        os.environ.pop("KALMIDO_BLOCK_DANGEROUS", None)
    pre = hs["hooks"].get("PreToolUse") or []
    cmd = pre[0]["hooks"][0]["command"] if pre else ""
    check(len(pre) == 1 and pre[0].get("matcher") == "Bash" and "--guard-hook" in cmd and "--secret-only" in cmd
          and f'--secret-file "{os.path.abspath(STARTER_ENV)}"' in cmd,
          f"(m) F2: every run (also KALMIDO_BLOCK_DANGEROUS=0) carries the env file part of the guard, naming the starter's file {pre}")
    deny = (hs.get("permissions") or {}).get("deny") or []
    check(all(x in deny for x in (f"Read(/{STARTER_ENV})", "Read(//srv/bot/state/run-env/p5.env)", "Edit(//srv/bot/state/run-env/p5.env)",
                                  "Read(//proc/*/environ)", "Read(//proc/*/task/*/environ)")),
          f"(m) F2: Read / Grep of the starter's and the run's env file and of /proc/*/environ are denied {deny}")
    for name in ("agent_launcher.sh", "agent_launcher.ps1"):
        src = read("mcp", name)
        check("KALMIDO_ENV_FILE" in src and "kalmido-capability: env_file_guard" not in src and "--secret-hook" not in src,
              f"(m) F2: {name} hands the env file's path on once (#6457), no second mechanism")

    def hook(line, envf="/srv/bot/state/run-env/p5.env"):
        cp = subprocess.run([sys.executable, os.path.join(ROOT, "mcp", "agent_run.py"), "--guard-hook", "--secret-only",
                             "--secret-file", "/srv/bot/agents/team-bot.env"],
                            input=json.dumps({"tool_name": "Bash", "tool_input": {"command": line}, "hook_event_name": "PreToolUse"}),
                            capture_output=True, text=True, timeout=60, env=dict(os.environ, KALMIDO_ENV_FILE=envf))
        try:
            return (json.loads(cp.stdout).get("hookSpecificOutput") or {}).get("permissionDecision")
        except ValueError:
            return None
    for line in ("cat ../kalmido-agent.env", "grep TOKEN /srv/bot/agents/team-bot.env", "cat $HOME/agents/team-bot.env",
                 "tr '\\0' '\\n' < /proc/$PPID/environ", "cat /proc/*/env*", "ps eww -p 1", "ps auxe", 'cat "$KALMIDO_ENV_FILE"'):
        check(hook(line) == "deny", f"(m) F2: {line} is refused (also with KALMIDO_BLOCK_DANGEROUS=0)")
    for line in ("ps -ef | grep node", "cat /proc/cpuinfo", "cat README.md", "git push --force origin main"):
        check(hook(line) is None, f"(m) F2: {line} stays allowed by the env file part")
    # reader R4 F2: only the arguments of ps itself count. Without the fix every line with ps and a later word with an e was
    # refused (docker ps --format table, ps -o etime, echo ps here), also with KALMIDO_BLOCK_DANGEROUS=0.
    # Reader job/5481 F9: "ps -o etime" / "ps -C node -o etime" are refused now (in doubt refused, see F9 below)
    for line in ("docker ps --format table", "ps -o etime=", "echo ps here", "ps -eo pid,etime", "ps axo pid,etime", "ps -C bash -o pid,etime",
                 "docker ps -a --filter name=web"):
        check(not ar.secret_ps(line) and ar.guard_secret(line, env={}) is None, f"(m) R4 F2: {line} is no environment read")
    for line in ("ps e", "ps aux e", "ps auxe", "ps -E", "ps eww", "sudo ps eww", "ls; /bin/ps e", "bash -c 'ps e'", "echo $(ps axe)"):
        check(ar.secret_ps(line.replace("'", "")) and ar.guard_secret(line, env={}) is not None, f"(m) R4 F2: {line} stays refused")
    check(hook("docker ps --format table") is None and hook("ps aux e") == "deny", "(m) R4 F2: ... also through the hook")
    # 2.1398.0 (#7132, reader of job/5387 F5): ps at every word again -- without the fix these passed (only a ps at the start
    # of a command was read; -N counted as an option with a value)
    for line in ("LC_ALL=C ps e", "FOO=1 ps auxe", "env FOO=1 ps e", "if true; then ps e; fi", "for i in 1; do ps eww; done",
                 "{ ps e; }", "! ps e", "timeout 5 ps e", "nice -n 5 ps e", "sudo -u root ps e", "stdbuf -o0 ps e", "setsid ps e",
                 "ps -N e", "ps -fN e", "ps -AN e", "ps o e", "ps e>out.txt", "/usr/bin/ps e"):
        check(ar.secret_ps(line) and ar.guard_secret(line, env={}) is not None, f"(m) #7132: {line} is refused")
    for line in ("docker compose ps --format json", "podman ps -a --filter name=web", "ps -o pid,etime > out.txt"):
        check(not ar.secret_ps(line) and ar.guard_secret(line, env={}) is None, f"(m) #7132: {line} stays allowed")
    # Fable reader job/5498 F3: the word before ps counts only from the same command (a line ending on echo / docker before
    # a newline hid the next line's ps e), and "}" ends no argument list (ps ${X} e passed)
    for line in ("echo\nps e", "docker\nps e", "printf x; ps e", "echo a && ps e", "ps ${X} e", "{ ps e}"):
        check(ar.secret_ps(line) and ar.guard_secret(line, env={}) is not None, f"(m) F3: {line!r} is refused")
    for line in ("docker ps --format '{{.Names}}'", "echo ps e"):
        check(not ar.secret_ps(line) and ar.guard_secret(line, env={}) is None, f"(m) F3: {line!r} stays allowed")
    # Fable reader job/5481 F9 (fourth round): a value attached to its option (-uroot) or an option the list did not know
    # (--User) made the next word a "value" and hid the e flag. Without the fix these passed. Now no option parsing: every
    # letters-only argument word with an e (or a dash block with E) is refused -- also a value such as etime or node.
    for line in ("ps -uroot eww", "ps -ukalmido eww", "ps Uroot eww", "ps --User root eww", "ps -Cgit eww", "ps --Group x eww",
                 "ps --width 200 eww", "ps -o etime", "ps -C node -o pid", "ps -p 1 e", "ps U root e", "ps -oE"):
        check(ar.secret_ps(line) and ar.guard_secret(line, env={}) is not None, f"(m) F9: {line!r} is refused")
    for line in ("ps -o pid,etime=", "ps -fu root", "ps aux", "ps -p 1 -o pid,cmd", "pgrep -a node", "ps -ef | grep node"):
        check(not ar.secret_ps(line) and ar.guard_secret(line, env={}) is None, f"(m) F9: {line!r} stays allowed")
    check("pgrep" in (ar.guard_secret("ps -o etime", env={}) or ""), "(m) F9: the refusal names the way out (pgrep, ps -o pid,etime=)")

    # review R3 F1: the request token files of OTHER people (op.env of the chosen person, p<other>.env, auto.env) lie next to
    # the run's own file in <state>/run-env. Without the fix only the run's own file and the starter's were named: a run for
    # person 5 read op.env (cat / Read) and worked with the chosen person's rights for up to 8 hours.
    hs = ar.hook_settings(False, usage=False, env_files=["/srv/bot/state/run-env/p5.env"], secret_dirs=["/srv/bot/state/run-env"])
    deny = (hs.get("permissions") or {}).get("deny") or []
    cmd = hs["hooks"]["PreToolUse"][0]["hooks"][0]["command"]
    check("Read(//srv/bot/state/run-env/**)" in deny and "Edit(//srv/bot/state/run-env/**)" in deny
          and any(x.endswith("/.cache/kalmido-agent/run-env/**)") and x.startswith("Read(") for x in deny),
          f"(m) R3 F1: Read / Edit of the whole run-env folder (the given state and the default one) are denied {deny}")
    check('--secret-dir "/srv/bot/state/run-env"' in cmd, f"(m) R3 F1: the guard hook names the run-env folder {cmd}")

    def hook3(line):
        cp = subprocess.run([sys.executable, os.path.join(ROOT, "mcp", "agent_run.py"), "--guard-hook", "--secret-only",
                             "--secret-dir", "/srv/bot/state/run-env"],
                            input=json.dumps({"tool_name": "Bash", "tool_input": {"command": line}, "hook_event_name": "PreToolUse"}),
                            capture_output=True, text=True, timeout=60,
                            env=dict(os.environ, KALMIDO_ENV_FILE="/srv/bot/state/run-env/p5.env"))
        try:
            return (json.loads(cp.stdout).get("hookSpecificOutput") or {}).get("permissionDecision")
        except ValueError:
            return None
    for line in ("cat /srv/bot/state/run-env/op.env", "cat /srv/bot/state/run-env/p7.env", "cd /srv/bot/state/run-env && cat op.env",
                 "grep TOKEN auto.env", "ls /srv/bot/state/run-env/", "cat p7.env"):
        check(hook3(line) == "deny", f"(m) R3 F1: {line} is refused (a sibling file of another person)")
    for line in ("cat README.md", "ls -la", "python3 tools/setup.env.py"):
        check(hook3(line) is None, f"(m) R3 F1: {line} stays allowed")
    # a job of the agent: the run-env folder of its state folder is denied as well (mcp/agent_job.py job_settings)
    import tempfile
    aj = sys.modules.get("agent_job")
    if aj is not None:
        jd = tempfile.mkdtemp(prefix="kalmido-p6668r3-")
        old = os.environ.get("KALMIDO_STATE_DIR")
        os.environ["KALMIDO_STATE_DIR"] = os.path.join(jd, "state")
        try:
            out = aj.job_settings(ar, {"cmd": ["claude"]}, ar.profile_args("claude", ["claude"]), jd)
        finally:
            if old is None:
                os.environ.pop("KALMIDO_STATE_DIR", None)
            else:
                os.environ["KALMIDO_STATE_DIR"] = old
        js = json.load(open(out[-1], encoding="utf-8")) if out[:1] == ["--settings"] else {}
        rp = ar.rule_path(os.path.join(jd, "state", "run-env"))
        check(f"Read({rp}/**)" in (js.get("permissions") or {}).get("deny", [])
              and os.path.join(jd, "state", "run-env") in json.dumps(js.get("hooks", {}).get("PreToolUse")),
              f"(m) R3 F1: a job's settings deny its state's run-env folder and name it to the guard {js}")
    else:
        check(False, "(m) R3 F1: agent_job is loaded for the job check")


_f2()


# ---------------------------------------------------------------- (o) the merge with #6457: MCP / CLI / job never reach the long-lived token
# #6457 lets the MCP server, kalmido_cli.py, agent_job.py and the usage hook read the token from KALMIDO_ENV_FILE. Without the
# run's own env file a team agent's run would name the starter's file there -- every one of them would read the agent's
# long-lived token and #6668 would be void. A run, a job of the run, a job the runner wakes and a job of the dispatcher read
# only a request token; a renewed token (401) reaches the same file.
def _o():
    import subprocess
    import sys
    import tempfile
    ar, km, aj = sys.modules["agent_run"], sys.modules["kalmido_mcp"], sys.modules["agent_job"]
    own, url = "abk_" + "m" * 30, "http://127.0.0.1:9"

    class Fake(ar.Api):
        def _req(self, method, path, body=None, query=None, timeout=30):
            if path == "/agent/request-token":
                self.n[0] += 1
                who = None if (body or {}).get("operator") else 5
                return {"token": "abk_req%02d" % self.n[0] + "x" * 24, "expires_at": "2099-01-01T00:00:00Z",
                        "asked_by": who if who else 9, "list_ids": [1]}
            if self.token in self.dead:
                raise ar.ApiError(401, '{"error": "Missing or invalid API token"}')
            if path.startswith("/agent/jobs/"):  # 2.1398.0 (#7132): the server's job of a woken job (job 801 is person 5's)
                return {"id": int(path.rsplit("/", 1)[1]), "user_id": 5 if path.endswith("/801") else 77}
            return {"ok": True}

    sd = tempfile.mkdtemp(prefix="kalmido-p6668o-")
    r = ar.Runner(["claude"], sd)
    r.extras = None
    r.agent = {"owner_id": None, "request_token": True, "perm_user_id": 9, "runtime": {}}
    r.api.__class__ = Fake
    r.api.n, r.api.dead = [0], set()
    ev = [{"event": "chat", "seq": 88, "data": {"user": {"id": 5}, "message": {"id": 1, "body": "hi"}}}]
    check(r.run_request(ev, 5) is True, "(o) the run gets its request token")
    ce = r.child_env(5, None)
    rf = ce.get("KALMIDO_ENV_FILE") or ""
    blob = json.dumps(ce)
    check(rf and rf != STARTER_ENV and STARTER_ENV not in blob and own not in blob and "KALMIDO_TOKEN" not in ce,
          f"(o) the run's environment names neither the starter's env file nor the long-lived token {rf}")
    if os.name != "nt":
        check(oct(os.stat(rf).st_mode & 0o777) == "0o600", f"(o) the run's env file is 0600 {oct(os.stat(rf).st_mode)}")
    t1 = r.run_api.token
    check(km.env_credentials(ce) == (url, t1), "(o) MCP server of the run: the request token")
    # kalmido_cli.py as the model would call it (stdlib only, no server: the token it would send)
    cli = subprocess.run([sys.executable, "-c", "import sys; sys.path.insert(0, sys.argv[1]); import kalmido_cli as c; "
                          "print(c.env_credentials()[1])", os.path.join(ROOT, "mcp")],
                         capture_output=True, text=True, timeout=60, env=ce)
    check(cli.stdout.strip() == t1, f"(o) kalmido_cli.py in the run: the request token {cli.stdout.strip()[:12]} {cli.stderr[-200:]}")
    job = subprocess.run([sys.executable, "-c", "import sys; sys.path.insert(0, sys.argv[1]); import agent_job as j; "
                          "print(j.Api().token)", os.path.join(ROOT, "mcp")],
                         capture_output=True, text=True, timeout=60, env=ce)
    check(job.stdout.strip() == t1, f"(o) agent_job.py started from the run: the request token {job.stdout.strip()[:12]} {job.stderr[-200:]}")
    # review F4 + #6457: a 401 renews the token -- the run's file carries the new one, the MCP server reads it again
    r.api.dead.add(t1)
    check(r.run_api.req("GET", "/tasks") == {"ok": True} and r.run_api.token != t1, "(o) F4: the runner's 401 asks anew")
    t2 = r.run_api.token
    check(km.env_credentials(ce) == (url, t2), "(o) F4: the new request token is in the same run file")
    k = km.Kalmido(url, t1)
    k.reload = lambda: km.env_credentials(ce)[1]
    seen = []

    def send(req, timeout, cap):
        tok = req.get_header("Authorization").split()[-1]
        seen.append(tok)
        if tok == t1:
            raise km.ApiError(401, "Missing or invalid API token")
        return {"ok": True}
    k._send = send
    check(k.call("GET", "/tasks") == {"ok": True} and seen == [t1, t2] and own not in seen,
          f"(o) MCP server: a 401 reads the run file once more, never the long-lived token {seen}")
    # a job the runner wakes (card answer) / continues: the file of its person, never the runner's environment
    aj.SPAWN_ENV = r.job_env
    # 2.1386.0 (#6668): reader R4 F1 -- job_env needs the token's person and kind the job started with (agent_job.py cmd_start)
    check(r.job_env({"id": 801, "chat_user": 5, "env_key": "p5", "token_person": 5}) == rf
          and r.job_env({"id": 802, "chat_user": 77, "env_key": "p77", "token_person": 77}) is None,
          "(o) a woken job of the person gets her request token file; a person without one: none (it stays asleep)")
    aj.SPAWN_ENV = None
    # the dispatcher's job: the chosen person's token file (op), never the starter's
    opc = r.op_api()
    check(opc is not None and getattr(r, "op_env_file", None) and km.env_credentials({"KALMIDO_ENV_FILE": r.op_env_file}) == (url, opc.token)
          and opc.token != own, "(o) the dispatcher's list work: the chosen person's token in its own env file")
    r.run_api, r.run_env_file = r.api, None  # after the run
    ce = r.child_env(5, None)
    check("KALMIDO_ENV_FILE" not in ce and "KALMIDO_TOKEN" not in ce, "(o) outside a request: no env file, no token")
    # a personal agent: unchanged #6457 (the starter's env file)
    r.agent = {"owner_id": 5, "request_token": True, "runtime": {}}
    check(r.run_request(ev, 5) is True and r.child_env(5, None).get("KALMIDO_ENV_FILE") == STARTER_ENV,
          "(o) a personal agent: the starter's env file as before (#6457)")


_o()


# ---------------------------------------------------------------- (n) review F4: a 401 of a request token asks once anew (no server)
# Without the fix the dispatcher's cached token (op_api) and the runner's run token stayed dead after being replaced: the
# list work failed for hours, the run's answer was lost.
def _f4():
    import sys
    import tempfile
    ar = sys.modules["agent_run"]

    class Fake(ar.Api):
        def _req(self, method, path, body=None, query=None, timeout=30):
            self.log.append((path, self.token, body))
            if path == "/agent/request-token":
                if self.refuse:
                    raise ar.ApiError(403, '{"error": {"code": "no_order"}}')
                self.n[0] += 1
                return {"token": "abk_new%02d" % self.n[0] + "x" * 24, "expires_at": "2099-01-01T00:00:00Z", "asked_by": 5, "list_ids": [1]}
            if self.token in self.dead:
                raise ar.ApiError(401, '{"error": "Missing or invalid API token"}')
            return {"ok": True}

    r = ar.Runner(["claude"], tempfile.mkdtemp(prefix="kalmido-p6668f4-"))
    r.extras = None
    # 2.1386.0 (#6668): R3 F9 -- the list work's token must be for the person the settings name (the server cuts it so: 5)
    r.agent = {"owner_id": None, "request_token": True, "perm_user_id": 5, "runtime": {}}
    r.api.__class__ = Fake
    r.api.log, r.api.dead, r.api.n, r.api.refuse = [], set(), [0], False
    c1 = r.op_api()
    t1 = c1.token
    r.api.dead.add(t1)
    check(c1.req("GET", "/tasks") == {"ok": True} and c1.token not in (t1, r.api.token) and r.op_api().token == c1.token,
          f"(n) F4: the list work's token answers 401 -> asked once anew with operator, the call goes through {r.api.log[-3:]}")
    check([b for p, _, b in r.api.log if p == "/agent/request-token"][-1] == {"operator": True}, "(n) F4: ... for the chosen person")
    r.api.dead.add(c1.token)
    r.api.refuse = True
    try:
        c1.req("GET", "/tasks")
        ok = False
    except ar.ApiError as e:
        ok = e.status == 401
    check(ok and r.api.token not in [t for p, t, _ in r.api.log if p == "/tasks"], "(n) F4: no new token = the 401 stands, never the own token")
    r.api.refuse = False
    ev = [{"event": "chat", "seq": 77, "data": {"user": {"id": 5}, "message": {"id": 1, "body": "hi"}}}]
    check(r.run_request(ev, 5) is True, "(n) the run gets its request token")
    t2 = r.run_api.token
    r.api.dead.add(t2)
    check(r.run_api.req("POST", "/tasks/1/comments", {"body": "x"}) == {"ok": True} and r.run_api.token != t2
          and [b for p, _, b in r.api.log if p == "/agent/request-token"][-1] == {"seqs": [77]},
          "(n) F4: the run's token answers 401 -> the runner asks once anew with the run's events")
    try:
        r.api.req("GET", "/agent")
        r.api.dead.add(r.api.token)
        r.api.req("GET", "/agent")
        ok = False
    except ar.ApiError as e:
        ok = e.status == 401
    check(ok, "(n) the agent's own client asks for nothing on a 401 (revoked computer: as before)")


_f4()


# ---------------------------------------------------------------- review R3 F9: another person chosen drops the list work's token
# Without the fix the token of the person chosen before stayed in the starter and in op.env for up to 8 hours (the dispatcher
# worked on as her), and job_env gave op.env to a job of the newly chosen person whose own file was missing.
def _f9():
    import sys
    import tempfile
    ar = sys.modules["agent_run"]
    r = ar.Runner(["claude"], tempfile.mkdtemp(prefix="kalmido-p6668f9-"))
    r.extras = None
    r.agent = {"owner_id": None, "request_token": True, "perm_user_id": 9, "runtime": {}}
    nxt = {"agent": dict(r.agent)}

    def req(method, path, body=None, query=None, timeout=30, retry=True):
        if path == "/agent/request-token":
            r.api.asked_by = nxt["agent"]["perm_user_id"]  # the server cuts it for the person chosen right now
            return {"token": "abk_op%02d" % nxt["agent"]["perm_user_id"] + "y" * 24, "expires_at": "2099-01-01T00:00:00Z",
                    "asked_by": nxt["agent"]["perm_user_id"], "list_ids": [1]}
        if path == "/agent":
            return dict(nxt["agent"])
        if path.startswith("/agent/jobs/"):  # 2.1398.0 (#7132): the server's job 900 + n is person n's
            return {"user_id": int(path.rsplit("/", 1)[1]) - 900}
        return {"ok": True}
    r.api.req = req
    opc = r.op_api()
    opf = os.path.join(r.state_dir, "run-env", "op.env")
    def oj(uid):  # 2.1386.0 (#6668): reader R4 F1 -- a job of the list work started with op.env for person uid
        return {"id": 900 + uid, "chat_user": uid, "env_key": "op", "token_person": uid}
    check(opc is not None and os.path.isfile(opf) and r.job_env(oj(9)) == opf and r.job_env(oj(5)) is None,
          "(s) R3 F9: op.env for a job of the chosen person (9) only")
    nxt["agent"] = {**r.agent, "perm_user_id": 7}
    r.refresh_agent()  # runtime_changed: the settings are read again
    check(not os.path.isfile(opf) and getattr(r, "_op_tok", (None, 0))[0] is None,
          "(s) R3 F9: another person chosen -- the starter drops the old token and op.env at once")
    check(r.job_env(oj(7)) is None and r.job_env(oj(9)) is None,
          "(s) R3 F9: no job gets op.env of another person (7 has no file of its own: it stays asleep)")
    opc = r.op_api()
    check(opc is not None and opc.token.startswith("abk_op07") and r.job_env(oj(7)) == opf,
          "(s) R3 F9: the next round asks for the newly chosen person")
    # the settings this runner knows are stale (the server cut the token for another person): read again, then decide
    r.agent = {**r.agent, "perm_user_id": 9}
    r._op_tok = (None, 0)
    opc = r.op_api()
    check(opc is not None and r.op_who == 7 and r.perm_uid() == 7, "(s) R3 F9: stale settings are read again before the token counts")


_f9()


# ---------------------------------------------------------------- reader R4 F1: a job keeps the person of the token it started with
# Without the fix agent_job.py start took the job's person from KALMIDO_CHAT_USER (the model's Bash line) and the runner gave
# a woken / continued job the request token file of that person (job_env by chat_user alone): a job of person 5's run named
# person 7, a card answer or a restart continued it with p7.env, and its end woke a run for 7.
def _r4f1():
    import sys
    import tempfile
    ar, aj = sys.modules["agent_run"], sys.modules["agent_job"]
    tmp = tempfile.mkdtemp(prefix="kalmido-p6668r4-")
    sd = os.path.join(tmp, "state")
    p5, p7 = os.path.join(sd, "run-env", "p5.env"), os.path.join(sd, "run-env", "p7.env")
    os.makedirs(os.path.join(sd, "run-env"), mode=0o700)
    ar.write_token_file(p5, "http://127.0.0.1:9", "abk_p5" + "a" * 26)
    ar.write_token_file(p7, "http://127.0.0.1:9", "abk_p7" + "b" * 26)
    brief = os.path.join(tmp, "brief.txt")
    with open(brief, "w", encoding="utf-8") as f:
        f.write("do it")
    keys = ("KALMIDO_TOKEN", "KALMIDO_ENV_FILE", "KALMIDO_STATE_DIR", "KALMIDO_CHAT_USER", "KALMIDO_JOB_CMD", "KALMIDO_URL")
    saved = {k: os.environ.get(k) for k in keys}
    old_sd, old_req, old_spawn = aj.STATE_DIR, aj.Api.req, aj.spawn_run
    calls, answer = [], {}

    def req(self, method, path, body=None, *a, **k):
        calls.append((method, path, body))
        return dict(answer) if method == "POST" else {}
    try:
        aj.STATE_DIR = None
        os.environ.pop("KALMIDO_TOKEN", None)
        os.environ.update(KALMIDO_ENV_FILE=p5, KALMIDO_STATE_DIR=sd, KALMIDO_JOB_CMD='["true"]', KALMIDO_URL="http://127.0.0.1:9")
        aj.Api.req, aj.spawn_run = req, (lambda j, extra=None: 0)
        check(aj.run_env_key() == "p5" and aj.run_env_key("/x/run-env/op.env") == "op" and aj.run_env_key("/x/kalmido-agent.env") is None,
              "(t) R4 F1: the kind of a run's request token file")
        os.environ["KALMIDO_CHAT_USER"] = "7"
        check(aj.cmd_start(["--title", "For seven", brief]) == 2 and not calls,
              f"(t) R4 F1: person 5's run starts no job for person 7 (KALMIDO_CHAT_USER), nothing asked {calls}")
        os.environ.pop("KALMIDO_CHAT_USER")
        answer.update(id=901, user_id=5)
        made = lambda: [c for c in calls if c[:2] == ("POST", "/agent/jobs")]  # noqa: E731 - 2.1394.0 (#5237): a brief post may follow
        check(aj.cmd_start(["--title", "For five", brief]) == 0 and made()[-1][2].get("user_id") == 5, f"(t) R4 F1: without a person: the token's {made()[-1:]}")
        check(calls[-1][:2] == ("POST", "/agent/chats/5") and calls[-1][2].get("kind") == "brief",
              f"(t) #5237: the brief goes into the chat of the token's person only {calls[-1:]}")
        j = aj.load(901) or {}
        check(j.get("chat_user") == 5 and j.get("token_person") == 5 and j.get("env_key") == "p5", f"(t) R4 F1: the job keeps the token's person {j}")
        answer.update(id=902, user_id=7)  # a server that named somebody else: the job is closed, not started
        check(aj.cmd_start(["--title", "Odd", brief]) == 2 and aj.load(902) is None and calls[-1][:2] == ("PATCH", "/agent/jobs/902"),
              f"(t) R4 F1: the server's job of another person is not started {calls[-1:]}")
        # the runner: woken / continued only with the file of the token's person
        os.environ["KALMIDO_TOKEN"] = "abk_" + "m" * 30
        r = ar.Runner(["claude"], sd)
        os.environ.pop("KALMIDO_TOKEN", None)
        r.extras = None
        r.agent = {"owner_id": None, "request_token": True, "runtime": {}}
        r.req_mode = lambda: "team"
        srv = {901: 5, 903: 5}  # 2.1398.0 (#7132): the person of each server job (set by the server, pin:user_id)
        r.api.req = lambda method, path, body=None, *a, **k: {"id": int(path.rsplit("/", 1)[1]), "user_id": srv.get(int(path.rsplit("/", 1)[1]))}
        bad = {"id": 903, "title": "x", "chat_user": 7, "env_key": "p5", "token_person": 5}
        check(r.job_env(bad) is None and r.job_env({**bad, "env_key": "p7"}) is None and r.job_env({"id": 904, "chat_user": 7}) is None,
              "(t) R4 F1: a job file with chat_user 7 and token person 5 never gets p7.env (nor without a token person)")
        check(r.job_env(j) == p5, "(t) R4 F1: the job of person 5 gets p5.env")
        # 2.1398.0 (#7132, reader of job/5387 N2): the job file lies in the state folder the model's processes write -- a file
        # rewritten as a whole to person 7 (chat_user, token_person, env_key) agrees with itself, not with the server's job
        forged = {**j, "chat_user": 7, "token_person": 7, "env_key": "p7"}
        check(r.job_env(forged) is None, "(t) #7132 N2: a job file rewritten to person 7 does not get p7.env (the server's job is 5's)")
        srv[905] = None
        check(r.job_env({**j, "id": 905}) is None, "(t) #7132 N2: a server job without that person (or not read): it stays asleep")
        aj.spawn_run = old_spawn
        aj.SPAWN_ENV = r.job_env
        os.makedirs(aj.job_dir(903), exist_ok=True)
        try:
            aj.spawn_run(dict(bad))
            raised = False
        except OSError:
            raised = True
        check(raised, "(t) R4 F1: waking / continuing such a job starts nothing")
        # the end of the job wakes a run only for the token's person
        queued = []
        r.queue_add = lambda evs: queued.extend(evs)
        aj.revive_lost, keep = (lambda api=None: []), aj.revive_lost
        try:
            aj.add_wake(dict(bad), "done", "result")
            aj.add_wake(dict(j), "done", "result")
            aj.add_wake({**forged, "id": 906, "title": "forged"}, "done", "result")  # #7132 N2: server job 906 is nobody's
            r.job_watch()
        finally:
            aj.revive_lost = keep
        check([e["data"]["user"]["id"] for e in queued] == [5], f"(t) R4 F1: the end wakes a run for person 5 only, never for 7 {queued}")
        # Fable reader job/5498 F6: a wake whose server job could not be read (network) goes back into the folder and wakes on
        # the next look; a 404 (no such job of the agent) drops it. Without the fix both were lost at once.
        down = {907}

        def req_f6(method, path, body=None, *a, **k):
            n = int(path.rsplit("/", 1)[1])
            if n in down:
                raise OSError("network down")
            if n == 908:
                raise ar.ApiError(404, "not found")
            return {"id": n, "user_id": srv.get(n)}
        r.api.req, srv[907], srv[908] = req_f6, 5, 5
        del queued[:]
        aj.revive_lost = lambda api=None: []
        try:
            aj.add_wake({**j, "id": 907, "title": "net"}, "done", "result")
            aj.add_wake({**j, "id": 908, "title": "gone"}, "done", "result")
            r.job_watch()
            wd = os.path.join(aj.state_dir(), "wakes")
            check(not queued and os.path.isfile(os.path.join(wd, "907.json")) and not os.path.exists(os.path.join(wd, "908.json")),
                  f"F6: a wake not checked waits in its folder, a 404 drops it {queued} {sorted(os.listdir(wd))}")
            down.clear()
            r.job_watch()
            check([e["data"]["job"]["id"] for e in queued] == [907], f"F6: ... and wakes on the next look once the server answers {queued}")
        finally:
            aj.revive_lost = keep
        # Fable reader job/5481 F10: GET /agent not read (mode None) said "yes" -- the job file got its token without the check
        mode_keep = r.req_mode
        r.req_mode = lambda: None
        check(r.server_job_of(901, 5) is None, f"F10: the agent's mode not known: the server's job counts as not read {r.server_job_of(901, 5)!r}")
        # #7162 (Fable reader job/5481 F12): the wake loop asked the server only in mode team -- with the mode not known
        # (GET /agent not read after a restart) a wake ran without the check; now it waits in its folder for the next look
        del queued[:]
        aj.revive_lost = lambda api=None: []
        try:
            aj.add_wake({**forged, "id": 909, "title": "early"}, "done", "result")
            r.job_watch()
            check(not queued and os.path.isfile(os.path.join(aj.state_dir(), "wakes", "909.json")),
                  f"F12: the mode not known: no wake run, the wake waits in its folder {queued}")
            r.req_mode = mode_keep
            r.job_watch()
            check(not queued and not os.path.exists(os.path.join(aj.state_dir(), "wakes", "909.json")),
                  f"F12: once the mode is known the server's check drops the forged wake {queued}")
        finally:
            aj.revive_lost = keep
        r.req_mode = mode_keep
        # F11: a job continued after a restart whose server job could not be read was lost for good (OSError, revived set);
        # now it stays lost without revived / lost_handled and is continued on the next look once the server answers
        spawned = []
        aj.SPAWN_ENV = r.job_env
        aj.spawn_run, real_spawn = (lambda jj, extra=None: (aj.SPAWN_ENV(jj), spawned.append(jj["id"]))), old_spawn
        down.add(901)
        lj = {**(aj.load(901) or j), "state": "lost", "session": "s-901"}
        lj.pop("lost_handled", None)
        lj.pop("revived", None)
        aj.save(lj)
        keep_all = aj.all_jobs
        aj.all_jobs = lambda: [x for x in (aj.load(901),) if x]
        try:
            check(aj.revive_lost() == [] and not spawned, "F11: not read: not continued now")
            st = aj.load(901) or {}
            check(st.get("state") == "lost" and not st.get("revived") and not st.get("lost_handled") and st.get("revive_tries") == 1,
                  f"F11: ... and not given up (lost, no revived / lost_handled, one try) {st}")
            down.clear()
            check(aj.revive_lost() == [901] and spawned == [901], f"F11: the next look continues it once the server answers {spawned}")
        finally:
            aj.all_jobs, aj.spawn_run = keep_all, real_spawn
        # F11: a wake file with tries that are no number stopped the whole round (int()); now it counts as used up
        check(aj.as_tries("x") == aj.WAKE_TRIES and aj.as_tries(None) == 0 and aj.as_tries("3") == 3 and aj.as_tries(-1) == aj.WAKE_TRIES,
              "F11: as_tries reads a forged value as used up")
        down.add(907)
        del queued[:]
        aj.revive_lost = lambda api=None: []
        try:
            aj.add_wake({**j, "id": 907, "title": "net"}, "done", "result")
            wp = os.path.join(aj.state_dir(), "wakes", "907.json")
            with open(wp, encoding="utf-8") as f:
                wd_ = json.load(f)
            wd_["tries"] = "many"
            with open(wp, "w", encoding="utf-8") as f:
                json.dump(wd_, f)
            aj.add_wake({**j, "id": 903, "title": "ok"}, "done", "result")
            try:
                r.job_watch()
                ok = True
            except (TypeError, ValueError):
                ok = False
            check(ok and [e["data"]["job"]["id"] for e in queued] == [903], f"F11: a wake with tries 'many' does not stop the round {queued}")
        finally:
            aj.revive_lost = keep
            down.clear()
    finally:
        aj.STATE_DIR, aj.Api.req, aj.spawn_run, aj.SPAWN_ENV = old_sd, old_req, old_spawn, None
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


_r4f1()

# ---------------------------------------------------------------- server
fresh(prefix="P6668")
docker_logs_on_first_fail()


def err(r):
    try:
        e = r.json()["error"]
        return e if isinstance(e, dict) else {}
    except (ValueError, KeyError, TypeError):
        return {}


assert sess().post(B + "/api/auth/setup", json={"username": "alice", "display_name": "Alice", "password": "password123"}).ok
A = sess("alice")
A.post(B + "/api/admin/setup", json={"org_name": "Example Studio", "lang": "en", "collab_all": True,
                                    "modules": ["comments", "collab"]})
FEAT = "comments,collab"
A.patch(B + "/api/settings", json={"tour": "done", "lang": "en", "features": FEAT})
ORG = A.get(B + "/api/state").json()["me"]["workspaces"][0]["id"]
check(A.put(B + "/api/admin/agent-policy", json={"user_agents": True}).ok, "setup: personal agents allowed")
uid = {}
for u, rk in (("bob", "admin"), ("carl", "member"), ("rita", "member")):
    r = A.post(B + "/api/users", json={"orgs": [{"id": ORG, "role": rk}], "username": u, "display_name": u.title(),
                                       "password": "password123", "email": f"{u}@example.com"})
    check(r.ok, f"setup: {u} as {rk} " + r.text[:200])
    uid[u] = r.json().get("id")
S = {u: sess(u) for u in uid}
Bo, Ca, Ri = S["bob"], S["carl"], S["rita"]
for s in S.values():
    s.patch(B + "/api/settings", json={"tour": "done", "lang": "en", "features": FEAT})
FID, Fr = freelancer(B, A)

r = A.post(B + "/api/admin/agents", json={"scopes": SCOPES, "username": "extbot", "display_name": "Ext Bot", "org_id": ORG})
check(r.status_code == 201, f"setup: a team agent with its own token {r.status_code} {r.text[:200]}")
XT, XTOK = r.json()["id"], r.json()["token"]
XH = {"Authorization": "Bearer " + XTOK}
check(dbx("SELECT owner_id FROM agents WHERE user_id=?", (XT,)) == [(None,)], "setup: a team agent (no owner)")
X1 = Bo.post(B + "/api/lists", json={"name": "Project one", "org_id": ORG}).json()["id"]
X2 = Bo.post(B + "/api/lists", json={"name": "Project two", "org_id": ORG}).json()["id"]
for u, role in (("carl", "edit"), ("rita", "view")):
    check(Bo.put(B + f"/api/lists/{X1}/members", json={"user_id": uid[u], "role": role}).ok, f"setup: {u} in project one ({role})")
for lid in (X1, X2):
    r = Bo.put(B + f"/api/lists/{lid}/members", json={"user_id": XT, "role": "edit", "bridge_ok": True})
    check(r.ok, f"setup: the agent in project {lid} {r.status_code} {r.text[:160]}")
    check(Bo.patch(B + f"/api/lists/{lid}", json={"agent_members": True}).ok, "setup: members may use the agent")
TX = Bo.post(B + "/api/tasks", json={"title": "Open stork task", "list_id": X1}).json()["id"]
SX = Bo.post(B + "/api/tasks", json={"title": "Secret crane budget", "list_id": X2}).json()["id"]
check(Ca.get(B + f"/api/tasks/{SX}").status_code == 404, "setup: carl does not see the task of project two")
check(requests.get(V + f"/tasks/{SX}", headers=XH, timeout=30).ok, "setup: before any request token the agent's own token reaches all (as before)")


def hdr(tok):
    return {"Authorization": "Bearer " + tok}


def seq_of(mark):
    """The seq of the agent's event whose payload carries mark (its own token, the channel)."""
    r = requests.get(V + "/agent/events", headers=XH, params={"since": 0, "limit": 500}, timeout=30)
    check(r.ok, f"the agent reads its events {r.status_code} {r.text[:160]}")
    hits = [e["seq"] for e in r.json().get("data", []) if mark in json.dumps(e)]
    check(len(hits) == 1, f"one event with {mark}: {hits}")
    return hits[0] if hits else -1


def ask(seqs=None, headers=None, **body):
    return requests.post(V + "/agent/request-token", headers=headers or XH, json={"seqs": seqs, **body} if seqs is not None else body, timeout=30)


# ================================================================ (a) a member of project one only
check(Ca.post(B + f"/api/tasks/{TX}/comments", json={"body": f"<@{XT}> CARL-ASKS tell me about the crane"}).ok, "(a) carl mentions the agent")
SC = seq_of("CARL-ASKS")
r = ask([SC])
check(r.ok and r.json().get("token") and r.json().get("asked_by") == uid["carl"] and r.json().get("list_ids") == [X1],
      f"(a) a request token for carl, cut to project one {r.status_code} {r.text[:200]}")
RC = r.json().get("token") or ""
check(dbx("SELECT asked_by, run_lists, name FROM api_tokens WHERE user_id=? AND asked_by IS NOT NULL", (XT,)) == [(uid["carl"], str(X1), "Agent request")],
      "(a) the token row carries carl and the cut")
check(requests.get(V + f"/tasks/{TX}", headers=hdr(RC), timeout=30).status_code == 200, "(a) carl's request reads the task of project one")
check(requests.get(V + f"/tasks/{SX}", headers=hdr(RC), timeout=30).status_code == 404, "(a) carl's request: the task of project two is 404")
check(SX not in [t["id"] for t in requests.get(V + "/tasks", headers=hdr(RC), params={"limit": 200}, timeout=30).json().get("data", [])],
      "(a) ... and not in the task list")
r = requests.get(V + "/agent", headers=hdr(RC), timeout=30)
check(r.ok, f"(a) the request token reaches the agent's own channel {r.status_code}")
check(r.json().get("request_token") is True, "(a) F1: GET /agent reports the capability request_token (the starter's only fallback signal)")

# ---- (k) F2: a second ask for the same person replaces the first token
r = ask([SC])
RCB = r.json().get("token") or "" if r.ok else ""
check(r.ok and RCB and RCB != RC, f"(k) F2: a second request token for carl {r.status_code}")
check(requests.get(V + f"/tasks/{TX}", headers=hdr(RC), timeout=30).status_code == 401, "(k) F2: carl's older request token is refused (401)")
check(requests.get(V + f"/tasks/{TX}", headers=hdr(RCB), timeout=30).status_code == 200, "(k) F2: the new one works")
check(dbx("SELECT COUNT(*) FROM api_tokens WHERE user_id=? AND name='Agent request' AND asked_by=?", (XT, uid["carl"])) == [(1,)],
      "(k) F2: one request token row for carl")
RC = RCB

# ---- review R3 F2: the request token keeps the narrower address rule of the asking computer (#6457)
# Without the fix agent_token_new copied the agent's rule (none here): a leaked request token worked from any address for 8 h.
dbx("UPDATE api_tokens SET allowed_ips='0.0.0.0/0,::/0' WHERE user_id=? AND asked_by IS NULL", (XT,))
r = ask([SC])
check(r.ok and dbx("SELECT allowed_ips FROM api_tokens WHERE user_id=? AND asked_by=?", (XT, uid["carl"])) == [("0.0.0.0/0,::/0",)],
      f"(k) R3 F2: the request token carries the asking computer's address rule {r.status_code} "
      f"{dbx('SELECT allowed_ips FROM api_tokens WHERE user_id=? AND asked_by=?', (XT, uid['carl']))}")
dbx("UPDATE api_tokens SET allowed_ips='' WHERE user_id=? AND asked_by IS NULL", (XT,))
r = ask([SC])
check(r.ok and dbx("SELECT allowed_ips FROM api_tokens WHERE user_id=? AND asked_by=?", (XT, uid["carl"])) == [("",)],
      "(k) R3 F2: without a rule of its own the agent's rule (none) as before")
RC = r.json().get("token") or "" if r.ok else ""

# ---- review R3 F3: every order event must be one the person may give; another event of hers carries none along
# Without the fix (any()) carl's order in project two (he is no member there: no order) came with a token as soon as one
# event of his that is no order (followup_due) was in the same ask.
def _ins(ev, lid, note):
    pl = {"id": str(uuid.uuid4()), "event": ev, "agent_id": XT, "actor": {"kind": "person", "id": uid["carl"]}, "via": "web",
          "data": {"task": {"id": SX if lid == X2 else TX, "list_id": lid}, "list_id": lid, "note": note}}
    return dbx("INSERT INTO agent_events(agent_id, uuid, event, payload, created_at) VALUES(?,?,?,CAST(? AS jsonb),now()) RETURNING id",
               (XT, pl["id"], ev, json.dumps(pl)))[0][0]


SO2, SF1 = _ins("mention", X2, "CARL-NO-ORDER"), _ins("followup_due", X1, "CARL-FOLLOWUP")
r = ask([SF1, SO2])
check(r.status_code == 403 and err(r).get("code") == "no_order" and not r.json().get("token"),
      f"(k) R3 F3: an order carl may not give is refused, also next to another event of his {r.status_code} {r.text[:160]}")
r = ask([SO2])
check(r.status_code == 403 and err(r).get("code") == "no_order", f"(k) R3 F3: ... and alone {r.status_code}")
check(requests.get(V + f"/tasks/{TX}", headers=hdr(RC), timeout=30).ok, "(k) R3 F3: a refused ask leaves carl's token alone")

# ================================================================ (e) the agent's own token is its channel now
check(dbx("SELECT per_request FROM agents WHERE user_id=?", (XT,)) == [(True,)], "(e) the agent works per request from the first ask on")
r = requests.get(V + f"/tasks/{SX}", headers=XH, timeout=30)
check(r.status_code == 403 and err(r).get("code") == "request_token_needed", f"(e) its own token: the content of a project 403 {r.status_code} {r.text[:160]}")
r = requests.get(V + f"/tasks/{TX}", headers=XH, timeout=30)
check(r.status_code == 403 and err(r).get("code") == "request_token_needed", f"(e) ... also of project one {r.status_code}")
check(requests.get(V + "/agent/events", headers=XH, params={"since": 0}, timeout=30).ok and requests.get(V + "/agent", headers=XH, timeout=30).ok,
      "(e) its own token keeps its channel: events, the agent")
# 2.1432 (#6808): GET /agent/chats reads what people wrote -- no part of the channel any more (before: 200 with every
# person's conversation); the request token of carl's event reads carl's conversation only
r = requests.get(V + "/agent/chats", headers=XH, timeout=30)
check(r.status_code == 403 and err(r).get("code") == "request_token_needed",
      f"(e) #6808: its own token reads no conversation (GET /agent/chats 403) {r.status_code} {r.text[:120]}")
r = requests.get(V + "/agent/chats", headers=hdr(RC), timeout=30)
check(r.ok and all((m.get("user") or {}).get("id") == uid["carl"] for m in r.json().get("data", [])),
      f"(e) #6808: carl's request token reads carl's conversation only {r.status_code} {r.text[:120]}")
check(requests.put(V + "/agent/status", headers=XH, json={"status": "idle"}, timeout=30).ok, "(e) ... and its status")
# 2.1386.0 (#6668, review F1): the classes mine / send / pin are capped only in a run (run_person); with the long-lived token
# nothing capped them -- without the fix these answered 200 with every project and person of the agent. The routes with a
# scope this agent lacks (/time, /office, /layouts) stop at the scope check first; tests/p6454_c_run_routes_test.py holds them.
for path, q in (("/search", {"q": "crane", "kind": "all"}), ("/news", {}), ("/briefing", {"user_id": uid["carl"]}),
                ("/me/waiting", {"user_id": uid["carl"]})):
    r = requests.get(V + path, headers=XH, params=q, timeout=30)
    check(r.status_code == 403 and err(r).get("code") == "request_token_needed",
          f"(e) F1: its own token gets no {path} any more (request_token_needed) {r.status_code} {r.text[:120]}")

# ---- (e) review R3 F4: the long-lived token changes only its own filters, never a project's shared view
# Without the fix PATCH / DELETE /filters/{id} (class own) changed and deleted bob's shared view of project one (200 / 204).
r = Bo.post(B + "/api/filters", json={"name": "Team view R3", "list_id": X1, "rules": {}})
check(r.ok, f"(e) R3 F4: bob saves a shared view of project one {r.status_code} {r.text[:160]}")
VW = r.json().get("id")
r = requests.patch(V + f"/filters/{VW}", headers=XH, json={"name": "Hijacked"}, timeout=30)
# 2.1433.0 (#7142): without a control level the circle rule holds first -- a shared view of a project whose readers the gate
# does not name is a card ("wider"); without the card the route's own 403 follows (lists/sections.py need_filter)
check(r.status_code == 409 and err(r).get("circle") == "wider", f"(e) R3 F4: its own token renames no shared view {r.status_code} {r.text[:160]}")
r = requests.delete(V + f"/filters/{VW}", headers=XH, timeout=30)
check(r.status_code == 403, f"(e) R3 F4: its own token deletes no shared view (this agent lacks the scope delete too) {r.status_code} {r.text[:160]}")
check(dbx("SELECT name FROM filters WHERE id=?", (VW,)) == [("Team view R3",)], "(e) R3 F4: the shared view is unchanged")
r = requests.post(V + "/filters", headers=XH, json={"name": "Own R3", "rules": {}}, timeout=30)
OWNF = r.json().get("id") if r.status_code == 201 else None
check(OWNF is not None, f"(e) R3 F4: its own filter is still its own {r.status_code} {r.text[:160]}")
r1 = requests.patch(V + f"/filters/{OWNF}", headers=XH, json={"name": "Own R3b"}, timeout=30)
check(r1.ok, f"(e) R3 F4: ... and changes it {r1.status_code} {r1.text[:150]}")
r = requests.patch(V + f"/filters/{VW}", headers=hdr(RC), json={"name": "Team view R3 (carl)"}, timeout=30)
check(r.ok, f"(e) R3 F4: carl's request token (editor of project one) renames the shared view {r.status_code} {r.text[:160]}")

# ================================================================ (b) a reader's order does not write
check(Ri.post(B + f"/api/agents/{XT}/chat", json={"body": "RITA-ASKS please comment on the stork task"}).status_code == 201, "(b) rita (reads project one) asks in the chat")
SR = seq_of("RITA-ASKS")
r = ask([SR])
check(r.ok and r.json().get("asked_by") == uid["rita"] and r.json().get("list_ids") == [X1], f"(b) a request token for rita {r.status_code} {r.text[:200]}")
RR = r.json().get("token") or ""
check(requests.get(V + f"/tasks/{TX}", headers=hdr(RR), timeout=30).ok, "(b) rita's request reads the task she reads herself")
r = requests.post(V + f"/tasks/{TX}/comments", headers=hdr(RR), json={"body": "FOR-RITA"}, timeout=30)
check(r.status_code == 409 and err(r).get("code") == "approval_required", f"(b) the agent (role edit) writes no comment for the reader: a card {r.status_code} {r.text[:200]}")
check(not dbx("SELECT 1 FROM obj_comments WHERE kind='task' AND ref_id=? AND body='FOR-RITA'", (TX,)), "(b) ... nothing written")
ap = err(r).get("approval") or {}
STEP = {k: ap[k] for k in ("method", "path", "body", "if_match") if k in ap}
r = requests.post(V + f"/tasks/{TX}/comments", headers=hdr(RC), json={"body": "FOR-CARL"}, timeout=30)
check(r.status_code == 201, f"(b) carl's request (he writes there) comments {r.status_code} {r.text[:200]}")

# ---- reader R4 F1: a job of carl's request is carl's -- never another person's (KALMIDO_CHAT_USER of the model's Bash line)
# Without the fix POST /agent/jobs (class send) took any person who shares a project with the agent: a job of carl's run named
# rita, the starter woke / continued it later with rita's request token file (p<rita>.env) and her rights.
r = requests.post(V + "/agent/jobs", headers=hdr(RC), json={"title": "R4 job for rita", "user_id": uid["rita"], "state": "done"}, timeout=30)
check(r.status_code == 403 and err(r).get("code") == "run_person", f"(f) R4 F1: carl's request starts no job for rita {r.status_code} {r.text[:200]}")
check(not dbx("SELECT 1 FROM agent_jobs WHERE agent_id=? AND title='R4 job for rita'", (XT,)), "(f) R4 F1: ... nothing stored")
r = requests.post(V + "/agent/jobs", headers=hdr(RC), json={"title": "R4 job unnamed", "state": "done"}, timeout=30)
check(r.status_code == 201 and r.json().get("user_id") == uid["carl"], f"(f) R4 F1: a job without a person is carl's (the requester) {r.status_code} {r.text[:200]}")
r = requests.post(V + "/agent/jobs", headers=hdr(RC), json={"title": "R4 job carl", "user_id": uid["carl"], "state": "done"}, timeout=30)
check(r.status_code == 201 and r.json().get("user_id") == uid["carl"], f"(f) R4 F1: carl named himself: his job {r.status_code} {r.text[:200]}")

# ---- reader R4 F3: the long-lived token reads no task titles / project names through its usage report
# Without the fix POST /agent/usage took any task the agent sees (project two too) and GET ?group=task gave its title back.
r = requests.post(V + "/agent/usage", headers=XH, json={"model": "m-r4", "input_tokens": 3, "output_tokens": 1, "task_id": SX}, timeout=30)
check(r.status_code == 201, f"(f) R4 F3: the long-lived token reports usage (its own data) {r.status_code} {r.text[:200]}")
check(requests.post(V + "/agent/usage", headers=hdr(RC), json={"model": "m-r4", "input_tokens": 3, "output_tokens": 1, "task_id": TX}, timeout=30).status_code == 201,
      "(f) R4 F3: carl's request reports usage on the stork task")
for grp, key, secret in (("task", "title", "Secret crane budget"), ("list", "name", "Project two")):
    r = requests.get(V + "/agent/usage", headers=XH, params={"group": grp}, timeout=30)
    rows = r.json().get("data", []) if r.ok else []
    check(r.ok and rows and all(d.get(key) is None for d in rows) and secret not in r.text,
          f"(f) R4 F3: GET /agent/usage?group={grp} with the long-lived token names no {key} {r.status_code} {r.text[:200]}")
r = requests.get(V + "/agent/usage", headers=hdr(RC), params={"group": "task"}, timeout=30)
check(r.ok and "Open stork task" in r.text and "Secret crane budget" not in r.text,
      f"(f) R4 F3: carl's request token reads the title of the task he sees, never the other {r.status_code} {r.text[:200]}")

# ---- (e) the card of rita's order, run with the agent's own token (the replay of an approved request)
# 2.1386.0 (#6668): since 2.1284.0 (#6453, review G13) a Yes to a write into a wider circle (project one is read by more
# people than project two) counts only from a person who reads every place the agent reads: carl (project one only) is
# refused, bob (both projects) approves and the step runs with the agent's own token.
# 2.1433.0 (#7142): the agent has no control level and counts as "free" for the circle rule: a card to a person who does not
# read every place it reads is itself a message into a wider circle (409, review G12). Such a card goes to bob (reads both
# projects) and the Yes is written as the other person's (as tests/p6453_circle_test.py G13): the run checks whose Yes it is.


def card_as(who, title, step, why):
    r = requests.post(V + f"/agent/chats/{uid[who]}", headers=XH, json={"approval": {"title": title, "step": step}}, timeout=30)
    check(r.status_code == 409 and err(r).get("circle") == "wider" and err(r).get("step") == "meta",
          f"{why}: a card to {who} (does not read every place of the agent) is a message into a wider circle {r.status_code} {r.text[:200]}")
    m = requests.post(V + f"/agent/chats/{uid['bob']}", headers=XH, json={"approval": {"title": title, "step": step}}, timeout=30)
    check(m.status_code == 201, f"{why}: its own token sends the card (its channel) {m.status_code} {m.text[:200]}")
    mid = m.json().get("id")
    from datetime import datetime, timezone
    dbx("UPDATE agent_chat SET choice=? WHERE id=?", (json.dumps({"ids": ["yes"], "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                                                                  "user_id": uid[who]}), mid))
    return mid


MID = card_as("carl", "Comment for Rita?", STEP, "(e)")
r = requests.post(V + f"/agent/approvals/{MID}/run", headers=XH, timeout=60)
check(r.status_code == 409 and err(r).get("code") == "approval_invalid" and err(r).get("reason") == "approver_rights",
      f"(e) carl's Yes runs nothing in the wider circle (#6453: he does not read project two) {r.status_code} {r.text[:300]}")
m = requests.post(V + f"/agent/chats/{uid['bob']}", headers=XH, json={"approval": {"title": "Comment for Rita?", "step": STEP}}, timeout=30)
check(m.status_code == 201, f"(e) a card to bob {m.status_code} {m.text[:200]}")
MID = m.json().get("id")
check(Bo.post(B + f"/api/agents/{XT}/chat/{MID}/choice", json=apv_body(Bo, B, f"chat:{MID}", "yes")).ok, "(e) bob (reads both projects) says Yes")
r = requests.post(V + f"/agent/approvals/{MID}/run", headers=XH, timeout=60)
check(r.status_code == 201 and dbx("SELECT COUNT(*) FROM obj_comments WHERE kind='task' AND ref_id=? AND body='FOR-RITA'", (TX,)) == [(1,)],
      f"(e) the approved step runs with the agent's own token (the replay) {r.status_code} {r.text[:300]}")

# ---- (i) review F3: the step of a card with the own token always checks the person who said Yes (no control level chosen)
# Without the fix a Yes of a reader ran with the agent's whole reach (a card's step is always a change: approval.step).
MID = card_as("rita", "Comment by Rita's Yes?", {"method": "POST", "path": f"/api/v1/tasks/{TX}/comments", "body": {"body": "RITA-SAID-YES"}}, "(i)")
r = requests.post(V + f"/agent/approvals/{MID}/run", headers=XH, timeout=60)
check(r.status_code == 409 and err(r).get("reason") in ("approver_rights", None) and err(r).get("code") == "approval_invalid",
      f"(i) the reader's Yes runs no change in project one {r.status_code} {r.text[:200]}")
check(not dbx("SELECT 1 FROM obj_comments WHERE kind='task' AND ref_id=? AND body='RITA-SAID-YES'", (TX,)), "(i) ... nothing written")

# ---- (j) second review F1: a card's "meta" step (no card check in ctl_gate) with the own token stays outside its channel
# Without the fix the long-lived token reached e.g. POST /tasks/brief through any answered card (req_main_gate lets a card's
# write through, ctl_gate stepped out for meta before checking the card).
BRIEF = {"method": "POST", "path": "/api/v1/tasks/brief", "body": {"task_ids": [TX]}}
m = requests.post(V + f"/agent/chats/{uid['bob']}", headers=XH, json={"approval": {"title": "Brief?", "step": BRIEF}}, timeout=30)
check(m.status_code == 201, f"(j) a card with the step POST /tasks/brief to bob {m.status_code} {m.text[:200]}")
check(Bo.post(B + f"/api/agents/{XT}/chat/{m.json().get('id')}/choice", json=apv_body(Bo, B, f"chat:{m.json().get('id')}", "yes")).ok, "(j) bob says Yes")
r = requests.post(V + f"/agent/approvals/{m.json().get('id')}/run", headers=XH, timeout=60)
check(r.status_code == 403 and err(r).get("code") == "request_token_needed",
      f"(j) the meta step of a card with the own token: 403 request_token_needed {r.status_code} {r.text[:300]}")
r = requests.post(V + "/tasks/brief", headers=hdr(RC), json={"task_ids": [TX]}, timeout=30)
check(r.ok, f"(j) ... with the request token of carl's order the brief stays allowed {r.status_code} {r.text[:200]}")

# ---- (p) #6978 F5: a card's step with the own token holds the route classes of the person who said Yes (as her request token)
# Without the fix the step of POST /folders/rename (class closed: only an admin of the agent's organisation) went past the
# class check with the Yes of carl (a member, no admin) -- his own request token gets 403 run_closed there.
REN = {"method": "POST", "path": "/api/v1/folders/rename", "body": {"old": "F6978-A", "new": "F6978-B"}}
r = requests.post(V + "/folders/rename", headers=hdr(RC), json=REN["body"], timeout=30)
check(r.status_code == 403 and err(r).get("code") == "run_closed",
      f"(p) F5: carl's request token: POST /folders/rename is 403 run_closed {r.status_code} {r.text[:200]}")
MID = card_as("carl", "Rename the folder?", REN, "(p) F5")
r = requests.post(V + f"/agent/approvals/{MID}/run", headers=XH, timeout=60)
check(r.status_code == 403 and err(r).get("code") == "run_closed",
      f"(p) F5: the card's step with the own token is 403 run_closed for carl's Yes, as his request token {r.status_code} {r.text[:300]}")
check(dbx("SELECT choices->'approval'->>'used_at' FROM agent_chat WHERE id=?", (MID,)) == [(None,)], "(p) F5: ... the card stays unused")
m = requests.post(V + f"/agent/chats/{uid['bob']}", headers=XH, json={"approval": {"title": "Rename the folder?", "step": REN}}, timeout=30)
check(m.status_code == 201, f"(p) F5: the same card to bob {m.status_code} {m.text[:200]}")
MID = m.json().get("id")
check(Bo.post(B + f"/api/agents/{XT}/chat/{MID}/choice", json=apv_body(Bo, B, f"chat:{MID}", "yes")).ok, "(p) F5: bob (admin of the organisation) says Yes")
r = requests.post(V + f"/agent/approvals/{MID}/run", headers=XH, timeout=60)
check(err(r).get("code") != "run_closed", f"(p) F5: bob's Yes passes the class check (an admin reaches it himself) {r.status_code} {r.text[:300]}")

# ================================================================ (c) an event without a person
payload = {"id": str(uuid.uuid4()), "event": "followup_due", "agent_id": XT, "actor": None, "via": "web",
           "data": {"task": {"id": TX, "list_id": X1}, "list_id": X1, "note": "NOBODY-ASKS"}}
SN = dbx("INSERT INTO agent_events(agent_id, uuid, event, payload, created_at) VALUES(?,?,?,CAST(? AS jsonb),now()) RETURNING id",
         (XT, payload["id"], "followup_due", json.dumps(payload)))[0][0]
r = ask([SN])
check(r.ok and r.json().get("asked_by") is None and r.json().get("list_ids") == [X1], f"(c) a request token without a person: its project only {r.status_code} {r.text[:200]}")
RN = r.json().get("token") or ""
check(dbx("SELECT asked_by FROM api_tokens WHERE user_id=? AND asked_by=0", (XT,)) == [(0,)], "(c) the token row: a request without a person (0)")
check(requests.get(V + f"/tasks/{TX}", headers=hdr(RN), timeout=30).ok, "(c) reads the task of its project")
check(requests.get(V + f"/tasks/{SX}", headers=hdr(RN), timeout=30).status_code == 404, "(c) the other project 404")
r = requests.post(V + f"/tasks/{TX}/comments", headers=hdr(RN), json={"body": "FROM-NOBODY"}, timeout=30)
check(r.status_code == 409 and err(r).get("code") == "approval_required", f"(c) every change is a card (no control level chosen) {r.status_code} {r.text[:200]}")
check(not dbx("SELECT 1 FROM obj_comments WHERE kind='task' AND ref_id=? AND body='FROM-NOBODY'", (TX,)), "(c) ... nothing written")
dbx("UPDATE agent_events SET created_at=now() - interval '25 hours' WHERE id=?", (SN,))
r = ask([SN])
check(r.status_code == 404 and err(r).get("code") == "event_gone", f"(c) review F4: an event older than 24 h gives no request token {r.status_code}")

# ================================================================ (d) what is refused
r = ask([SC, SR])
check(r.status_code == 400 and err(r).get("code") == "several_people", f"(d) events of two people: 400 {r.status_code} {r.text[:160]}")
r = requests.post(V + "/agent/request-token", headers=hdr(RC), json={"seqs": [SC]}, timeout=30)
check(r.status_code == 403 and err(r).get("code") == "request_token_main", f"(d) a request token asks for no other one {r.status_code}")
r = Ca.post(B + "/api/v1/agent/request-token", json={"seqs": [SC]})
check(r.status_code in (401, 403), f"(d) a person (no agent) gets none {r.status_code}")
r = ask([SC + 100000])
check(r.status_code == 404 and err(r).get("code") == "event_gone", f"(d) an unknown event 404 {r.status_code}")
r = A.post(B + "/api/admin/agents", json={"scopes": SCOPES, "username": "otherbot", "display_name": "Other Bot", "org_id": ORG})
check(r.status_code == 201, f"setup: another team agent {r.status_code}")
YT, YH = r.json().get("id"), {"Authorization": "Bearer " + r.json().get("token", "")}
r = requests.post(V + "/agent/request-token", headers=YH, json={"seqs": [SC]}, timeout=30)
check(r.status_code == 404 and not r.json().get("token"), f"(d) another agent gets no token for this agent's event (404) {r.status_code}")
r = requests.post(V + "/agent/request-token", headers=YH, json={"seqs": []}, timeout=30)
check(r.status_code == 400, f"(d) no event: 400 {r.status_code}")
check(dbx("SELECT per_request FROM agents WHERE user_id=?", (YT,)) == [(False,)],
      "(d) review F5: refused asks never switch an agent to per request (only an issued request token does)")
# 2.1432 (#6808): the hint in Settings > Agents -- a team agent that never asked names the day (KALMIDO_REQ_MAIN_FROM,
# default 2027-01-01) from which its own token reaches only its channel; one that asked (XT) needs none
AGS = {a["id"]: a for a in A.get(B + "/api/admin/agents").json().get("agents", [])}
check(AGS.get(YT, {}).get("req_main_due") == "2027-01-01" and AGS.get(XT, {}).get("req_main_due") is None,
      f"(d) #6808: the admin list names the day on the agent that never asked {AGS.get(YT, {}).get('req_main_due')!r} {AGS.get(XT, {}).get('req_main_due')!r}")
check(requests.get(V + "/tasks", headers=YH, params={"limit": 5}, timeout=30).ok,
      "(d) #6808: before that day its own token keeps its whole reach (transition)")
r = ask(None, operator=True)
check(r.status_code == 409 and err(r).get("code") == "no_operator", f"(d) nobody chosen for its questions: 409 {r.status_code} {r.text[:160]}")
r = ask([])
check(r.status_code == 400, f"(d) no event: 400 {r.status_code}")
dbx("UPDATE api_tokens SET expires_at=now() - interval '1 minute' WHERE user_id=? AND asked_by=?", (XT, uid["carl"]))
r = requests.get(V + f"/tasks/{TX}", headers=hdr(RC), timeout=30)
check(r.status_code == 401, f"(d) carl's expired request token is refused {r.status_code}")
r = ask([SC])
check(r.ok and not dbx("SELECT 1 FROM api_tokens WHERE user_id=? AND asked_by=? AND expires_at<now()", (XT, uid["carl"])),
      "(d) the next ask clears the expired request tokens")
XA = [a for a in A.get(B + "/api/admin/agents").json().get("agents", []) if a.get("id") == XT]
check(XA and XA[0].get("tokens") and not any(t.get("name") == "Agent request" for t in XA[0]["tokens"]),
      "(d) request tokens are not listed with the agent's tokens")
# #6978 F7: a request token is known by its columns (asked_by + its place), never by its name: a long-lived token named
# "Agent request" is listed and can be removed like any other (without the fix it was hidden and refused: invisible, unremovable)
FAKE = dbx("""INSERT INTO api_tokens(user_id, name, token_hash, prefix, scopes, created_at)
              SELECT user_id, 'Agent request', 'p6978-f7-not-a-hash', 'abk_p6978f7', scopes, created_at FROM api_tokens
              WHERE user_id=? AND asked_by IS NULL ORDER BY id LIMIT 1 RETURNING id""", (XT,))
FID7 = FAKE[0][0] if FAKE else 0
check(FID7, "(d) #6978 F7: a long-lived token of the agent named like a request token")
XA2 = [a for a in A.get(B + "/api/admin/agents").json().get("agents", []) if a.get("id") == XT]
check(XA2 and any(t.get("id") == FID7 for t in XA2[0]["tokens"]), "(d) #6978 F7: ... it is listed with the agent's tokens")
r = A.delete(B + f"/api/admin/agents/{XT}/machines/{FID7}")
check(r.ok and not dbx("SELECT 1 FROM api_tokens WHERE id=?", (FID7,)), f"(d) #6978 F7: ... and removed as a computer {r.status_code} {r.text[:160]}")
check(requests.get(V + f"/tasks/{TX}", headers=hdr(RC), timeout=30).status_code == 401, "(d) #6978 F7: removing it ends the agent's request tokens (as every computer)")
r = ask([SR])
RR = r.json().get("token") or "" if r.ok else ""
check(r.ok and RR, f"(d) rita asks anew {r.status_code}")
r = ask([SC])
RC = r.json().get("token") or "" if r.ok else ""
check(r.ok and RC, f"(d) carl asks anew {r.status_code}")

# ================================================================ (l) F4: a locked person gets no request token
RC2 = r.json().get("token") or ""
check(requests.get(V + f"/tasks/{TX}", headers=hdr(RR), timeout=30).ok, "(l) rita's request token works before the lock")
check(A.patch(B + f"/api/users/{uid['rita']}", json={"disabled": True}).ok, "(l) the admin locks rita")
r = ask([SR])
check(r.status_code == 403 and err(r).get("code") == "no_order" and not r.json().get("token"),
      f"(l) F4: rita's event gives no request token while her account is locked {r.status_code} {r.text[:160]}")
# review F3: the request token she already gave stops at once (without the fix it worked on with her rights for up to 8 hours)
# #6978 F6: the lock deletes it (asked_by = rita) -- it never comes back with an unlock (401 instead of the 403 no_order before)
r = requests.get(V + f"/tasks/{TX}", headers=hdr(RR), timeout=30)
check(r.status_code == 401, f"(l) F3 / #6978 F6: rita's request token stops with the lock {r.status_code} {r.text[:160]}")
check(not dbx("SELECT 1 FROM api_tokens WHERE asked_by=? AND req_slot<>''", (uid["rita"],)), "(l) #6978 F6: the lock deleted rita's request tokens")
check(requests.get(V + f"/tasks/{TX}", headers=hdr(RC2), timeout=30).ok, "(l) F3: carl's request token goes on")
check(A.patch(B + f"/api/users/{uid['rita']}", json={"disabled": False}).ok, "(l) the admin unlocks rita")
check(requests.get(V + f"/tasks/{TX}", headers=hdr(RR), timeout=30).status_code == 401, "(l) #6978 F6: unlocked, her old request token stays gone")
r = ask([SR])
RR = r.json().get("token") or "" if r.ok else ""
check(r.ok and RR and requests.get(V + f"/tasks/{TX}", headers=hdr(RR), timeout=30).ok, f"(l) #6978 F6: unlocked, she gets a new one {r.status_code}")
# #6978 F6: a role in the agent's organisation that gives no orders (guest) ends her request tokens of its agents at once
check(A.put(B + f"/api/orgs/{ORG}/members", json={"user_id": uid["rita"], "role": "guest"}).ok, "(l) #6978 F6: rita becomes a guest")
check(requests.get(V + f"/tasks/{TX}", headers=hdr(RR), timeout=30).status_code == 401, "(l) #6978 F6: a guest's request token is gone (401)")
check(requests.get(V + f"/tasks/{TX}", headers=hdr(RC2), timeout=30).ok, "(l) #6978 F6: carl's request token goes on")
check(A.put(B + f"/api/orgs/{ORG}/members", json={"user_id": uid["rita"], "role": "member"}).ok, "(l) rita is a member again")
check(A.patch(B + f"/api/users/{uid['rita']}", json={"disabled": True}).ok, "(l) the admin locks rita again")

# ================================================================ (n) review F4: the dispatcher's place is its own
# Without the fix bob's chat run (bob is chosen for the agent's questions) ended the token of the starter's list work (401).
check(A.patch(B + f"/api/admin/agents/{XT}", json={"runtime": {"perm_user": uid["bob"]}}).ok, "(n) bob answers the agent's questions")
r = ask(None, operator=True)
OPT = r.json().get("token") or "" if r.ok else ""
check(r.ok and OPT and r.json().get("asked_by") == uid["bob"], f"(n) the list work's token for bob {r.status_code} {r.text[:160]}")
check(Bo.post(B + f"/api/tasks/{TX}/comments", json={"body": f"<@{XT}> BOB-ASKS"}).ok, "(n) bob mentions the agent")
r = ask([seq_of("BOB-ASKS")])
RBT = r.json().get("token") or "" if r.ok else ""
check(r.ok and RBT and RBT != OPT, f"(n) a run token for bob {r.status_code}")
check(requests.get(V + f"/tasks/{SX}", headers=hdr(OPT), timeout=30).ok and requests.get(V + f"/tasks/{SX}", headers=hdr(RBT), timeout=30).ok,
      "(n) F4: both work -- bob's chat run does not end the list work's token")
MAIN = dbx("SELECT id FROM api_tokens WHERE user_id=? AND name<>'Agent request' AND asked_by IS NULL", (XT,))
check(sorted(x[0] for x in dbx("SELECT req_slot FROM api_tokens WHERE user_id=? AND asked_by=?", (XT, uid["bob"]))) ==
      sorted(["op:%s" % MAIN[0][0], "run:%s" % MAIN[0][0]]) if MAIN else False, "(n) F4: the places are kind + the asking computer")
r = ask(None, operator=True)
check(r.ok and requests.get(V + f"/tasks/{SX}", headers=hdr(OPT), timeout=30).status_code == 401
      and requests.get(V + f"/tasks/{SX}", headers=hdr(RBT), timeout=30).ok, "(n) a new list-work token replaces only the older list-work token")
# review R3 F9: choosing another person for the agent's questions ends the list-work token of the one before at once
# (without the fix bob's token worked on for up to 8 hours although carl was chosen now)
OPB = r.json().get("token") or "" if r.ok else ""
r = A.patch(B + f"/api/admin/agents/{XT}", json={"runtime": {"perm_user": uid["carl"]}})
check(r.ok, f"(n) R3 F9: carl answers the agent's questions now {r.status_code} {r.text[:160]}")
check(requests.get(V + f"/tasks/{TX}", headers=hdr(OPB), timeout=30).status_code == 401,
      "(n) R3 F9: bob's list-work token ends with the change (401)")
check(requests.get(V + f"/tasks/{SX}", headers=hdr(RBT), timeout=30).ok, "(n) R3 F9: bob's run token stays (only the list work's place)")
r = ask(None, operator=True)
check(r.ok and r.json().get("asked_by") == uid["carl"], f"(n) R3 F9: the next list-work token is carl's {r.status_code}")

# ================================================================ (h) review F2: removing the computer ends its request tokens
# Without the fix the request tokens fetched with a removed computer's token lived on for up to 8 h, unlisted and unrevocable.
check(requests.get(V + f"/tasks/{TX}", headers=hdr(RC2), timeout=30).ok, "(h) carl's new request token works")
MT = [t["id"] for t in XA[0]["tokens"]] if XA else []
check(len(MT) == 1, f"(h) the agent has one computer (its own token) {MT}")
r = A.delete(B + f"/api/admin/agents/{XT}/machines/{MT[0] if MT else 0}")
check(r.ok, f"(h) the admin removes the computer {r.status_code} {r.text[:160]}")
check(requests.get(V + f"/tasks/{TX}", headers=hdr(RC2), timeout=30).status_code == 401,
      "(h) the request token fetched with it is refused (401)")
check(not dbx("SELECT 1 FROM api_tokens WHERE user_id=? AND name='Agent request'", (XT,)), "(h) no request token of the agent is left")

# ================================================================ the person without an organisation loses nothing
r = Fr.post(B + "/api/my/agents", json={"username": "fridabot", "display_name": "Fridabot", "scopes": SCOPES})
check(r.status_code in (200, 201), f"freelancer: her personal agent {r.status_code} {r.text[:160]}")
FA, FH = r.json()["id"], {"Authorization": "Bearer " + r.json()["token"]}
FL = Fr.post(B + "/api/lists", json={"name": "Frida work"}).json()["id"]
check(Fr.put(B + f"/api/lists/{FL}/members", json={"user_id": FA, "role": "edit"}).ok, "freelancer: her project is shared with her agent")
FT = Fr.post(B + "/api/tasks", json={"title": "Frida's task", "list_id": FL}).json()["id"]
r = requests.post(V + "/agent/request-token", headers=FH, json={"seqs": [1]}, timeout=30)
check(r.ok and r.json().get("token") is None and r.json().get("asked_by") == FID, f"freelancer: her personal agent needs no request token {r.status_code} {r.text[:160]}")
check(dbx("SELECT per_request FROM agents WHERE user_id=?", (FA,)) == [(False,)], "freelancer: her agent does not switch to per request")
check(requests.get(V + f"/tasks/{FT}", headers=FH, timeout=30).ok, "freelancer: her agent's own token reaches her project as before")
r = requests.post(V + f"/tasks/{FT}/comments", headers=FH, json={"body": "from her agent"}, timeout=30)
check(r.status_code == 201, f"freelancer: her agent comments in her project {r.status_code} {r.text[:160]}")

# ================================================================ (q) #6808: after the transition day every team agent
# The same data, the server started again with KALMIDO_REQ_MAIN_FROM in the past: the other team agent (YT) never asked
# for a request token -- without #6808 its own token kept the whole reach (GET /tasks 200, GET /agent/chats 200).
if fresh(env={"KALMIDO_REQ_MAIN_FROM": "2000-01-01"}, prefix="P6668", keep=True):
    check(dbx("SELECT per_request FROM agents WHERE user_id=?", (YT,)) == [(False,)], "(q) #6808: the agent never asked")
    for path in ("/tasks", "/agent/chats"):
        r = requests.get(V + path, headers=YH, timeout=30)
        check(r.status_code == 403 and err(r).get("code") == "request_token_needed",
              f"(q) #6808: after the day its own token gets no {path} (request_token_needed) {r.status_code} {r.text[:120]}")
    check(requests.get(V + "/agent/events", headers=YH, params={"since": 0}, timeout=30).ok
          and requests.put(V + "/agent/status", headers=YH, json={"status": "idle"}, timeout=30).ok,
          "(q) #6808: ... its channel stays (events, status)")
    A = sess("alice")
    AGS = {a["id"]: a for a in A.get(B + "/api/admin/agents").json().get("agents", [])}
    check(YT in AGS and AGS[YT].get("req_main_due") is None, "(q) #6808: the day has passed: no hint any more")
    check(requests.get(V + f"/tasks/{FT}", headers=FH, timeout=30).ok,
          "(q) #6808: a personal agent (the person without an organisation) keeps its owner's reach")
else:
    print("(q) #6808: skipped -- a running server (KMT_NOSTART / P6668_NOSTART) cannot be started with KALMIDO_REQ_MAIN_FROM")

raise SystemExit(done("p6668_ext_team_agent"))
