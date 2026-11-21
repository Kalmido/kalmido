"""(#5352): "Recently edited" over the areas Knowledge, Files, Reading, the office and Tables (#7662) --
ONE route for the overview "All workspaces" of these areas and the start page's block "Recently edited" (static/js/recent.js).
Read only: it makes nothing, stores nothing and changes no area.

    GET /api/recent?space=all | private | org:<id>&limit=20&areas=wiki,files,reading,office,sheets
        -> {space, items: [{area (wiki | files | reading | office | sheets), id, space (private | org:<id> | shared), title,
            place, by, by_name, at, url (reading: the link), kind (office: offer | invoice | credit | client | receipt)}]}, newest first; limit 1..50 (default 20); space all (default) = every workspace plus
            what others shared with the person, private / org:<id> = only that workspace (an organisation the person is not
            in = 404)

Rights: every area answers with its OWN check, there is no check of this module (the shared core, 2.558.0):
  wiki     the spaces through wiki/pages.py wiki_space (member, need_org_area: guests / accounting nothing), every page then
           through wiki_may_read (wkfolder.wkf_role: closed folders); pages shared with the person from spaces she is not in
           through wkshare.wsh_reach (the list "Shared with me"); a page of a space with a lock (ciphertext names) is left out
  files    the file store's own visibility (files/store.py fs_visible_sql_c: owner, organisation, shares, mail, receipts,
           references), fs_mail_rows like a folder's listing and fsviews.fsv_drop (the folders of other areas, as the file
           store's own views); files of a locked folder (fslock: names are ciphertexts) are left out
  reading  the spaces through life/rss.py rss_space, the projects through reading.rl_lists (vis_sql) -- the view "Read later"
  office   (#7662) the office areas of the asked workspaces (an organisation's office, "Private" = the person's personal office,
           pb_personal, never made here), each through office_role (no role / guest: nothing) and office/rights.py office_can,
           the one check of the areas outside /api/office (office groups, else the role's previous access): "offers" for
           quotations, invoices, credit notes and the office's clients (pb_cl_sql), "receipts" for the receipts of the office's
           documents space (bk_ws), every receipt then through the file store's own role (fs_roles_many); a receipt is listed
           as the office's, not a second time as a file
  sheets   (#7662) the tables' own index sheets/core.py sh_index (workspace, projects, folders and shares; sh_space = 404 for a
           workspace the person is not in, every table through sh_may)
An area the organisation's admins switched off (accounts/wsareas.py wsa_org_off) gives nothing of that organisation, a module
the person switched off (features) nothing at all. People only: an agent or an API token gets 403 (like Read later and the
favourites), so the agent API has no such route (docs/AGENTS.md unchanged)."""
from flask import g, has_request_context, jsonify, request

from ..core.access import Denied, live_sql
from ..core.config import app
from ..core.db import db
from ..core.errors import BadInput
from ..core.i18n import tr
from ..accounts.session import me
from ..accounts.orgs import user_orgs
from ..accounts.wsareas import WSA_KEY_RE, wsa_org_off
from ..collab.comments import user_names
from ..life.model import feat_on
from ..life.reading import rl_lists, rl_site
from ..life.rss import rss_space
from ..files.fslock import fsl_map
from ..files.fsviews import fsv_drop
from ..files.store import fs_mail_rows, fs_roles_many, fs_visible_sql_c
from ..office.books import bk_ws
from ..office.model import office_role, pb_cl_sql, pb_personal
from ..office.rights import office_can
from ..sheets.core import sh_index
from ..wiki.pages import wiki_may_read, wiki_space
from ..wiki.wkfolder import wkf_locked
from ..wiki.wkshare import wsh_reach

RCN_LIMIT, RCN_MAX = 20, 50
RCN_AREAS = ("wiki", "files", "reading", "office", "sheets")
RCN_FEAT = {"wiki": "wiki", "files": "files", "reading": "reading", "office": "office", "sheets": "sheets"}  # the module switch of the person (features)
RCN_WSA = {"wiki": "wiki", "files": "ablage", "reading": "reading", "office": "office", "sheets": "sheets"}  # the area id an organisation's admins switch off
RCN_DOC_KINDS = ("offer", "invoice", "credit")  # the office documents listed (contacts/history.py CTK_DOC_KINDS)


def rcn_person():
    """403 for an agent or an API token (the same rule as Read later, life/reading.py rl_need)."""
    u = getattr(g, "user", None) if has_request_context() else None
    if (u is not None and "kind" in u.keys() and u["kind"] == "agent") or (has_request_context() and g.get("auth_via") == "token"):
        raise Denied(403, tr("Recently edited is only available in the app"))


def rcn_space_arg(c, uid, v):
    """?space= -> (key, org id | None): 'all' | 'private' | 'org:<id>' (an organisation uid is not in: 404)."""
    v = (v or "all").strip()
    if v == "all":
        return "all", None
    if not WSA_KEY_RE.fullmatch(v):
        raise BadInput(tr("Invalid value: {0}", "space"))
    if v == "private":
        return "private", None
    oid = int(v[4:])
    if oid not in user_orgs(c, uid):
        raise Denied(404)
    return v, oid


def _sp_key(c, uid, org_id, owner_id):
    """The workspace an item opens in for uid; 'shared' = shared with uid from a workspace that is not uid's own."""
    if org_id:
        return "org:%d" % org_id if org_id in user_orgs(c, uid) else "shared"
    return "private" if owner_id == uid else "shared"


def _spaces(c, uid, key, oid):
    """The workspaces asked for: [None (private), org ids ...]."""
    if key == "all":
        return [None, *user_orgs(c, uid)]
    return [oid]


def _off(c, oid, area):
    return bool(oid) and RCN_WSA[area] in wsa_org_off(c, oid)


def _want(key, sp):
    """Is an item of workspace sp ('private' | 'org:<id>' | 'shared') asked for?"""
    return key == "all" or sp == key


# ---------------------------------------------------------------- knowledge pages
def rcn_wiki(c, uid, key, oid, limit):
    orgs, own = [], False
    for o in _spaces(c, uid, key, oid):
        if _off(c, o, "wiki"):
            continue
        try:
            got = wiki_space(c, uid, "org:%d" % o if o else "private")  # the area's own check of a space (404 / 403)
        except (Denied, BadInput):
            continue
        if got:
            orgs.append(int(got))
        else:
            own = True
    conds, args = [], []
    if own:
        conds.append("(org_id IS NULL AND owner_id=?)")
        args.append(uid)
    if orgs:
        conds.append(f"org_id IN ({','.join(str(o) for o in orgs)})")
    rows = []
    if conds:
        rows = c.execute(f"SELECT * FROM wiki_pages WHERE {live_sql()} AND ({' OR '.join(conds)}) "
                         f"ORDER BY updated_at DESC, id DESC LIMIT ?", (*args, limit * 4)).fetchall()
    own_ids, info, via_share = {r["id"] for r in rows}, {}, set()
    if key == "all":  # pages others shared with uid from spaces uid does not read anyway (the list "Shared with me")
        shared, info = wsh_reach(c, uid)
        shared = [r for r in shared if not _off(c, r["org_id"], "wiki") and r["id"] not in own_ids]
        via_share = {r["id"] for r in shared}
        rows = list(rows) + shared
    out, seen = [], set()
    for r in sorted(rows, key=lambda x: (rcn_at_key(x["updated_at"]), x["id"]), reverse=True):
        if r["id"] in seen or wkf_locked(c, r) or not wiki_may_read(c, uid, r):
            continue
        seen.add(r["id"])
        parts = str(r["path"]).split("/")
        place, sp = "/".join(parts[:-1]), _sp_key(c, uid, r["org_id"], r["owner_id"])
        if r["id"] in via_share:  # review: like /api/wiki/shared - a folder share shows the path from the shared folder on,
            x = info.get(r["id"])  # never the folders above it; and it counts as shared, not as a space uid reads
            place, sp = (x["folder"] or "") if x else place, "shared"
        out.append({"area": "wiki", "id": r["id"], "space": sp, "title": parts[-1],
                    "place": place, "by": r["updated_by"], "at": r["updated_at"]})
        if len(out) >= limit:
            break
    return out


# ---------------------------------------------------------------- files of the file store
def rcn_files(c, uid, key, oid, limit):
    if key == "private":
        w, a = "org_id IS NULL AND owner_id=?", [uid]
    elif key == "all":
        w, a = "TRUE", []
    else:
        w, a = "org_id=?", [oid]
    rows = c.execute(f"SELECT * FROM fs_nodes WHERE kind='file' AND {live_sql()} AND {w} AND id IN {fs_visible_sql_c(c, uid)} "
                     f"ORDER BY updated_at DESC, id DESC LIMIT ?", (*a, limit * 4)).fetchall()
    rows = fsv_drop(c, fs_mail_rows(c, uid, rows))  # like a folder's listing; no file of another area's folders
    lk = fsl_map(c, [r["id"] for r in rows])
    rows = [r for r in rows if r["id"] not in lk and not _off(c, r["org_id"], "files")][:limit]
    by = {}
    if rows:
        q = ",".join(str(int(r["id"])) for r in rows)
        by = {n: u for n, u in c.execute(f"SELECT v.node_id, v.created_by FROM fs_versions v JOIN fs_nodes n ON n.id=v.node_id "
                                         f"AND v.no=n.cur_version WHERE v.node_id IN ({q})")}
    return [{"area": "files", "id": r["id"], "space": _sp_key(c, uid, r["org_id"], r["owner_id"]), "title": r["name"], "place": "",
             "by": by.get(r["id"]) or r["created_by"] or r["owner_id"], "at": r["updated_at"]} for r in rows]


# ---------------------------------------------------------------- read later
def rcn_reading(c, uid, key, oid, limit):
    lsp = {}
    for o in _spaces(c, uid, key, oid):
        if _off(c, o, "reading"):
            continue
        try:
            got = rss_space(c, uid, "org:%d" % o if o else "private")  # the area's own check of a space
        except (Denied, BadInput):
            continue
        for lid in rl_lists(c, uid, got):
            lsp[lid] = "org:%d" % got if got else "private"
    if not lsp:
        return []
    ph = ",".join("?" * len(lsp))
    rows = c.execute(f"SELECT id, list_id, title, url, created_at, created_by FROM tasks WHERE list_id IN ({ph}) AND {live_sql()} "
                     f"AND parent_id IS NULL AND status=0 ORDER BY created_at DESC, id DESC LIMIT ?", (*lsp, limit)).fetchall()
    return [{"area": "reading", "id": r["id"], "space": lsp[r["list_id"]], "title": r["title"], "place": rl_site(r["url"]),
             "url": r["url"] or "", "by": r["created_by"], "at": r["created_at"]} for r in rows]


# ---------------------------------------------------------------- the office (#7662)
def _office_areas(c, uid, key, oid):
    """{office area id: workspace key} of the asked workspaces where uid has a role in the office (not a guest): an
    organisation's office is the organisation, "private" the personal office (only when it exists, never made here)."""
    out = {}
    for o in _spaces(c, uid, key, oid):
        if _off(c, o, "office"):
            continue
        ofid = o or pb_personal(c, uid, create=False)
        role = office_role(c, uid, ofid) if ofid else None
        if role and role != "guest":
            out[ofid] = "org:%d" % o if o else "private"
    return out


def rcn_office(c, uid, key, oid, limit):
    out = []
    for ofid, sp in _office_areas(c, uid, key, oid).items():
        if office_can(c, uid, ofid, "offers"):  # the area's own check: quotations & invoices (and their clients)
            ph = ",".join("?" * len(RCN_DOC_KINDS))
            for r in c.execute(f"SELECT id, kind, number, project_title, created_by, updated_at FROM office_docs WHERE org_id=? "
                               f"AND kind IN ({ph}) AND {live_sql()} ORDER BY updated_at DESC, id DESC LIMIT ?",
                               (ofid, *RCN_DOC_KINDS, limit)).fetchall():
                title = r["number"] or r["project_title"] or ""
                out.append({"area": "office", "kind": r["kind"], "id": r["id"], "space": sp, "title": title,
                            "place": r["project_title"] if r["number"] else "", "by": r["created_by"], "at": r["updated_at"]})
            for r in c.execute(f"SELECT id, name, created_by, updated_at FROM clients WHERE {pb_cl_sql(c, ofid)} AND {live_sql()} "
                               f"ORDER BY updated_at DESC, id DESC LIMIT ?", (limit,)).fetchall():
                out.append({"area": "office", "kind": "client", "id": r["id"], "space": sp, "title": r["name"], "place": "",
                            "by": r["created_by"], "at": r["updated_at"]})
        if office_can(c, uid, ofid, "receipts"):  # the receipts: the office's right, then each file's own role
            rows = c.execute("SELECT n.id, n.name, n.owner_id, n.created_by, n.updated_at FROM rc_receipts r JOIN doc_meta d ON "
                             "d.node_id=r.node_id JOIN fs_nodes n ON n.id=r.node_id WHERE d.ws=? AND n.kind='file' AND "
                             f"{live_sql('n')} ORDER BY n.updated_at DESC, n.id DESC LIMIT ?", (bk_ws(c, ofid), limit * 2)).fetchall()
            acc = fs_roles_many(c, [r["id"] for r in rows], uid) if rows else {}
            got = 0
            for r in rows:
                gone, role = acc.get(r["id"], (True, None))
                if gone or not role or got >= limit:
                    continue
                got += 1
                out.append({"area": "office", "kind": "receipt", "id": r["id"], "space": sp, "title": r["name"], "place": "",
                            "by": r["created_by"] or r["owner_id"], "at": r["updated_at"]})
    return out


# ---------------------------------------------------------------- tables (#7662)
def rcn_sheets(c, uid, key, oid, limit):
    try:
        rows = sh_index(c, uid, key)  # the tables' own check (sh_space, sh_may; "all" with the shared ones)
    except (Denied, BadInput):
        return []
    rows = [r for r in rows if not _off(c, r["org_id"], "sheets")]
    rows.sort(key=lambda r: (rcn_at_key(r["updated_at"]), r["id"]), reverse=True)
    return [{"area": "sheets", "id": r["id"], "space": _sp_key(c, uid, r["org_id"], r["owner_id"]), "title": r["title"], "place": "",
             "by": r["updated_by"] or r["created_by"] or r["owner_id"], "at": r["updated_at"]} for r in rows[:limit]]


RCN_GET = {"wiki": rcn_wiki, "files": rcn_files, "reading": rcn_reading, "office": rcn_office, "sheets": rcn_sheets}


def rcn_at_key(v):
    """A sortable form of a stored UTC time: the areas write seconds (files, tasks) or milliseconds (pages)."""
    v = str(v or "")
    return v[:19] + (v[19:23] if v[19:20] == "." else ".000")


def rcn_items(c, uid, space="all", limit=RCN_LIMIT, areas=RCN_AREAS):
    """The newest items of the areas over the workspaces asked for (module docstring) -> (space key, [item])."""
    key, oid = rcn_space_arg(c, uid, space)
    out = []
    for a in areas:
        if feat_on(c, uid, RCN_FEAT[a]):
            out += [x for x in RCN_GET[a](c, uid, key, oid, limit) if _want(key, x["space"])]
    rc = {x["id"] for x in out if x.get("kind") == "receipt"}  # (#7662) a receipt once: as the office's, not again as a file
    if rc:
        out = [x for x in out if not (x["area"] == "files" and x["id"] in rc)]
    out.sort(key=lambda x: (rcn_at_key(x["at"]), x["area"], x["id"]), reverse=True)
    out = out[:limit]
    names = user_names(c, {x["by"] for x in out})
    for x in out:
        x["by_name"] = names.get(x["by"], "")
    return key, out


@app.get("/api/recent")
def recent_get():
    """?space=all|private|org:<id> &limit=1..50 &areas=wiki,files,reading,office,sheets -> {space, items} (module docstring)."""
    rcn_person()
    c, uid = db(), me()
    try:
        limit = int(request.args.get("limit") or RCN_LIMIT)
    except ValueError:
        raise BadInput(tr("Invalid value: {0}", "limit")) from None
    if not 1 <= limit <= RCN_MAX:
        raise BadInput(tr("Invalid value: {0}", "limit"))
    areas = [x for x in (request.args.get("areas") or ",".join(RCN_AREAS)).split(",") if x]
    if not areas or any(x not in RCN_AREAS for x in areas):
        raise BadInput(tr("Invalid value: {0}", "areas"))
    key, items = rcn_items(c, uid, request.args.get("space"), limit, tuple(dict.fromkeys(areas)))
    return jsonify(space=key, items=items)
