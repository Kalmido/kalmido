"""2.235.0 C (#2903): the standing rules of an agent ("from now on always ..."), visible and editable.

Kalmido never formulates for the agent: the agent itself recognises a standing instruction in a chat message or a comment,
stores it as a rule with its source (POST /api/v1/agent/rules) and confirms it in ONE line. The owner of a personal agent (a
person without an organisation is their own admin) or an instance admin (team agent) reads, rewords, pauses and deletes the
rules in the agent's settings (agents/workstyle.py ws_need_editor, everyone else 404) and may add one by hand. The agent reads
its ACTIVE rules in GET /api/v1/agent "rules" and gets the event rules_changed when a person changed them (never for its own
POST: agent_emit skips the agent's own actions).

Table agent_rules (new, additive): body, state active | paused, source kind chat | comment | manual + id (+ the task of a
comment, the person of a chat message) + a short excerpt taken from the source at creation.

2.1269.0 (#6451): a rule the AGENT stores is only a proposal (state proposed, on every control level): it never applies, is not
in GET /api/v1/agent "rules" nor in rules_changed, and GET /api/v1/agent/rules lists it apart ("proposed"). The server posts a
card into the chat of the person of the source with the agent (agent_chat kind 'rule', agent_rules.card_id): the rule's text
as the agent's words, Confirm / Reject. Only that person decides (POST /api/agents/<id>/rules/<rid>/decide, never an agent,
never through an agent route); confirmed = active + rules_changed to the agent, and the same card then offers to take the rule
back. The owner / an instance admin see proposed rules in the settings and may delete them, not confirm them. At most
AR_PROPOSED_MAX open proposals per agent."""
import re
from flask import g, jsonify

from ..core.config import app
from ..core.i18n import tr
from ..core.db import body, bump, db, iso, iso_ms, now_utc
from ..core.pg import insert_id, write_lock
from ..core.access import Denied, task_visible
from ..api.runfor import run_chat_ok  # 2.1287.0 (#6454, review F1)
from ..core.errors import BadInput, UnknownFields
from ..core.conflict import ccf_check  # 2.564.0 D (#4701)
from ..api.common import v1_args, v1_json, v1_view
from ..agents.core import agent_emit, agent_row, agent_shares, agent_usable, is_agent, need_agent
from ..agents.workstyle import ws_need_editor
from ..agents.chat import chat_add  # 2.1269.0 (#6451): the confirmation card
from ..api.common import v1_err

AR_TEXT_MAX = 500  # characters of one rule
AR_MAX = 100  # rules per agent (active + paused)
AR_EXCERPT = 120  # characters of the source kept as its excerpt
AR_STATES = ("active", "paused")  # what a person sets; 2.1269.0 (#6451): + "proposed" (stored by the agent, not in force)
AR_PROPOSED = "proposed"
AR_PROPOSED_MAX = 5  # 2.1269.0 (#6451): open proposals per agent (it cannot flood its person's chat with cards)
AR_DECISIONS = ("confirm", "reject", "withdraw")
AR_KINDS = ("chat", "comment")  # what an agent may name as the source; "manual" = added by a person in the settings
_MENTION = re.compile(r"<@(\d+)>")


def _excerpt(s):
    s = " ".join(_MENTION.sub("@", s or "").split())
    return s if len(s) <= AR_EXCERPT else s[:AR_EXCERPT - 1].rstrip() + "…"


def _text(v):
    if not isinstance(v, str) or not v.strip() or len(v.strip()) > AR_TEXT_MAX:
        raise BadInput(tr("Invalid value: {0}", "text"))
    return v.strip()


def _rows(c, aid, active_only=False):
    return c.execute("SELECT * FROM agent_rules WHERE agent_id=?" + (" AND state='active'" if active_only else "") + " ORDER BY id",
                     (aid,)).fetchall()


def _proposed(r):
    return r["state"] == AR_PROPOSED


def _source(r):
    return {"kind": r["source_kind"] or "manual", "id": r["source_id"], "task_id": r["source_task_id"],
            "user_id": r["source_user_id"]}


def ar_dict(r, excerpt=True):
    d = {"id": r["id"], "text": r["body"], "state": r["state"], "created_at": r["created_at"], "updated_at": r["updated_at"],
         "created_by": r["created_by"], "source": _source(r)}
    if excerpt:
        d["source"]["excerpt"] = r["source_excerpt"] or ""
    return d


def ar_public(c, a):
    """What agent row a reads in GET /api/v1/agent "rules" (and the event rules_changed): its ACTIVE rules, oldest first
    (paused ones are left out)."""
    return [{k: v for k, v in ar_dict(r, excerpt=False).items() if k in ("id", "text", "created_at", "source")}
            for r in _rows(c, a["user_id"], active_only=True)]


def ar_changed(c, aid, what):
    """Event rules_changed to the agent (a person changed its rules; the caller commits)."""
    a = agent_row(c, aid)
    agent_emit(c, aid, "rules_changed", {"change": what, "rules": ar_public(c, a)})
    print("agent", aid, "rules", what, "by", g.user["username"], flush=True)


def _source_of_agent(c, aid, src):
    """The checked source of a rule the agent stores: {kind: chat | comment, id} it can see -> the row values; 404 otherwise."""
    if not isinstance(src, dict) or set(src) - {"kind", "id"} or src.get("kind") not in AR_KINDS \
            or isinstance(src.get("id"), bool) or not isinstance(src.get("id"), int):
        raise BadInput(tr("Invalid value: {0}", "source"))
    sid = src["id"]
    if src["kind"] == "chat":
        m = c.execute("SELECT id, user_id, sender, body FROM agent_chat WHERE id=? AND agent_id=?", (sid, aid)).fetchone()
        # a message of a person to this agent (its own answers are no instruction), in a conversation it still has
        if not m or m["sender"] != "user" or not agent_shares(c, aid, m["user_id"]) or not run_chat_ok(m["user_id"]):
            raise Denied(404)
        return ("chat", sid, None, m["user_id"], _excerpt(m["body"]))
    m = c.execute("""SELECT k.id, k.ref_id AS task_id, k.user_id, k.body, k.ext_name, u.kind, t.list_id FROM obj_comments k
                     JOIN tasks t ON t.id=k.ref_id AND k.kind='task' LEFT JOIN users u ON u.id=k.user_id
                     WHERE k.id=? AND k.deleted_at IS NULL""", (sid,)).fetchone()
    if not m or m["user_id"] == aid or not task_visible(c, m["task_id"], aid, full=True):
        raise Denied(404)
    # 2.235.0 B2 (#2903): only a person who may address this agent in the task's project gives it a rule (no agent, no
    # customer through the approval link, no member the agent is not opened to)
    if not m["user_id"] or m["ext_name"] or m["kind"] in (None, "agent") or not agent_usable(c, aid, m["user_id"], m["list_id"]):
        raise Denied(404)
    return ("comment", sid, m["task_id"], m["user_id"], _excerpt(m["body"]))


def _insert(c, aid, text, src, state="active"):
    """Stores a new rule (limit AR_MAX per agent, under a lock: two parallel requests never pass it); -> its row. 2.1269.0
    (#6451): state proposed = stored by the agent (the caller posts the card)."""
    write_lock(c, f"agent_rules:{aid}")
    if c.execute("SELECT COUNT(*) FROM agent_rules WHERE agent_id=?", (aid,)).fetchone()[0] >= AR_MAX:
        raise BadInput(tr("At most {0} standing rules per agent.", AR_MAX))
    kind, sid, tid, uid, ex = src
    ts = iso(now_utc())
    rid = insert_id(c, """INSERT INTO agent_rules(agent_id, body, state, source_kind, source_id, source_task_id, source_user_id,
                          source_excerpt, created_by, created_at, updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                    (aid, text, state, kind, sid, tid, uid, ex, g.user["id"], ts, ts))
    return c.execute("SELECT * FROM agent_rules WHERE id=?", (rid,)).fetchone()


def _card(c, aid, r):
    """2.1269.0 (#6451): the server's card for proposed rule r in the chat of the person of its source with agent aid (kind
    'rule': no agent answer, no buttons of the agent; the app draws it from the rule, chat.py chat_rule_cards). The line stays
    unread until the person opens the chat."""
    m = chat_add(c, aid, r["source_user_id"], "agent", r["body"], r["source_task_id"])
    c.execute("UPDATE agent_chat SET kind='rule' WHERE id=?", (m["id"],))
    c.execute("UPDATE agent_rules SET card_id=? WHERE id=?", (m["id"], r["id"]))


# ---------------------------------------------------------------- the agent (its own token)
@app.get("/api/v1/agent/rules")
@v1_view
def v1_agent_rules():
    """The agent's standing rules, active and paused: {data: [{id, text, state, created_at, updated_at, created_by, source:
    {kind, id, task_id, user_id, excerpt}}], max, text_max}. Only the active ones apply. 2.1269.0 (#6451): the rules it proposed
    and its person has not confirmed yet come apart in "proposed" (never in data: an older launcher reads data as rules)."""
    v1_args(())
    aid = need_agent()
    c = db()
    out, prop = [], []
    for r in _rows(c, aid):
        d = ar_dict(r)
        if d["source"]["excerpt"] and not _src_seen(c, r, aid):
            d["source"]["excerpt"] = ""  # 2.235.0 B2 (#2903): the source is gone or locked / out of reach now
        (prop if _proposed(r) else out).append(d)
    return jsonify(data=out, proposed=prop, proposed_max=AR_PROPOSED_MAX, max=AR_MAX, text_max=AR_TEXT_MAX)


def _src_seen(c, r, aid):
    """2.235.0 B2 (#2903): does the source of rule r still exist for agent aid (the chat message in a conversation it still
    has, the comment on a task it may see in full)?"""
    if r["source_kind"] == "chat":
        m = c.execute("SELECT user_id FROM agent_chat WHERE id=? AND agent_id=?", (r["source_id"], aid)).fetchone()
        return bool(m) and agent_shares(c, aid, m["user_id"]) and run_chat_ok(m["user_id"])
    if r["source_kind"] == "comment":
        return _comment_alive(c, r["source_id"]) and task_visible(c, r["source_task_id"], aid, full=True)
    return True


def _comment_alive(c, cid):
    return bool(cid) and bool(c.execute("SELECT 1 FROM obj_comments WHERE id=? AND kind='task' AND deleted_at IS NULL", (cid,)).fetchone())


@app.post("/api/v1/agent/rules")
@v1_view
def v1_agent_rule_add():
    """{text, source: {kind: chat | comment, id}} -- proposes a standing rule the agent recognised ("from now on always ...")
    in a chat message of a person to it or a comment it can see (404 otherwise). The same text as an existing rule = that rule
    (200, duplicate: true); a new one 201. At most 100 rules, 500 characters each. 2.1269.0 (#6451): a new rule is a proposal
    (state proposed, applies: false): the person of the source confirms it in a card the server posts into their chat with the
    agent; only then it applies (rules_changed). At most AR_PROPOSED_MAX open proposals (429)."""
    v1_args(())
    aid = need_agent()
    b = v1_json()
    unknown = sorted(k for k in b if k not in ("text", "source"))
    if unknown:
        raise UnknownFields(unknown)
    text = _text(b.get("text"))
    from ..agents.apvdesc import apvx_clean
    if apvx_clean(text, AR_TEXT_MAX) != text:  # 2.1269.0 (#6451): the card shows the rule as one clean line, and the person
        raise BadInput(tr("Invalid value: {0}", "text"))  # confirms what they see: no control / invisible characters, no breaks
    c = db()
    src = _source_of_agent(c, aid, b.get("source"))
    old = next((r for r in _rows(c, aid) if r["body"].casefold() == text.casefold()), None)
    if old:
        return jsonify(rule=ar_dict(old), duplicate=True, applies=old["state"] == "active", hint=_hint(old))
    write_lock(c, f"agent_rules:{aid}")
    if c.execute("SELECT COUNT(*) FROM agent_rules WHERE agent_id=? AND state=?", (aid, AR_PROPOSED)).fetchone()[0] >= AR_PROPOSED_MAX:
        return v1_err(429, tr("At most {0} rules may wait for a confirmation; wait until the person decided.", AR_PROPOSED_MAX))
    r = _insert(c, aid, text, src, state=AR_PROPOSED)
    _card(c, aid, r)
    bump(c)
    c.commit()
    print("agent", aid, "rule", r["id"], "proposed from", src[0], src[1], flush=True)
    return jsonify(rule=ar_dict(r), duplicate=False, applies=False, hint=_hint(r)), 201


def _hint(r):
    """The plain line for the agent: does the rule apply now (2.1269.0, #6451)."""
    if _proposed(r):
        return ("Saved as a proposal only: it does NOT apply yet. The person it came from confirms or rejects it in a card in "
                "their chat with you; you get rules_changed when it applies. Tell them in one line that it waits for their confirmation.")
    return "This rule applies." if r["state"] == "active" else "This rule is paused by a person; it does not apply."


# ---------------------------------------------------------------- the owner / an instance admin (agent settings)
def _view(c, r, uid):
    """A rule for the settings: the excerpt and the link only when the person may see the source themselves."""
    d = ar_dict(r)
    s = d["source"]
    if s["kind"] == "chat":  # 2.235.0 B2 (#2903): and the message still exists
        s["visible"] = s["user_id"] == uid and bool(c.execute("SELECT 1 FROM agent_chat WHERE id=?", (s["id"],)).fetchone())
    elif s["kind"] == "comment":
        s["visible"] = bool(s["task_id"]) and _comment_alive(c, s["id"]) and task_visible(c, s["task_id"], uid, full=True)
    else:
        s["visible"] = True
    if not s["visible"]:
        s["excerpt"], s["user_id"] = "", None  # 2.235.0 B2 (#2903): nor who chatted with the agent
    return d


def _list(c, aid):
    uid = g.user["id"]
    return jsonify(rules=[_view(c, r, uid) for r in _rows(c, aid)], max=AR_MAX, text_max=AR_TEXT_MAX)


def _need_rule(c, aid, rid):
    r = c.execute("SELECT * FROM agent_rules WHERE id=? AND agent_id=?", (rid, aid)).fetchone()
    if not r:
        raise Denied(404)
    return r


@app.get("/api/agents/<int:aid>/rules")
def ar_route_list(aid):
    c = db()
    ws_need_editor(c, aid)
    return _list(c, aid)


@app.post("/api/agents/<int:aid>/rules")
def ar_route_add(aid):
    """{text} -- a rule added by hand (source manual)."""
    c = db()
    ws_need_editor(c, aid)
    b = body()
    unknown = sorted(k for k in b if k != "text")
    if unknown:
        raise UnknownFields(unknown)
    r = _insert(c, aid, _text(b.get("text")), ("", None, None, None, ""))
    ar_changed(c, aid, "added")
    bump(c)
    c.commit()
    return jsonify(rule=_view(c, r, g.user["id"])), 201


@app.patch("/api/agents/<int:aid>/rules/<int:rid>")
def ar_route_patch(aid, rid):
    """{text?, state?: active | paused} -- rewords / pauses / resumes one rule. 2.1269.0 (#6451): a proposed rule only the
    person of its source confirms (in the chat card); here it can only be deleted (409)."""
    c = db()
    ws_need_editor(c, aid)
    b = body()
    unknown = sorted(k for k in b if k not in ("text", "state", "expect_updated_at"))
    if unknown:
        raise UnknownFields(unknown)
    _need_rule(c, aid, rid)
    write_lock(c, f"agent_rules-{rid}")  # 2.564.0 D (#4701): reworded meantime by someone else -> 409 + the rule
    r = _need_rule(c, aid, rid)
    if _proposed(r):
        return jsonify(error=tr("Only the person it came from can confirm this rule, in their chat with the agent. You can delete it.")), 409
    ccf_check(b, r["updated_at"], "rule", lambda: _view(c, r, g.user["id"]))
    text = _text(b["text"]) if "text" in b else r["body"]
    state = b.get("state", r["state"])
    if state not in AR_STATES:
        raise BadInput(tr("Invalid value: {0}", "state"))
    if (text, state) != (r["body"], r["state"]):
        c.execute("UPDATE agent_rules SET body=?, state=?, updated_at=? WHERE id=?", (text, state, iso_ms(now_utc()), rid))
        ar_changed(c, aid, "paused" if state != r["state"] and state == "paused" else
                   "resumed" if state != r["state"] else "edited")
        bump(c)
        c.commit()
    return jsonify(rule=_view(c, _need_rule(c, aid, rid), g.user["id"]))


@app.delete("/api/agents/<int:aid>/rules/<int:rid>")
def ar_route_delete(aid, rid):
    c = db()
    ws_need_editor(c, aid)
    r = _need_rule(c, aid, rid)
    c.execute("DELETE FROM agent_rules WHERE id=?", (rid,))
    if not _proposed(r):  # 2.1269.0 (#6451): a proposal never applied, the agent's rules did not change
        ar_changed(c, aid, "deleted")
    bump(c)
    c.commit()
    return jsonify(ok=True)


# ---------------------------------------------------------------- 2.1269.0 (#6451): the person of the source decides
@app.post("/api/agents/<int:aid>/rules/<int:rid>/decide")
def ar_route_decide(aid, rid):
    """{decision: confirm | reject | withdraw} -- the card of a rule the agent proposed, only for the person of its source (the
    chat message's person, the comment's author); everyone else 404, an agent 403. confirm: the rule applies (rules_changed to
    the agent); reject: the proposal is gone; withdraw (a confirmed rule, from the same card): the rule is gone again.
    confirm / withdraw only while the person may still address the agent (_still_addresses), else 404."""
    c = db()
    if not g.get("user") or is_agent(g.user):
        raise Denied(403)
    b = body()
    unknown = sorted(k for k in b if k != "decision")
    if unknown:
        raise UnknownFields(unknown)
    dec = b.get("decision")
    if dec not in AR_DECISIONS:
        raise BadInput(tr("Invalid value: {0}", "decision"))
    write_lock(c, f"agent_rules-{rid}")
    r = c.execute("SELECT * FROM agent_rules WHERE id=? AND agent_id=?", (rid, aid)).fetchone()
    if not r or not r["card_id"] or r["source_user_id"] != g.user["id"]:
        raise Denied(404)
    if dec != "reject" and not _still_addresses(c, aid, r):
        raise Denied(404)  # 2.1269.0 (#6451): removed / locked out since the proposal: no say any more (the owner deletes it)
    if (dec == "withdraw") == _proposed(r):
        return err_state(r)
    if dec == "confirm":
        c.execute("UPDATE agent_rules SET state='active', updated_at=? WHERE id=?", (iso_ms(now_utc()), rid))
        ar_changed(c, aid, "confirmed")
    else:
        c.execute("DELETE FROM agent_rules WHERE id=?", (rid,))
        if dec == "withdraw":
            ar_changed(c, aid, "deleted")
    bump(c)
    c.commit()
    print("agent", aid, "rule", rid, dec, "by", g.user["id"], flush=True)
    return jsonify(ok=True, state="active" if dec == "confirm" else "gone")


def _still_addresses(c, aid, r):
    """2.1269.0 (#6451): may the person of rule r's source still address agent aid -- the same check as when the agent stored
    it (a chat: agent_shares; a comment: agent_usable in the project of its task)?"""
    uid = r["source_user_id"]
    if r["source_kind"] == "chat":
        return agent_shares(c, aid, uid)
    t = c.execute("SELECT list_id FROM tasks WHERE id=?", (r["source_task_id"],)).fetchone() if r["source_task_id"] else None
    return bool(t) and agent_usable(c, aid, uid, t["list_id"])


def err_state(r):
    return jsonify(error=tr("This rule was already decided.") if not _proposed(r) else tr("This rule does not apply yet.")), 409

def ar_spec(paths, schemas, op, ok, errs, ref):
    """OpenAPI of the agent's standing rules (2.235.0 C, #2903; called from agents/usage.py agent_spec)."""
    AG = "Agents"
    src = {"type": "object", "properties": {
        "kind": {"type": "string", "enum": ["chat", "comment", "manual"], "description": "a chat message of a person to you, a comment, or added by a person in your settings"},
        "id": {"type": ["integer", "null"], "description": "the chat message / comment id"},
        "task_id": {"type": ["integer", "null"], "description": "the task of a comment"},
        "user_id": {"type": ["integer", "null"], "description": "the person of the chat / the author of the comment"},
        "excerpt": {"type": "string", "description": "the start of the source text, taken at creation"}}}
    schemas["AgentRule"] = {"type": "object", "properties": {
        "id": {"type": "integer"}, "text": {"type": "string"}, "state": {"type": "string", "enum": [*AR_STATES, AR_PROPOSED], "description": "only active rules apply; 2.1269.0 (#6451): proposed = "
                  "you stored it, the person of its source has not confirmed it yet (never applies)"},
        "created_at": {"type": "string", "format": "date-time"}, "updated_at": {"type": "string", "format": "date-time"},
        "created_by": {"type": ["integer", "null"]}, "source": src}}
    paths["/agent/rules"] = {
        "get": op("2.235.0 (#2903): your standing rules, active and paused (only the active ones apply; they also come in GET /agent "
                  "rules and with the event rules_changed). 2.1269.0 (#6451): the ones you proposed and nobody confirmed yet come apart "
                  "in proposed", AG,
                  ok({"type": "object", "properties": {"data": {"type": "array", "items": ref("AgentRule")}, "max": {"type": "integer"},
                                                       "proposed": {"type": "array", "items": ref("AgentRule")},
                                                       "proposed_max": {"type": "integer"},
                                                       "text_max": {"type": "integer"}}}) | errs("403")),
        "post": op("2.235.0 (#2903): propose a standing rule you recognised (\"from now on always ...\") with its source: a chat message of a "
                   "person to you or a comment you can see (else 404). The same text as an existing rule returns that one (200, "
                   "duplicate: true). At most 100 rules, 500 characters each. 2.1269.0 (#6451): a new rule is only a proposal "
                   "(state proposed, applies: false) until the person of its source confirms it in a card Kalmido posts into their "
                   f"chat with you; you get rules_changed then. At most {AR_PROPOSED_MAX} open proposals (429). Tell the person in ONE "
                   "line that it waits for their confirmation", AG,
                   ok({"type": "object", "properties": {"rule": ref("AgentRule"), "duplicate": {"type": "boolean"}, "applies": {"type": "boolean"},
                                                        "hint": {"type": "string"}}}, code="201")
                   | ok({"type": "object", "properties": {"rule": ref("AgentRule"), "duplicate": {"type": "boolean"}, "applies": {"type": "boolean"},
                                                          "hint": {"type": "string"}}}) | errs("400", "403", "404", "429"),
                   scope="write", body={"type": "object", "required": ["text", "source"], "additionalProperties": False, "properties": {
                       "text": {"type": "string", "minLength": 1, "maxLength": AR_TEXT_MAX},
                       "source": {"type": "object", "required": ["kind", "id"], "additionalProperties": False, "properties": {
                           "kind": {"type": "string", "enum": list(AR_KINDS)}, "id": {"type": "integer"}}}}})}
