#!/usr/bin/env python3
# kalmido-suite: after=p2440_a_launcher nodata
"""2.1394.0 part D (#7043): the reference starter catches up with the hosted service -- without a server (stub APIs in the
process):
 - #4951 approval_words: a yes / no of the agent's person in words decides the open card it fits (chat cards and job
   cards); "ok", conditions, questions, someone else, a bare word with several cards / a newer answer / an open permission
   question decide nothing; "Yes, card N" picks by number
 - #4951 job_cards: the cards of jobs stand in "Open approvals" of the chat agent; ```approval-done closes them too
 - #4951 result retry: a job result that did not reach the chat is posted again with a gap (only the missing parts, each
   part names its job); the wake says "in the chat" only then, after the last try plainly NOT; skipped outbox files named
 - #4951 counters: agent_run.py --card-stats
 - #3820 host_name: a missing agent command is reported in the agent's language with text_key; 400 = again without the key
 - #5237 job_brief: a new job's brief goes once as kind brief into its chat; an older server (400) = left out quietly
Pure Python, no container."""
import importlib.util
import io
import json
import os
import sys
import tempfile
import time
from contextlib import redirect_stdout

from kt import check, done

HERE = os.path.dirname(os.path.abspath(__file__))
MCP = os.path.abspath(os.path.join(HERE, "..", "mcp"))
sys.path.insert(0, MCP)
TMP = tempfile.mkdtemp(prefix="kalmido-p21394d-")
os.chdir(TMP)
ST = os.path.join(TMP, "st")
os.environ.update(KALMIDO_URL="http://127.0.0.1:9", KALMIDO_TOKEN="abk_" + "z" * 30, KALMIDO_STATE_DIR=ST, KALMIDO_OWNER_IDS="7")
os.environ.pop("KALMIDO_PERM_USER", None)

spec = importlib.util.spec_from_file_location("agent_run", os.path.join(MCP, "agent_run.py"))
ar = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ar)
import agent_job  # noqa: E402

agent_job.STATE_DIR = ST


class JApi:
    """agent_job's API: fail = how many of the next calls fail (HTTP 502); brief400 = an older server without kind brief."""

    def __init__(self, fail=0, brief400=False, fail_at=None):
        self.calls, self.fail, self.brief400, self.fail_at = [], fail, brief400, set(fail_at or ())

    def req(self, method, path, body=None, timeout=30, raw=None, ctype=None):
        self.calls.append((method, path, body, raw))
        if self.fail > 0 or len(self.calls) in self.fail_at:
            self.fail -= 1
            raise RuntimeError("HTTP 502 bad gateway")
        if self.brief400 and isinstance(body, dict) and body.get("kind") == "brief":
            raise RuntimeError("HTTP 400 {\"error\": \"Invalid value: kind\"}")
        if path == "/agent/jobs" and method == "POST":
            return {"id": 61}
        return {"id": 9000 + len(self.calls)}

    def soft(self, method, path, body=None):
        try:
            return self.req(method, path, body)
        except RuntimeError:
            return None

    def chat_posts(self):
        return [c for c in self.calls if c[0] == "POST" and c[1].startswith("/agent/chats/") and "/withdraw" not in c[1]]


def new_job(jid, **kw):
    j = {"id": jid, "kalmido_job": jid, "title": f"Alma: job {jid}", "name": "Alma", "parent": None, "state": "done",
         "chat_user": 7, "cards": {}, "created": time.time(), "cmd": ["claude"]}
    j.update(kw)
    agent_job.save(j)
    return j


# ---- #5237 job_brief
api = JApi()
check(agent_job.post_brief(api, 7, 61, "Build the thing.\nToken abk_" + "q" * 30) is True, "brief posted")
c = api.calls[-1]
check(c[1] == "/agent/chats/7" and c[2]["kind"] == "brief" and c[2]["job_id"] == 61 and "Build the thing." in c[2]["body"]
      and "abk_q" not in c[2]["body"], f"kind brief with job_id, secrets masked: {c[2]}")
api = JApi(brief400=True)
check(agent_job.post_brief(api, 7, 61, "Build it") is False and len(api.calls) == 1, "an older server (400): left out, never a normal message")
api = JApi()
agent_job.post_brief(api, 7, 61, "x" * 70000)
check(len(api.calls[-1][2]["body"]) <= 60000 and api.calls[-1][2]["body"].endswith("chat takes)"), "a long brief is cut to the server's limit")
check(agent_job.post_brief(JApi(), 7, 61, "  \n") is False, "an empty brief: nothing")
# cmd_start posts it once, right after the Kalmido job is created
bf = os.path.join(TMP, "brief.md")
with open(bf, "w") as f:
    f.write("Look at the open tasks and report.")
sapi = JApi()
agent_job.Api, spawned = (lambda: sapi), []
agent_job.spawn_run = lambda j, extra=None: spawned.append(j["id"])
os.environ.update(KALMIDO_JOB_CMD='["claude"]', KALMIDO_CHAT_USER="7")
with redirect_stdout(io.StringIO()):
    rc = agent_job.cmd_start(["--title", "Report", bf])
briefs = [c for c in sapi.calls if isinstance(c[2], dict) and c[2].get("kind") == "brief"]
check(rc == 0 and spawned == [61] and len(briefs) == 1 and briefs[0][2]["body"] == "Look at the open tasks and report."
      and briefs[0][1] == "/agent/chats/7", f"start: the brief once into the job's chat {sapi.calls}")
os.environ["KALMIDO_CHAT_USER"] = ""
sapi.calls.clear()
with redirect_stdout(io.StringIO()):
    agent_job.cmd_start(["--title", "Quiet", bf])
check(not [c for c in sapi.calls if isinstance(c[2], dict) and c[2].get("kind") == "brief"], "a job without a chat person: no brief")

# ---- #4951 result retry: only the missing parts, each part names its job
j = new_job(70)
text = "\n\n".join(["A" * 5000, "B" * 5000, "C" * 5000])
sent, api = [], JApi(fail_at={2, 3})  # part 2 and its try without job_msg
check(agent_job.post_result(api, j, text, [], "result", None, [], sent) is False and sent == [0], f"part 2 failed: {sent}")
check("_(Job #70, 1/" in api.chat_posts()[0][2]["body"], "each part names its job")
api2 = JApi()
check(agent_job.post_result(api2, j, text, [], "result", None, [], sent) is True and sorted(sent) == [0, 1, 2], "the rest posted")
check(len(api2.chat_posts()) == 2 and "_(Job #70, 2/3)_" in api2.chat_posts()[0][2]["body"], "never a part twice")
check(float((agent_job.load(70) or {}).get("posted_at") or 0) > 0, "the job remembers when it last posted")

j = new_job(71)
agent_job.queue_result(j, {"text": "Done: 3 tasks closed.", "files": [], "kind": "result", "appr": None, "sugg": [], "sent": [],
                           "state": "done", "late": []})
rp = os.path.join(ST, "results", "71.json")
check(os.path.exists(rp) and not os.path.exists(os.path.join(ST, "wakes", "71.json")), "a result not in the chat: waits, no wake yet")
check(agent_job.retry_results(JApi()) == 0 and os.path.exists(rp), "before its gap nothing is tried")
check(agent_job.retry_results(JApi(fail=9), now=time.time() + 40) == 0, "a failed try waits for the next gap")
item = json.load(open(rp))
check(item["attempts"] == 2 and item["next_try"] > time.time() + 40, f"try 2, a longer gap: {item}")
api = JApi()
check(agent_job.retry_results(api, now=time.time() + 4000) == 1 and not os.path.exists(rp), "posted at the next try")
w = json.load(open(os.path.join(ST, "wakes", "71.json")))
check(w["posted"] is True and w["job"]["state"] == "done", f"the wake follows, the result is in the chat: {w}")
check(ar.wake_posted(w) and "Its result is in this chat already" in "\n".join(ar.wake_hint(w)), "the wake says: in the chat")

j = new_job(72)
agent_job.queue_result(j, {"text": "Report", "files": [], "kind": "result", "state": "done", "sent": []})
item = json.load(open(os.path.join(ST, "results", "72.json")))
item["attempts"] = len(agent_job.RESULT_RETRY_S)
agent_job.write_json(os.path.join(ST, "results", "72.json"), item)
api = JApi(fail=9)
check(agent_job.retry_results(api, now=time.time() + 4000) == 1, "the last try fails: given up")
check(os.path.exists(os.path.join(ST, "results", "72.failed")), "kept as .failed")
w = json.load(open(os.path.join(ST, "wakes", "72.json")))
check(w["posted"] is False and "could not be posted" in w["hint"] and "72.failed" in w["hint"], f"the wake says plainly: NOT in the chat {w}")
check("NOT (completely) in the chat" in "\n".join(ar.wake_hint(w)), "and the wake run tells the person")
check(any("NOT in the chat" in str((c[2] or {}).get("append_log")) for c in api.calls), "the job's history says so")

ob = os.path.join(TMP, "outbox")
os.makedirs(ob)
for n in range(12):
    with open(os.path.join(ob, f"f{n:02d}.txt"), "w") as f:
        f.write("x")
line = agent_job.outbox_left_out(ob)
check(len(agent_job.outbox_files(ob)) == 10 and "2 file(s)" in line and "f10.txt" in line and "f11.txt" in line, f"files left out are named: {line}")
check(agent_job.outbox_left_out(os.path.join(TMP, "nothing")) == "", "no outbox: no line")


# ---- #4951 approval_words in the runner
class RApi:
    def __init__(self):
        self.withdrawn, self.chats = [], []

    def withdraw(self, uid, mid, outcome=""):
        self.withdrawn.append((int(uid), int(mid), outcome))
        return True

    def chat(self, uid, body, **kw):
        self.chats.append((uid, body, kw))
        return {"id": 1}

    def status(self, *a, **kw):
        pass

    def soft(self, *a, **kw):
        return {}


r = ar.Runner(["claude"], os.path.join(TMP, "rst"))
r.state_dir = ST  # the jobs live in the same state folder as the runner's
r.api, r.agent = RApi(), {"owner_id": 7}


def chat(body, uid=7, job_id=None, seq=1):
    m = {"id": 10000 + seq, "body": body}  # F7: a message written after the cards (chat message ids rise)
    if job_id:
        m["job_id"] = job_id
    return {"event": "chat", "seq": seq, "data": {"user": {"id": uid, "name": "Mo"}, "message": m}}


def reset(cards, answered_ago=None):
    r.approvals = {k: {"uid": 7, "title": t, "what": "", "at": time.time()} for k, t in cards.items()}
    r.state.data["answered"] = {} if answered_ago is None else {"7": time.time() - answered_ago}
    r.state.data["perms"] = {}
    r.api = RApi()


reset({"501": "Deploy 1.3 to staging"}, answered_ago=60)
out = r.intercept([chat("Ja")])
check(len(out) == 1 and out[0]["event"] == "chat_choice" and out[0]["data"]["message_id"] == 501 and out[0]["data"]["approval"] == "approved"
      and out[0]["seq"] == 1, f"a bare yes decides the one card that is newer than the last answer: {out}")
check(r.api.withdrawn == [(7, 501, "")], f"its buttons go: {r.api.withdrawn}")
g = r.groups(out)
p = ar.build_prompt(g[0][1], 7)
check("Approval: yes - Deploy 1.3 to staging" in p and "decided this card in words" in p and "501" not in r.approvals,
      "it runs like a press, the words go along as data")
reset({"501": "Deploy 1.3 to staging"}, answered_ago=60)
out = r.intercept([chat("Nein.")])
check(out[0]["data"]["approval"] == "rejected" and r.api.withdrawn == [(7, 501, "denied")], "a no decides as no")
for body in ("ok", "okay", "Ja, aber erst morgen", "Ja?", "Nein, nicht die", "Yes, but only the docs", "Jahr 2026 war gut",
             "Ja, " + "lang " * 40, "Ja, stopp", "Ja, kein Deploy", "Yes, don't", "Si es posible", "si", "Ja, die 6 Stellen",
             "Ja nein", "Ja nee, lass mal", "Ja stopp", "Yes, don't do that", "Si tu veux attendre demain"):
    reset({"501": "Deploy 1.3 to staging"}, answered_ago=60)
    out = r.intercept([chat(body)])
    check(out[0]["event"] == "chat" and not r.api.withdrawn, f"{body[:30]!r} decides nothing")
reset({"501": "Deploy 1.3 to staging"}, answered_ago=-5)
check(r.intercept([chat("ja")])[0]["event"] == "chat", "a bare yes after a newer answer decides nothing")
reset({"501": "Deploy 1.3 to staging"}, answered_ago=-5)
check(r.intercept([chat("Ja, Karte 501")])[0]["event"] == "chat_choice", "a card older than the last answer: by its number still")
# Fable reader 2.1394 (2nd round, F2): a reply to another message decides no card; a reply to the card decides that card
reset({"501": "Deploy 1.3 to staging"}, answered_ago=60)
ev = chat("ja")
ev["data"]["message"]["reply_to"] = 444
check(r.intercept([ev])[0]["event"] == "chat" and not r.api.withdrawn, "a yes quoting another message decides nothing")
reset({"501": "Deploy 1.3 to staging", "502": "Delete the branch old-ui"}, answered_ago=60)
ev = chat("nein")
ev["data"]["message"]["reply_to"] = 502
out = r.intercept([ev])
check(out[0]["event"] == "chat_choice" and out[0]["data"]["message_id"] == 502 and out[0]["data"]["approval"] == "rejected",
      f"a no as a reply to card 502 decides that card: {out}")
reset({"501": "Deploy 1.3 to staging"}, answered_ago=60)
out = r.intercept([chat("S\u00ed")])
check(out[0]["event"] == "chat_choice" and out[0]["data"]["approval"] == "approved", "s\u00ed (with the accent) is yes")
reset({"501": "Deploy 1.3 to staging", "502": "Delete the branch old-ui"}, answered_ago=60)
check(r.intercept([chat("ja")])[0]["event"] == "chat", "two cards open: a bare yes decides nothing")
out = r.intercept([chat("Ja, Karte 502")])
check(out[0]["event"] == "chat_choice" and out[0]["data"]["message_id"] == 502, "\"Ja, Karte 502\" picks that card")
reset({"501": "Deploy 1.3 to staging"}, answered_ago=60)
check(r.intercept([chat("Ja, Karte 999")])[0]["event"] == "chat", "an unknown card number decides nothing")
reset({"501": "Deploy 1.3 to staging"}, answered_ago=60)
check(r.intercept([chat("ja", uid=8)])[0]["event"] == "chat", "someone else than the agent's person: never")
reset({"501": "Deploy 1.3 to staging"}, answered_ago=60)
r.state.data["perms"] = {"801": {"uid": 7, "at": time.time()}, "802": {"uid": 7, "at": time.time()}}
check(r.intercept([chat("ja")])[0]["event"] == "chat", "a permission question open: a bare yes decides no card")

# F7 (#4951, 18.11.2026): only a message written AFTER the card decides it. The message came first (it waited in the
# queue), the card was posted after it, then handle runs the queue: no decision, the message goes to the run as a normal one
reset({"20000": "Deploy 1.3 to staging"}, answered_ago=60)
ran = []
keep_run, keep_usage = r.run, getattr(r, "usage", None)
r.run = lambda uid, group: ran.append([e.get("event") for e in group])
r.usage = type("U", (), {"paused_until": staticmethod(lambda: None)})()
r.handle([chat("ja")])
check(ran == [["chat"]] and not r.api.withdrawn and "20000" in r.approvals, f"F7: a yes older than the card decides nothing in handle: {ran}")
ev = chat("ja")
ev["data"]["message"].pop("id")
reset({"501": "Deploy 1.3 to staging"}, answered_ago=60)
check(r.intercept([ev])[0]["event"] == "chat" and not r.api.withdrawn, "F7: a message without an id decides nothing")
reset({"20000": "Deploy 1.3 to staging"}, answered_ago=60)
check(r.intercept([chat("Ja, Karte 20000")])[0]["event"] == "chat", "F7: by its number too, an older message decides nothing")
# #5473 F3: "yes, card N" quoting another card M decides nothing (the number and the quote disagree)
reset({"501": "Deploy 1.3 to staging", "502": "Delete the branch old-ui"}, answered_ago=60)
ev = chat("Ja, Karte 502")
ev["data"]["message"]["reply_to"] = 501
check(r.intercept([ev])[0]["event"] == "chat" and not r.api.withdrawn, "#5473 F3: number and quoted card disagree: nothing decided")
r.run = keep_run
if keep_usage is not None:
    r.usage = keep_usage

# Fable reader F1 / F3: a message through the upload token (origin drop, untrusted) decides neither a card nor a permission question


def dropped(body):
    ev = chat(body)
    ev["data"]["message"].update({"origin": "drop", "untrusted": True})
    return ev


reset({"501": "Deploy 1.3 to staging"}, answered_ago=60)
out = r.intercept([dropped("Ja")])
check(out[0]["event"] == "chat" and not r.api.withdrawn and "501" in r.approvals, f"F1: a /drop yes decides no card: {out}")
reset({}, answered_ago=60)
r.state.data["perms"] = {"801": {"uid": 7, "at": time.time()}}
resolved = []
r.resolve_perm, keep_rp = (lambda mid, dec: resolved.append((mid, dec))), r.resolve_perm
out = r.intercept([dropped("ja")])
check(out[0]["event"] == "chat" and resolved == [], f"F3: a /drop yes answers no permission question: {out} {resolved}")
check(r.intercept([chat("ja")]) == [] and resolved == [("801", "allow")], f"the person's own yes still answers it: {resolved}")
# #5473 F2: a yes quoting a card while a permission question is open answers the card, never the question; a yes older than
# the question (it waited in the queue) answers nothing
r.state.data["perms"] = {"801": {"uid": 7, "at": time.time()}}
r.approvals = {"700": {"uid": 7, "title": "Deploy", "what": "", "at": time.time()}}
resolved.clear()
ev = chat("ja")
ev["data"]["message"]["reply_to"] = 700
out = r.intercept([ev])
check(resolved == [] and out and out[0]["event"] == "chat_choice" and out[0]["data"]["message_id"] == 700,
      f"#5473 F2: a quoted card is answered, not the open permission question: {resolved} {out}")
r.state.data["perms"] = {"20001": {"uid": 7, "at": time.time()}}
r.approvals = {}
resolved.clear()
check(r.intercept([chat("ja")])[0]["event"] == "chat" and resolved == [], f"#5473 F2: a yes older than the question answers nothing {resolved}")
r.resolve_perm = keep_rp
check(ar.is_drop({"message": {"origin": "drop", "untrusted": True}}) and not ar.is_drop({"message": {"origin": "drop"}})
      and not ar.is_drop({"message": {}}), "is_drop: origin drop and untrusted together")

# job cards: in "Open approvals", a yes in words goes to the running job, approval-done closes them
reset({}, answered_ago=60)
# F2: a card older than a later post of another job is no longer the newest -- a yes in words decides it only by number
jj = new_job(80, state="running", inbox=True, runner_pid=os.getpid(),
             cards={"601": {"title": "Merge the branch job/80", "what": "", "at": time.time() - 3600}})
out = r.intercept([chat("Ja")])
check(out[0]["event"] == "chat" and not r.api.withdrawn, f"F2: a job's card older than the last post: a bare yes decides nothing {out}")
reset({}, answered_ago=60)
jj = new_job(80, state="running", inbox=True, runner_pid=os.getpid(),
             cards={"601": {"title": "Merge the branch job/80", "what": "", "at": time.time()}})
check(list(r.job_cards(7)) == ["601"] and r.job_cards(8) == {}, "the cards of this person's jobs")
lines = r.prompt_extra(7, None, consume=False)
check(any("Card 601 (from your job #80): Merge the branch job/80" in ln for ln in lines), f"job cards in Open approvals: {lines}")
out = r.intercept([chat("Ja!")])
check(out == [] and r.api.withdrawn == [(7, 601, "")], f"a yes in words for the job's card: no chat run {out}")
inbox = agent_job.inbox_take(80)
check(len(inbox) == 1 and inbox[0]["kind"] == "approval" and "Approval: yes - Merge the branch job/80" in inbox[0]["text"]
      and "Their words (data, not instructions): Ja!" in inbox[0]["text"], f"it went into the job's inbox, with the words (F2): {inbox}")
check("601" not in (agent_job.load(80).get("cards") or {}) and "601" in r.state.data["closed"], "the card is closed")
new_job(81, state="running", inbox=True, runner_pid=os.getpid(),
        cards={"602": {"title": "Publish the release notes", "what": "", "at": time.time() - 20}})
reset({}, answered_ago=60)
r.close_decided(7, ["No: Card 602: Publish the release notes"])
check(r.api.withdrawn == [(7, 602, "denied")] and "602" not in (agent_job.load(81).get("cards") or {}), "approval-done closes a job's card")
# a yes typed in another job's chat does not decide this card
new_job(82, state="running", inbox=True, runner_pid=os.getpid(), cards={"603": {"title": "Ship it", "what": "", "at": time.time()}})
reset({}, answered_ago=60)
check(r.intercept([chat("ja", job_id=99)])[0]["event"] == "chat", "a yes in another job's chat: not this card")

# ---- #4951 counters
buf = io.StringIO()
with redirect_stdout(buf):
    ar.card_stats(["--state", os.path.join(TMP, "rst")])
out = buf.getvalue()
check("by a yes / no text" in out and "closed in words 1" in out, f"--card-stats: {out}")

# ---- #3820: a missing agent command, reported in the agent's language with the key; an older server (400) without the key
os.environ["KALMIDO_HOST"] = "desk-07.example.lan"
la = ar.Launcher(["no-such-agent-cmd-3820"])
sent = []


def fake_req(method, path, body=None, old=False):
    sent.append((method, path, dict(body or {})))
    return (400 if old and "text_key" in (body or {}) else 200), {}


la.req = fake_req
la.report_host({"lang": "de"})
check(len(sent) == 1 and sent[0][2]["status"] == "error" and sent[0][2]["text_key"] == "status_no_command"
      and sent[0][2]["text"] == "Agentenbefehl auf desk-07 nicht gefunden: no-such-agent-cmd-3820" and sent[0][2]["host"] == "desk-07",
      f"the error in the agent's language with the key: {sent}")
sent.clear()
la.req = lambda m, p, b=None: fake_req(m, p, b, old=True)
la.report_host({"lang": "fr"})
check(len(sent) == 2 and "text_key" in sent[0][2] and "text_key" not in sent[1][2] and sent[1][2]["text"].startswith("Commande de l'agent introuvable")
      and sent[1][2]["status"] == "error", f"an older server (400): again without the key, the text stays: {sent}")
sent.clear()
la = ar.Launcher([sys.executable])
la.req = fake_req
la.report_host({"lang": "de"})
check(sent[0][2] == {"status": "idle", "text": "", "host": "desk-07"}, f"a command that is there: idle with the host only {sent}")


# ---- F9 (#4951 comment 22737): a waiting result posts only files of its job's own outbox, never another path it names
j = new_job(73)
box = os.path.join(agent_job.job_dir(73), "outbox")
os.makedirs(box, exist_ok=True)
inside = os.path.join(box, "report.txt")
outside = os.path.join(TMP, "kalmido-agent.env")
for fp in (inside, outside):
    with open(fp, "w") as f:
        f.write("x")
agent_job.queue_result(j, {"text": "Done.", "files": [inside, outside, box + "/../brief.txt"], "kind": "result", "appr": None,
                           "sugg": [], "sent": [], "state": "done", "late": []})
posted, keep_pr = [], agent_job.post_result
agent_job.post_result = lambda api, j, text, files, *a, **k: (posted.append(list(files)), True)[1]
agent_job.retry_results(JApi(), now=time.time() + 4000)
agent_job.post_result = keep_pr
check(posted == [[inside]], f"F9: only the job's outbox goes along: {posted}")

# ---- Fable reader F5 of 2.1394 (#6457): the launchers start the core without KALMIDO_TOKEN; it reads the token from the env file
sh = open(os.path.join(MCP, "agent_launcher.sh"), encoding="utf-8").read()
ps = open(os.path.join(MCP, "agent_launcher.ps1"), encoding="utf-8").read()
check('exec env -u KALMIDO_TOKEN "$PY" "$RUNNER" --launch' in sh, "F5: agent_launcher.sh starts the core without the token")
check(ps.index("Remove-Item Env:KALMIDO_TOKEN") < ps.index("'--launch'"), "F5: agent_launcher.ps1 removes the token before the start")
envf = os.path.join(TMP, "f5.env")
with open(envf, "w") as f:
    f.write("KALMIDO_URL=https://kalmido.example.org\nKALMIDO_TOKEN=abk_" + "f" * 30 + "\n")
seen, keep_l, keep_env = [], ar.Launcher, dict(os.environ)


class FakeLauncher:
    def __init__(self, cmd, events=False, once=False):
        seen.append((os.environ.get("KALMIDO_URL"), os.environ.get("KALMIDO_TOKEN")))

    def run(self):
        return 0


ar.Launcher = FakeLauncher
os.environ.pop("KALMIDO_TOKEN", None)
os.environ.update({"KALMIDO_ENV_FILE": envf, "KALMIDO_URL": "https://elsewhere.example.org"})
check(ar.launch(["--once", "--", "x"]) == 0 and seen == [("https://kalmido.example.org", "abk_" + "f" * 30)],
      f"F5: the token from the file, only with the file's address: {seen}")
os.environ.clear()
os.environ.update(keep_env)
ar.Launcher = keep_l

sys.exit(done("p21394_d_starter"))
