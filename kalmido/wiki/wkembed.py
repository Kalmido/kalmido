"""2.123.0 C (#2103, #2107): files of the file store ("Ablage") and tables in knowledge pages -- by reference, never a copy.

A page shows a file of the Ablage as ![label](/api/files/nodes/<id>/content) (a picture) or [label](/api/files/nodes/<id>/content)
(a file to open) and links a file or a table as [[datei:<path or id>]] / [[tabelle:<name or id>]] (an optional |label). The
content always comes through the Ablage's own routes (files/web.py: its rights, the virus lock, sealed at rest); this module
only says, for one viewer, which of the referenced objects they may see -- POST /api/wiki/pages/<id>/refs answers names and
types of the visible ones only, the rest stays a placeholder ("File not available") or plain text without any name.
Same space only: a page of an organisation references that organisation's Ablage / tables, a private page the owner's own
private ones (a file shared with the owner by someone else is not offered). After a move to another workspace (wkmove.py) the
references into the old space stay as text and show as unavailable.
wiki_links keeps the resolved references (to_file / to_sheet, rebuilt on every save by pages.wiki_set_links) for the
backlinks: GET /api/wiki/refs?file=<id> | sheet=<id> = the pages one may read that reference it. A space with the lock keeps no
links on the server (the browser asks /refs with the ids it finds in the decrypted text).
wem_visible(c, uid, node_id) is the one check for a viewer (uid None = not signed in, e.g. a guest link: never).
"""
import re
from datetime import datetime

from flask import jsonify, request

from ..core import objhooks  # 2.1284.0 (#6321): START, the rows of the pages written before wiki_embeds
from ..core.config import app
from ..core.db import body, db, gset, gsetting, iso_ms, now_utc
from ..core.i18n import tr
from ..core.pg import system_ctx  # 2.1368.0 (#6868)
from ..core.access import Denied, live_sql
from ..accounts.session import me
from ..core.errors import BadInput
from ..sheets.core import sh_may, sh_need  # 2.369.5 (#2517): pulled up from functions
from ..sheets.shbook import shb_deleted  # 2.369.5 (#2517): pulled up from functions
from .pages import wiki_may_read, wiki_need, wiki_space_key  # 2.369.5 (#2517): pulled up from functions
from ..accounts.orgs import user_orgs  # 2.369.5 (#2517): pulled up from functions
from .wikie2e import wke_open_sql  # 2.369.5 (#2517): pulled up from functions
from ..accounts.orgroles import user_orgs_full  # 2.369.5 (#2517): pulled up from functions

WEM_EMBED_RE = re.compile(r"/api/files/nodes/(\d{1,15})/content\b")
WEM_LINK_RE = re.compile(r"\[\[\s*(datei|tabelle)\s*:\s*([^\[\]|#\n]{1,250}?)\s*(?:\|[^\[\]\n]*)?\]\]", re.I)
WEM_MAX = 200  # references per page / per question
# 2.380 H (#2356): a picture of the file store embedded in a page: ![label](/api/files/nodes/<id>/content); 2.380 (#2356
# review): code shows as text -- a picture named in a fenced block or in `code` is not embedded (2.1284.0, #6321: here from
# wkshare.py, the one reading of "embedded" for the shares and for wiki_embeds)
WEM_IMG_RE = re.compile(r"!\[[^\[\]\n]*\]\(\s*<?/api/files/nodes/(\d{1,15})/content>?")
WEM_CODE_RE = re.compile(r"^[ \t]*(```|~~~).*?(?:^[ \t]*\1[^\n]*$|\Z)|`[^`\n]*`", re.S | re.M)


def wem_refs_of(text):
    """(node ids embedded, [(kind 'datei' | 'tabelle', the reference as written)]) of a page text."""
    t = text or ""
    ids = sorted({int(m.group(1)) for m in WEM_EMBED_RE.finditer(t) if int(m.group(1)) < 2 ** 62})
    links, seen = [], set()
    for m in WEM_LINK_RE.finditer(t):
        k = (m.group(1).lower(), m.group(2).strip())
        if k[1] and k not in seen:
            seen.add(k)
            links.append(k)
    return ids[:WEM_MAX], links[:WEM_MAX]


def wem_img_ids(text):
    """2.1284.0 (#6321): the node ids of the file store pictures embedded in a page text, sorted, all of them (a share shows
    the first WEM_MAX, wkshare.py wsh_img_nodes). A text of a locked space (e2e1:) has none on the server."""
    t = text or ""
    if t.startswith("e2e1:"):
        return []
    return sorted({int(m.group(1)) for m in WEM_IMG_RE.finditer(WEM_CODE_RE.sub("", t)) if int(m.group(1)) < 2 ** 62})


def wem_embeds_set(c, pid, text, by=None, old=None):
    """2.1284.0 (#6321): wiki_embeds of page pid follows its new text (pages.wiki_set_links calls it at every write of a
    page's text). One rule (Fable review 1 of #6321, F1-F5): only a person or an agent who SAVES a text they wrote claims a
    picture -- by = that account, old = the page's text before this save ("" = a new page). A picture this save turns into
    an embed is theirs; one that stays keeps its row (also a row with nobody); one that left the text loses its row.
    Everything else only follows (by None): a relink, a move, a rename of a folder, a restored version, an undo, a text that
    comes out of a space's lock, an import nobody here stands for -- an embed that appears there gets a row with nobody
    (user_id NULL = no picture through a share until someone takes it out and puts it in again). No row never means "the
    next writer's": an embed that stood in the old text without a row gets nobody too, as does every embed when old is not
    given."""
    ids = set(wem_img_ids(text))
    have = {r[0] for r in c.execute("SELECT node_id FROM wiki_embeds WHERE page_id=?", (pid,)).fetchall()}
    gone = sorted(have - ids)
    for i in range(0, len(gone), 500):
        part = gone[i:i + 500]
        c.execute(f"DELETE FROM wiki_embeds WHERE page_id=? AND node_id IN ({','.join('?' * len(part))})", [pid, *part])
    new = sorted(ids - have)
    was = set(wem_img_ids(old)) if new and by and old is not None else None
    for nid in new:
        c.execute("INSERT INTO wiki_embeds(page_id,node_id,user_id,created_at) VALUES(?,?,?,CURRENT_TIMESTAMP) "
                  "ON CONFLICT (page_id,node_id) DO NOTHING", (pid, nid, by if was is not None and nid not in was else None))
    if by:  # 2.1401.0 (#7056): their own pictures are confirmed for the shares with pictures over the page now
        wem_confirm(c, pid, by)


def wem_embeds_copy(c, src, pid, by):
    """2.1284.0 (#6321, review 1 F4 + re-check N1): page pid was made by account `by` from the text of page src (a template).
    An embed that `by` put into src themselves stays theirs on the new page; every other one stays nobody's (the row with
    user_id NULL of wem_embeds_set without `by`) -- reading a template is no right to carry a colleague's embed, with their
    name on it, to a page of one's own choice (e.g. under a folder link with pictures). Called after wem_embeds_set
    without `by`."""
    c.execute("UPDATE wiki_embeds SET user_id=s.user_id FROM wiki_embeds s WHERE s.page_id=? AND wiki_embeds.page_id=? "
              "AND s.node_id=wiki_embeds.node_id AND s.user_id=?", (src, pid, by))
    wem_confirm(c, pid, by)  # 2.1401.0 (#7056): confirmed for the shares over the new page, never the template's


def wem_embeds_drop(c, where, args):
    """2.1284.0 (#6321): the pages `where` (a condition on wiki_pages, fixed text of the caller) keep no embed rows: their
    text went behind the lock of a space (the places that empty wiki_links without pages.wiki_set_links)."""
    c.execute(f"DELETE FROM wiki_embeds WHERE page_id IN (SELECT id FROM wiki_pages WHERE {where})", args)


def wem_embed_rows(c, pid):
    """2.1401.0 (#7056): {node id: (account id | None, {share key, ...})} -- who embedded which picture into page pid and for
    which shares with pictures it is confirmed (wiki_embeds.shares, wkshare.wsh_ikey)."""
    return {r[0]: (r[1], set(r[2] or ())) for r in c.execute("SELECT node_id, user_id, shares FROM wiki_embeds WHERE page_id=?",
                                                              (pid,)).fetchall()}


# 2.1401.0 (#7056): the keys of shares go into wiki_embeds.shares (TEXT[]): added, never twice, sorted
WEM_ADD = ("UPDATE wiki_embeds SET shares=ARRAY(SELECT DISTINCT k FROM unnest(COALESCE(shares, CAST('{}' AS TEXT[])) || CAST(? AS TEXT[])) "
           "AS k ORDER BY k) WHERE page_id=? AND node_id=?")


def wem_img_shares(c, page):
    """2.1401.0 (#7056): {share key: its maker} of the live shares with pictures that cover page (a row with id, org_id,
    owner_id, path) now: the links of its space and, in a private space, the person shares (wkshare.wsh_rows)."""
    from .wkshare import wsh_covers, wsh_ikey, wsh_rows
    with system_ctx(c):  # every share of the space, also the ones of others the writer's context does not list
        rows = wsh_rows(c, page["org_id"], None if page["org_id"] else page["owner_id"])
    return {wsh_ikey(s): s["created_by"] for s in rows if s.get("images") and wsh_covers(s, page["path"], page["id"])}


def wem_confirm(c, pid, by):
    """2.1401.0 (#7056): a person's own save of page pid (wem_embeds_set with by, a page from a template): every picture in
    it that `by` embedded and sees is confirmed for the shares with pictures that cover the page NOW. A share shows a
    picture only when its row is confirmed for exactly that share (wkshare.wsh_img_nodes) -- the one check at the output,
    whichever way the page came under the share (a rename, a move, the tree, a folder merged into another, the trash and
    back, a round trip through another workspace): no way of moving a page confirms anything. -> rows confirmed."""
    if not by:
        return 0
    page = c.execute(f"SELECT id, org_id, owner_id, path FROM wiki_pages WHERE id=? AND {live_sql()}", (pid,)).fetchone()
    keys = sorted(wem_img_shares(c, page)) if page else []
    if not keys:
        return 0
    n = 0
    for nid, (who, _ok) in sorted(wem_embed_rows(c, pid).items()):
        if who == by and wem_visible(c, by, nid, page):
            n += c.execute(WEM_ADD, (keys, pid, nid)).rowcount
    return n


def wem_share_confirm(c, s, key):
    """2.1401.0 (#7056): share s (key wkshare.wsh_ikey) was made with pictures or got them switched on: its maker shares
    the pages as they are now, so every picture embedded in them now (by a person, wiki_embeds.user_id) that the maker
    sees is confirmed for s. A page that comes under s later shows its pictures only after its embedder saves it there
    (wem_confirm). -> rows confirmed."""
    from .wkshare import wsh_pub_pages
    maker, n = s["created_by"], 0
    if not maker:
        return 0
    with system_ctx(c):  # the pages of the share and the maker's rights on the file store, whoever switches the pictures on
        for p in wsh_pub_pages(c, s):
            for nid, (who, ok) in sorted(wem_embed_rows(c, p["id"]).items()):
                if who is not None and key not in ok and wem_visible(c, maker, nid, p):
                    n += c.execute(WEM_ADD, ([key], p["id"], nid)).rowcount
    return n


WEM_OK_FLAG = "wem_ok7056"  # settings: the live shares with pictures of before #7056 confirmed their pictures once


def wem_ok_start(c):
    """2.1401.0 (#7056, core/objhooks.START, once): the pictures that a share with pictures showed before this version are
    confirmed for it (wem_share_confirm for every live link and person share with pictures), so an update takes no picture
    away; from now on only an embedder's save and a share's pictures switched on confirm."""
    from .wkshare import wsh_ikey, wsh_rows
    n = 0
    with system_ctx(c):
        spaces = c.execute("SELECT DISTINCT org_id, owner_id FROM wiki_shares WHERE kind='link' AND images=1 AND revoked_at IS NULL "
                           "UNION SELECT DISTINCT CAST(NULL AS BIGINT), n.owner_id FROM wiki_share_cards k JOIN fs_shares f ON f.id=k.fs_share_id "
                           "JOIN fs_nodes n ON n.id=f.node_id WHERE k.images AND n.org_id IS NULL").fetchall()
        for sp in spaces:
            for s in wsh_rows(c, sp[0], None if sp[0] else sp[1]):
                if s.get("images"):
                    n += wem_share_confirm(c, s, wsh_ikey(s))
    return n


WEM_SINCE = "wem_since6321"  # settings: the start of the last run of wem_embeds_start (a point in time)


def wem_embeds_start(c):
    """2.1284.0 (#6321, core/objhooks.START, every start; review 1 F3/F6): wiki_embeds agrees with the texts again.
    The first start (no WEM_SINCE): every page -- the pages written before wiki_embeds get their rows, every picture
    embedded in a page's text with the page's last editor (the rule of #6295 that stood until then: nothing better is
    known), nobody (NULL) when the page has no editor any more.
    Every later start: only the pages changed since the start before (a version without wiki_embeds may have run in
    between, a rollback; else this finds nothing to do) -- a row whose picture is no longer in the text goes, an embed
    without a row gets nobody. A text that cannot be opened keeps what it has (no row = no picture).
    2.1368.0 (#6657, re-check N2): and every page whose stamp (wiki_pages.wem_at, migrations.d/6657.py) does not match its
    updated_at -- a version without the stamp (a rollback) or a hand wrote it: its rows may name someone who took the
    picture out meanwhile while another put it in again, so ALL its rows go to nobody (then the rule above). At the end
    every page is stamped (wem_at = updated_at)."""
    from .wkhist import WikiUnreadable, wkh_open
    since, ts = gsetting(c, WEM_SINCE), iso_ms(now_utc())
    try:
        datetime.fromisoformat((since or "").replace("Z", "+00:00"))
    except ValueError:
        since = None
    last, n = 0, 0
    stale = "(wem_at IS NOT NULL AND wem_at<>CAST(updated_at AS timestamptz))"  # the cast: a time column still TEXT (#5306)
    while True:
        rows = c.execute(f"SELECT id, org_id, owner_id, body, updated_by, {stale} AS stale FROM wiki_pages WHERE id>?"
                         + (f" AND (updated_at>=? OR {stale})" if since else "") + " ORDER BY id LIMIT 500",
                         (last, *([since] if since else ()))).fetchall()
        if not rows:
            break
        for r in rows:
            last = r["id"]
            if r["stale"]:  # 2.1368.0 (#6657): written without the stamp -- nobody stands for its pictures any more
                n += c.execute("UPDATE wiki_embeds SET user_id=NULL, shares=NULL WHERE page_id=? AND (user_id IS NOT NULL OR shares IS NOT NULL)", (r["id"],)).rowcount  # 2.1401.0 (#7056): and no share confirmed
            try:
                ids = set(wem_img_ids(wkh_open(c, r["org_id"], r["owner_id"], r["body"])))
            except WikiUnreadable:
                continue
            have = {x[0] for x in c.execute("SELECT node_id FROM wiki_embeds WHERE page_id=?", (r["id"],)).fetchall()}
            who = r["updated_by"] if not since and not have else None
            for nid in sorted(have - ids):
                n += c.execute("DELETE FROM wiki_embeds WHERE page_id=? AND node_id=?", (r["id"], nid)).rowcount
            for nid in sorted(ids - have):
                n += c.execute("INSERT INTO wiki_embeds(page_id,node_id,user_id,created_at) VALUES(?,?,?,CURRENT_TIMESTAMP) "
                               "ON CONFLICT (page_id,node_id) DO NOTHING", (r["id"], nid, who)).rowcount
    c.execute("UPDATE wiki_pages SET wem_at=CAST(updated_at AS timestamptz) WHERE wem_at IS DISTINCT FROM CAST(updated_at AS timestamptz)")  # 2.1368.0 (#6657)
    if not since:  # 2.1401.0 (#7056): the pages of before had no confirmations either -- the shares that showed them confirm once
        n += wem_ok_start(c)
    gset(c, WEM_SINCE, ts)
    return n


def wem_same_space(row, page):
    """Does an Ablage node / a table row lie in the space of the page (organisation, or the page owner's private one)?"""
    if page["org_id"]:
        return row["org_id"] == page["org_id"]
    return row["org_id"] is None and row["owner_id"] == page["owner_id"]


def wem_visible(c, uid, node_id, page=None):
    """May account uid see the Ablage file node_id (a file, not in the trash, its Ablage rights)? page: also in the page's space.
    uid None (a guest / public link, nobody signed in) -> False."""
    from ..files.store import fs_chain, fs_deleted, fs_role
    if not uid or not isinstance(node_id, int) or not 0 < node_id < 2 ** 62:
        return False
    chain = fs_chain(c, node_id)
    if not chain or fs_deleted(chain) or chain[0]["kind"] != "file":
        return False
    if page is not None and not wem_same_space(chain[0], page):
        return False
    return bool(fs_role(c, node_id, uid, chain=chain))


def wem_sheet_ok(c, uid, sid, page):
    if not uid or not isinstance(sid, int) or not 0 < sid < 2 ** 62:
        return None
    r = c.execute("SELECT * FROM sheets WHERE id=? AND deleted_at IS NULL", (sid,)).fetchone()
    if r and shb_deleted(c, r):  # 2.124.0 (#2116): a further sheet of a table in the trash
        return None
    return r if r and wem_same_space(r, page) and sh_may(c, uid, r) else None


def wem_find_file(c, page, ref):
    """The node id a [[datei:…]] reference names in the page's space: an id, or a path of folder names from the top (case
    does not matter); None when there is none. No rights check (the caller checks the viewer)."""
    ref = ref.strip().strip("/")
    if ref.isdigit():
        r = c.execute("SELECT id, org_id, owner_id FROM fs_nodes WHERE id=?", (int(ref),)).fetchone() if len(ref) < 16 else None
        return r["id"] if r and wem_same_space(r, page) else None
    parts = [p.strip() for p in ref.split("/") if p.strip()]
    if not parts or len(parts) > 32:
        return None
    if page["org_id"]:
        w, a = "parent_id IS NULL AND org_id=?", [page["org_id"]]
    else:
        w, a = "parent_id IS NULL AND org_id IS NULL AND owner_id=?", [page["owner_id"]]
    nid = None
    for i, p in enumerate(parts):
        kind = "file" if i == len(parts) - 1 else "folder"
        r = c.execute(f"SELECT id FROM fs_nodes WHERE {w} AND deleted_at IS NULL AND lower(name)=? AND kind=? ORDER BY id LIMIT 1",
                      [*a, p.lower(), kind]).fetchone()
        if not r:
            return None
        nid = r["id"]
        w, a = "parent_id=?", [nid]
    return nid


def wem_find_sheet(c, page, ref):
    """The table id a [[tabelle:…]] reference names in the page's space (an id or the title, case does not matter)."""
    ref = ref.strip()
    w, a = ("org_id=?", [page["org_id"]]) if page["org_id"] else ("org_id IS NULL AND owner_id=?", [page["owner_id"]])
    if ref.isdigit() and len(ref) < 16:
        r = c.execute(f"SELECT id FROM sheets WHERE id=? AND deleted_at IS NULL AND {w}", [int(ref), *a]).fetchone()
    else:
        r = c.execute(f"SELECT id FROM sheets WHERE lower(title)=? AND deleted_at IS NULL AND book_id IS NULL AND {w} ORDER BY id LIMIT 1", [ref.lower(), *a]).fetchone()
    return r["id"] if r else None


def wem_set_links(c, pid, text):
    """The to_file / to_sheet rows of a page (called by pages.wiki_set_links after it removed the old rows)."""
    if (text or "").startswith("e2e1:"):  # a locked space keeps no links on the server
        return
    ids, links = wem_refs_of(text)
    if not ids and not links:
        return
    page = c.execute("SELECT id, org_id, owner_id FROM wiki_pages WHERE id=?", (pid,)).fetchone()
    if not page:
        return
    files, sheets = set(), set()
    for nid in ids:
        r = c.execute("SELECT id, org_id, owner_id FROM fs_nodes WHERE id=?", (nid,)).fetchone()
        if r and wem_same_space(r, page):
            files.add(nid)
    for kind, ref in links:
        x = wem_find_file(c, page, ref) if kind == "datei" else wem_find_sheet(c, page, ref)
        if x:
            (files if kind == "datei" else sheets).add(x)
    for f in sorted(files):
        c.execute("INSERT INTO wiki_links(from_id,to_file) VALUES(?,?)", (pid, f))
    for s in sorted(sheets):
        c.execute("INSERT INTO wiki_links(from_id,to_sheet) VALUES(?,?)", (pid, s))


def wem_file_dict(c, nid):
    r = c.execute("SELECT id, name, mime, size FROM fs_nodes WHERE id=?", (nid,)).fetchone()
    return {"kind": "file", "id": r["id"], "name": r["name"], "mime": r["mime"] or "", "size": r["size"],
            "image": (r["mime"] or "").startswith("image/"), "url": f"/api/files/nodes/{r['id']}/content"}


def wem_list(v, what, item):
    if v is None:
        return []
    if not isinstance(v, list) or len(v) > WEM_MAX or not all(item(x) for x in v):
        raise BadInput(tr("Invalid value: {0}", what))
    return v


@app.post("/api/wiki/pages/<int:pid>/refs")
def wem_refs(pid):
    """{files: [node id …], links: ["datei:<path or id>" | "tabelle:<name or id>" …]} -- what of it the signed-in person may
    see from this page (they need to read the page): {files: {id: {name, mime, size, image, url}}, links: {"<kind>:<ref in
    lower case>": {kind file | sheet, id, name, url, image?}}}. Not visible / not there / another space = left out (no name).
    Read-only; POST only because the browser sends what it found in the text (a locked space: the decrypted text)."""
    c = db()
    page = wiki_need(c, pid)
    uid = me()
    b = body()
    ids = wem_list(b.get("files"), "files", lambda x: isinstance(x, int) and not isinstance(x, bool))
    links = wem_list(b.get("links"), "links", lambda x: isinstance(x, str) and 0 < len(x) <= 260)
    files, out = {}, {}
    for nid in ids:
        if wem_visible(c, uid, nid, page):
            files[str(nid)] = wem_file_dict(c, nid)
    for s in links:
        kind, _, ref = s.partition(":")
        kind = kind.strip().lower()
        if kind not in ("datei", "tabelle") or not ref.strip():
            continue
        key = f"{kind}:{ref.strip().lower()}"
        if kind == "datei":
            nid = wem_find_file(c, page, ref)
            if nid and wem_visible(c, uid, nid, page):
                out[key] = wem_file_dict(c, nid)
        else:
            sid = wem_find_sheet(c, page, ref)
            r = wem_sheet_ok(c, uid, sid, page) if sid else None
            if r:
                out[key] = {"kind": "sheet", "id": r["id"], "name": r["title"] or tr("Untitled table"), "url": f"#sheets/{r['id']}"}
    return jsonify(files=files, links=out)


@app.get("/api/wiki/refs")
def wem_backlinks():
    """?file=<node id> | ?sheet=<table id> -- the knowledge pages one may read (spaces without the lock) that show or link it;
    404 when one may not see the file / table itself."""
    c = db()
    uid = me()
    fid, sid = request.args.get("file", type=int), request.args.get("sheet", type=int)
    if fid:
        if not wem_visible(c, uid, fid):
            raise Denied(404)
        col, oid = "to_file", fid
    elif sid:
        sh_need(c, sid)
        col, oid = "to_sheet", sid
    else:
        raise BadInput(tr("Invalid value: {0}", "file"))
    orgs = [o for o in user_orgs(c, uid) if o in user_orgs_full(c, uid)]  # 2.143.0 A (#2151)
    rows = c.execute(f"SELECT p.* FROM wiki_pages p WHERE p.id IN (SELECT k.from_id FROM wiki_links k WHERE k.{col}=?) "
                     f"AND {wke_open_sql('p')} AND p.deleted_at IS NULL AND ((p.org_id IS NULL AND p.owner_id=?)"
                     + (f" OR p.org_id IN ({','.join(str(int(x)) for x in orgs)})" if orgs else "") + ") ORDER BY p.path LIMIT 200",
                     (oid, uid)).fetchall()
    rows = [r for r in rows if wiki_may_read(c, uid, r)][:50]  # 2.750.0 (#5264): the page's own role (wkf_role), not the membership; 200 read so the hidden ones take no place of the 50
    return jsonify(pages=[{"id": r["id"], "path": r["path"], "space": wiki_space_key(r["org_id"])} for r in rows])


def wem_purged(c, nid):
    """A file removed for good (files/store.fs_purge): its backlink rows go with it, 2.1284.0 (#6321) and who embedded it."""
    c.execute("DELETE FROM wiki_links WHERE to_file=?", (nid,))
    c.execute("DELETE FROM wiki_embeds WHERE node_id=?", (nid,))


def _wem_hook():
    from ..files.store import fs_on_delete
    if wem_purged not in fs_on_delete:
        fs_on_delete.append(wem_purged)


_wem_hook()


objhooks.START.append(("wem_embeds_start", False, wem_embeds_start))  # 2.1284.0 (#6321): every start (the first one: all pages)
objhooks.START.append((WEM_OK_FLAG, True, wem_ok_start))  # 2.1401.0 (#7056): once, after the step above
