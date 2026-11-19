"""2.1337.0 (#6600, decided 16.11.2026, variant A of #6595): the move of an organisation ("Umzug").

An admin of the organisation starts the move in Settings > Organisation > Data (a second confirmation: the organisation's name
typed). From then on the whole organisation is read only for everybody - members, agents, tokens, public forms, booking pages,
file requests, incoming mail - through ONE lock in the database (core/movelock.py); the background work for it rests
(mv_skip). Reading, downloading and the organisation's export stay possible: the export shows this fixed state. Every member
sees the bar with the reason and who started it (core/state.py workspaces, static/js/render.js mvSync). An admin ends the move
at any time (everything runs again; invoice series that missed a period meanwhile are NOT made late, they are paused with the
task "Invoice series ... paused", office/recurring.py rin_moved) or has the organisation deleted. Starting and ending are written
to the organisation's log (org_list_log, actions move_on / move_off: Projects of the organisation > History).

GET    /api/orgs/<org id>/moving   every member: {moving, since?, by_name?, why?}
POST   /api/orgs/<org id>/moving   an admin: {confirm: the organisation's name, why?} -> starts it (409 when it runs already)
DELETE /api/orgs/<org id>/moving   an admin: ends it -> {moving: false, paused: [series ids]}; (#6951): an instance admin
                                   too when the organisation has no active admin of its own (else 409; org log move_off with
                                   instance_admin), so no organisation stays read only
People only (agents 403); app only (APP_ONLY "* /api/orgs" in tests/parity_test.py)."""
import json

from flask import g, jsonify

from ..core.config import app
from ..core.db import body, bump, db, iso, local_now, now_utc
from ..core.access import live_sql
from ..core.errors import Denied
from ..core.i18n import tr
from ..core.movelock import mv_allow, mv_forget, mv_info
from ..core.pg import system_ctx
from .bgjobs import bgj_add
from .session import me
from .orgs import _need_org_admin, org_need_person, org_own_admin

MV_WHY_MAX = 500


def _org(c, oid):
    with system_ctx(c):  # the organisation's own row (structure; the caller checked the membership)
        r = c.execute("SELECT * FROM orgs WHERE id=? AND personal_of IS NULL", (int(oid),)).fetchone()
    if r is None:
        raise Denied(404)
    return r


def _log(c, oid, action, detail=None):
    c.execute("INSERT INTO org_list_log(org_id, list_id, list_name, action, by_id, owner_id, to_id, created_at, detail) "
              "VALUES(?,NULL,'',?,?,NULL,NULL,?,?)", (int(oid), action, me(), iso(now_utc()),
                                                     json.dumps(detail, ensure_ascii=False) if detail else None))


def _out(r):
    i = mv_info(r)
    return {"moving": False} if i is None else {"moving": True, **{k: i[k] for k in ("since", "by_name", "why")}}


@app.get("/api/orgs/<int:oid>/moving")
def org_moving_get(oid):
    c = db()
    org_need_person(c, oid)
    return jsonify(_out(_org(c, oid)))


@app.post("/api/orgs/<int:oid>/moving")
def org_moving_start(oid):
    c, b = db(), body()
    _need_org_admin(c, oid)
    r = _org(c, oid)
    if r["moving_at"]:
        return jsonify(error=tr("The move of this organisation has already started"), **_out(r)), 409
    if not isinstance(b, dict) or not isinstance(b.get("confirm"), str) or b["confirm"].strip().casefold() != (r["name"] or "").strip().casefold():
        raise Denied(400, tr("Type the name of the organisation to start the move"))
    why = b.get("why", "")
    if not isinstance(why, str):
        raise Denied(400, tr("Invalid value: {0}", "why"))
    why = why.strip()[:MV_WHY_MAX]
    u = c.execute("SELECT display_name, username FROM users WHERE id=?", (me(),)).fetchone()
    name = (u["display_name"] or u["username"]) if u else ""
    _log(c, oid, "move_on", {"why": why} if why else None)  # first: from the next statement on the organisation is read only
    with system_ctx(c):  # the organisation's own row (orgs has no org_id: its admin switches it, checked above)
        c.execute("UPDATE orgs SET moving_at=?, moving_by=?, moving_by_name=?, moving_why=? WHERE id=? AND moving_at IS NULL",
                  (iso(now_utc()), me(), name, why, int(oid)))
    bump(c)
    c.commit()
    mv_forget()
    return jsonify(_out(_org(c, oid)))


def _need_ender(c, oid):
    """(#6951, Fable review of job/5128): an admin of the organisation ends the move - or an instance admin (a person),
    but only when the organisation has no active admin of its own any more (org_own_admin), so it never stays read only
    without one; while it has one, the move stays its decision (also hosted: never past the client, op_foreign_org).
    True when it is the instance admin's way."""
    try:
        _need_org_admin(c, oid)
        return False
    except Denied as e:
        u = g.get("user")
        if e.code not in (403, 404) or not (u and u["is_admin"] and (u["kind"] or "user") != "agent"):  # a person, never an agent
            raise
        with system_ctx(c):  # the organisation's admins (structure; the caller is an instance admin)
            own = org_own_admin(c, oid)
        if own is not None:
            raise Denied(409, tr("This organisation has an admin of its own: only that admin can end the move")) from None
        return True


@app.delete("/api/orgs/<int:oid>/moving")
def org_moving_end(oid):
    c = db()
    inst = _need_ender(c, oid)
    r = _org(c, oid)
    if not r["moving_at"]:
        return jsonify(moving=False, paused=[])
    if r["retired_at"]:  # (#7199, reader F7): a retired organisation (orgretain) keeps its data as it is -- no series
        # pause, no history line written into it; its move stays (nobody works there any more, only the export reads it)
        return jsonify(error=tr("This organisation is retired: its data stays as it is"), moving=True), 409  # reader F2: no names / reason
    mv_allow(c)  # ending the move is one of the writes the move allows
    with system_ctx(c):  # the organisation's own row
        c.execute("UPDATE orgs SET moving_at=NULL, moving_by=NULL, moving_by_name='', moving_why='' WHERE id=?", (int(oid),))
    paused = mv_series_pause(c, oid)
    detail = dict({"paused": len(paused)} if paused else {}, **({"instance_admin": True} if inst else {}))
    if inst:  # (#6951): in the organisation's log as well, written as system (the instance admin need not be a member)
        with system_ctx(c):
            _log(c, oid, "move_off", detail)
    else:
        _log(c, oid, "move_off", detail or None)
    bump(c)
    c.commit()
    mv_forget()
    if paused:
        bgj_add("office:series_moved", int(oid), paused, org_id=int(oid))  # the task "paused" for the series' people
    return jsonify(moving=False, paused=paused)


def mv_series_pause(c, oid):
    """The running invoice series of organisation oid whose next period came during the move: paused (pause_why 'moving'), not
    made late (decision #6600). Returns their ids; the caller commits and has their people told (office/recurring.py rin_moved)."""
    today = local_now().date().isoformat()
    with system_ctx(c):  # every series of the organisation (its admin ends the move; the office may be off for them)
        return sorted(x[0] for x in c.execute(
            "UPDATE office_inv_series SET active=false, fail_count=0, pause_why='moving', updated_at=? WHERE org_id=? AND active "
            f"AND {live_sql()} AND next_date<>'' AND next_date<=? RETURNING id", (iso(now_utc()), int(oid), today)).fetchall())
