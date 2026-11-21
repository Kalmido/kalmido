"""(#7531): the one intake for reports of people ("Meldung"): Kalmido's own "Report a problem", the inbound webhook
(integrations/hookin.py) and the browser's error reports (integrations/errorreports.py) share it.

The context block. A report may carry a block that says where it happened: the page (route without its query), the app
version, the device (platform, browser, touch, window size, pixel ratio), the last errors of the browser (message cut like
cer_text, place below /static/) and the failed requests (method, path without query, status, duration). It never holds
contents: no texts of tasks, documents or input fields, no request or answer bodies, no query parts, no tokens -
rpt_ctx_clean keeps only these keys and shapes, everything else goes. The block is its own attachment of the task (the core's
attachments: tasks/attachments.py, saved through core/pages.py save_attachment_bytes, name RPT_ATT_NAME, type RPT_ATT_MIME),
never part of the free text; the task view shows it as a file, the trash, export and purge take it with the task.

Kalmido's own report (POST /api/reports, people only) goes to the project the server admin chose for error reports
(Settings > Server, block "Errors in the browser", gsetting client_errors_list, errorreports.py cer_list): in the hosting the operator's project, on
an own server the admin's choice; without a choice the client keeps its old way (hosting: the support mail, else GitHub).
A bug asks "Problem" and "Expected", a wish "What do you want to do" and "What is in the way today" (required) and "How
should it work" (optional), like the ticket templates (tasks/validation.py TICKET_TPL). task_reports keeps who reported
which task at which place with the reporter's own title; the reporter sees the state over GET /api/reports - mechanically
from the task (RPT_STATE, a fixed table, nobody keeps it by hand) and never the task's later title or notes (another
organisation's project). The dialog lists what was already reported at this place (own reports and those of people who
share an organisation with the reporter), open ones first."""
import json
import re
import secrets

from flask import g, jsonify, request
from werkzeug.exceptions import HTTPException

from ..core.config import app
from ..core.db import bump, db, err, iso, now_utc
from ..api.common import hit_limit
from ..core.errors import BadInput
from ..core.i18n import N_, lang, tr
from ..core.pages import save_attachment_bytes
from ..core.pg import system_ctx
from ..core.access import acx_anon_bind
from ..accounts.orgs import user_orgs
from ..tasks.validation import CONTENT_MAX
from .errorreports import cer_list, cer_place, cer_text, err_rate_ok, err_take

RPT_ATT_NAME = "kalmido-context.json"
RPT_ATT_MIME = "application/json"
RPT_TEXT_MAX = 4000
RPT_PER_HOUR = 10          # reports per person and hour
RPT_ERRORS_MAX, RPT_REQ_MAX = 5, 8
RPT_KINDS = {  # kind -> (required fields, optional fields, the ticket type)
    "bug": (("problem", "expected"), (), "bug"),
    "wish": (("want", "blocker"), ("how",), "feature"),
}
RPT_LABEL = {"problem": N_("Problem"), "expected": N_("Expected"), "want": N_("What do you want to do?"),
             "blocker": N_("What is in the way today?"), "how": N_("How should it work?")}
RPT_FIELDS = ("kind", "place", "context", "problem", "expected", "want", "blocker", "how")
RPT_METHODS = ("GET", "POST", "PUT", "PATCH", "DELETE")


def rpt_state(status, assignee, deleted):
    """The state a reporter sees, from the task alone (the fixed table of #7531): won't do or in the trash -> wont,
    done -> fixed, open with an assignee -> working, else open."""
    if deleted or status == -1:
        return "wont"
    if status == 2:
        return "fixed"
    return "working" if assignee else "open"


def _s(v, n, pat=None):
    v = re.sub(r"[\x00-\x1f\x7f]+", " ", v).strip()[:n] if isinstance(v, str) else ""
    return v if not pat or re.fullmatch(pat, v) else ""


def _n(v, lo, hi):
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) and lo <= v <= hi else None


def rpt_route(u):
    """The page of a report (route / place): its first part (the view) and numbers only - every other part becomes "_", so a
    tag, a search or a name in the address never goes along (#7531 F2)."""
    p = rpt_path(u)
    if not p:
        return ""
    lead, parts = p[0], p[1:].split("/")
    return lead + "/".join(x if i == 0 or re.fullmatch(r"\d{1,12}|n|_", x) else "_" for i, x in enumerate(parts))[:159]


def rpt_path(u):
    """A page or request address as its path only: origin, query (?...) and anything that is no plain path go."""
    u = re.sub(r"^[a-z][\w+.-]*://[^/]+", "", str(u or "").strip(), flags=re.I).split("?")[0]
    return u[:160] if re.fullmatch(r"[#/][\w./#-]{0,159}", u) else ""


def rpt_req_route(method, path):
    """A failed request as the pattern of its route only (#7531 F8): /api/team/dispo/callsheet/<job>, never the job's or a
    file's name of the real path; a path no route of the server takes is dropped ("")."""
    p = rpt_path(path)
    if not p.startswith("/"):
        return ""
    try:
        rule, _ = app.url_map.bind("localhost").match(p, method=method, return_rule=True)
    except HTTPException:  # no such route (NotFound), not this method, a redirect (RequestRedirect): nothing goes along
        return ""
    return rule.rule[:160] if rule.rule.startswith("/api/") else ""


def rpt_ctx_clean(raw, names=()):
    """A context block from outside -> the clean block (only the known keys and shapes) or None. BadInput when it is no object."""
    if isinstance(raw, str) and raw.strip():  # a form field of the inbound webhook carries the block as JSON text
        try:
            raw = json.loads(raw)
        except ValueError:
            raise BadInput(tr("Invalid value: {0}", "context")) from None
    if raw in (None, "", {}):
        return None
    if not isinstance(raw, dict):
        raise BadInput(tr("Invalid value: {0}", "context"))
    out = {}
    if rpt_route(raw.get("route")):
        out["route"] = rpt_route(raw.get("route"))
    if _s(raw.get("version"), 30, r"[\w.+-]+"):
        out["version"] = _s(raw.get("version"), 30)
    d = raw.get("device") if isinstance(raw.get("device"), dict) else {}
    dev = {k: _s(d.get(k), 40, r"[\w .,()/+-]*") for k in ("platform", "browser") if _s(d.get(k), 40, r"[\w .,()/+-]*")}
    for k, hi in (("width", 20000), ("height", 20000), ("dpr", 8)):
        if _n(d.get(k), 0, hi) is not None:
            dev[k] = round(d[k], 2) if k == "dpr" else int(d[k])
    if isinstance(d.get("touch"), bool):
        dev["touch"] = d["touch"]
    if dev:
        out["device"] = dev
    errs = []
    for e in (raw.get("errors") if isinstance(raw.get("errors"), list) else [])[:RPT_ERRORS_MAX]:
        msg = cer_text(e.get("msg"), 300, names) if isinstance(e, dict) else ""
        if msg:
            errs.append({"msg": msg, **({"place": cer_place(e.get("place"))} if cer_place(e.get("place")) else {})})
    if errs:
        out["errors"] = errs
    reqs = []
    for q in (raw.get("requests") if isinstance(raw.get("requests"), list) else [])[:RPT_REQ_MAX]:
        pat = rpt_req_route(q.get("method"), q.get("path")) if isinstance(q, dict) and q.get("method") in RPT_METHODS else ""
        if not pat:
            continue
        reqs.append({"method": q["method"], "path": pat, "status": int(_n(q.get("status"), 0, 599) or 0),
                     "ms": int(_n(q.get("ms"), 0, 600000) or 0)})
    if reqs:
        out["requests"] = reqs
    return out or None


def rpt_ctx_attach(c, tid, ctx, owner=None, anon=False):
    """The block as the task's own attachment (never in the notes). -> None when filed, else why not (save_attachment_bytes)."""
    if not ctx:
        return None
    data = json.dumps({"kalmido_context": 1, **ctx}, ensure_ascii=False, indent=1).encode()
    return save_attachment_bytes(c, tid, RPT_ATT_NAME, RPT_ATT_MIME, data, owner=owner, anon=anon)


def rpt_fields(b):
    """The checked fields of a report: (kind, {field: text}) or BadInput (a required one empty, an unknown key, too long)."""
    unknown = sorted(k for k in b if k not in RPT_FIELDS)
    if unknown:
        raise BadInput(tr("Invalid value: {0}", unknown[0]))
    kind = b.get("kind") or "bug"
    if kind not in RPT_KINDS:
        raise BadInput(tr("Invalid value: {0}", "kind"))
    need, opt, _ = RPT_KINDS[kind]
    out = {}
    for k in need + opt:
        v = b.get(k)
        if v is not None and not isinstance(v, str):
            raise BadInput(tr("Invalid value: {0}", k))
        v = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]+", "", (v or "").replace("\r\n", "\n")).strip()
        if len(v) > RPT_TEXT_MAX:
            raise BadInput(tr("{0} is too long (at most {1} characters)", tr(RPT_LABEL[k]), RPT_TEXT_MAX))
        if k in need and not v:
            raise BadInput(tr("Please fill in: {0}", tr(RPT_LABEL[k])))
        if v:
            out[k] = v
    for k in RPT_FIELDS[3:]:
        if k not in need + opt and b.get(k) not in (None, ""):
            raise BadInput(tr("Invalid value: {0}", k))
    return kind, out


def rpt_content(kind, f, who, lg):
    """The task's notes: the reporter's fields under their labels (the ticket template's order), then who reported."""
    need, opt, _ = RPT_KINDS[kind]
    parts = [f"**{tr(RPT_LABEL[k], lg=lg)}**\n{f[k]}" for k in need + opt if f.get(k)]
    parts.append(tr("Reported in the app by {0}", who, lg=lg))
    return "\n\n".join(parts)[:CONTENT_MAX]


def _place(b):
    return rpt_route(b.get("place")) or rpt_route((b.get("context") or {}).get("route") if isinstance(b.get("context"), dict) else "")


@app.post("/api/reports")
def rpt_create():
    """A person reports a problem or a wish from the app: {kind: bug | wish, problem + expected | want + blocker (+ how),
    place? (the page, no query), context? (the block, rpt_ctx_clean; null = left out by the reporter)} -> 201 {task_id: null,
    context, report: {...}} (the task lies in the chosen project, the reporter sees its state, not the task); 409 {none: true}
    without a chosen project (the client then takes its old way). The task comes through the error reports' way (err_take:
    the project's hourly limit, its first section, the tidy / added events, the News item of a new bug)."""
    u = g.user
    if not u or u.get("kind", "user") != "user":
        return err(tr("Not allowed"), 403)
    c, b = db(), request.get_json(silent=True)
    if not isinstance(b, dict):
        return err(tr("Invalid value: {0}", "body"))
    try:
        kind, f = rpt_fields(b)
    except BadInput as e:
        return err(str(e))
    lid, r = cer_list(c)
    if not lid or r["archived"]:
        return jsonify(none=True, error=tr("No project takes reports on this server.")), 409
    # the hour over every process; a failed shared count falls back to the process counter (hit_limit), never lets through.
    # (#7531 F7): project and limit before the block is cleaned - its cleaning is the costly part
    if hit_limit(f"rpt:{u['id']}", RPT_PER_HOUR, 3600) or not err_rate_ok(lid):
        return err(tr("Too many attempts, please wait a few minutes"), 429)
    try:
        ctx = rpt_ctx_clean(b.get("context"), (u["display_name"], u["username"]))
    except BadInput as e:
        return err(str(e))
    place = _place(b)
    title = (f.get("problem") or f.get("want") or "").split("\n")[0][:120].strip() or tr("Report a problem")
    who = f"{u['display_name']} (@{u['username']})"
    rid, now = u["id"], iso(now_utc())
    # from here on as nobody inside the chosen project's organisation (like cer_report / errhook_in): the reporter may be of
    # another organisation (hosting) and never gets the project's rights
    g.user = None
    acx_anon_bind(c, r["org_id"])
    rep = {"source": "person", "title": title, "culprit": "", "url": "", "level": "error" if kind == "bug" else "info", "fid": "",
           "body": "", "fp": "rpt:" + secrets.token_hex(12), "content": rpt_content(kind, f, who, lang(c, r["owner_id"])),
           "ttype": RPT_KINDS[kind][2], "quiet": kind != "bug"}
    res = err_take(c, lid, r, rep)
    tid = (res[0] if isinstance(res, tuple) else res).get_json().get("task_id")
    if not tid:  # the project's hourly limit: only counted
        return err(tr("Too many attempts, please wait a few minutes"), 429)
    c.execute("INSERT INTO task_reports(task_id,list_id,reporter_id,kind,place,title,created_at) VALUES(?,?,?,?,?,?,?)",
              (tid, lid, rid, kind, place, title, now))
    skipped = rpt_ctx_attach(c, tid, ctx, owner=r["owner_id"])
    bump(c)
    c.commit()
    return jsonify(task_id=None, context=bool(ctx) and not skipped,
                   report={"kind": kind, "place": place, "title": title, "state": "open", "created_at": now, "mine": True, "here": True}), 201


@app.get("/api/reports")
def rpt_list():
    """{target: whether reports have a project, items: [{kind, title, place, state, created_at, mine, here}]}: what was reported
    at ?place= (own reports and those of people who share an organisation with me) and my own other reports; open ones
    first, newest first, at most 30. Only the reporter's own title and the state - never the task itself."""
    u = g.user
    if not u or u.get("kind", "user") != "user":
        return err(tr("Not allowed"), 403)
    c = db()
    lid, r = cer_list(c)
    place = rpt_route(request.args.get("place"))
    # my organisations as the request has them (accounts/orgs.py user_orgs: narrowed for an agent / a support session, #6977),
    # never a membership lookup of its own inside system_ctx (p6977_support_roles_src)
    orgs = [int(o) for o in user_orgs(c, u["id"])] or [0]
    with system_ctx(c):  # the tasks lie in the chosen project (another organisation in the hosting): only state + own title
        rows = c.execute(f"""SELECT r.kind, r.title, r.place, r.created_at, r.reporter_id, t.status, t.assignee_id, t.deleted_at
                            FROM task_reports r JOIN tasks t ON t.id=r.task_id
                            WHERE r.reporter_id=? OR (r.place=? AND r.place<>'' AND r.reporter_id IN
                              (SELECT m.user_id FROM org_members m WHERE m.org_id IN ({",".join("?" * len(orgs))})))
                            ORDER BY r.created_at DESC LIMIT 200""", (u["id"], place, *orgs)).fetchall()
    # (#7531 F1): the title (the reporter's own first line) only for the reporter - people who share an organisation see
    # kind, state and time at this place, never the words of a report from another workspace
    items = [{"kind": x["kind"], "title": x["title"] if x["reporter_id"] == u["id"] else "", "place": x["place"], "created_at": x["created_at"],
              "state": rpt_state(x["status"], x["assignee_id"], x["deleted_at"]), "mine": x["reporter_id"] == u["id"],
              "here": bool(place) and x["place"] == place} for x in rows]
    items.sort(key=lambda x: (not x["here"], x["state"] in ("fixed", "wont")))  # stable: newest first inside
    return jsonify(target=bool(lid and r and not r["archived"]), items=items[:30])
