"""2.1284.0 (#6453): an agent writes freely only towards the same or a smaller circle of people.

The bridge rule of 2.30.0 (agents/safety.py) looks at the moment of sharing and calls two nested circles harmless in both
directions. It is not: a private project (only its owner) and a project shared with one more person are nested, and text a
person of the shared project (or somebody outside through a form / a mail) leaves there can make the agent copy private
content into it. So the control gate (agents/control.py ctl_gate) asks here before it lets a write pass WITHOUT a card:

  TARGET   what the request writes into: its project(s); a team chat room without a project; a knowledge page.
  SOURCES  everything the agent can read: every project it can really use (safety.agent_reach) and every live share of the
           file store's nodes with exactly this agent (knowledge folders / pages / areas, file folders, calendars, address
           books, tables, channels -- the shared core's one way in for an agent).
  RULE     every person who reads the target must read every source too. One person of the target who does not see one
           source = the target is "wider": a card. People only (agents never count); a source nobody reads (the agent's own
           project without a person) holds nobody's content and does not count; a pair of projects a person who manages both
           approved as a bridge (agent_bridges) stays approved.
  PUBLIC   a target people without an account read is the circle "everyone": always a card. A project with a live public
           link; a task with a client report (the portal: its title, state and the answers marked for the client); a
           knowledge page a live share covers (a public link = public, a share with a person outside the space = wider).
           (#7478) An answer to a customer's comment of a sign-off (videos), and done / open of such a comment or answer:
           a customer page shows them (circle_video_public; also while no link is live - a later link shows them).

circle_of(...) -> None (free as far as the circles go) | "wider" | "public". The gate turns that into 409 approval_required
with the field circle; the approval card of such a step carries the same mark (set by the server, never by the agent), the
person reads "visible to more people" / "publicly visible" on it. approve_all is untouched (every write is a card there
anyway); a one-way step stays a one-way step.

An agent that reaches one project only and nothing else gets no card from this rule: nothing can flow.

Review of 16.11.2026 (G1 - G13), all in the direction "in doubt a card":
  * who READS a source: only a full role of a project (owner, admin, edit, view, the organisation's people of an open one) --
    a participant sees only the own tasks and is no reader of the whole; a member whose own share ran out is none either.
    The TARGET side counts everybody (list_circles2 -> (all, full)).
  * a target without a project is named where the shared core knows it (CIRCLE: a calendar / an event, an address book / a
    contact, a file or folder, a knowledge page, a chat room): its readers are the people with a role on it
    (core/objects.py obj_role / files/store.py fs_role, asked per person) and they must read every source. A target the
    gate cannot name (a table without a project, office, documents, polls, clients, forms ...; an object the agent itself does not see or that does not exist -- the same
    answer for both, no oracle) is a card as soon as the agent has more than one source (projects with people + shares).
  * an approved bridge (agent_bridges) holds only for the circles of the moment of the approval (circle_a / circle_b,
    migrations.d/6453.py): both circles of today must lie inside them, and the person who approved must still manage both
    projects. A circle that grew = a card again (and safety.bridge_conflicts asks again at the share).
  * limits close: more shares than CIRCLE_NODES_MAX, or persons of the target x shares above CIRCLE_PAIRS_MAX = "wider".
  * a TEAM agent's message to a person (POST /agent/chats/<uid>) is a target with one reader; its status text is hidden
    from a person who does not read every source (circle_reader). A personal agent writes only to its owner: free.
  * who says Yes to a card of this rule must read every source (control.ctl_claim: circle_reader), else approver_rights.
  * 2.1398.0 (#6863): a team agent's job for a person (POST /agent/jobs with user_id / in a run for a person, PATCH of its
    title / log) is a message to that person (control.ctl_meta_circle); a job without a task shows its words only to who
    reads every source (job_mute); a proposal for the rules / playbook / layout of a project is a write into that project
    (circle_of), a layout proposal a message to its person too.
  * (#7142, decision of #6863): an agent without a chosen control level counts as "free" for this rule: every step
    as before, a write into a wider / public circle, a message or job to a person outside it = a card; its status text,
    progress line and job words are hidden from people who do not read every source (wk_mute / st_mute / job_mute).

The cost per request: the agent's projects, their circles (four statements for all of them, list_circles2) and its shares
once per request and agent (_sources); a person's roles on the shares once per request, the shares' chains once. wk_mute
(asked at every load of tasks with a mark) keeps its answer per agent and project for WK_MUTE_TTL seconds."""
import time

from flask import g, has_request_context

from ..core.access import collab_all, Denied, live_sql, MANAGE_ROLES, list_role, ov_open
from ..core.db import iso, now_utc
from ..core.objects import obj_role, obj_space
from ..core.pg import system_ctx
from ..core.serializers import WK_MUTE
from ..files.fsref import fs_ref_node
from ..files.fsroots import fs_area_root_of
from ..files.store import fs_chain, fs_chains, fs_deleted, fs_role, fs_roles_many
from ..collab.teamchat import tchat_room_members, tchat_room_ok
from ..wiki.wkfolder import _root_of_chain
from ..wiki.wkshare import wsh_covers, wsh_live_rows
from ..wiki.wkv1 import wkv_need
from .core import agent_row, agent_shares, JOB_MUTE, ST_MUTE

CIRCLE_PAIRS_MAX = 400  # persons of the target x node shares of the agent one request looks at; more = "wider"
CIRCLE_NODES_MAX = 500  # node shares of one agent the rule reads; more = it cannot tell: "wider" (review G10)
CIRCLE_PEOPLE_MAX = 200  # people asked one by one for their role on a target without a project; more = not nameable
WK_MUTE_TTL = 10  # seconds wk_mute / the status text keep an answer per agent and project / person (review G11)
# the kinds of the shared core (core/objects.py OBJ) a route without a project writes into (their names as registered:
# events/model.py EV_KIND, contacts/ctfolder.py CTF_BOOK; a file / folder is its node, files/fskern.py FSK_KIND)
K_CAL, K_BOOK, K_FILE = "evcal", "address_book", "fs_entry"
_MEMO = {}  # (kind, agent id, x) -> (until, answer): wk_mute and the status text, WK_MUTE_TTL seconds


def _short(key, fn):
    """fn() kept for WK_MUTE_TTL seconds under key (this process; the answer of a read path only, never of the gate)."""
    now = time.monotonic()
    hit = _MEMO.get(key)
    if hit and hit[0] > now:
        return hit[1]
    if len(_MEMO) > 5000:
        _MEMO.clear()
    out = fn()
    _MEMO[key] = (now + WK_MUTE_TTL, out)
    return out


def list_circles2(c, lids):
    """({lid: frozenset of ALL its people}, {lid: frozenset of the people who read the WHOLE project}) for many lists at
    once. All = safety.list_circle (owner + members that are persons + the organisation's people of a list open to it): the
    readers of a target. Whole (review G6) = without participants (they see only their own tasks) and without members whose
    own share ran out (core/access.py lr_own_ran_out): the people a source is no secret to. Read as "system": only ids, and
    a circle must not shrink because the asking agent does not see a row."""
    lids = sorted({int(x) for x in lids if x})
    al, full = {x: set() for x in lids}, {x: set() for x in lids}
    if not lids:
        return {}, {}
    with system_ctx(c):
        rows = c.execute("SELECT id, owner_id, org_id, life, family, org_visibility FROM lists WHERE id = ANY(CAST(? AS BIGINT[]))", (lids,)).fetchall()
        pairs = [(r["id"], r["owner_id"], True) for r in rows if r["owner_id"]]
        pairs += [(r[0], r[1], r[2] != "participant") for r in c.execute(
            "SELECT list_id, user_id, role FROM list_members WHERE list_id = ANY(CAST(? AS BIGINT[]))", (lids,))]
        open_ = {r["id"]: r["org_id"] for r in rows if r["org_id"] and collab_all() and ov_open(r)}
        if open_:
            om = {}
            for r in c.execute("""SELECT org_id, user_id FROM org_members WHERE org_id = ANY(CAST(? AS BIGINT[]))
                                  AND role IN ('admin', 'member', 'readonly')""", (sorted(set(open_.values())),)):
                om.setdefault(r[0], []).append(r[1])
            pairs += [(lid, u, True) for lid, org in open_.items() for u in om.get(org, ())]
        ids = sorted({u for _, u, _ in pairs})
        people = {r[0] for r in c.execute("""SELECT id FROM users WHERE id = ANY(CAST(? AS BIGINT[])) AND COALESCE(kind,'user')!='agent'
                                             AND id NOT IN (SELECT user_id FROM agents)""", (ids,))} if ids else set()
        gone = {(r[0], r[1]) for r in c.execute(
            """SELECT n.ref_id, s.user_id FROM fs_nodes n JOIN fs_shares s ON s.node_id=n.id WHERE n.kind='ref' AND n.ref_kind='list'
               AND n.ref_id = ANY(CAST(? AS BIGINT[])) AND s.list_own=1 AND s.user_id IS NOT NULL AND s.expires_at IS NOT NULL
               AND s.expires_at <= ?""", (lids, iso(now_utc())))}
    for lid, u, whole in pairs:
        if u in people and lid in al:
            al[lid].add(u)
            if whole and (lid, u) not in gone:
                full[lid].add(u)
    return {k: frozenset(v) for k, v in al.items()}, {k: frozenset(v) for k, v in full.items()}


def list_circles(c, lids):
    """{lid: frozenset of all its people} (list_circles2's first half)."""
    return list_circles2(c, lids)[0]


def circle_public_lists(c, lids):
    """The ids of lids with a live public link (lists/public.py: one row per project; a folder's link = its projects' rows)."""
    lids = sorted({int(x) for x in lids if x})
    if not lids:
        return set()
    with system_ctx(c):
        return {r[0] for r in c.execute("""SELECT list_id FROM public_links WHERE list_id = ANY(CAST(? AS BIGINT[]))
                                           AND (expires_at IS NULL OR expires_at > ?)""", (lids, iso(now_utc())))}


def circle_ticket_tasks(c, tids, lids):
    """The ids of tids that carry a client report (team/portal.py portal_tickets): the reporter reads them without an account.
    Only tasks of lids, the projects of the request the agent sees (review G9: a task of somebody else's project gives no
    answer here -- a batch with foreign ids told "client report" from "none")."""
    tids = sorted({int(x) for x in tids if isinstance(x, int) and not isinstance(x, bool)})[:500]
    lids = sorted({int(x) for x in lids or [] if x})
    if not tids or not lids:
        return set()
    with system_ctx(c):
        return {r[0] for r in c.execute("""SELECT p.task_id FROM portal_tickets p JOIN tasks t ON t.id=p.task_id
                                           WHERE p.task_id = ANY(CAST(? AS BIGINT[])) AND t.list_id = ANY(CAST(? AS BIGINT[]))""", (tids, lids))}


def circle_video_public(c, path, va, b, lids):
    """(#7478) True: the write reaches the customer page of a sign-off (videos/review.py: it shows the customer's own comments
    and the team's answers to them, with done): an answer to a customer's comment (POST .../comments with parent_id) or done /
    open of a customer's comment or of an answer to one (PATCH .../comments/{}). Always, also without a live customer link
    (reader F4: a link made later shows the whole customer thread). The comment id is read exactly as the route reads it
    (videos/v1.py vdr_v1_id, reader F1: "+7" or "7_0" reach comment 7 there; unreadable = the route's 400 here too).
    The team's other comments stay internal: their project's circle decides (control.CTL_OBJ /videos/{}).
    Only for a sign-off of a project of the request the agent sees (lids, reader F7: like circle_ticket_tasks, review G9 -
    a sign-off of somebody else's project gives no answer here, else the gate would tell which foreign ones have customer
    comments; the route answers its 404)."""
    vid = _int(va.get("vid"))
    if not vid or not (path == "/videos/{}/comments" or path == "/videos/{}/comments/{}"):
        return False
    from ..videos.v1 import vdr_v1_id  # here: videos loads the collab modules, which load the agents
    if path == "/videos/{}/comments":
        cid = _int(b.get("parent_id"))
    else:
        cid = vdr_v1_id(va.get("comment_id"), "comment_id")
    if not cid:
        return False
    lids = sorted({int(x) for x in lids or [] if x})
    if not lids:
        return False
    with system_ctx(c):  # the comment's author kind, whatever the agent's own view of it (the sign-off is in lids: seen)
        p = c.execute("SELECT COALESCE(v.list_id, t.list_id) FROM video_reviews v LEFT JOIN tasks t ON t.id=v.task_id WHERE v.id=?",
                      (vid,)).fetchone()
        if not p or p[0] not in lids:
            return False
        x = c.execute("""SELECT k.ext_name, p.ext_name AS par_ext FROM obj_comments k LEFT JOIN obj_comments p ON p.id=k.parent_id
                         WHERE k.id=? AND k.kind='video' AND k.ref_id=?""", (cid, vid)).fetchone()
    return bool(x and (x["ext_name"] or (path != "/videos/{}/comments" and x["par_ext"])))


def circle_nodes(c, aid):
    """The nodes of the file store shared with exactly agent aid and alive (not run out, not in the trash; a projects folder
    is the agent's memberships, counted as projects) -> ([node id], over). over (review G10): more shares than
    CIRCLE_NODES_MAX -- the rule cannot read them all, so it answers "wider". As agents/agsees.py reads them."""
    with system_ctx(c):
        rows = c.execute("""SELECT DISTINCT s.node_id FROM fs_shares s WHERE (s.agent_id=? OR s.user_id=?) AND COALESCE(s.list_own, 0)=0
                            AND (s.expires_at IS NULL OR s.expires_at > ?) ORDER BY s.node_id LIMIT ?""",
                         (aid, aid, iso(now_utc()), CIRCLE_NODES_MAX + 1)).fetchall()
        over = len(rows) > CIRCLE_NODES_MAX
        chains = fs_chains(c, [r[0] for r in rows])  # one read for all of them
        out, area = [], {}
        for r in rows:
            chain = chains.get(r[0])
            if not chain or fs_deleted(chain):
                continue
            top = chain[-1]["id"]
            if top not in area:
                area[top] = fs_area_root_of(c, top)
            if area[top] and area[top][1] == "lists":
                continue
            out.append(r[0])
    return out, over


def _sources(c, aid):
    """Everything agent aid reads, once per request (review G11): {reach: its projects, all / full: their circles
    (list_circles2), nodes: its node shares, over, chains: the nodes' chains (read at the first use), reads: {person: reads
    every node}}."""
    from .safety import agent_reach  # here, not on top: safety loads agents.admin, which loads the gate (and so this module)
    memo = g.setdefault("_circle_src", {}) if has_request_context() else {}
    if aid not in memo:
        with system_ctx(c):  # also asked for another account's request (wk_mute: a person looks at the task): the agent's own reach
            reach = agent_reach(c, aid)
        nodes, over = circle_nodes(c, aid)
        al, full = list_circles2(c, reach)
        memo[aid] = {"reach": reach, "all": al, "full": full, "nodes": nodes, "over": over, "chains": None, "reads": {}, "ok": None}
    return memo[aid]


def _reads_nodes(c, src, p):
    """Does person p have a role on every node share of the agent? Once per request and person, the chains once."""
    if not src["nodes"]:
        return True
    if p not in src["reads"]:
        with system_ctx(c):  # another person's role on a node: structure only (yes / no), nothing of it is handed on
            if src["chains"] is None:
                src["chains"] = fs_chains(c, src["nodes"])
            roles = fs_roles_many(c, src["nodes"], p, chains=src["chains"])
        src["reads"][p] = all((roles.get(n) or (False, None))[1] for n in src["nodes"])
    return src["reads"][p]


def circle_ids(v):
    """The people of a stored circle ("3,7,12") as a frozenset; '' / None = none stored."""
    return frozenset(int(x) for x in str(v or "").split(",") if x.strip().isdigit())


def circle_csv(people):
    return ",".join(str(x) for x in sorted(people))


def bridge_holds(c, row, circ):
    """Does the approval row of agent_bridges still hold (review G5)? Only while both projects' circles of today (circ
    {lid: people}) lie inside the circles the person approved (circle_a / circle_b) -- a person who came since was never
    approved. A row without stored circles (never: the start step filled the old ones) holds nothing."""
    a, b = circle_ids(row["circle_a"]), circle_ids(row["circle_b"])
    return bool(a and b and circ.get(row["list_a"]) is not None and circ.get(row["list_b"]) is not None
                and circ[row["list_a"]] <= a and circ[row["list_b"]] <= b)


def _approved(c, aid, circ):
    """The pairs of projects a person approved as a bridge for agent aid and that still hold: {(smaller id, larger id)}.
    bridge_holds, and the person who approved still manages both projects (the owner of a personal agent may approve the
    share without managing them, safety.may_approve_bridge: that opens the share, not the free way of the gate)."""
    out = set()
    with system_ctx(c):
        for r in c.execute("SELECT list_a, list_b, by_id, circle_a, circle_b FROM agent_bridges WHERE agent_id=?", (aid,)).fetchall():
            if bridge_holds(c, r, circ) and r["by_id"] and all(list_role(c, x, r["by_id"]) in MANAGE_ROLES for x in (r["list_a"], r["list_b"])):
                out.add((r["list_a"], r["list_b"]))
    return out


def circle_wider(c, aid, people, src, lid=None, circ=None):
    """Does one person of people (the target's readers) not read one of the agent's sources (src = _sources)? lid: the
    target project (itself no source; its approved bridges hold), circ: all circles incl. the target's (for the bridges)."""
    if not people:
        return False  # nobody reads the target (the agent's own project without a person)
    if src["over"]:
        return True
    ok = None
    for x in src["reach"]:
        if x == lid or not src["all"].get(x) or people <= src["full"][x]:
            continue
        if lid:
            if ok is None:
                ok = _approved(c, aid, circ if circ is not None else src["all"])
            if (min(x, lid), max(x, lid)) in ok:
                continue
        return True
    if src["nodes"]:
        if len(people) * len(src["nodes"]) > CIRCLE_PAIRS_MAX:
            return True
        return any(not _reads_nodes(c, src, p) for p in sorted(people))
    return False


def circle_reader(c, aid, uid):
    """Does person uid read EVERY source of agent aid (a full role in each of its projects with people, a role on each of
    its node shares)? The person a team agent may write to, see its status text, and whose Yes counts on a card of this
    rule (review G12, G13)."""
    src = _sources(c, aid)
    if not uid or src["over"]:
        return False
    if any(src["all"].get(x) and uid not in src["full"][x] for x in src["reach"]):
        return False
    return _reads_nodes(c, src, uid)


def circle_person(c, a, uid):
    """"wider" | None for a message of agent row a to person uid (POST /agent/chats/<uid>; review G12): a TEAM agent
    writes to everybody it shares an open project with -- a person who does not read every source of it is a wider circle.
    A personal agent writes only to its owner (agents/core.py agent_shares): free. A person the agent cannot write to at
    all: None (the route refuses)."""
    if a["owner_id"] or not isinstance(uid, int) or isinstance(uid, bool):
        return None
    if not agent_shares(c, a["user_id"], uid):
        return None
    return None if circle_reader(c, a["user_id"], uid) else "wider"


def _int(v):
    return v if isinstance(v, int) and not isinstance(v, bool) and v > 0 else None


def _obj_targets(c, path, va, b):
    """The objects of the shared core a request without a project writes into: [(kind, id)], or None = the gate cannot
    name the target. Read with the agent's own view (a row it does not see = not nameable)."""
    def under(p):
        return path == p or path.startswith(p + "/")

    def moved(kind, cur, key):  # the object the row lies in + the one a body moves it into
        if not cur:
            return None
        if b.get(key) is None:
            return [(kind, cur)]
        return [(kind, cur), (kind, _int(b[key]))] if _int(b[key]) else None
    if under("/events/{}") and "eid" in va:
        r = c.execute("SELECT cal_id FROM events WHERE id=?", (va["eid"],)).fetchone()
        return moved(K_CAL, r[0] if r else None, "cal_id")
    if path == "/events":
        return [(K_CAL, _int(b.get("cal_id")))] if _int(b.get("cal_id")) else None  # none given: the route picks a default
    if under("/event-calendars/{}") and "cid" in va:
        return [(K_CAL, va["cid"])]
    if under("/contacts/{}") and "cid" in va:
        r = c.execute("SELECT book_id FROM contacts WHERE id=?", (va["cid"],)).fetchone()
        return moved(K_BOOK, r[0] if r else None, "book_id")
    if path == "/contacts":
        return [(K_BOOK, _int(b.get("book_id")))] if _int(b.get("book_id")) else None
    if under("/address-books/{}") and "bid" in va:
        return [(K_BOOK, va["bid"])]
    if under("/files/{}") and "nid" in va:
        return [(K_FILE, va["nid"])]
    if path == "/files":
        return [(K_FILE, _int(b.get("parent_id")))] if _int(b.get("parent_id")) else None  # none given: the agent's own folder
    return None  # a table without a project, office, documents, polls ...: the shared core names no readers for them here


def _obj_people(c, kind, rid):
    """The people who read object rid of kind, or None = too many to ask (CIRCLE_PEOPLE_MAX) / no such object. A calendar,
    an address book: the people with a role from the shared core (core/objects.py obj_role, THE role there). A file or
    folder: the people with a role on the node (files/store.py fs_role -- the core's kind of the file store only answers
    for its trash). Asked per person: everybody while the instance has few people; else the people of the object's
    organisation plus everybody a share on its node's chain names; a private object then is not nameable."""
    person = "COALESCE(u.kind,'user')!='agent' AND u.id NOT IN (SELECT user_id FROM agents)"
    with system_ctx(c):  # the readers of the target, also people the agent does not see: ids only, a yes / no per person
        if kind == K_FILE:
            chain = fs_chain(c, rid)
            if not chain or fs_deleted(chain):
                return None
            org = chain[0]["org_id"] or None
        else:
            sp = obj_space(c, kind, rid)
            if sp is None:
                return None
            org, n = sp[0], fs_ref_node(c, kind, rid)
            chain = fs_chain(c, n["id"]) if n else []
        cand = [r[0] for r in c.execute(f"SELECT u.id FROM users u WHERE {person} ORDER BY u.id LIMIT ?", (CIRCLE_PEOPLE_MAX + 1,))]
        if len(cand) > CIRCLE_PEOPLE_MAX:
            if not org:
                return None
            ids = [x["id"] for x in chain]
            cand = [r[0] for r in c.execute(
                f"""SELECT u.id FROM users u WHERE {person} AND (u.id IN (SELECT user_id FROM org_members WHERE org_id=?)
                    OR u.id IN (SELECT user_id FROM fs_shares WHERE node_id = ANY(CAST(? AS BIGINT[])) AND user_id IS NOT NULL)
                    OR u.id IN (SELECT m.user_id FROM group_members m JOIN fs_shares s ON s.group_id=m.group_id
                                WHERE s.node_id = ANY(CAST(? AS BIGINT[])))) ORDER BY u.id LIMIT ?""",
                (org, ids, ids, CIRCLE_PEOPLE_MAX + 1))]
            if len(cand) > CIRCLE_PEOPLE_MAX:
                return None
        if kind == K_FILE:
            return frozenset(p for p in cand if fs_role(c, rid, p, chain=chain))
        return frozenset(p for p in cand if obj_role(c, p, kind, rid))


def _obj_sees(c, aid, kind, rid):
    """Does the agent itself see the object (review G9: asked before anything of it is read as "system")?"""
    return bool(fs_role(c, rid, aid) if kind == K_FILE else obj_role(c, aid, kind, rid))


def _wiki_target(c, aid, va, b):
    """A knowledge page as the target -> ("public" | "wider" | None, its readers or None): a live share covers the page
    (PATCH / append / replace), or the space of the folder a new page goes into has live shares at all (a folder's share
    covers pages made later). No share: the readers are the space's own people -- the owner of a private space, the
    organisation's people (admin, member, read-only) of an organisation's. (None, None) = not nameable: no such page /
    folder, or one the agent itself does not see (review G9: asked first, with the agent's own role -- the same answer
    for both, so the gate tells nothing about a page of somebody else)."""
    if "pid" in va:
        try:
            wkv_need(c, aid, va["pid"])  # the route's own check (wiki/wkv1.py): its role through the folders' shares
        except Denied:
            return None, None
    else:
        fid = _int(b.get("folder_id"))
        if not fid or not fs_role(c, fid, aid):
            return None, None
    with system_ctx(c):  # the space's shares and people (structure only): the readers must not shrink to what the agent sees
        if "pid" in va:
            r = c.execute(f"SELECT id, org_id, owner_id, path FROM wiki_pages WHERE id=? AND {live_sql()}", (va["pid"],)).fetchone()
            if not r:
                return None, None
            org, owner = r["org_id"] or None, None if r["org_id"] else r["owner_id"]
            rows = [s for s in wsh_live_rows(c, org, owner) if wsh_covers(s, r["path"], r["id"])]
        else:
            top = _root_of_chain(c, fs_chain(c, fid))
            if top is None:
                return None, None
            org, owner = top["org_id"] or None, None if top["org_id"] else top["owner_id"]
            rows = wsh_live_rows(c, org, owner)
        if rows:
            return ("public" if any((s["kind"] if "kind" in s.keys() else "") == "link" for s in rows) else "wider"), None
        if not org:
            return None, frozenset([owner] if owner else [])
        return None, frozenset(x[0] for x in c.execute("""SELECT m.user_id FROM org_members m JOIN users u ON u.id=m.user_id WHERE m.org_id=?
                                                          AND m.role IN ('admin', 'member', 'readonly') AND COALESCE(u.kind,'user')!='agent'""", (org,)))


def _room_people(c, aid, va, path):
    """The people of a team chat room without a project (a channel, a group, a direct message), or None = not nameable (no
    such room, a project's room, or a room the agent is not in -- review G9: its own membership is asked first)."""
    if path.startswith("/team/rooms/{}") and "rid" in va:
        q, a = "SELECT * FROM tchat_rooms WHERE id=?", va["rid"]
    elif path.startswith("/team/messages/{}") and "mid" in va:
        q, a = "SELECT r.* FROM tchat_msgs m JOIN tchat_rooms r ON r.id=m.room_id WHERE m.id=?", va["mid"]
    else:
        return None
    with system_ctx(c):  # the room's row and member ids (structure only): the readers must not shrink to what the agent sees
        r = c.execute(q, (a,)).fetchone()
        if not r or r["list_id"] or not tchat_room_ok(c, r, aid):
            return None
        ids = sorted(x for x in tchat_room_members(c, r) if x)
        if not ids:
            return frozenset()
        return frozenset(x[0] for x in c.execute("SELECT id FROM users WHERE id = ANY(CAST(? AS BIGINT[])) AND COALESCE(kind,'user')!='agent'", (ids,)))


def _target(c, a, path, va, b):
    """A target without a project -> ("public" | "wider" | None, its readers | None = the gate cannot name them)."""
    aid = a["user_id"]
    if path == "/lists":
        # a new project of the agent is its own until somebody shares it (an agent's share waits for a person): nobody reads
        # it. (#7142): also a team agent's and one for an organisation -- a project without a folder and not of a
        # family gets no person on creation (lists.list_created: folder people and groups come only through a folder; the
        # organisation reads it only once it is opened, access.ov_open; the admins' overview only shared ones, orgtasks.ot_lists).
        # In a folder or of a family: not nameable
        own = not any(b.get(k) not in (None, "", False) for k in ("folder", "family"))
        return None, (frozenset() if own else None)
    if path == "/filters" or path == "/filters/{}":
        # (#7142): a saved view the agent keeps for itself (POST /api/v1/filters makes only private ones) is read by
        # nobody else; a project's shared view: not nameable here (and the route holds it, lists/sections.py need_filter)
        if path == "/filters":
            return None, frozenset()
        with system_ctx(c):
            r = c.execute("SELECT user_id, shared FROM filters WHERE id=?", (va.get("fid"),)).fetchone()
        return None, (frozenset() if r and not r["shared"] and r["user_id"] == aid else None)
    if path == "/wiki/pages" or path.startswith("/wiki/pages/{}"):
        return _wiki_target(c, aid, va, b)
    if path.startswith("/team/rooms/{}") or path.startswith("/team/messages/{}"):
        return None, _room_people(c, aid, va, path)
    objs = _obj_targets(c, path, va, b)
    if not objs:
        return None, None
    people = set()
    for kind, rid in objs:
        if not _obj_sees(c, aid, kind, rid):  # review G9: an object the agent does not see is no nameable target
            return None, None
        p = _obj_people(c, kind, rid)
        if p is None:
            return None, None
        people |= p
    return None, frozenset(people)


def circle_tasks(c, method, path, va, b):
    """The tasks a request changes in a way a client of the portal reads (title, state, an answer marked for the client)."""
    if path == "/tasks/batch":
        return [x for x in b.get("ids") or [] if isinstance(x, int) and not isinstance(x, bool)][:500] if isinstance(b.get("ids"), list) else []
    if "tid" not in va or not (path == "/tasks/{}" or path.startswith("/tasks/{}/")):
        return []
    if path == "/tasks/{}/working":  # the agent's mark is never shown to a client
        return []
    if path == "/tasks/{}/comments":  # an internal comment never leaves the app (comments.portal = 0)
        return [va["tid"]] if b.get("portal") not in (None, False, 0, "0", "false", "") else []
    return [va["tid"]]


def circle_of(c, a, method, path, va, b, lids):
    """None | "wider" | "public" for a write request of agent row a (module docstring). path = control.ctl_rule_path, va = the
    route variables, b = the JSON body, lids = the projects the request concerns (control.ctl_lists; only ones the agent sees)."""
    aid = a["user_id"]
    lids = [x for x in lids or [] if x]
    if lids and circle_public_lists(c, lids):
        return "public"
    if circle_ticket_tasks(c, circle_tasks(c, method, path, va, b), lids):
        return "public"
    if circle_video_public(c, path, va, b, lids):
        return "public"
    src = _sources(c, aid)
    if path == "/tasks" and not lids:  # a new task without a project: the agent's own basket
        lids = [r[0] for r in c.execute("SELECT id FROM lists WHERE owner_id=? AND is_inbox AND id = ANY(CAST(? AS BIGINT[]))", (aid, src["reach"]))][:1]
        if not lids:
            return None
    if lids:
        if not src["nodes"] and not src["over"] and len(set(src["reach"]) | set(lids)) == 1:
            return None  # ONE project and nothing else (review G3: reach and targets together): nothing can flow
        circ = {**src["all"], **list_circles(c, [x for x in lids if x not in src["all"]])}
        return "wider" if any(circle_wider(c, aid, circ.get(t) or frozenset(), src, lid=t, circ=circ) for t in lids) else None
    w, people = _target(c, a, path, va, b)
    if w:
        return w
    if people is not None:
        return "wider" if circle_wider(c, aid, people, src) else None
    # a target whose readers the gate cannot name (review G2): a card as soon as the agent has more than one source
    return "wider" if src["over"] or sum(1 for x in src["reach"] if src["all"].get(x)) + len(src["nodes"]) > 1 else None


def wk_mute(c, marks):
    """The "agent is working" marks {task id: agent id} that show no text: the task's project is a wider or public place for
    that agent. The progress line (the last line of the job's log, whatever route wrote it: the mark itself, a job's log) is
    no channel of its own there -- people see that the agent works, not its words. Asked when the mark is read, so every way
    of writing the log is covered. One answer per agent and project for WK_MUTE_TTL seconds (review G11: this runs at every
    load of tasks with a mark; a project that became wider / public shows no words after that time at the latest). The job
    list hides title, name and log by the same answer (agents/core.py job_dict, review G4)."""
    if not marks:
        return set()
    out = set()
    with system_ctx(c):
        lists = {r[0]: r[1] for r in c.execute("SELECT id, list_id FROM tasks WHERE id = ANY(CAST(? AS BIGINT[]))", (sorted(marks),))}

    def ask(aid, tid, lid):
        with system_ctx(c):  # the agent's own row (its level), also when a person of another organisation looks at the task
            a = agent_row(c, aid)
        return bool(a is not None and circle_of(c, a, "POST", "/tasks/{}/working", {"tid": tid}, {}, [lid]))
    for tid, aid in marks.items():
        lid = lists.get(tid)
        if lid and _short(("wk", aid, lid), lambda: ask(aid, tid, lid)):
            out.add(tid)
    return out


def st_mute(c, a, uid):
    """Is the status text of agent row a hidden from person uid (review G12)? A TEAM agent: everybody who shares a project
    with it sees its status, so its words show only to a person who reads every source of it (the simple form, as the
    progress line). A personal agent's status is its owner's: shown."""
    if a is None or a["owner_id"] or not uid or uid == a["user_id"]:
        return False
    return _short(("st", a["user_id"], uid), lambda: not circle_reader(c, a["user_id"], uid))


def job_mute(c, aid, uid):
    """2.1398.0 (#6863): are the words (title, name, log) of a job of agent aid WITHOUT a task hidden from person uid? No
    task, no place whose circle wk_mute could ask: the job reaches the person it is for (the gate asks for that person, as
    for a chat message: control.ctl_meta_circle) and the admins who share the agent (core.job_visible) -- a team agent's
    words show there only to a person who reads every source of it (as wk_mute). A personal agent: never."""
    if not uid or uid == aid:
        return False

    def ask():
        with system_ctx(c):  # the agent's own row, also when a person of another organisation looks
            a = agent_row(c, aid)
        return bool(a is not None and not a["owner_id"] and not circle_reader(c, aid, uid))
    return _short(("jb", aid, uid), ask)


WK_MUTE.append(wk_mute)
ST_MUTE.append(st_mute)
JOB_MUTE.append(job_mute)
