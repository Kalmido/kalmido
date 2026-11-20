"""(#7530): answer buttons with a bound step -- an option of an agent's question (a task comment's buttons, collab/cchoice.py,
or a chat message's, agents/chat.py) may carry `do`, ONE step of a fixed list that Kalmido itself runs after the click, with
the rights of the person who clicked, without an agent run:

  section  {kind, section_id}   the task into a column of its own project
  state    {kind, state}        done | in_progress (the delivery mark "in progress", tasks/deliver.py)
  wont     {kind, reason}       "will not be done" (status -1) -- the reason goes along as the person's answer
  park     {kind, reason}       parked with that reason (delivery parked)
  wait     {kind, until, note?} waiting until that day (tasks/tasks.py set_waiting)
  tag      {kind, tag}          a tag of the project on the task

Protection (decision of #7530): only these steps, never a free API call; only at the object the question hangs on (the task
of the comment / of the chat message) -- a step naming any other object is refused when the agent posts it (400); the person
needs the right to change the task (else 403 with the reason, nothing stored); the step runs exactly once (the answer is
written once under the comment's / message's row lock, collab/cchoice.py lv_answer, agents/chat.py chat_choice_set). A task
that is further already (done, will not be done, a job works on it) keeps its state: the answer is stored and reaches the
agent, the step is skipped (the answer says why). Before the click the app shows the step at its button (an option without
one is "answer only"), after it the task's history names it (activity "choice", data.step)."""
from flask import g

from ..core.access import Denied, need_task
from ..core.errors import BadInput
from ..core.i18n import tr
from ..tasks.validation import valid_date
from ..tasks.deliver import dv_apply
from ..tasks.lifecycle import apply_update, need_live, tsk_finish
from ..tasks.tasks import set_waiting
from .reactions import ltag_get_or_create, ltag_names, set_ltags

CST_KINDS = ("section", "state", "wont", "park", "wait", "tag")
CST_KEYS = {"section": {"section_id"}, "state": {"state"}, "wont": {"reason"}, "park": {"reason"}, "wait": {"until", "note"},
            "tag": {"tag"}}
CST_NEED = {"section": {"section_id"}, "state": {"state"}, "wont": {"reason"}, "park": {"reason"}, "wait": {"until"}, "tag": {"tag"}}
CST_STATES = ("done", "in_progress")
CST_REASON_MAX, CST_TAG_MAX = 300, 40
CST_FOREIGN = ("task_id", "list_id", "id", "object", "kind_id", "path", "url", "method")  # naming another object


def _bad(what):
    return BadInput(tr("Invalid value: {0}", what))


def cst_has(ch):
    """True when the choices ch carry a bound step on at least one option -- any `do` that is not None, also an empty one,
    so that cst_choices checks it (reader F3: `do: {}` was stored unchecked and looked like a step to the app)."""
    return bool(ch) and any(isinstance(x, dict) and x.get("do") is not None for x in ch.get("choices") or [])


def cst_clean(c, do, tid):
    """A step `do` of an option -> the stored dict, checked against task tid (the object of the question). 400 otherwise:
    an unknown kind or key, another object (a task / list / path named in the step, a column of another project)."""
    if not isinstance(do, dict):
        raise _bad("do")
    if any(k in do for k in CST_FOREIGN):
        raise BadInput(tr("A step of an answer button acts only on the task of the question"))
    kind = do.get("kind")
    if kind not in CST_KINDS:
        raise _bad("do.kind")
    keys = set(do) - {"kind"}
    if keys - CST_KEYS[kind] or CST_NEED[kind] - keys:
        raise _bad("do")
    if not tid:
        raise BadInput(tr("A step of an answer button needs the task of the question (task_id)"))
    out = {"kind": kind}
    if kind == "section":
        s = do["section_id"]
        r = c.execute("SELECT s.id, s.name FROM sections s JOIN tasks t ON t.list_id=s.list_id WHERE s.id=? AND t.id=?",
                      (s, tid)).fetchone() if isinstance(s, int) and not isinstance(s, bool) else None
        if not r:
            raise BadInput(tr("A step of an answer button acts only on the task of the question"))
        out.update(section_id=r["id"], name=r["name"])
    elif kind == "state":
        if do["state"] not in CST_STATES:
            raise _bad("do.state")
        out["state"] = do["state"]
    elif kind in ("wont", "park"):
        v = do["reason"]
        if not isinstance(v, str) or not v.strip() or len(v.strip()) > CST_REASON_MAX:
            raise _bad("do.reason")
        out["reason"] = " ".join(v.split())
    elif kind == "wait":
        if not isinstance(do["until"], str) or not valid_date(do["until"]):
            raise _bad("do.until")
        out["until"] = do["until"]
        n = do.get("note")
        if n not in (None, ""):
            if not isinstance(n, str) or len(n.strip()) > CST_REASON_MAX:
                raise _bad("do.note")
            out["note"] = n.strip()
    else:
        v = do["tag"]
        if not isinstance(v, str) or not v.strip() or len(v.strip()) > CST_TAG_MAX:
            raise _bad("do.tag")
        # reader F14: only a tag the project has (its own or its organisation's label) - a click never makes a new one
        # with a name the agent chose; unknown: 400 "Unknown project tag"
        lid = c.execute("SELECT list_id FROM tasks WHERE id=?", (tid,)).fetchone()
        ltag_get_or_create(c, lid[0] if lid else 0, v.strip(), False)
        out["tag"] = v.strip()
    return out


def cst_choices(c, ch, tid):
    """The checked choices dict ch (agents/chat.py chat_choices_clean kept `do` as sent) with every step checked against
    task tid -> ch. An approval card or a permission question takes no step (their Yes has its own, ctl_run_replay)."""
    if not cst_has(ch):
        return ch
    if ch.get("permission") or ch.get("approval") or ch.get("multi"):  # one option = one step: no multi-pick with steps
        raise _bad("do")
    for x in ch["choices"]:
        if x.get("do") is not None:
            if x.get("href"):
                raise _bad("do")
            x["do"] = cst_clean(c, x["do"], tid)
    return ch


def cst_further(c, tid):
    """None, or why the task is further already than a question about it: 'done' (done / will not be done) | 'in_progress'."""
    t = c.execute("SELECT status, delivery FROM tasks WHERE id=?", (tid,)).fetchone()
    if not t:
        return None
    if t["status"] != 0:
        return "done"
    return "in_progress" if (t["delivery"] or "") == "in_progress" else None


def cst_may(c, tid):
    """The clicking person may change task tid (else 403 with the reason: the step would not run, nothing is stored). A token
    needs the scope tasks:write too (reader F8: the answer routes ask only for comments - a step must not widen that)."""
    if g.get("auth_via") == "token" and "tasks:write" not in (g.get("scopes") or set()):  # as api/scopes.py need_scope (a lower layer)
        raise Denied(403, tr("This token lacks the permission “{0}”", tr("Tasks")))
    try:
        need_task(c, tid)
    except Denied as e:
        if e.code == 404:
            raise
        raise Denied(403, tr("You cannot change this task, so this answer cannot run its step")) from None


def cst_run(c, tid, do, label=""):
    """Runs step do on task tid as the signed-in person (the caller checked cst_may and commits) -> {kind, state: done |
    skipped, why?}. A task that is further already keeps its state (skipped, why done | in_progress)."""
    need_live(c, tid)
    why = cst_further(c, tid)
    if why:
        return {"kind": do["kind"], "state": "skipped", "why": why}
    k = do["kind"]
    if k == "section":
        # reader F11: the column was checked against the project when the question was posted; a task moved since then would
        # lose its column silently (lifecycle.apply_update) - skipped instead, with why
        s = c.execute("SELECT 1 FROM sections s JOIN tasks t ON t.list_id=s.list_id WHERE s.id=? AND t.id=?", (do["section_id"], tid)).fetchone()
        if not s:
            return {"kind": k, "state": "skipped", "why": "moved"}
        e = apply_update(c, tid, {"section_id": do["section_id"]}, [], lock=True)
        if e:
            raise BadInput(e)
    elif k == "state" and do["state"] == "done":
        tsk_finish(c, tid, 2, {})
    elif k == "state":
        dv_apply(c, tid, {"state": "in_progress"}, g.user)
    elif k == "wont":
        tsk_finish(c, tid, -1, {})
    elif k == "park":
        dv_apply(c, tid, {"state": "parked", "note": do["reason"]}, g.user)
    elif k == "wait":
        set_waiting(c, tid, {"until": do["until"], **({"note": do["note"]} if do.get("note") else {})})
    else:
        # (#7530, reader F15): the tag is checked again at the click against the task's project now - deleted /
        # renamed since the question, or the task moved: skipped (moved), nothing is created (set_ltags would make it anew)
        lid = c.execute("SELECT list_id FROM tasks WHERE id=?", (tid,)).fetchone()
        try:
            ltag_get_or_create(c, lid[0] if lid else 0, do["tag"], False)
        except BadInput:
            return {"kind": k, "state": "skipped", "why": "moved"}
        set_ltags(c, tid, ltag_names(c, tid) + [do["tag"]])
    return {"kind": k, "state": "done"}


def cst_of(ch, ids):
    """The step of the chosen option(s) (several with multi: the first that carries one) -> dict | None."""
    return next((x["do"] for x in (ch or {}).get("choices") or [] if x["id"] in ids and x.get("do")), None)
