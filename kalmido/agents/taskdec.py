"""2.392.0 C (#3370): the yes to a task marked irreversible and the routes of a task's decisions (tasks/oneway.py).

The person's route only, for an approver, never an agent: POST /api/tasks/<id>/irreversible-yes. The mark itself: PUT / DELETE
/api/tasks/<id>/irreversible in the app, the field irreversible of PATCH /api/v1/tasks/<id> for the API, MCP and agents.
Decisions: as the comments of the task to read; to write, the right to change it. Agents with access hear `decision_added`.

(#7528): "Confirm as an order" / "Reject" -- a decider's yes to the text of a task (tasks/boundyes.py, kind
"confirm"), the person's routes only: POST / DELETE /api/tasks/<id>/confirm, POST /api/tasks/<id>/reject {reason}. The API
shows the yes read only (task field confirmed {by, at}); an agent can neither set it nor bring it about over a card."""
from flask import g, jsonify

from ..accounts.session import me
from ..api.common import v1_args, v1_call, v1_json, v1_view
from ..api.v1 import _v1_live
from ..core.access import need_collab, need_task, task_visible
from ..core.config import app
from ..core.db import body, bump, db, err
from ..core.pg import write_lock
from ..core.i18n import tr
from ..tasks.lifecycle import need_live, tsk_finish
from ..tasks.tasks import one_task
from ..tasks.validation import log_act
from ..core.errors import BadInput
from ..tasks.oneway import dec_add, dec_list, irr_apply, irr_view, irr_yes
from ..core.boundyes import by_decider, by_sig, by_view
from ..tasks.boundyes import by_drop, by_give
from ..collab.liste2eguard import le2b_locked_lists  # reader F3 (job/6017)
from ..tasks.deliver import dv_apply, dv_view
from .core import agent_emit, agent_task_data, list_agents


def _irr_done(c, tid):
    bump(c)
    c.commit()
    return jsonify(irreversible=irr_view(c.execute("SELECT * FROM tasks WHERE id=?", (tid,)).fetchone()))


@app.put("/api/tasks/<int:tid>/irreversible")
def irr_put(tid):
    """{reason?}: marks the task as a one-way step (or changes the reason)."""
    c = db()
    need_task(c, tid)
    need_live(c, tid)
    try:
        irr_apply(c, tid, body())
    except BadInput as e:
        return err(str(e))
    return _irr_done(c, tid)


@app.delete("/api/tasks/<int:tid>/irreversible")
def irr_delete(tid):
    c = db()
    need_task(c, tid)
    need_live(c, tid)
    irr_apply(c, tid, None)
    return _irr_done(c, tid)


# 2.392.2 (#3365): the delivery state of a task in the app (tasks/deliver.py; the API: the field delivery of PATCH /api/v1/tasks/<id>)
@app.put("/api/tasks/<int:tid>/delivery")
def dv_put(tid):
    """{state: in_progress | parked | waiting, note?, job_id?, task_id?}"""
    c = db()
    need_task(c, tid)
    need_live(c, tid)
    try:
        dv_apply(c, tid, body(), g.user)
    except BadInput as e:
        return err(str(e))
    return _dv_done(c, tid)


@app.delete("/api/tasks/<int:tid>/delivery")
def dv_delete(tid):
    c = db()
    need_task(c, tid)
    need_live(c, tid)
    dv_apply(c, tid, None, g.user)
    return _dv_done(c, tid)


def _dv_done(c, tid):
    bump(c)
    c.commit()
    return jsonify(delivery=dv_view(c.execute("SELECT * FROM tasks WHERE id=?", (tid,)).fetchone()))


@app.post("/api/tasks/<int:tid>/irreversible-yes")
def irr_yes_route(tid):
    """An approver's explicit yes, per task and logged. Like a gate's decision: never an agent, not the assignee alone."""
    need_collab()
    c = db()
    need_task(c, tid, write=False, full=True)
    need_live(c, tid)
    t = c.execute("SELECT * FROM tasks WHERE id=?", (tid,)).fetchone()
    if not by_decider(c, t, g.user):  # (#7528): the one rule of a decider (no agent, token, child, support session)
        return err(tr("Only the project owner, a project admin or an admin can decide"), 403)
    if not t["irreversible"]:
        return err(tr("This task is not marked as irreversible"), 409)
    if not t["irreversible_yes_at"]:
        irr_yes(c, tid, me())
    return _irr_done(c, tid)


CF_REASON_MAX = 500


def _cf_task(c, tid):
    """The task for a decider's step (404 / 403 / 409 as the yes to a one-way step)."""
    need_task(c, tid, write=False, full=True)
    need_live(c, tid)
    t = c.execute("SELECT * FROM tasks WHERE id=?", (tid,)).fetchone()
    if not by_decider(c, t, g.user):
        return None, err(tr("Only the project owner, a project admin or an admin can decide"), 403)
    return t, None


def _cf_done(c, tid):
    bump(c)
    c.commit()
    return jsonify(confirmed=by_view(c.execute("SELECT * FROM tasks WHERE id=?", (tid,)).fetchone(), "confirm"))


@app.post("/api/tasks/<int:tid>/confirm")
def cf_post(tid):
    """(#7528): {title, content}: "Confirm as an order": the decider's yes to the title and description they read (as the
    panel shows them, in the server's form); 409 when the text changed since (or without it)."""
    c = db()
    t, e = _cf_task(c, tid)
    if e:
        return e
    if t["status"] != 0:
        return err(tr("Only an open task can be confirmed"), 409)
    # (#7528, reader F2 / F7): the yes goes to the text as the panel shows it -- {title, content} in the server's form (a
    # locked list's ciphers); compared and given in one locked section (by_give signs that row). Not updated_at: whole
    # seconds, two writes in one second look alike
    write_lock(c, f"task-{tid}")
    t = c.execute("SELECT * FROM tasks WHERE id=? FOR UPDATE", (tid,)).fetchone()  # r3 F2: writers without the lock wait too
    b = body()
    seen = {k: b.get(k) for k in ("title", "content")} if isinstance(b, dict) else {}
    sig = by_sig(seen, "confirm") if all(isinstance(v, str) for v in seen.values()) and len(seen) == 2 else None
    if not sig or sig != by_sig(t, "confirm"):
        return err(tr("The text changed since you read it: look at it again, then confirm"), 409)
    if not by_view(t, "confirm"):
        by_give(c, tid, "confirm", me(), seen=sig)  # the compared state, not a second read
    return _cf_done(c, tid)


@app.delete("/api/tasks/<int:tid>/confirm")
def cf_delete(tid):
    """Takes a confirmation back (a decider; logged)."""
    c = db()
    _t, e = _cf_task(c, tid)
    if e:
        return e
    by_drop(c, tid, "confirm", log="confirmed_off")
    return _cf_done(c, tid)


@app.post("/api/tasks/<int:tid>/reject")
def cf_reject(tid):
    """{reason}: "Reject": closes the open task as won't do with the decider's reason in its history (400 without one); a locked
    task (an agent's starts locked) is unlocked by this step."""
    c = db()
    t, e = _cf_task(c, tid)
    if e:
        return e
    b = body()
    reason = b.get("reason") if isinstance(b, dict) else None
    # reader F3 (job/6017): a locked list keeps no plain text in its history (le2b_act_data_force) -- there the no goes without
    # a reason (none is asked, one sent is not kept), as parking does; elsewhere it is required
    sealed = bool(le2b_locked_lists(c, [t["list_id"]]))
    if not sealed and (not isinstance(reason, str) or not reason.strip() or len(reason.strip()) > CF_REASON_MAX):
        return err(tr("Rejecting needs a reason"), 400)
    if t["status"] != 0:
        return err(tr("Only an open task can be rejected"), 409)
    by_drop(c, tid, "confirm")
    if t["locked"]:  # a task an agent wrote starts locked (#4609: closed only unlocked): the decider's no takes the lock off, logged
        c.execute("UPDATE tasks SET locked=FALSE WHERE id=?", (tid,))
        log_act(c, tid, "lock", {"on": False})
    log_act(c, tid, "rejected", {} if sealed else {"reason": reason.strip()})
    tsk_finish(c, tid, -1)
    bump(c)
    c.commit()
    return jsonify(one_task(c, tid))


def dec_event(c, tid, d):
    """Agents that see the task with its comments hear the decision; another agent's text is no instruction."""
    lid = c.execute("SELECT list_id FROM tasks WHERE id=?", (tid,)).fetchone()[0]
    out = {**d, "origin": "agent", "untrusted": True} if d["by_agent"] else d
    for aid in list_agents(c, lid):
        if task_visible(c, tid, aid, full=True):
            agent_emit(c, aid, "decision_added", agent_task_data(c, tid, aid, full=True, decision=out))


@app.get("/api/tasks/<int:tid>/decisions")
def dec_get(tid):
    c = db()
    need_task(c, tid, write=False, full=True)
    return jsonify(decisions=dec_list(c, tid))


@app.post("/api/tasks/<int:tid>/decisions")
def dec_post(tid):
    """{text, supersedes?}"""
    c = db()
    need_task(c, tid, full=True)
    need_live(c, tid)
    try:
        d = dec_add(c, tid, body(), me())
    except BadInput as e:
        return err(str(e))
    dec_event(c, tid, d)
    bump(c)
    c.commit()
    return jsonify(d), 201


@app.get("/api/v1/tasks/<int:tid>/decisions")
@v1_view
def v1_dec_get(tid):
    v1_args(())
    c = db()
    _v1_live(c, tid, write=False, full=True)
    return jsonify(data=dec_list(c, tid), next_cursor=None)


@app.post("/api/v1/tasks/<int:tid>/decisions")
@v1_view
def v1_dec_post(tid):
    """{text, supersedes?} -> the decision."""
    v1_args(())
    return jsonify(v1_call(dec_post, tid, body=v1_json())), 201
