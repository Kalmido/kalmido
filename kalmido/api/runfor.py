"""2.1287.0 (#6454, review): the run of a team agent for a person -- the one gate over every route of /api/v1.

The run token of a TEAM server agent carries the person it works for (api_tokens.asked_by, agents/srvteam.py srv_run_cut;
core/access.py run_person / act_for). Projects are cut by the token (token_lists), the areas without a project by their
role functions (for_cap). What neither reaches is decided HERE, once, for every route: RUN_ROUTES names for each route of
/api/v1 how it is held in such a run, and run_gate (called by api/v1.py api_authenticate for every request of a run token)
refuses what is not held. A route missing in the table is CLOSED in a run (and tests/p6454_c_run_routes_test.py is red
until somebody decides): a new route never reaches a run without a cap by forgetting.

The classes:
  cut      everything it reaches is a project of the run's cut (list_role / vis_sql / task_visible: token_lists); writes
           by the control level, capped to the requester's role in the project (agents/control.py ctl_cap)
  cap      the area's role function ends with the person cap (obj_role / obj_need, fs_role, book_role, wkf_role, sh_may,
           the calendars' ev_role / my_cal_ids, the rooms' obj_need): at most the requester's own role
  mine     the agent's own channel, answered in a run only with the requester's rows (run_person; run_job_ok, run_chat_ok)
  pin:<p>  the route names a person (path, query or body parameter <p>): in a run that person is the requester, nobody else
  send     writes a message or a card to a person who shares a project of the run's cut; reads nothing of that person
           (the designed way of a reader's order: the card goes to somebody who may decide)
  org      an area of the agent's organisation as a whole (polls, equipment, absences, new projects / tables / calendars):
           only when the requester is a full member or admin of that organisation (run_org_ok); never a run without a person
  closed   reaches over all the agent's projects or by the agent's own membership, with no cap: only when the requester is
           an admin of the agent's organisation (run_boss: they reach all of it themselves); never a run without a person
  own      the agent's own technical data (status, usage, rules, queue, its habits and filters): no content of other places
  noagent  an agent's token never gets here (a scope agents never have, need_person, a key of another kind)
  safe     no access question (help texts, the OpenAPI document, the server's announcement)
Personal agents, ordinary tokens and people are untouched: their token carries no requester (run_person() is None)."""
import re

from flask import g, request

from ..accounts.orgroles import org_role_key
from ..core.access import list_role, run_person
from ..core.i18n import tr
from ..core.pg import system_ctx
from ..api.common import v1_err

RUN_PASS = ("cut", "cap", "mine", "send", "own", "noagent", "safe")
RUN_CLASSES = RUN_PASS + ("pin", "org", "closed")
RUN_FULL = ("admin", "member")  # the organisation roles that reach the organisation's areas themselves


def run_key(method, rule):
    """'GET /tasks/{}' of a request's method and url rule (the key of RUN_ROUTES)."""
    m = "GET" if method in ("HEAD", "OPTIONS") else method
    return m + " " + re.sub(r"<[^>]+>", "{}", rule[len("/api/v1"):])


def _agent_org(c, aid):
    with system_ctx(c):  # structure: the agent's workspace
        r = c.execute("SELECT org_id FROM agents WHERE user_id=?", (aid,)).fetchone()
    return r[0] if r else None


def run_org_ok(c, aid, by):
    """Is person by a full member / admin of team agent aid's organisation? An agent without an organisation has no such
    areas (its own private space only): True."""
    oid = _agent_org(c, aid)
    if not oid:
        return True
    with system_ctx(c):
        return org_role_key(c, by, oid) in RUN_FULL


def run_boss(c, aid, by):
    """Is person by an admin of team agent aid's organisation (an agent without one: of the server)?"""
    oid = _agent_org(c, aid)
    with system_ctx(c):
        if oid:
            return org_role_key(c, by, oid) == "admin"
        r = c.execute("SELECT is_admin FROM users WHERE id=? AND NOT disabled", (by,)).fetchone()
        return bool(r and r[0])


def _named(name):
    """The values the request gives for person parameter name: path, query, JSON body."""
    out = []
    va = request.view_args or {}
    if name in va:
        out.append(va[name])
    out.extend(request.args.getlist(name))
    b = request.get_json(silent=True) if request.is_json else None
    if isinstance(b, dict) and b.get(name) not in (None, ""):
        out.append(b[name])
    return out


def run_gate(c, row, u):
    """api_authenticate: a 403 for a request of a run token (row: api_tokens with asked_by) the table does not hold, else None."""
    by = row["asked_by"] if "asked_by" in row.keys() else None
    if by is None or request.url_rule is None:
        return None
    by = int(by)
    if g.get("approved_job") and g.get("ctl_for"):
        by = int(g.ctl_for)  # the replay of an approved request: the person who said Yes (api/scopes.py approval_replay_token)
    cls = RUN_ROUTES.get(run_key(request.method, request.url_rule.rule), ("closed", ""))[0]
    kind, _, par = cls.partition(":")
    if kind in RUN_PASS:
        return None
    if kind == "pin":
        if all(str(v) == str(by) and by for v in _named(par)):
            return None
        return v1_err(403, tr("In this run you work for one person: only that person can be named here"), name="run_person", parameter=par)
    ok = bool(by) and (run_org_ok(c, u["id"], by) if kind == "org" else run_boss(c, u["id"], by))
    if ok:
        return None
    return v1_err(403, tr("Not available in this run: the person you work for does not reach this themselves"), name="run_closed")


# 2.1386.0 (#6668): what the long-lived token of a team agent that works per request still reaches: its own technical
# data and what asks nothing (the classes REQ_MAIN_PASS) plus its channel, by name (REQ_MAIN_CHANNEL: what the reference
# starter mcp/agent_run.py and its job runner agent_job.py send with that token -- events, chats, jobs, progress, typing).
# Review F1: the classes mine / send / pin are capped only by run_person(), which is None for this token -- so no class of
# them as a whole: /search, /news, /time/*, /office/*, /briefing, /me/waiting, /layouts/* ... need the request token.
# tests/p6668_ext_team_agent_test.py checks every route of RUN_ROUTES against these two.
REQ_MAIN_PASS = ("own", "safe", "noagent")
REQ_MAIN_CHANNEL = frozenset((
    "GET /agent/chats", "POST /agent/chats/{}", "POST /agent/chats/{}/messages/{}/withdraw",
    "GET /agent/events", "GET /agent/jobs", "GET /agent/jobs/{}", "PATCH /agent/jobs/{}",
    "POST /agent/progress", "POST /agent/typing",
))


def req_main_open(key):
    """2.1386.0 (#6668, review F1): does the long-lived token of a team agent per request reach route key ('GET /agent')?"""
    return RUN_ROUTES.get(key, ("closed", ""))[0].partition(":")[0] in REQ_MAIN_PASS or key in REQ_MAIN_CHANNEL


def req_main_gate(c, row, u):
    """2.1386.0 (#6668, agents/reqtoken.py): api/v1.py api_authenticate -- a 403 for a request of the long-lived token of a
    team agent that works per request (agents.per_request) on a route outside its own channel, else None. A run / request
    token (asked_by) is held by run_gate; the replay of an approved job and the step of an answered card (run in this process
    by agents/control.py ctl_run_replay, environ "kalmido.ctl_run" = CTL_RUN_ENV, never set by a network request: the step a
    person said Yes to; review F3: only a write -- ctl_gate then always checks the card and the rights of the person who said
    Yes, also without a control level; a read through a card needs the request token; second review F1: a write ctl_class
    calls "meta" gets no card check in ctl_gate, so ctl_gate holds it with req_main_step below) are no such request."""
    if ("asked_by" in row.keys() and row["asked_by"] is not None) or g.get("approved_job") or request.url_rule is None:
        return None
    if request.environ.get("kalmido.ctl_run") and request.method in ("POST", "PUT", "PATCH", "DELETE"):
        return None  # review F3: only a change, and agents/control.py ctl_gate checks the card and the Yes-sayer's rights
    with system_ctx(c):  # structure: the agent row
        a = c.execute("SELECT owner_id, per_request FROM agents WHERE user_id=?", (u["id"],)).fetchone()
    if a is None or a["owner_id"] or not a["per_request"]:
        return None
    if req_main_open(run_key(request.method, request.url_rule.rule)):
        return None
    return v1_err(403, tr("This agent works per request: use the request token of the event (POST /api/v1/agent/request-token)"),
                  name="request_token_needed")


def req_main_step():
    """2.1386.0 (#6668, second review F1): agents/control.py ctl_gate -- the "meta" step of an answered card run with the
    long-lived token of a team agent per request (req_main_gate lets every write of a card run through, and ctl_gate checks
    no card for a meta step): a 403 request_token_needed outside the agent's own channel (req_main_open), else None. So the
    token reaches e.g. POST /tasks/brief or /news/read through a card no more than without one."""
    if req_main_open(run_key(request.method, request.url_rule.rule)):
        return None
    return v1_err(403, tr("This agent works per request: use the request token of the event (POST /api/v1/agent/request-token)"),
                  name="request_token_needed")


def run_job_ok(c, j):
    """May the request read / change job j of its agent? No run: yes. A run: the requester's jobs, and the agent's own jobs
    without a person whose task (if any) lies in the run's cut."""
    by = run_person()
    if by is None:
        return True
    if j["user_id"]:
        return bool(by) and j["user_id"] == by
    if not j["task_id"]:
        return True
    t = c.execute("SELECT list_id FROM tasks WHERE id=?", (j["task_id"],)).fetchone()
    return bool(t and list_role(c, t[0], j["agent_id"]))


def run_chat_ok(uid):
    """May the request read the agent's conversation with person uid? No run: yes. A run: only the requester's."""
    by = run_person()
    return by is None or (bool(by) and int(uid) == by)


# route -> (class, by what). Sorted by path; tests/p6454_c_run_routes_test.py compares it with the routes of the server.
RUN_ROUTES = {
    "GET /absences": ("org", "an area of the agent's organisation: only for a requester who is a full member of it"),
    "GET /address-books": ("cap", "op_books -> books_for -> my_book_ids kalmido/contacts/model.py (act_for ); book_public -> book_role"),
    "POST /address-books": ("org", "an area of the agent's organisation: only for a requester who is a full member of it"),
    "DELETE /address-books/{}": ("cap", "op_book_delete -> need_book(manage) kalmido/contacts/model.py -> book_role (for_cap )"),
    "PATCH /address-books/{}": ("cap", "the area's role function ends with for_cap (calendars: ev_role / my_cal_ids, files: fs_role / fs_ref_role, books: book_role, tables: sh_may)"),
    "GET /address-books/{}/export": ("cap", "op_export -> need_book kalmido/contacts/model.py (book_role, for_cap)"),
    "POST /address-books/{}/import": ("cap", "need_book(write) kalmido/contacts/model.py (book_role, for_cap); op_import kalmido/contacts/web.py"),
    "DELETE /address-books/{}/members/{}": ("cap", "op_book_member_rm kalmido/contacts/web.py -> need_book (book_role, for_cap)"),
    "PUT /address-books/{}/members/{}": ("cap", "the area's role function ends with for_cap (calendars: ev_role / my_cal_ids, files: fs_role / fs_ref_role, books: book_role, tables: sh_may)"),
    "GET /approvals/diff": ("noagent", "need_person 403 kalmido/agents/proposals.py v1_approval_diff (2.1386.0, #6623)"),
    "GET /admin/agents/{}/audit": ("noagent", "api_authenticate admin gate kalmido/api/v1.py; spec scope admin-read kalmido/api/openapi.py"),
    "PUT /admin/announcement": ("noagent", "scope account (hosting_spec kalmido/admin/hosting.py) + is_admin + need_scope admin-read"),
    "GET /admin/orgs/activity": ("noagent", "api_authenticate api/v1.py; scope admin-read (SCOPES_AGENT_NEVER api/v1.py)"),
    "GET /admin/status": ("noagent", "api_authenticate api/v1.py; scope admin-read (SCOPES_AGENT_NEVER api/v1.py)"),
    "GET /admin/users": ("noagent", "api_authenticate api/v1.py; scope admin-read (SCOPES_AGENT_NEVER api/v1.py)"),
    "GET /agent": ("own", "need_agent kalmido/agents/core.py; agent_self kalmido/agents/api.py"),
    "POST /agent/aborted": ("own", "need_agent; own job check agent_jobs.agent_id kalmido/agents/api.py"),
    "POST /agent/approvals/{}/run": ("own", "the agent's own card; the step runs again through this gate and the caps"),
    "GET /agent/chats": ("mine", "only the requester's rows (core/access.py run_person)"),
    "POST /agent/chats/{}": ("send", "writes a message / card to a person who shares a project of the run's cut (agent_shares / the project's people); reads nothing of theirs"),
    "POST /agent/chats/{}/messages/{}/pin": ("pin:uid", "only in the requester's own chat"),
    "POST /agent/chats/{}/messages/{}/reactions": ("pin:uid", "only in the requester's own chat"),
    "POST /agent/chats/{}/messages/{}/withdraw": ("pin:uid", "only in the requester's own chat"),
    "GET /agent/chats/{}/reply-style": ("pin:uid", "only in the requester's own chat"),
    "POST /agent/request-token": ("own", "2.1386.0 (#6668): only the agent's own long-lived token (agents/reqtoken.py); a run / request token 403"),
    "POST /agent/decisions": ("own", "need_agent; ctl_log kalmido/agents/control.py"),
    "GET /agent/events": ("mine", "only the requester's rows (core/access.py run_person)"),
    "GET /agent/jobs": ("mine", "only the requester's rows (core/access.py run_person)"),
    "POST /agent/jobs": ("send", "writes a message / card to a person who shares a project of the run's cut (agent_shares / the project's people); reads nothing of theirs"),
    "GET /agent/jobs/{}": ("mine", "only the requester's rows (core/access.py run_person)"),
    "PATCH /agent/jobs/{}": ("mine", "only the requester's rows (core/access.py run_person)"),
    "POST /agent/jobs/{}/proposal": ("mine", "only the requester's rows (core/access.py run_person)"),
    "GET /agent/objects/{}": ("cap", "v1_obj_list kalmido/core/objweb.py -> obj_rows kalmido/core/objects.py (_visible_sql act_for , obj_role)"),
    "GET /agent/objects/{}/{}": ("cap", "_one kalmido/core/objweb.py -> obj_need kalmido/core/objects.py -> obj_role (_for_cap )"),
    "PATCH /agent/objects/{}/{}": ("cap", "obj_write kalmido/core/writes.py -> obj_need(write)"),
    "GET /agent/objects/{}/{}/links": ("cap", "the area's role function ends with for_cap (calendars: ev_role / my_cal_ids, files: fs_role / fs_ref_role, books: book_role, tables: sh_may)"),
    "POST /agent/objects/{}/{}/links": ("cap", "the area's role function ends with for_cap (calendars: ev_role / my_cal_ids, files: fs_role / fs_ref_role, books: book_role, tables: sh_may)"),
    "DELETE /agent/objects/{}/{}/links/{}": ("cap", "obj_unlink kalmido/core/objlinks.py (obj_need write on the source; src must be a core kind)"),
    "POST /agent/objects/{}/{}/proposals": ("send", "writes a message / card to a person who shares a project of the run's cut (agent_shares / the project's people); reads nothing of theirs"),
    "POST /agent/progress": ("pin:chat_user_id", "only into the requester's own chat"),
    "POST /agent/proposals": ("pin:user_id", "a named person must be the requester"),
    "POST /agent/proposals/import": ("pin:user_id", "a named person must be the requester"),
    "POST /agent/proposals/sheet-tasks": ("send", "writes a message / card to a person who shares a project of the run's cut (agent_shares / the project's people); reads nothing of theirs"),
    "POST /agent/proposals/shoot": ("send", "writes a message / card to a person who shares a project of the run's cut (agent_shares / the project's people); reads nothing of theirs"),
    "POST /agent/proposals/time": ("send", "writes a message / card to a person who shares a project of the run's cut (agent_shares / the project's people); reads nothing of theirs"),
    "GET /agent/queue": ("cut", "_wq_rows kalmido/agents/workqueue.py (vis_sql + tvis as the agent)"),
    "PUT /agent/queue": ("cut", "_wq_rows kalmido/agents/workqueue.py; UPDATE agents.queue_order"),
    "DELETE /agent/quota": ("own", "need_agent; kalmido/agents/quota.py"),
    "GET /agent/quota": ("own", "need_agent; kalmido/agents/quota.py"),
    "PUT /agent/quota": ("own", "need_agent; kalmido/agents/quota.py"),
    "GET /agent/rules": ("mine", "the rules are the agent's own; a chat source only of the requester's chat"),
    "POST /agent/rules": ("mine", "the rules are the agent's own; a chat source only of the requester's chat"),
    "GET /agent/schedules": ("mine", "only the requester's rows (core/access.py run_person)"),
    "PUT /agent/status": ("own", "need_agent; task_id via task_visible kalmido/agents/api.py"),
    "POST /agent/typing": ("pin:chat_user_id", "only into the requester's own chat"),
    "GET /agent/usage": ("own", "need_agent; kalmido/agents/usage.py; titles via task_visible / list_role"),
    "POST /agent/usage": ("own", "need_agent; kalmido/agents/usage.py; task_visible / list_role ; own job"),
    "GET /agents": ("own", "is_agent -> agent_public(agent_row(me)) (agents/proposals.py)"),
    "POST /agents/{}/chat/{}/choice": ("noagent", "need_chat_agent: is_agent(g.user) -> 404 (agents/core.py)"),
    "POST /agents/{}/chat/{}/reactions": ("noagent", "need_person 403 (agents/proposals.py)"),
    "GET /announcement": ("safe", "announce_get kalmido/admin/hosting.py"),
    "DELETE /attachments/{}": ("cut", "need_attachment kalmido/tasks/attachments.py -> need_task kalmido/core/access.py -> list_role"),
    "GET /attachments/{}": ("cut", "need_attachment + need_task(full=True) -> list_role (tasks/attachments.py, core/access.py)"),
    "POST /attachments/{}/restore": ("cut", "need_attachment(trash=True) kalmido/tasks/attachments.py -> need_task kalmido/core/access.py -> list_role"),
    "GET /attachments/{}/text": ("cut", "need_attachment tasks/attachments.py + need_task core/access.py -> list_role (token_lists) (full)"),
    "GET /briefing": ("pin:user_id", "a named person must be the requester"),
    "DELETE /chat-attachments/{}": ("mine", "only the requester's rows (core/access.py run_person)"),
    "GET /chat-attachments/{}": ("mine", "only the requester's rows (core/access.py run_person)"),
    "GET /clients": ("noagent", "client_rows kalmido/team/clients.py (agent -> []), clients_list"),
    "POST /clients": ("noagent", "_gate kalmido/team/clients.py"),
    "POST /clients/bulk": ("noagent", "_gate kalmido/team/clients.py via clients_bulk kalmido/team/clients_bulk.py"),
    "DELETE /clients/{}": ("noagent", "_gate kalmido/team/clients.py"),
    "GET /clients/{}": ("noagent", "need_client kalmido/team/clients.py -> client_rows"),
    "PATCH /clients/{}": ("noagent", "_gate kalmido/team/clients.py"),
    "DELETE /comments/{}": ("cut", "need_live_comment kalmido/collab/comments.py -> need_task kalmido/core/access.py -> list_role"),
    "PATCH /comments/{}": ("cut", "need_live_comment kalmido/collab/comments.py -> need_task kalmido/core/access.py -> list_role"),
    "POST /comments/{}/choice": ("noagent", "need_task kalmido/core/access.py then lv_answer kalmido/collab/cchoice.py (is_agent -> 403)"),
    "POST /comments/{}/reactions": ("cut", "the project by the cut; writes by the control level capped to the requester's role (ctl_cap); calendars / contacts by the person cap"),
    "DELETE /comments/{}/reactions/{}": ("cut", "need_live_comment kalmido/collab/comments.py -> need_task"),
    "POST /comments/{}/withdraw": ("cut", "task_visible kalmido/core/access.py + lv_withdraw kalmido/collab/cchoice.py (own comment only)"),
    "GET /contacts": ("cap", "op_contacts kalmido/contacts/web.py -> need_book / contacts_query kalmido/contacts/model.py (my_book_ids, _ct_"),
    "POST /contacts": ("cap", "op_contact_new kalmido/contacts/web.py -> need_book(write) (book_role, for_cap)"),
    "POST /contacts/bulk": ("cap", "op_contacts_bulk kalmido/contacts/bulk.py / ms_set -> my_book_ids kalmido/contacts/model.py; need_book(write) "),
    "DELETE /contacts/{}": ("cap", "op_contact_delete -> need_contact(write, own) kalmido/contacts/model.py"),
    "GET /contacts/{}": ("cap", "the area's role function ends with for_cap (calendars: ev_role / my_cal_ids, files: fs_role / fs_ref_role, books: book_role, tables: sh_may)"),
    "PATCH /contacts/{}": ("cap", "the area's role function ends with for_cap (calendars: ev_role / my_cal_ids, files: fs_role / fs_ref_role, books: book_role, tables: sh_may)"),
    "PUT /contacts/{}/care": ("cap", "contact_visible kalmido/life/v1.py + need_contact kalmido/life/model.py (book_role / _ct_fold end in for_cap, "),
    "GET /dayplan": ("cut", "the project by the cut; writes by the control level capped to the requester's role (ctl_cap); calendars / contacts by the person cap"),
    "GET /dayplan/review": ("cut", "the project by the cut; writes by the control level capped to the requester's role (ctl_cap); calendars / contacts by the person cap"),
    "GET /dispo": ("org", "an area of the agent's organisation: only for a requester who is a full member of it"),
    "GET /dispo/free": ("org", "an area of the agent's organisation: only for a requester who is a full member of it"),
    "GET /documents": ("cap", "doc_query kalmido/docs/web.py -> doc_visible (fs_visible_sql, _for_sql kalmido/files/store.py); view= -> obj_n"),
    "POST /documents": ("cap", "v1_doc_create kalmido/docs/v1.py: need_node(write) / docs_ingest -> fs_put -> _place kalmido/files/store.py (f"),
    "GET /documents/upload-target": ("noagent", "scope docs:upload (kalmido/docs/v1.py; kalmido/api/scopes.py never for an agent; UPLOAD_ROUTES kalmido/api/v1."),
    "GET /documents/{}": ("cap", "v1_doc_get kalmido/docs/v1.py -> need_node kalmido/files/store.py (fs_role )"),
    "PATCH /documents/{}": ("cap", "v1_doc_patch kalmido/docs/v1.py -> need_node(write)"),
    "POST /documents/{}/receipt-suggestion": ("cap", "the area's role function ends with for_cap (calendars: ev_role / my_cal_ids, files: fs_role / fs_ref_role, books: book_role, tables: sh_may)"),
    "GET /event-calendars": ("cap", "the area's role function ends with for_cap (calendars: ev_role / my_cal_ids, files: fs_role / fs_ref_role, books: book_role, tables: sh_may)"),
    "POST /event-calendars": ("org", "an area of the agent's organisation: only for a requester who is a full member of it"),
    "DELETE /event-calendars/{}": ("cap", "op_cal_delete -> need_evcal(manage) kalmido/events/model.py -> ev_role -> obj_role (KERN role, _for_cap)"),
    "PATCH /event-calendars/{}": ("cap", "op_cal_edit kalmido/events/web.py -> need_evcal (ev_role -> obj_role); obj_write"),
    "GET /event-calendars/{}/export": ("cap", "need_evcal kalmido/events/model.py (ev_role -> obj_role)"),
    "POST /event-calendars/{}/import": ("cap", "need_evcal(write) kalmido/events/model.py (ev_role -> obj_role)"),
    "DELETE /event-calendars/{}/members/{}": ("cap", "op_member_remove kalmido/events/web.py -> need_evcal (ev_role -> obj_role)"),
    "PUT /event-calendars/{}/members/{}": ("cap", "the area's role function ends with for_cap (calendars: ev_role / my_cal_ids, files: fs_role / fs_ref_role, books: book_role, tables: sh_may)"),
    "GET /events": ("cap", "the area's role function ends with for_cap (calendars: ev_role / my_cal_ids, files: fs_role / fs_ref_role, books: book_role, tables: sh_may)"),
    "POST /events": ("cap", "the area's role function ends with for_cap (calendars: ev_role / my_cal_ids, files: fs_role / fs_ref_role, books: book_role, tables: sh_may)"),
    "GET /events/freebusy": ("org", "an area of the agent's organisation: only for a requester who is a full member of it"),
    "DELETE /events/{}": ("cap", "op_event_delete kalmido/events/web.py -> need_event(write) kalmido/events/model.py (write needs owner / edit ="),
    "GET /events/{}": ("cap", "the area's role function ends with for_cap (calendars: ev_role / my_cal_ids, files: fs_role / fs_ref_role, books: book_role, tables: sh_may)"),
    "PATCH /events/{}": ("cap", "the area's role function ends with for_cap (calendars: ev_role / my_cal_ids, files: fs_role / fs_ref_role, books: book_role, tables: sh_may)"),
    "POST /events/{}/prep-task": ("cut", "the project by the cut; writes by the control level capped to the requester's role (ctl_cap); calendars / contacts by the person cap"),
    "POST /events/{}/restore": ("cap", "op_event_restore kalmido/events/web.py -> need_event(write, deleted) (calendar role: ev_role -> obj_role)"),
    "POST /events/{}/rsvp": ("cap", "the area's role function ends with for_cap (calendars: ev_role / my_cal_ids, files: fs_role / fs_ref_role, books: book_role, tables: sh_may)"),
    "GET /export": ("cut", "token_lists() kalmido/api/scopes.py"),
    "GET /family": ("cut", "family_overview kalmido/family/family.py (vis_sql , visible_lists )"),
    "GET /family/deadline-types": ("safe", "family_dl_types kalmido/family/web.py"),
    "POST /family/deadlines": ("cut", "deadline_create kalmido/family/family.py (need_list ; else pm_fam_target -> fam_list wr_sql )"),
    "GET /family/kids": ("noagent", "kids_for kalmido/family/family.py"),
    "POST /family/kids/{}/rewards": ("noagent", "need_kid kalmido/family/family.py (family_reward_new kalmido/family/web.py)"),
    "POST /family/kids/{}/stars": ("noagent", "need_kid kalmido/family/family.py (family_kid_stars kalmido/family/web.py)"),
    "POST /family/occasions": ("cut", "occ_create kalmido/family/family.py (need_list ; else pm_fam_target -> fam_list wr_sql )"),
    "GET /family/packing": ("safe", "packing_templates kalmido/family/family.py"),
    "POST /family/packing": ("own", "packing_create kalmido/family/family.py -> fam_list_create"),
    "DELETE /family/rewards/{}": ("noagent", "need_reward kalmido/family/web.py -> need_kid kalmido/family/family.py"),
    "PATCH /family/rewards/{}": ("noagent", "need_reward kalmido/family/web.py -> need_kid kalmido/family/family.py"),
    "POST /family/rewards/{}/decide": ("noagent", "need_reward kalmido/family/web.py -> need_kid kalmido/family/family.py"),
    "POST /family/rewards/{}/request": ("noagent", "need_reward(parent=False) kalmido/family/web.py -> need_kid kalmido/family/family.py; kid_id == me()"),
    "GET /issuer": ("noagent", "v1_issuer_get kalmido/office/issuers.py -> _iss_me (g.issuer from iss_authenticate, else 403); an agent's token never"),
    "GET /issuer/clients/by-ref/{}": ("noagent", "isc_get kalmido/office/issclients.py -> _iss_me (g.issuer from iss_authenticate, else 403); an agent's token never"),
    "PUT /issuer/clients/by-ref/{}": ("noagent", "isc_put kalmido/office/issclients.py -> _iss_me (g.issuer from iss_authenticate, else 403); an agent's token never"),
    "GET /fetcher": ("noagent", "v1_fetcher_get kalmido/docs/fetcher.py -> _fx_row (g.fetcher from fx_authenticate, else 403); scope docs:uploa"),
    "POST /fetcher/documents": ("noagent", "v1_fetcher_upload kalmido/docs/fetcher.py -> _fx_row (g.fetcher from fx_authenticate, else 403); scope docs:up"),
    "GET /fetcher/recipes": ("noagent", "v1_fetcher_recipes kalmido/docs/fetcher.py -> _fx_row (g.fetcher from fx_authenticate, else 403); scope docs:u"),
    "PUT /fetcher/status": ("noagent", "v1_fetcher_status kalmido/docs/fetcher.py -> _fx_row (g.fetcher from fx_authenticate, else 403); scope docs:up"),
    "DELETE /fields/{}": ("cut", "need_field kalmido/lists/fields.py -> need_list kalmido/core/access.py -> list_role (token_lists )"),
    "PATCH /fields/{}": ("cut", "need_field kalmido/lists/fields.py -> need_list kalmido/core/access.py -> list_role (token_lists )"),
    "GET /files": ("cap", "the area's role function ends with for_cap (calendars: ev_role / my_cal_ids, files: fs_role / fs_ref_role, books: book_role, tables: sh_may)"),
    "POST /files": ("cap", "v1_file_create kalmido/files/v1.py -> _place kalmido/files/store.py (fs_role ) / fs_put"),
    "GET /files/{}": ("cap", "the area's role function ends with for_cap (calendars: ev_role / my_cal_ids, files: fs_role / fs_ref_role, books: book_role, tables: sh_may)"),
    "GET /files/{}/content": ("cap", "the area's role function ends with for_cap (calendars: ev_role / my_cal_ids, files: fs_role / fs_ref_role, books: book_role, tables: sh_may)"),
    "GET /files/{}/text": ("cap", "the area's role function ends with for_cap (calendars: ev_role / my_cal_ids, files: fs_role / fs_ref_role, books: book_role, tables: sh_may)"),
    "POST /files/{}/versions": ("cap", "v1_file_version kalmido/files/v1.py -> need_node(write); only kind file"),
    "GET /filters": ("own", "SELECT filters WHERE user_id=me AND list_id IS NULL kalmido/api/scopes.py"),
    "POST /filters": ("own", "filter_create kalmido/lists/sections.py (branch list_id None)"),
    "DELETE /filters/{}": ("own", "the agent's own filter; a project's view by the cut"),
    "PATCH /filters/{}": ("own", "the agent's own filter; a project's view by the cut"),
    "GET /focus": ("noagent", "v1f_person kalmido/personal/v1focus.py (need_person 403, first statement of the view)"),
    "POST /focus/start": ("noagent", "v1f_person kalmido/personal/v1focus.py (need_person 403, first statement of the view)"),
    "GET /focus/stats": ("noagent", "v1f_person kalmido/personal/v1focus.py (need_person 403, first statement of the view)"),
    "POST /focus/{}/pause": ("noagent", "v1f_person kalmido/personal/v1focus.py (need_person 403, first statement of the view)"),
    "POST /focus/{}/resume": ("noagent", "v1f_person kalmido/personal/v1focus.py (need_person 403, first statement of the view)"),
    "POST /focus/{}/stop": ("noagent", "v1f_person kalmido/personal/v1focus.py (need_person 403, first statement of the view)"),
    "GET /folders": ("closed", "reaches over all the agent's projects / by the agent's own membership: only for an admin of the agent's organisation"),
    "POST /folders/delete": ("closed", "reaches over all the agent's projects / by the agent's own membership: only for an admin of the agent's organisation"),
    "POST /folders/rename": ("closed", "reaches over all the agent's projects / by the agent's own membership: only for an admin of the agent's organisation"),
    "DELETE /forms/{}": ("cut", "_form_row kalmido/team/forms.py -> need_form_manager -> need_list -> list_role"),
    "PATCH /forms/{}": ("cut", "_form_row kalmido/team/forms.py -> need_form_manager -> need_list -> list_role"),
    "GET /groups": ("closed", "reaches over all the agent's projects / by the agent's own membership: only for an admin of the agent's organisation"),
    "GET /groups/{}": ("closed", "reaches over all the agent's projects / by the agent's own membership: only for an admin of the agent's organisation"),
    "GET /habits": ("own", "v1_habits api/v1.py: habits.user_id = me()"),
    "POST /habits": ("own", "habit_create kalmido/personal/habits.py (user_id = me)"),
    "DELETE /habits/{}": ("own", "need_habit kalmido/personal/habits.py (user_id = me)"),
    "PATCH /habits/{}": ("own", "need_habit kalmido/personal/habits.py (user_id = me)"),
    "POST /habits/{}/checkin": ("own", "need_habit personal/habits.py (user_id = me())"),
    "GET /habits/{}/stats": ("own", "need_habit kalmido/personal/habits.py (habits.user_id = me())"),
    "GET /help": ("safe", "hlp_overview / hlp_admin kalmido/api/helpdocs.py"),
    "GET /help/section": ("safe", "hlp_section / hlp_admin kalmido/api/helpdocs.py"),
    "POST /import/{}": ("cut", "imp_opts integrations/importers.py need_list(target); imp_run token_lists (no new lists, only lists in the cut"),
    "POST /imports/{}/undo": ("closed", "reaches over all the agent's projects / by the agent's own membership: only for an admin of the agent's organisation"),
    "GET /layouts/blocks": ("pin:user_id", "a named person must be the requester"),
    "POST /layouts/proposals": ("send", "writes a message / card to a person who shares a project of the run's cut (agent_shares / the project's people); reads nothing of theirs"),
    "GET /layouts/{}": ("pin:user_id", "a named person must be the requester"),
    "GET /life": ("cut", "the project by the cut; writes by the control level capped to the requester's role (ctl_cap); calendars / contacts by the person cap"),
    "POST /life/contracts": ("cut", "contract_create -> _target_list kalmido/life/model.py (need_list ; else life_list wr_sql )"),
    "POST /life/devices": ("cut", "device_create -> _target_list kalmido/life/model.py (need_list ; else life_list wr_sql )"),
    "POST /life/health": ("noagent", "scope private (life_spec kalmido/life/v1.py)"),
    "PUT /life/journal/{}": ("noagent", "scope private (life_spec kalmido/life/v1.py)"),
    "POST /life/karakeep/sync": ("own", "kk_sync kalmido/life/karakeep.py (kk_conns.user_id = me(); target list list_role / life_list wr_sql)"),
    "GET /life/review": ("cut", "review kalmido/life/model.py (every query list_id IN vis_sql + tvis )"),
    "POST /life/trips": ("org", "an area of the agent's organisation: only for a requester who is a full member of it"),
    "POST /life/upkeep": ("cut", "upkeep_create -> _target_list kalmido/life/model.py (need_list ; else life_list wr_sql )"),
    "GET /life/upkeep-presets": ("safe", "upkeep_presets kalmido/life/model.py"),
    "POST /list-files/{}/restore": ("cut", "need_list_file kalmido/lists/projects.py -> need_overview -> need_list kalmido/core/access.py -> list_role (to"),
    "GET /lists": ("cut", "visible_lists core/state.py (token_lists ), visible_sections vis_sql, v1_list_fields vis_sql"),
    "POST /lists": ("org", "an area of the agent's organisation: only for a requester who is a full member of it"),
    "DELETE /lists/{}": ("cut", "need_list kalmido/core/access.py -> list_role (token_lists ) (manage)"),
    "GET /lists/{}": ("cut", "need_list core/access.py -> list_role (token_lists); visible_lists core/state.py; pb_effective lists/playbook."),
    "PATCH /lists/{}": ("cut", "the project by the cut; writes by the control level capped to the requester's role (ctl_cap); calendars / contacts by the person cap"),
    "GET /lists/{}/build-status": ("cut", "need_list kalmido/integrations/gitbuild.py; gb_status (pvis for participants)"),
    "GET /lists/{}/delivery-report": ("cut", "need_list kalmido/integrations/delivery.py; delivery_report (tvis)"),
    "POST /lists/{}/deployments": ("cut", "need_overview lists/projects.py -> need_list (write); env_deploy lists/envs.py"),
    "POST /lists/{}/duplicate": ("org", "an area of the agent's organisation: only for a requester who is a full member of it"),
    "GET /lists/{}/environments": ("cut", "need_overview lists/projects.py -> need_list"),
    "GET /lists/{}/error-hook": ("cut", "errhook_get kalmido/integrations/errorreports.py (need_list , tvis )"),
    "PATCH /lists/{}/error-hook": ("noagent", "git_need_manage kalmido/integrations/git.py (need_person 403 first), called errorreports.py"),
    "GET /lists/{}/fields": ("cut", "need_list kalmido/core/access.py -> list_role (token_lists ) (read)"),
    "POST /lists/{}/fields": ("cut", "field_create kalmido/lists/fields.py -> need_list kalmido/core/access.py -> list_role (token_lists ) (manage)"),
    "GET /lists/{}/files": ("cut", "need_overview lists/projects.py -> need_list"),
    "POST /lists/{}/files": ("cut", "list_file_upload lists/projects.py -> need_overview (write)"),
    "DELETE /lists/{}/files/{}": ("cut", "need_list_file lists/projects.py -> need_overview"),
    "GET /lists/{}/files/{}": ("cut", "need_list_file lists/projects.py -> need_overview"),
    "GET /lists/{}/flow": ("cut", "fx_need_kpis lists/kpis.py -> need_list"),
    "GET /lists/{}/forms": ("cut", "need_form_manager kalmido/team/forms.py -> need_list -> list_role"),
    "POST /lists/{}/forms": ("cut", "need_form_manager kalmido/team/forms.py -> need_list -> list_role"),
    "GET /lists/{}/groups": ("cut", "list_groups_get lists/groups.py -> need_list"),
    "DELETE /lists/{}/groups/{}": ("cut", "need_list core/access.py -> list_role (token_lists) (manage); need_approval"),
    "PUT /lists/{}/groups/{}": ("cut", "the project by the cut; writes by the control level capped to the requester's role (ctl_cap); calendars / contacts by the person cap"),
    "POST /lists/{}/join": ("noagent", "ov_join lists/orgvis.py: list_role (cut) then ov_role core/access.py (agents: None)"),
    "GET /lists/{}/kpis": ("cut", "fx_need_kpis lists/kpis.py -> need_list"),
    "GET /lists/{}/links": ("cut", "need_overview lists/projects.py -> need_list"),
    "POST /lists/{}/links": ("cut", "need_overview lists/projects.py -> need_list (write)"),
    "PUT /lists/{}/links/order": ("cut", "need_overview lists/projects.py -> need_list (write)"),
    "DELETE /lists/{}/links/{}": ("cut", "need_overview lists/projects.py -> need_list (write)"),
    "PATCH /lists/{}/links/{}": ("cut", "need_overview lists/projects.py -> need_list (write)"),
    "GET /lists/{}/members": ("cut", "need_list kalmido/core/access.py -> list_role (token_lists ) (read), v1_members kalmido/api/scopes.py"),
    "DELETE /lists/{}/members/{}": ("cut", "the project by the cut; writes by the control level capped to the requester's role (ctl_cap); calendars / contacts by the person cap"),
    "PUT /lists/{}/members/{}": ("cut", "the project by the cut; writes by the control level capped to the requester's role (ctl_cap); calendars / contacts by the person cap"),
    "GET /lists/{}/milestones": ("cut", "need_overview lists/projects.py -> need_list (full)"),
    "POST /lists/{}/milestones": ("cut", "need_overview lists/projects.py -> need_list (write)"),
    "DELETE /lists/{}/milestones/{}": ("cut", "need_overview lists/projects.py -> need_list (write)"),
    "PATCH /lists/{}/milestones/{}": ("cut", "need_overview lists/projects.py -> need_list (write)"),
    "GET /lists/{}/notepads": ("cut", "_apin_list kalmido/agents/agentpin.py -> need_overview kalmido/lists/projects.py -> list_role / need_list"),
    "POST /lists/{}/notepads": ("cut", "_apin_list kalmido/agents/agentpin.py (write) -> need_overview -> need_list"),
    "GET /lists/{}/notes": ("cut", "note_role kalmido/collab/notes.py -> list_role"),
    "POST /lists/{}/notes": ("cut", "note_role(write) kalmido/collab/notes.py -> list_role"),
    "GET /lists/{}/notify-template": ("cut", "list_tpl_get kalmido/notify/caps.py (list_role )"),
    "GET /lists/{}/overview": ("cut", "need_overview lists/projects.py -> need_list; overview_build"),
    "PATCH /lists/{}/overview": ("cut", "need_overview lists/projects.py -> need_list (write)"),
    "POST /lists/{}/overview/append": ("cut", "need_overview lists/projects.py -> need_list (write)"),
    "POST /lists/{}/overview/replace-section": ("cut", "need_overview lists/projects.py -> need_list (write)"),
    "POST /lists/{}/owner": ("noagent", "need_person agents/core.py (api/v1.py) before any data"),
    "GET /lists/{}/playbook": ("cut", "need_list core/access.py -> list_role (token_lists); pb_effective lists/playbook.py"),
    "POST /lists/{}/playbook/proposals": ("cut", "need_agent + need_list core/access.py -> list_role (token_lists)"),
    "GET /lists/{}/repos": ("cut", "need_list kalmido/integrations/errorreports.py; git_conns_of_list kalmido/integrations/git.py"),
    "POST /lists/{}/repos": ("noagent", "scope integrations (kalmido/api/v1setup.py v1s_spec scope=S; SCOPES_AGENT_NEVER kalmido/api/v1.py) + v1s_perso"),
    "PUT /lists/{}/repos/version-field": ("noagent", "scope integrations (kalmido/api/v1setup.py v1s_spec scope=S; SCOPES_AGENT_NEVER kalmido/api/v1.py) + v1s_perso"),
    "PUT /lists/{}/review": ("cut", "list_review_put tasks/review.py need_list (write)"),
    "GET /lists/{}/rules": ("cut", "_v1_rules_list lists/rules.py list_role (agent needs a write role)"),
    "POST /lists/{}/rules/proposals": ("cut", "_v1_rules_list lists/rules.py list_role; rul_prop_person"),
    "GET /lists/{}/sections": ("cut", "need_list kalmido/core/access.py -> list_role (token_lists ) (read)"),
    "POST /lists/{}/sections": ("cut", "section_create kalmido/lists/sections.py -> need_list kalmido/core/access.py -> list_role (token_lists ) (writ"),
    "PUT /lists/{}/sections/order": ("cut", "sections_order kalmido/lists/sections.py -> need_list kalmido/core/access.py -> list_role (token_lists ) (writ"),
    "POST /lists/{}/shift": ("cut", "list_shift tasks/roadmap.py need_list; dependents: dch_plan tasks/depchain.py task_visible"),
    "POST /lists/{}/shop-areas": ("cut", "list_shop_areas kalmido/family/web.py (need_list write )"),
    "GET /lists/{}/sprints": ("cut", "sprints_get lists/sprints.py need_list"),
    "POST /lists/{}/sprints/assign": ("cut", "sprints_assign lists/sprints.py need_list (write); spr_assign_ids list_id = lid"),
    "PUT /lists/{}/status": ("cut", "list_status_set kalmido/lists/projects.py -> need_list kalmido/core/access.py -> list_role (token_lists ) (wri"),
    "PUT /lists/{}/status-pad": ("cut", "need_agent + _apin_list kalmido/agents/agentpin.py (write) -> need_overview -> need_list"),
    "GET /lists/{}/status-report": ("cut", "_report lists/report.py need_list; project_status"),
    "GET /lists/{}/tags": ("cut", "need_list kalmido/core/access.py; ltags_of_lists kalmido/collab/reactions.py"),
    "POST /lists/{}/tags": ("cut", "the project by the cut; writes by the control level capped to the requester's role (ctl_cap); calendars / contacts by the person cap"),
    "DELETE /lists/{}/tags/{}": ("cut", "_v1_ltag_of kalmido/agents/usage.py (tag must be in ltags_of_lists of that list); ltag_delete -> need_ltag -> "),
    "PATCH /lists/{}/tags/{}": ("cut", "_v1_ltag_of kalmido/agents/usage.py; ltag_update -> need_ltag -> need_list kalmido/collab/reactions.py"),
    "GET /lists/{}/ticket-types": ("cut", "need_list core/access.py -> list_role (token_lists); tt_offered"),
    "GET /lists/{}/velocity": ("cut", "need_list core/access.py -> list_role (token_lists)"),
    "GET /lists/{}/views": ("cut", "need_list kalmido/core/access.py -> list_role (token_lists ) (read)"),
    "POST /lists/{}/views": ("cut", "filter_create kalmido/lists/sections.py (branch list_id) -> need_list kalmido/core/access.py -> list_role (tok"),
    "GET /lists/{}/weekly-status": ("cut", "_apin_list kalmido/agents/agentpin.py -> need_overview; blockers of other lists via VisIds kalmido/personal/ti"),
    "GET /mails": ("closed", "reaches over all the agent's projects / by the agent's own membership: only for an admin of the agent's organisation"),
    "GET /mails/{}": ("closed", "reaches over all the agent's projects / by the agent's own membership: only for an admin of the agent's organisation"),
    "GET /me": ("own", "the agent's own marks / numbers, no content of other places"),
    "GET /me/app-passwords": ("noagent", "scope account (scope_refine api/scopes.py) + need_person (v1_person api/v1.py)"),
    "POST /me/app-passwords": ("noagent", "scope account (SCOPE_RULES ^/me/ api/scopes.py) + need_person; always 403"),
    "DELETE /me/app-passwords/{}": ("noagent", "scope account (SCOPE_RULES ^/me/ api/scopes.py) + need_person"),
    "PATCH /me/notifications": ("noagent", "scope account (SCOPE_RULES ^/me/ api/scopes.py)"),
    "POST /me/purpose": ("noagent", "scope account (family_spec kalmido/family/v1.py)"),
    "GET /me/storage": ("own", "the agent's own marks / numbers, no content of other places"),
    "GET /me/tokens": ("noagent", "scope integrations (kalmido/api/v1setup.py v1s_spec scope=S; SCOPES_AGENT_NEVER kalmido/api/v1.py) + v1s_token"),
    "POST /me/tokens": ("noagent", "scope integrations (kalmido/api/v1setup.py v1s_spec scope=S; SCOPES_AGENT_NEVER kalmido/api/v1.py) + v1s_token"),
    "DELETE /me/tokens/{}": ("noagent", "scope integrations (kalmido/api/v1setup.py v1s_spec scope=S; SCOPES_AGENT_NEVER kalmido/api/v1.py) + v1s_token"),
    "GET /me/waiting": ("pin:user_id", "a named person must be the requester"),
    "GET /me/webhooks": ("noagent", "scope integrations (kalmido/api/v1setup.py v1s_spec scope=S; SCOPES_AGENT_NEVER kalmido/api/v1.py) + v1s_perso"),
    "POST /me/webhooks": ("noagent", "scope integrations (kalmido/api/v1setup.py v1s_spec scope=S; SCOPES_AGENT_NEVER kalmido/api/v1.py) + v1s_perso"),
    "DELETE /me/webhooks/{}": ("noagent", "scope integrations (kalmido/api/v1setup.py v1s_spec scope=S; SCOPES_AGENT_NEVER kalmido/api/v1.py) + v1s_perso"),
    "PATCH /me/webhooks/{}": ("noagent", "scope integrations (kalmido/api/v1setup.py v1s_spec scope=S; SCOPES_AGENT_NEVER kalmido/api/v1.py) + v1s_perso"),
    "GET /me/webhooks/{}/log": ("noagent", "scope integrations (kalmido/api/v1setup.py v1s_spec scope=S; SCOPES_AGENT_NEVER kalmido/api/v1.py) + v1s_perso"),
    "POST /me/webhooks/{}/secret": ("noagent", "scope integrations (kalmido/api/v1setup.py v1s_spec scope=S; SCOPES_AGENT_NEVER kalmido/api/v1.py) + v1s_perso"),
    "POST /me/webhooks/{}/test": ("noagent", "scope integrations (kalmido/api/v1setup.py v1s_spec scope=S; SCOPES_AGENT_NEVER kalmido/api/v1.py) + v1s_perso"),
    "GET /news": ("mine", "only News of the run's projects"),
    "POST /news/read": ("own", "the agent's own marks / numbers, no content of other places"),
    "DELETE /notepads/{}": ("cut", "_apin_pad kalmido/agents/agentpin.py -> _apin_list(write) -> need_overview; agent only its own pad"),
    "PATCH /notepads/{}": ("cut", "_apin_pad kalmido/agents/agentpin.py -> _apin_list(write) -> need_overview; agent only its own pad"),
    "GET /notes": ("cut", "notes_search kalmido/collab/notes.py -> notes_visible_sql (list_id IN vis_sql, participant lists out)"),
    "DELETE /notes/{}": ("cut", "need_note(write) kalmido/collab/notes.py -> note_role -> list_role"),
    "GET /notes/{}": ("cut", "need_note kalmido/collab/notes.py -> note_role -> list_role"),
    "PATCH /notes/{}": ("cut", "need_note(write) kalmido/collab/notes.py; move target list_id: note_role(write) ; qn_audience names people of "),
    "POST /notes/{}/restore": ("cut", "need_note(write, trash) kalmido/collab/notes.py -> note_role -> list_role"),
    "GET /office": ("pin:requested_by", "the office works with the rights of the named person, who must be the requester (office/agentdocs.py _v1ctx)"),
    "GET /office/deals": ("pin:requested_by", "the office works with the rights of the named person, who must be the requester (office/agentdocs.py _v1ctx)"),
    "POST /office/deals": ("pin:requested_by", "the office works with the rights of the named person, who must be the requester (office/agentdocs.py _v1ctx)"),
    "PATCH /office/deals/{}": ("pin:requested_by", "the office works with the rights of the named person, who must be the requester (office/agentdocs.py _v1ctx)"),
    "GET /office/docs": ("pin:requested_by", "the office works with the rights of the named person, who must be the requester (office/agentdocs.py _v1ctx)"),
    "GET /office/docs/{}": ("pin:requested_by", "the office works with the rights of the named person, who must be the requester (office/agentdocs.py _v1ctx)"),
    "GET /office/docs/{}/pdf": ("pin:requested_by", "the office works with the rights of the named person, who must be the requester (office/agentdocs.py _v1ctx)"),
    "POST /office/invoices": ("pin:requested_by", "the office works with the rights of the named person, who must be the requester (office/agentdocs.py _v1ctx)"),
    "GET /office/leads": ("pin:requested_by", "the office works with the rights of the named person, who must be the requester (office/agentdocs.py _v1ctx)"),
    "POST /office/leads": ("pin:requested_by", "the office works with the rights of the named person, who must be the requester (office/agentdocs.py _v1ctx)"),
    "PATCH /office/leads/{}": ("pin:requested_by", "the office works with the rights of the named person, who must be the requester (office/agentdocs.py _v1ctx)"),
    "GET /office/letters": ("pin:requested_by", "the office works with the rights of the named person, who must be the requester (office/agentdocs.py _v1ctx)"),
    "POST /office/letters": ("pin:requested_by", "the office works with the rights of the named person, who must be the requester (office/agentdocs.py _v1ctx)"),
    "GET /office/letters/{}": ("pin:requested_by", "the office works with the rights of the named person, who must be the requester (office/agentdocs.py _v1ctx)"),
    "PATCH /office/letters/{}": ("pin:requested_by", "the office works with the rights of the named person, who must be the requester (office/agentdocs.py _v1ctx)"),
    "POST /office/letters/{}/links": ("pin:requested_by", "the office works with the rights of the named person, who must be the requester (office/agentdocs.py _v1ctx)"),
    "POST /office/offers": ("pin:requested_by", "the office works with the rights of the named person, who must be the requester (office/agentdocs.py _v1ctx)"),
    "PATCH /office/offers/{}": ("pin:requested_by", "the office works with the rights of the named person, who must be the requester (office/agentdocs.py _v1ctx)"),
    "POST /office/offers/{}/invoice": ("pin:requested_by", "the office works with the rights of the named person, who must be the requester (office/agentdocs.py _v1ctx)"),
    "GET /office/payment-suggestions": ("pin:requested_by", "the office works with the rights of the named person, who must be the requester (office/agentdocs.py _v1ctx)"),
    "POST /office/payment-suggestions": ("pin:requested_by", "the office works with the rights of the named person, who must be the requester (office/agentdocs.py _v1ctx)"),
    "POST /office/reminders": ("pin:requested_by", "the office works with the rights of the named person, who must be the requester (office/agentdocs.py _v1ctx)"),
    "GET /office/series": ("pin:requested_by", "the office works with the rights of the named person, who must be the requester (office/agentdocs.py _v1ctx)"),
    "GET /office/subs": ("pin:requested_by", "the office works with the rights of the named person, who must be the requester (office/agentdocs.py _v1ctx)"),
    "GET /office/{}": ("pin:requested_by", "the office works with the rights of the named person, who must be the requester (office/agentdocs.py _v1ctx)"),
    "GET /openapi.json": ("safe", "api_authenticate api/v1.py"),
    "GET /orgs/{}/webhooks": ("noagent", "scope integrations (kalmido/api/v1setup.py v1s_spec scope=S; SCOPES_AGENT_NEVER kalmido/api/v1.py) + v1s_perso"),
    "POST /orgs/{}/webhooks": ("noagent", "scope integrations (kalmido/api/v1setup.py v1s_spec scope=S; SCOPES_AGENT_NEVER kalmido/api/v1.py) + v1s_perso"),
    "DELETE /orgs/{}/webhooks/{}": ("noagent", "scope integrations (kalmido/api/v1setup.py v1s_spec scope=S; SCOPES_AGENT_NEVER kalmido/api/v1.py) + v1s_perso"),
    "PATCH /orgs/{}/webhooks/{}": ("noagent", "scope integrations (kalmido/api/v1setup.py v1s_spec scope=S; SCOPES_AGENT_NEVER kalmido/api/v1.py) + v1s_perso"),
    "GET /orgs/{}/webhooks/{}/log": ("noagent", "scope integrations (kalmido/api/v1setup.py v1s_spec scope=S; SCOPES_AGENT_NEVER kalmido/api/v1.py) + v1s_perso"),
    "POST /orgs/{}/webhooks/{}/secret": ("noagent", "scope integrations (kalmido/api/v1setup.py v1s_spec scope=S; SCOPES_AGENT_NEVER kalmido/api/v1.py) + v1s_perso"),
    "POST /orgs/{}/webhooks/{}/test": ("noagent", "scope integrations (kalmido/api/v1setup.py v1s_spec scope=S; SCOPES_AGENT_NEVER kalmido/api/v1.py) + v1s_perso"),
    "GET /polls": ("org", "an area of the agent's organisation: only for a requester who is a full member of it"),
    "POST /polls": ("org", "an area of the agent's organisation: only for a requester who is a full member of it"),
    "GET /polls/{}": ("org", "an area of the agent's organisation: only for a requester who is a full member of it"),
    "GET /receipt-suggestions": ("cap", "v1_rc_list kalmido/receipts/suggest.py: own rows (agent_id) filtered by rc_doc -> need_node (CAP); project nam"),
    "DELETE /repos/{}": ("noagent", "scope integrations (kalmido/api/v1setup.py v1s_spec scope=S; SCOPES_AGENT_NEVER kalmido/api/v1.py) + v1s_perso"),
    "PATCH /repos/{}": ("noagent", "scope integrations (kalmido/api/v1setup.py v1s_spec scope=S; SCOPES_AGENT_NEVER kalmido/api/v1.py) + v1s_perso"),
    "GET /roadmap": ("cut", "roadmap_build tasks/roadmap.py: visible_lists (token_lists), vis_sql + tvis"),
    "GET /search": ("mine", "messages: only the requester's chat with the agent and the rooms they read; the rest cut / capped"),
    "DELETE /sections/{}": ("cut", "need_section kalmido/lists/sections.py -> need_list kalmido/core/access.py -> list_role (token_lists ) (write)"),
    "PATCH /sections/{}": ("cut", "sec_apply kalmido/lists/sections.py -> need_section -> need_list kalmido/core/access.py -> list_role (token_li"),
    "GET /sheets": ("cap", "v1_sheets_list kalmido/sheets/v1.py -> sh_index kalmido/sheets/core.py (every row through sh_may ; list_id by "),
    "POST /sheets": ("org", "an area of the agent's organisation: only for a requester who is a full member of it"),
    "GET /sheets/{}": ("cap", "sh_need kalmido/sheets/core.py -> sh_may (act_for )"),
    "PATCH /sheets/{}": ("cap", "the area's role function ends with for_cap (calendars: ev_role / my_cal_ids, files: fs_role / fs_ref_role, books: book_role, tables: sh_may)"),
    "POST /sheets/{}/batches/{}/undo": ("cap", "v1_sheet_undo kalmido/sheets/v1.py -> sh_need(write) (sh_may); only the agent's own batches"),
    "PUT /sheets/{}/cells": ("cap", "v1_sheet_cells kalmido/sheets/v1.py -> sh_need(write) (sh_may)"),
    "POST /sheets/{}/columns": ("cap", "v1_sheet_column kalmido/sheets/v1.py -> sh_need(write) (sh_may)"),
    "POST /sheets/{}/rows": ("cap", "v1_sheet_rows kalmido/sheets/v1.py -> sh_need(write) (sh_may)"),
    "PUT /sheets/{}/rules": ("cap", "v1_sheet_rules kalmido/sheets/shfmt.py -> sh_need(write) (sh_may)"),
    "GET /sheets/{}/tabs": ("cap", "v1_sheet_tabs kalmido/sheets/shbook.py -> _need_book -> sh_need (sh_may)"),
    "POST /sheets/{}/tabs": ("cap", "v1_sheet_tab_add kalmido/sheets/shbook.py -> sh_need(write) (sh_may)"),
    "GET /sheets/{}/vars": ("cap", "the area's role function ends with for_cap (calendars: ev_role / my_cal_ids, files: fs_role / fs_ref_role, books: book_role, tables: sh_may)"),
    "GET /sprints/{}": ("cut", "need_sprint lists/sprints.py -> need_list"),
    "GET /stale": ("cut", "stale_query tasks/stale.py list_role; stale_tasks vis_sql + tvis"),
    "GET /stats": ("own", "the agent's own marks / numbers, no content of other places"),
    "GET /tags": ("cut", "v1_tags api/v1.py: vis_sql + tvis; visible_lists"),
    "GET /tasks": ("cut", "v1_tasks api/v1.py: vis_sql + tvis, need_list, filter_read lists/sections.py, v1_field_filter list_role; load_"),
    "POST /tasks": ("cut", "the project by the cut; writes by the control level capped to the requester's role (ctl_cap); calendars / contacts by the person cap"),
    "POST /tasks/batch": ("cut", "the project by the cut; writes by the control level capped to the requester's role (ctl_cap); calendars / contacts by the person cap"),
    "POST /tasks/brief": ("cut", "task_brief kalmido/integrations/taskbrief.py (need_task full ; subtasks / dependencies through _sees)"),
    "DELETE /tasks/{}": ("cut", "_v1_live api/v1.py -> need_task (write)"),
    "GET /tasks/{}": ("cut", "need_task core/access.py -> list_role (token_lists); v1_one / v1_task_by_key api/v1.py: need_task per candidate"),
    "PATCH /tasks/{}": ("cut", "_v1_live -> need_task (write); apply_update tasks/lifecycle.py (need_list target , check_move, check_assignee,"),
    "POST /tasks/{}/approval": ("send", "writes a message / card to a person who shares a project of the run's cut (agent_shares / the project's people); reads nothing of theirs"),
    "GET /tasks/{}/attachments": ("cut", "_v1_live -> need_task(write=False, full=True) (api/v1.py; agents/proposals.py)"),
    "POST /tasks/{}/attachments": ("cut", "_v1_live kalmido/api/v1.py -> need_task kalmido/core/access.py -> list_role ; attachment_upload kalmido/tasks/"),
    "POST /tasks/{}/attachments/text": ("cut", "_v1_live kalmido/api/v1.py -> need_task kalmido/core/access.py -> list_role"),
    "GET /tasks/{}/comments": ("cut", "_v1_live -> need_task (full); ocm_list"),
    "POST /tasks/{}/comments": ("cut", "the project by the cut; writes by the control level capped to the requester's role (ctl_cap); calendars / contacts by the person cap"),
    "POST /tasks/{}/complete": ("cut", "_v1_live -> need_task (write)"),
    "POST /tasks/{}/contacts": ("cut", "the project by the cut; writes by the control level capped to the requester's role (ctl_cap); calendars / contacts by the person cap"),
    "DELETE /tasks/{}/contacts/{}": ("cut", "the project by the cut; writes by the control level capped to the requester's role (ctl_cap); calendars / contacts by the person cap"),
    "GET /tasks/{}/decisions": ("cut", "_v1_live kalmido/api/v1.py -> need_task(write=False, full=True)"),
    "POST /tasks/{}/decisions": ("cut", "dec_post kalmido/agents/taskdec.py -> need_task(full=True)"),
    "GET /tasks/{}/dependencies": ("cut", "_v1_live kalmido/api/v1.py -> need_task kalmido/core/access.py -> list_role (read, full); deps_get kalmido/tas"),
    "POST /tasks/{}/dependencies": ("cut", "_v1_live kalmido/api/v1.py -> need_task kalmido/core/access.py -> list_role ; dep_add kalmido/tasks/dependenci"),
    "DELETE /tasks/{}/dependencies/{}": ("cut", "_v1_live kalmido/api/v1.py -> need_task kalmido/core/access.py -> list_role ; dep_remove kalmido/tasks/depende"),
    "POST /tasks/{}/duplicate": ("cut", "task_duplicate kalmido/lists/templates.py -> need_task kalmido/core/access.py -> list_role (write)"),
    "GET /tasks/{}/events": ("cut", "the project by the cut; writes by the control level capped to the requester's role (ctl_cap); calendars / contacts by the person cap"),
    "POST /tasks/{}/links": ("cut", "ml_check tasks/multilist.py need_task + need_list(target)"),
    "DELETE /tasks/{}/links/{}": ("cut", "ml_unlink tasks/multilist.py list_role(target) or need_task"),
    "GET /tasks/{}/milestone": ("cut", "_v1_live -> need_task (full); ms_report lists/projects.py"),
    "POST /tasks/{}/move": ("cut", "_v1_live kalmido/api/v1.py -> need_task kalmido/core/access.py -> list_role ; task_update target need_list kal"),
    "POST /tasks/{}/notes/append": ("cut", "_v1_notes_edit api/v1.py _v1_live -> need_task (write)"),
    "POST /tasks/{}/notes/replace-section": ("cut", "_v1_notes_edit api/v1.py _v1_live -> need_task (write)"),
    "POST /tasks/{}/partial": ("cut", "_v1_live kalmido/integrations/gitbuild.py (need_task write)"),
    "GET /tasks/{}/related": ("cut", "need_task core/access.py -> list_role (token_lists) (full); rt9_related _visible tasks/related.py vis_sql + tv"),
    "GET /tasks/{}/relations": ("cut", "need_task core/access.py -> list_role (token_lists) (full); rel_of core/serializers.py VisIds (vis_sql)"),
    "POST /tasks/{}/relations": ("cut", "rel_add tasks/relations.py need_task both tasks"),
    "DELETE /tasks/{}/relations/{}": ("cut", "rel_remove tasks/relations.py need_task + task_visible(other)"),
    "POST /tasks/{}/reopen": ("cut", "_v1_live -> need_task (write)"),
    "POST /tasks/{}/restore": ("cut", "need_task kalmido/core/access.py -> list_role (write); otr_err_task kalmido/lists/listtrash.py (otr_can: an ag"),
    "POST /tasks/{}/review": ("cut", "task_review -> rvw_apply tasks/review.py task_visible / need_task; rvw_reviewer_problem"),
    "POST /tasks/{}/skip": ("cut", "_v1_live kalmido/api/v1.py -> need_task kalmido/core/access.py -> list_role ; task_skip kalmido/tasks/lifecycl"),
    "POST /tasks/{}/snippets": ("cut", "_v1_live -> need_task (write)"),
    "POST /tasks/{}/state": ("cut", "_v1_live -> need_task (write)"),
    "GET /tasks/{}/subtasks": ("cut", "_v1_live -> need_task; vis_sql + tvis"),
    "POST /tasks/{}/subtasks": ("cut", "_v1_live -> need_task (write); task_create with parent_id"),
    "POST /tasks/{}/take": ("cut", "_v1_live -> need_task; task_take lists/groups.py task_visible + grp_of_user(agent)"),
    "POST /tasks/{}/tidy": ("cut", "need_agent + _v1_live -> need_task(write) + tidy_agent_of (agents/proposals.py)"),
    "POST /tasks/{}/to-shopping": ("cut", "_v1_live kalmido/family/v1.py + task_to_shopping kalmido/family/web.py (need_task , recipe_of task_visible, ne"),
    "POST /tasks/{}/typing": ("cut", "task_typing_set -> need_task(write=False, full=True) (agents/chat.py)"),
    "DELETE /tasks/{}/waiting": ("cut", "_v1_live -> need_task (write)"),
    "PUT /tasks/{}/waiting": ("cut", "_v1_live -> need_task (write)"),
    "GET /tasks/{}/watchers": ("cut", "need_task core/access.py -> list_role (token_lists) (full); wat_info tasks/watchers.py"),
    "POST /tasks/{}/watchers": ("cut", "wat_add tasks/watchers.py need_task (full); _wat_may_add task_visible(target)"),
    "DELETE /tasks/{}/watchers/{}": ("cut", "wat_remove tasks/watchers.py need_task (full)"),
    "DELETE /tasks/{}/working": ("cut", "wk_need kalmido/agents/api.py (need_agent + task_visible full + write)"),
    "GET /tasks/{}/working": ("cut", "need_agent + task_visible(full) kalmido/agents/api.py; wk_job"),
    "PATCH /tasks/{}/working": ("cut", "wk_need kalmido/agents/api.py; wk_pick"),
    "POST /tasks/{}/working": ("cut", "wk_need kalmido/agents/api.py; wk_set"),
    "GET /team/channels": ("cap", "the room by obj_need (person cap), a project's room by the cut"),
    "POST /team/channels": ("noagent", "need_person kalmido/collab/teamchan.py (agents/core.py) in tcx_channel_new"),
    "POST /team/dm": ("noagent", "need_person kalmido/agents/core.py in tchat_dm kalmido/collab/teamchat.py"),
    "GET /team/files/{}": ("cap", "the room by obj_need (person cap), a project's room by the cut"),
    "POST /team/groups": ("noagent", "need_person kalmido/collab/teamchan.py in tcx_group_new"),
    "DELETE /team/messages/{}": ("cap", "the room by obj_need (person cap), a project's room by the cut"),
    "PATCH /team/messages/{}": ("cap", "the room by obj_need (person cap), a project's room by the cut"),
    "POST /team/messages/{}/pin": ("cap", "the room by obj_need (person cap), a project's room by the cut"),
    "POST /team/messages/{}/reactions": ("cap", "the room by obj_need (person cap), a project's room by the cut"),
    "GET /team/messages/{}/versions": ("cap", "the room by obj_need (person cap), a project's room by the cut"),
    "GET /team/rooms": ("cap", "the room by obj_need (person cap), a project's room by the cut"),
    "PATCH /team/rooms/{}": ("noagent", "need_person kalmido/collab/teamchan.py in tcx_room_patch"),
    "DELETE /team/rooms/{}/groups/{}": ("noagent", "need_person kalmido/collab/teamchan.py in tcx_group_del"),
    "POST /team/rooms/{}/members": ("noagent", "need_person kalmido/collab/teamchan.py in tcx_member_add"),
    "DELETE /team/rooms/{}/members/{}": ("cap", "the room by obj_need (person cap), a project's room by the cut"),
    "GET /team/rooms/{}/messages": ("cap", "the room by obj_need (person cap), a project's room by the cut"),
    "POST /team/rooms/{}/messages": ("cap", "the room by obj_need (person cap), a project's room by the cut"),
    "POST /team/rooms/{}/read": ("cap", "the room by obj_need (person cap), a project's room by the cut"),
    "GET /templates": ("cap", "tk_rows kalmido/lists/tplkind.py -> obj_rows kalmido/core/objects.py"),
    "POST /templates": ("cut", "token_lists() kalmido/lists/templates.py"),
    "DELETE /templates/{}": ("cap", "need_template kalmido/lists/templates.py -> tk_need kalmido/lists/tplkind.py -> obj_need (view, write)"),
    "PATCH /templates/{}": ("cap", "need_template kalmido/lists/templates.py -> tk_need kalmido/lists/tplkind.py -> obj_need (view, write)"),
    "POST /templates/{}/apply": ("org", "an area of the agent's organisation: only for a requester who is a full member of it"),
    "GET /ticket-types": ("org", "an area of the agent's organisation: only for a requester who is a full member of it"),
    "POST /ticket-types": ("noagent", "tt_person_only tasks/ttypes.py (tt_create ) before any data"),
    "DELETE /ticket-types/{}": ("noagent", "tt_get tasks/ttypes.py (write) -> tt_person_only"),
    "PATCH /ticket-types/{}": ("noagent", "tt_get tasks/ttypes.py (write) -> tt_person_only"),
    "GET /time/check": ("pin:user_id", "a named person must be the requester"),
    "GET /time/entries": ("mine", "other people.s entries by the cut; the agent.s own entry of a project outside it without title and note (personal/timetrack.py entry_out)"),
    "POST /time/entries": ("cut", "time_target personal/timetrack.py need_task (full) / need_list"),
    "DELETE /time/entries/{}": ("mine", "other people.s entries by the cut; the agent.s own entry of a project outside it without title and note (personal/timetrack.py entry_out)"),
    "PATCH /time/entries/{}": ("mine", "other people.s entries by the cut; the agent.s own entry of a project outside it without title and note (personal/timetrack.py entry_out)"),
    "GET /time/from-events": ("pin:user_id", "a named person must be the requester"),
    "GET /time/gaps": ("pin:user_id", "a named person must be the requester"),
    "DELETE /time/timer": ("mine", "other people.s entries by the cut; the agent.s own entry of a project outside it without title and note (personal/timetrack.py entry_out)"),
    "GET /time/timer": ("mine", "other people.s entries by the cut; the agent.s own entry of a project outside it without title and note (personal/timetrack.py entry_out)"),
    "POST /time/timer": ("mine", "other people.s entries by the cut; the agent.s own entry of a project outside it without title and note (personal/timetrack.py entry_out)"),
    "DELETE /trash": ("cut", "tre_plan kalmido/tasks/lifecycle.py: trashed tasks in wr_sql() and in the lists the agent owns (purge_lists )"),
    "GET /trash": ("cut", "vis_sql() + tvis kalmido/api/scopes.py"),
    "GET /videos": ("cut", "vdr_v1_list kalmido/videos/v1.py -> vdr_may(api) kalmido/videos/review.py (task_visible / list_role; vdm_files"),
    "GET /videos/{}": ("cut", "vdr_v1_need kalmido/videos/v1.py -> vdr_may(api) kalmido/videos/review.py (task_visible / list_role)"),
    "POST /videos/{}/comments": ("cut", "vdr_v1_need -> vdr_may(api) kalmido/videos/review.py; vdr_comment_add (need_org_say as the agent)"),
    "PATCH /videos/{}/comments/{}": ("cut", "vdr_v1_need -> vdr_may(api) kalmido/videos/review.py; author or write role"),
    "GET /videos/{}/versions/{}/file": ("cut", "vdr_v1_need -> vdr_may(api); vdm_send kalmido/videos/vdmedia.py -> vdm_node (need_node = CAP unless uploaded f"),
    "GET /wiki/files/{}": ("cap", "_file_need kalmido/wiki/wkv1.py -> wkv_need kalmido/wiki/wkv1.py -> wkf_role kalmido/wiki/wkfolder.py (for_cap"),
    "GET /wiki/files/{}/text": ("cap", "_file_need kalmido/wiki/wkv1.py -> wkv_need kalmido/wiki/wkv1.py -> wkf_role kalmido/wiki/wkfolder.py (for_cap"),
    "GET /wiki/pages": ("cap", "wkv_list kalmido/wiki/wkv1.py: wkf_visible_sql / wkf_shared_ids (wkf_shared kalmido/wiki/wkfolder.py, act_for "),
    "POST /wiki/pages": ("cap", "wkv_create kalmido/wiki/wkv1.py -> _new_in_folder (fs_role on the folder, then wkf_role == edit on the new pag"),
    "GET /wiki/pages/{}": ("cap", "wkv_need kalmido/wiki/wkv1.py -> wkf_role kalmido/wiki/wkfolder.py (for_cap )"),
    "PATCH /wiki/pages/{}": ("cap", "wkv_update kalmido/wiki/wkv1.py -> wkv_need kalmido/wiki/wkv1.py -> wkf_role kalmido/wiki/wkfolder.py (for_cap"),
    "POST /wiki/pages/{}/append": ("cap", "_wkv_edit kalmido/wiki/wkv1.py -> wkv_need kalmido/wiki/wkv1.py -> wkf_role kalmido/wiki/wkfolder.py (for_cap "),
    "GET /wiki/pages/{}/files": ("cap", "wkv_files kalmido/wiki/wkv1.py -> wkv_need kalmido/wiki/wkv1.py -> wkf_role kalmido/wiki/wkfolder.py (for_cap "),
    "POST /wiki/pages/{}/replace-section": ("cap", "_wkv_edit kalmido/wiki/wkv1.py -> wkv_need kalmido/wiki/wkv1.py -> wkf_role kalmido/wiki/wkfolder.py (for_cap "),
    "GET /workload": ("org", "an area of the agent's organisation: only for a requester who is a full member of it"),
}
