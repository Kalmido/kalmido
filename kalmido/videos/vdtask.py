"""(#7533): a task from a comment of a review (sign-off of a video, an image or a PDF) with one click.

"Task from it" at a top-level comment (a point, an area, a timecode or none) makes a task in the review's project: title =
the comment's text (first line), description = the text + where it stands (review, version, place); the review's project is
its list, or the list of the task it hangs at. A review only at a client (no project) offers nothing. Only a person who may
change the review AND write in the project makes it -- the app's routes are closed to agents (videos/review.py vdr_may), an
agent proposes it in a comment and a person clicks.

The connection is a link of the shared core (obj_links, core/objlinks.py), no field of its own: rel 'review_task',
video_review -> task, extra = {comment_id, version (its number), at (seconds) | page / mark}. The review shows at the comment
the task and its state (vdt_of, read live: title and done of the task, only when the reader sees the task); the task's panel
shows the review it came from (vdt_from, GET /api/videos?task_id= answers it as `from`). Removing a task leaves the link with
"target deleted" (olnk_state); deleting the review for good takes its links (core/writes.py _purge_rows)."""
from flask import jsonify

from ..core.config import app
from ..core.access import Denied, WRITE_ROLES, list_archived_sql, list_role, task_visible
from ..core.db import body, bump, db, iso, now_utc
from ..core.errors import BadInput
from ..core.i18n import tr
from ..core.objhooks import TASK_ADDED
from ..core.objlinks import olnk_extra, olnk_put, olnk_rel, olnk_rows
from ..accounts.session import me
from ..collab.liste2eguard import le2b_list_locked
from ..tasks.repo import task_insert
from ..tasks.validation import log_act
from .review import VDR_KIND, vdr_comment_row, vdr_comments, vdr_dict, vdr_may, vdr_need, vdr_reload, vdr_tc, vdr_versions
from .vdmedia import vdm_marks, vdm_pos_text

VDT_REL = "review_task"  # obj_links video_review -> task (core/objhooks.py OLNK_AREA_RELS)
VDT_TITLE_MAX = 300


def vdt_list(c, r):
    """The project a task of review r goes to: its list, or the list of the task it hangs at; None at a client only."""
    if r["list_id"]:
        return r["list_id"]
    if r["task_id"]:
        t = c.execute("SELECT list_id FROM tasks WHERE id=?", (r["task_id"],)).fetchone()
        return t["list_id"] if t else None
    return None


def vdt_project(c, uid, r):
    """The project a task from a comment of review r goes to for uid, or None: the review's project (vdt_list) when uid may
    change the review (videos/review.py vdr_may) and write in the project (core/access.py list_role), not archived, not locked
    -- the existing rights of both sides, no rule of its own."""
    lid = vdt_list(c, r)
    if not lid or not vdr_may(c, uid, r, write=True) or list_role(c, lid, uid) not in WRITE_ROLES:
        return None
    lr = c.execute(f"SELECT e2e, {list_archived_sql('')} AS archived FROM lists WHERE id=?", (lid,)).fetchone()
    return lid if lr and not lr["archived"] and not lr["e2e"] and not le2b_list_locked(c, lid) else None


def vdt_of(c, uid, vid):
    """{comment id: {id, title, done} | {id: None, gone: True}} of the tasks made from the comments of review vid that uid sees."""
    out = {}
    for row in olnk_rows(c, VDR_KIND, vid, side="src", rel=VDT_REL):
        cid = olnk_extra(row).get("comment_id")
        if not isinstance(cid, int) or row["dst_kind"] != "task":
            continue
        t = c.execute("SELECT title, status, deleted_at FROM tasks WHERE id=?", (row["dst_id"],)).fetchone()
        if t is None or t["deleted_at"]:
            out.setdefault(cid, {"id": None, "gone": True})
        elif task_visible(c, row["dst_id"], uid, full=True):
            out[cid] = {"id": row["dst_id"], "title": t["title"], "done": bool(t["status"])}
    return out


def vdt_from(c, uid, tid):
    """The reviews task tid was made from that uid sees: [{id, title, comment_id}]."""
    out = []
    for row in olnk_rows(c, "task", tid, side="dst", rel=VDT_REL):
        if row["src_kind"] != VDR_KIND:
            continue
        r = c.execute("SELECT * FROM video_reviews WHERE id=?", (row["src_id"],)).fetchone()
        if r is not None and not r["deleted_at"] and vdr_may(c, uid, r):
            out.append({"id": r["id"], "title": r["title"], "comment_id": olnk_extra(row).get("comment_id")})
    return out


def _vdt_may(c, uid, row):
    """Who may take a removal of such a link back (core/objlinks.py olnk_rel): changes the review, writes in the task."""
    r = c.execute("SELECT * FROM video_reviews WHERE id=?", (row["src_id"],)).fetchone()
    if r is None or r["deleted_at"] or not vdr_may(c, uid, r, write=True):
        raise Denied(404)
    if not task_visible(c, row["dst_id"], uid, write=True):
        raise Denied(403)


olnk_rel(VDT_REL, _vdt_may)


def _place(c, r, x):
    """Where comment x stands, in words: "Version 2 · 01:23" / "Version 1 · Page 2 · 3" / "Version 1"."""
    ns = {v["id"]: v["n"] for v in vdr_versions(c, r["id"])}
    mark = vdm_marks(vdr_comments(c, r["id"])).get(x["id"])
    return " · ".join(p for p in (tr("Version {0}", ns.get(x["version_id"], "")), vdr_tc(x["at_sec"]) or vdm_pos_text(x, mark)) if p), mark, ns


@app.post("/api/videos/<int:vid>/comments/<int:cid>/task")
def vdt_make(vid, cid):
    """{title?} -- a task from comment cid of review vid in the review's project (people only: an agent sees no review here);
    once per comment (a second click answers the task made already). Answers the review (its comments carry the task)."""
    c, uid = db(), me()
    r = vdr_need(c, vid)
    x = vdr_comment_row(c, r, cid)
    if x["parent_id"]:
        raise BadInput(tr("Invalid value: {0}", "comment"))
    lid = vdt_project(c, uid, r)
    if not lid:
        raise Denied(403, tr("Tasks from a sign-off need a project you may write in"))
    if vdt_of(c, uid, vid).get(cid, {}).get("id"):
        return jsonify(vdr_dict(c, vdr_reload(c, vid), uid, full=True))  # made already: the same answer, no second task
    b = body() if isinstance(body(), dict) else {}
    text = " ".join((x["body"] or "").split())
    title = b.get("title")
    if title is not None and not isinstance(title, str):
        raise BadInput(tr("Invalid value: {0}", "title"))
    title = (" ".join((title or "").split()) or text or tr("Sign-off: {0}", r["title"]))[:VDT_TITLE_MAX]
    where, mark, ns = _place(c, r, x)
    desc = f"{x['body'] or ''}\n\n{tr('From the sign-off “{0}”', r['title'])}: {where}"
    tid = task_insert(c, uid, lid, title=title, content=desc, ts=iso(now_utc()))
    log_act(c, tid, "created", uid=uid)
    for f in TASK_ADDED:  # a normal task for the project's agents (agents/core.py agent_added_events)
        f(c, tid, "review")
    extra = {"comment_id": cid, "version": ns.get(x["version_id"])}
    if x["at_sec"] is not None:
        extra["at"] = x["at_sec"]
    if x["page"] is not None:
        extra["page"] = x["page"]
    if mark:
        extra["mark"] = mark
    olnk_put(c, uid, VDR_KIND, vid, "task", tid, VDT_REL, org_id=r["org_id"], extra=extra)
    bump(c)
    c.commit()
    return jsonify(dict(vdr_dict(c, vdr_reload(c, vid), uid, full=True), task_id=tid)), 201
