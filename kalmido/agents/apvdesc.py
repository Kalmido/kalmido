"""2.1269.0 (#6450): the SERVER's words for the step an approval card binds -- what a Yes does, in plain words.

An agent's approval card binds a step (agents/control.py ctl_card_extra: method, path, body); a Yes runs exactly that step.
The card's title and text are the agent's own words and may say anything ("May I sort the task?") while the bound step
shares a project, moves a task elsewhere or changes many tasks at once. So the person sees the server's description of
the bound step, reckoned from method, path and body (never from the agent's words) when the card is shown, with the rights
and in the language of the person who looks at it (GET /api/approvals/diff, agents/apvdiff.py: the answer's "desc"):

  desc = {fam, lines: [[[part, text], ...], ...], warn: the first of warns or None, warns: [[hidden | share | invite |
         export | move, its line], ...], hidden: bool}
         part "t" = the server's words, "v" = a value (a name, a field's value: foreign text, cleaned, shown set apart)

Every write route an approval card can bind has its decided family in tests/p21269_d_apvdesc_routes.json (checked by
tests/p21269_d_apvdesc_routes_test.py: a new route fails there until it is entered); a step whose route matches none gets the general description (method, target and
every value of the body). Names come only from objects the person may see; anything else reads "something you cannot
see" with the warning line "hidden". Values are cut, control and direction characters dropped, line breaks shown as one
sign, so a value can never look like a second line of the server.
"""
import json
import re
import unicodedata

from ..core.config import API_PREFIX, app
from ..core.access import Denied, list_role, task_visible
from ..core.i18n import N_, fmt_int, tr, trn
from ..collab.liste2e import le2e_is_cipher
from ..accounts.orgs import may_see
from ..api.scopes import BATCH_TITLE, ROLE_WORD
from ..core.objcomments import ocm_row
from ..core.objects import OBJ, obj_role, obj_row, obj_title
from ..lists.groups import grp_visible
from ..contacts.ctfolder import CTF_BOOK
from ..events.evkern import EV_KIND
from ..core.objlight import LT_EVENT, LT_CLIENT
from ..sheets.shkern import SHK_KIND
from ..wiki.wkkern import WKK_KIND
from ..lists.tplkind import TK_KIND
from ..collab.tcxcore import TCX_KIND
from ..videos.vdkern import VDR_KIND
from .control import CTL_DESC, ctl_rule_path
from . import apvdiff

APVX_VAL_MAX = 120  # characters of one value
APVX_FIELDS_MAX = 20  # fields of a body shown (people, projects and outward keys first), the rest counted
APVX_LINES_MAX = 26
APVX_BATCH_NAMES = 3  # titles of a batch shown by name
APVX_BATCH_CHECK = 500  # ids of a batch checked one by one (the route's own ceiling); more are counted as not seen
APVX_DEPTH = 3  # levels of a nested body opened up as lines "a.b: value" (review: a dict as one cut JSON value hid its keys)
APVX_LIST_SHOW = 3  # entries of a list of objects opened up (all of them are searched for the warning keys)
APVX_OLD_OK = {"title", "name", "priority", "due", "due_time", "start", "status", "color", "locked", "starts", "ends",
               "location", "icon", "role", "archived", "open"}  # the columns whose value now is shown as "old -> new"
APVX_HIDE_KEYS = {"expect_updated_at", "_prev", "_files", "if_match", "If-Match", "prev"}  # helpers, not values (files: the card's own line)

# (methods, route below /api/v1 as ctl_rule_path writes it, family). First match wins. The families: share (gives access),
# unshare, owner (hands over), join, invite (adds people to a conversation / invites), export (data or access leaves
# Kalmido), move, batch (many at once), delete, update (fields: old -> new), create, action (a verb on an object),
# meta (the agent's own channel: what it says about itself), text (a text step: the diff of apvdiff.py shows it as well).
APVX_ROUTES = (
    (("PUT",), r"^/(lists|address-books|event-calendars)/\{\}/members/\{\}$", "share"),
    (("PUT",), r"^/lists/\{\}/groups/\{\}$", "share"),
    (("DELETE",), r"^/(lists|address-books|event-calendars|team/rooms)/\{\}/(members|groups)/\{\}$", "unshare"),
    (("POST",), r"^/lists/\{\}/owner$", "owner"),
    (("POST",), r"^/lists/\{\}/join$", "join"),
    (("POST",), r"^/team/rooms/\{\}/members$", "invite"),
    (("POST",), r"^/team/(dm|channels|groups)$", "invite"),
    (("PUT",), r"^/admin/announcement$", "announce"),
    (("POST", "PATCH", "DELETE"), r"^/(me|orgs/\{\})/webhooks(/\{\})?(/(secret|test))?$", "export"),
    (("PATCH",), r"^/lists/\{\}/error-hook$", "export"),
    (("POST", "DELETE"), r"^/me/(tokens|app-passwords)(/\{\})?$", "export"),
    (("POST", "PATCH", "PUT", "DELETE"), r"^/(lists/\{\}/repos(/version-field)?|repos/\{\})$", "export"),
    (("POST",), r"^/lists/\{\}/forms$", "export"),  # a form answers people from outside
    (("PATCH",), r"^/forms/\{\}$", "export"),  # 2.1269.0 (#6450): access, enabled, a new public address
    (("POST",), r"^/life/karakeep/sync$", "export"),  # 2.1269.0 (#6450): writes back to the person's Karakeep
    (("POST",), r"^/tasks/\{\}/watchers$", "invite"),  # 2.1269.0 (#6450): the person gets the task's messages
    (("POST",), r"^/tasks/\{\}/(move|to-shopping|links)$", "move"),  # links: shown in a further project as well
    (("POST",), r"^/(tasks/batch|clients/bulk|contacts/bulk|sheets/\{\}/batches/\{\}/undo)$", "batch"),
    (("PUT",), r"^/sheets/\{\}/cells$", "batch"),
    (("PATCH",), r"^/tasks/\{\}$", "task"),  # update, or a move when the body names another project
    (("PATCH", "POST"), r"^/(wiki/pages/\{\}|tasks/\{\}/notes|lists/\{\}/overview)/(append|replace-section)$", "text"),
    (("PATCH",), r"^/(wiki/pages|comments|lists/\{\}/overview)(/\{\})?$", "text"),
    (("POST", "DELETE"), r"^/agent/objects/\{\}/\{\}/links(/\{\})?$", "link"),
    (("PATCH",), r"^/agent/objects/\{\}/\{\}$", "update"),  # an object of the shared core: data a person sees, not the agent's channel
    (("POST", "PUT", "PATCH", "DELETE"), r"^/(agent|agents/\{\}/chat)(/|$)", "meta"),
    (("POST",), r"^/(news/read|team/rooms/\{\}/read|tasks/\{\}/typing|tasks/brief)$", "meta"),
    (("POST", "PATCH", "DELETE"), r"^/tasks/\{\}/working$", "meta"),
    (("DELETE",), r"", "delete"),
    (("POST",), r"^/folders/delete$", "delete"),
    (("PATCH",), r"", "update"),
    (("PUT",), r"/\{\}$", "update"),
    (("PUT",), r"", "update"),
    (("POST",), r"^/(folders/rename|focus/start|life/karakeep/sync|me/purpose)$", "action"),  # verbs without an object id
    (("POST",), r"^(/[a-z-]+)+$", "create"),  # a collection: /tasks, /office/offers, /life/trips ...
    (("POST",), r"/\{\}/(comments|subtasks|attachments|attachments/text|contacts|dependencies|links|relations|watchers|"
                r"snippets|decisions|rewards|stars|fields|files|forms|milestones|notepads|notes|sections|tags|views|"
                r"shop-areas|deployments|columns|rows|tabs|messages|reactions|prep-task|versions|import|choice)$", "create"),
    (("POST",), r"", "action"),
)
APVX_WARN = {"share": N_("Other people get access - check who and to what"),
             "invite": N_("Invites people - they get a message"),
             "export": N_("Data or access leaves Kalmido"),
             "move": N_("Moves it to another project - other people may see it there"),
             "hidden": N_("The step concerns something you cannot see - say yes only if you know what it is")}
APVX_WARN_OF = {"share": "share", "owner": "share", "join": "share", "announce": "share", "invite": "invite", "export": "export"}
# a body key that brings people in or data out, on any route
APVX_BODY_WARN = {"attendees": "invite", "invitees": "invite", "guests": "invite", "members": "invite", "recipients": "invite",
                  "emails": "invite", "url": "export", "hook_url": "export", "webhook": "export", "public": "share",
                  "visibility": "share", "org_id": "share",
                  # 2.1269.0 (#6450): agents get a project, a comment goes to the client's portal or out by mail
                  "agent_members": "share", "agent_peers": "share", "listen_agent_ids": "share", "portal": "export",
                  "mail_reporter": "export"}
APVX_WARN_RANK = ("hidden", "share", "invite", "export", "move")
# the word of an object below /api/v1 by the path segment before its id (the label alone when no name can be read)
APVX_LABEL = {
    "lists": N_("Project"), "tasks": N_("Task"), "address-books": N_("Address book"), "event-calendars": N_("Calendar"),
    "events": N_("Event"), "sheets": N_("Table"), "pages": N_("Knowledge page"), "clients": N_("Client"),
    "templates": N_("Template"), "rooms": N_("Channel"), "videos": N_("Video sign-off"), "comments": N_("Comment"),
    "contacts": N_("Contact"), "sections": N_("Section"), "notes": N_("Note"), "notepads": N_("Notepad"),
    "milestones": N_("Milestone"), "tags": N_("Tag"), "fields": N_("Field"), "filters": N_("Filter"), "forms": N_("Form"),
    "habits": N_("Habit"), "entries": N_("Time entry"), "attachments": N_("Attachment"), "chat-attachments": N_("Attachment"),
    "documents": N_("Document"), "files": N_("File"), "list-files": N_("File"), "repos": N_("Repository"),
    "webhooks": N_("Webhook"), "links": N_("Link"), "groups": N_("Group"), "members": N_("Person"),
    "messages": N_("Message"), "offers": N_("Quotation"), "letters": N_("Letter"), "leads": N_("Lead"), "deals": N_("Deal"),
    "rewards": N_("Reward"), "kids": N_("Child"), "ticket-types": N_("Ticket type"), "tokens": N_("Access token"),
    "app-passwords": N_("App password"), "imports": N_("Import"), "import": N_("Import"), "journal": N_("Journal"),
    "focus": N_("Focus time"), "dependencies": N_("Dependency"), "relations": N_("Relation"), "watchers": N_("Person"),
    "reactions": N_("Reaction"), "batches": N_("Change"), "orgs": N_("Organisation"), "jobs": N_("Job"),
    "chats": N_("Chat"), "objects": N_("Object"), "rules": N_("Rule"),
}
APVX_ACT = {"complete": N_("Completes {0}"), "reopen": N_("Reopens {0}"), "skip": N_("Skips {0} once"),
            "restore": N_("Restores {0} from the trash"), "duplicate": N_("Duplicates {0}"), "take": N_("Takes over {0}"),
            "undo": N_("Undoes {0}"), "apply": N_("Applies {0}")}


# ---------------------------------------------------------------- cleaning foreign text
def apvx_clean(v, n=APVX_VAL_MAX):
    """A value as one short line: control, format (direction, zero width) and private characters out, line breaks as ↵."""
    s = v if isinstance(v, str) else json.dumps(v, ensure_ascii=False, sort_keys=True, default=str)
    out = []
    for ch in s[:n * 4]:
        if ch in "\r\n\u2028\u2029\x85\x0b\x0c":
            out.append(" ↵ ")
        elif ch == "\t":
            out.append(" ")
        elif unicodedata.category(ch) in ("Cc", "Cf", "Co", "Cs", "Zl", "Zp"):
            continue
        else:
            out.append(ch)
    s = re.sub(r"\s+", " ", "".join(out)).strip()
    return s if len(s) <= n else s[:n - 1].rstrip() + "…"


def _say(key, *vals):
    """The parts of one line: the translated text with its {n} filled -- a str value is foreign ("v"), a list of parts
    stands as it is (a phrase of the server with its own values)."""
    out = []
    for i, bit in enumerate(re.split(r"\{(\d+)\}", tr(key))):
        if i % 2 == 0:
            if bit:
                out.append(["t", bit])
            continue
        v = vals[int(bit)] if int(bit) < len(vals) else ""
        out += v if isinstance(v, list) else [["v", apvx_clean(v)]]
    return out


def _w(word):
    """A server word inside a line (a label, a role): set apart like a value but never foreign."""
    return [["v", tr(word)]]


# ---------------------------------------------------------------- names, read with the rights of the viewer
class _Ctx:
    def __init__(self, c, uid, decided):
        self.c, self.uid, self.decided, self.hidden, self.warn = c, uid, decided, False, set()

    def unseen(self):
        self.hidden = True
        return [["t", tr("something you cannot see")]]


def _plain(v):
    return "" if not isinstance(v, str) or le2e_is_cipher(v) else v


def _row(c, sql, rid):
    try:
        return c.execute(sql, (int(rid),)).fetchone()
    except (TypeError, ValueError):
        return None


def _obj(x, kind, rid):
    """(name, row) of an object of the shared core the viewer may see, or None."""
    try:
        if obj_role(x.c, x.uid, kind, int(rid)) is None:
            return None
        r = obj_row(x.c, kind, rid)
        if r is None or ("deleted_at" in r.keys() and r["deleted_at"]):
            return None
        return _plain(obj_title(x.c, kind, rid)) or next((_plain(r[k]) for k in ("title", "name", "path") if k in r.keys() and _plain(r[k])), ""), r
    except (Denied, TypeError, ValueError):
        return None


def _seen(x, seg, rid):
    """(name, row) of object rid of path segment seg when the viewer may see it, None when not (or gone), False when
    this kind of object has no reader here (the label and number only)."""
    c, uid = x.c, x.uid
    if seg == "lists":
        r = _row(c, "SELECT * FROM lists WHERE id=?", rid)
        return (_plain(r["name"]), r) if r is not None and list_role(c, int(rid), uid) else None
    if seg == "tasks":
        r = _row(c, "SELECT * FROM tasks WHERE id=?", rid)
        return (_plain(r["title"]), r) if r is not None and not r["deleted_at"] and task_visible(c, int(rid), uid) else None
    if seg == "comments":
        r = ocm_row(c, int(rid), live=True) if str(rid).isdigit() else None
        if r is None or not task_visible(c, r["task_id"], uid, full=True):
            return None
        t = _row(c, "SELECT title FROM tasks WHERE id=?", r["task_id"])
        return (tr("on task {0}", _plain(t["title"]) if t else ""), None)
    if seg in ("members", "watchers"):
        return _person(x, rid)
    if seg == "groups":
        return _group(x, rid)
    kind = _kind_of(seg)
    if kind:
        return _obj(x, kind, rid)
    return False


def _kind_of(seg):
    return {"address-books": CTF_BOOK, "event-calendars": EV_KIND, "events": LT_EVENT, "clients": LT_CLIENT,
            "sheets": SHK_KIND, "pages": WKK_KIND, "templates": TK_KIND, "rooms": TCX_KIND, "videos": VDR_KIND}.get(seg)


def _person(x, rid):
    try:
        u = int(rid)
    except (TypeError, ValueError):
        return None
    r = _row(x.c, "SELECT display_name, username FROM users WHERE id=?", u)
    if r is None or not may_see(x.c, x.uid, u):
        return None
    return (r["display_name"] or r["username"] or "", None)


def _group(x, rid):
    r = _row(x.c, "SELECT * FROM groups WHERE id=?", rid)
    return (r["name"] or "", r) if r is not None and grp_visible(x.c, r) else None


def _who(x, rid):
    """A person as parts: the name, or "a person you cannot see"."""
    p = _person(x, rid)
    if not p:
        x.hidden = True
        return [["t", tr("a person you cannot see")]]
    return [["v", apvx_clean(p[0])]]


def _thing(x, seg, rid, label=True):
    """An object as parts: "Project" + its name, or "something you cannot see"."""
    s = _seen(x, seg, rid)
    lab = tr(APVX_LABEL.get(seg) or seg.replace("-", " "))
    if s is None:
        return x.unseen()
    if s is False:
        return [["t", f"{lab} "], ["v", f"#{apvx_clean(rid, 20)}"]]
    name = apvx_clean(s[0]) if s[0] else ""
    head = [["t", f"{lab} "]] if label else []
    return head + ([["v", name]] if name else [["t", f"#{apvx_clean(rid, 20)}"]])


def _pairs(rule_text, args):
    """[(segment before a variable, its value)] of a matched route: the rule's own variables with the values url_map.match
    gave (review: never by position in the path -- a converter with a slash would shift every later segment)."""
    segs = rule_text.strip("/").split("/")
    out = []
    for i, seg in enumerate(segs):
        hit = re.fullmatch(r"<(?:[^:<>]+:)?([^<>]+)>", seg)
        if hit and hit.group(1) in args:
            prev = segs[i - 1] if i else ""
            out.append(("{}" if prev.startswith("<") else prev, str(args[hit.group(1)])))
    return out


def _target(x, rule, pr):
    """The object a step works on, as parts (the last object of the path, "of" its parent's)."""
    if rule.startswith("/agent/objects/{}/{}") and len(pr) >= 2:
        kind, rid = pr[0][1], pr[1][1]
        reg = OBJ.get(kind)
        o = _obj(x, kind, rid) if reg else None
        if o is None:
            return x.unseen()
        return [["t", tr(reg["label"]) + " "], ["v", apvx_clean(o[0]) or f"#{rid}"]]
    if not pr:
        tail = [s for s in rule.strip("/").split("/") if s != "{}"]
        return [["v", tr(APVX_LABEL.get(tail[-1], tail[-1].replace("-", " "))) if tail else "/"]]
    if len(pr) == 1:
        return _thing(x, *pr[0])
    parent = _thing(x, *pr[0])
    if x.hidden:
        return parent
    return _thing(x, *pr[-1]) + [["t", " · "]] + parent


# ---------------------------------------------------------------- values of the body
APVX_PERSON_KEYS = re.compile(r"^(user_id|user_ids|assignee_id|assignee_ids|owner_id|approver_id|members|watchers|person_id)$")


def _id(v):
    """An id from a body (an int or a string of digits, as the routes take it) or None."""
    if isinstance(v, bool):
        return None
    if isinstance(v, int):
        return v if 0 < v < 2 ** 62 else None
    return int(v) if isinstance(v, str) and v.isdigit() and len(v) < 18 else None


def _val(x, k, v):
    """A body value as parts: people and projects by name (when the viewer sees them), the rest cleaned."""
    if APVX_PERSON_KEYS.match(k):
        ids = v if isinstance(v, list) else [v]
        if ids and all(isinstance(i, int) and not isinstance(i, bool) for i in ids):
            out = []
            for i, u in enumerate(ids[:APVX_BATCH_NAMES * 2]):
                out += ([["t", ", "]] if i else []) + _who(x, u)
            return out + ([["t", " " + trn("and {0} more", "and {0} more", len(ids) - len(ids[:APVX_BATCH_NAMES * 2]))]]
                          if len(ids) > APVX_BATCH_NAMES * 2 else [])
    if k in ("list_id", "parent_id", "task_id", "group_id") and _id(v):
        return _thing(x, {"list_id": "lists", "group_id": "groups"}.get(k, "tasks"), _id(v))
    if v is None or v == "":
        return [["t", tr("(empty)")]]
    if isinstance(v, str) and le2e_is_cipher(v):
        return [["t", tr("(encrypted)")]]
    if isinstance(v, list) and len(v) > 3:
        return [["v", apvx_clean(trn("{0} entry", "{0} entries", len(v)) + ": " + ", ".join(apvx_clean(i, 40) for i in v[:3]) + " …")]]
    return _cut(v)


def _cut(v):
    """A value as one part; cut: + its whole length in words (more is bound than shown)."""
    src = v if isinstance(v, str) else json.dumps(v, ensure_ascii=False, sort_keys=True, default=str)
    return [["v", apvx_clean(src)]] + ([["t", " " + tr("({0} characters)", fmt_int(len(src)))]] if len(src) > APVX_VAL_MAX else [])


def _flat(v, path="", key="", depth=0, skip=()):
    """[(path, leaf key, value | ("count", n))] of a body: objects opened up to APVX_DEPTH levels ("a.b"), a list of
    objects as its count and its first APVX_LIST_SHOW entries ("a[0].b"); deeper or plain values stay one value."""
    if isinstance(v, dict) and depth < APVX_DEPTH:
        out = []
        for k, y in v.items():
            if depth == 0 and (k in APVX_HIDE_KEYS or k in skip):
                continue
            out += _flat(y, f"{path}.{k}" if path else str(k), str(k), depth + 1)
        return out
    if isinstance(v, list) and v and all(isinstance(i, dict) for i in v) and depth < APVX_DEPTH:
        out = [(path, key, ("count", len(v)))]
        for i, y in enumerate(v[:APVX_LIST_SHOW]):
            out += _flat(y, f"{path}[{i}]", key, depth + 1)
        return out
    return [(path, key, v)]


def _scan(x, v, depth=0):
    """The warning keys anywhere in a body: every level, every entry of every list (not only the ones shown)."""
    if depth > 12:
        return
    if isinstance(v, dict):
        for k, y in v.items():
            if k in APVX_BODY_WARN:
                x.warn.add(APVX_BODY_WARN[k])
            _scan(x, y, depth + 1)
    elif isinstance(v, list):
        for y in v:
            _scan(x, y, depth + 1)


def _order(row):
    """The place of a body value among the lines (review: never the agent's order in the body, which decides what falls
    behind "and N more fields"): 0 the keys that bring people in, data out or name a project / group / organisation, 1 the
    plain top-level columns (title, due ... APVX_OLD_OK), 2 the rest -- each alphabetical by its path."""
    path, key = row[0], row[1]
    if key in APVX_BODY_WARN or APVX_PERSON_KEYS.match(key) or key in ("list_id", "group_id", "org_id"):
        return (0, path)
    return (1 if path == key and key in APVX_OLD_OK else 2, path)


def _fields(x, b, old=None, skip=()):
    """One line per value of body b: "field: new" or "field: old → new" (old: the target's row, when it has the column);
    nested objects as "a.b: value", lists of objects as their count and first entries (_flat)."""
    if not isinstance(b, (dict, list)):
        return []
    _scan(x, {k: v for k, v in b.items() if k not in skip} if isinstance(b, dict) else b)
    if isinstance(b, list) and not (b and all(isinstance(i, dict) for i in b)):
        return [_say(N_("Values: {0}"), _val(x, "", b))]
    rows = _flat(b, skip=skip)
    rows.sort(key=_order)
    lines = []
    for path, k, v in rows[:APVX_FIELDS_MAX]:
        head = [["v", apvx_clean(path or "[]", 60)], ["t", ": "]]
        if isinstance(v, tuple) and len(v) == 2 and v[0] == "count":
            lines.append(head + [["t", trn("{0} entry", "{0} entries", v[1])]])
            continue
        col = k if path == k and k in APVX_OLD_OK else None  # only plain top-level columns: never one the body names freely
        prev = old[col] if col and old is not None and not x.decided and col in old.keys() and not isinstance(v, (dict, list)) else None
        if prev is not None and not isinstance(prev, (bytes, memoryview)) and not le2e_is_cipher(str(prev)) and str(prev) != str(v):
            lines.append(head + _val(x, k, prev) + [["t", " → "]] + _val(x, k, v))
        else:
            lines.append(head + _val(x, k, v))
    if len(rows) > APVX_FIELDS_MAX:
        lines.append([["t", trn("and {0} more field", "and {0} more fields", len(rows) - APVX_FIELDS_MAX)]])
    return lines


# ---------------------------------------------------------------- the families
def _fam(method, rule):
    for ms, rx, fam in APVX_ROUTES:
        if method in ms and re.search(rx, rule):
            return fam
    return "general"


def _rule_of(st):
    """(rule path below /api/v1 with {} for the variables, concrete path below /api/v1, [(segment, value)] of its
    variables) of a step, or (None, path, [])."""
    p = st.get("path") if isinstance(st.get("path"), str) else ""
    sub = p[len(API_PREFIX) - 1:] if p.startswith(API_PREFIX) else p
    try:
        rule, args = app.url_map.bind("localhost").match(p, method=st.get("method"), return_rule=True)
        return ctl_rule_path(rule), sub, _pairs(rule.rule, args)
    except Exception:  # noqa: BLE001  no such route (any more): the general description
        return None, sub, []


def _batch(x, b, rule):
    lines = []
    if rule == "/tasks/batch" and isinstance(b, dict):
        ids = [i for i in b.get("ids") or [] if isinstance(i, int) and not isinstance(i, bool)] if isinstance(b.get("ids"), list) else []
        act = str(b.get("action") or "")
        lines.append(_say(BATCH_TITLE[act], str(len(ids))) if act in BATCH_TITLE else _say(N_("Runs {0} on {1} tasks at once"), act, str(len(ids))))
        names, unseen = [], 0
        for i in ids[:APVX_BATCH_CHECK]:
            s = _seen(x, "tasks", i)
            if s:
                if len(names) < APVX_BATCH_NAMES:
                    names.append(s[0] or f"#{i}")
            else:
                unseen += 1
        unseen += len(ids[APVX_BATCH_CHECK:])  # review: a task not checked counts like one the viewer cannot see
        if names:
            lines.append(_say(N_("Among them: {0}"), [p for i, n in enumerate(names) for p in ([["t", ", "]] if i else []) + [["v", apvx_clean(n, 60)]]]))
        if unseen:
            x.hidden = True
            lines.append([["t", trn("{0} task you cannot see", "{0} tasks you cannot see", unseen)]])
        ch = b.get("changes") if isinstance(b.get("changes"), dict) else {}
        if "list_id" in ch:
            x.warn.add("move")
            lines.append(_say(N_("Moves them to {0}"), _val(x, "list_id", ch["list_id"])))
        return lines + _fields(x, ch, skip=("list_id",))
    n = len(b) if isinstance(b, list) else len(next((v for v in (b or {}).values() if isinstance(v, list)), [])) if isinstance(b, dict) else 0
    lines.append(_say(N_("Many at once: {0} entries"), str(n)))
    return lines + _fields(x, b)


def _move(x, tid, cur, b):
    """Moving task tid (row cur): from its project to the body's list_id (another project: the warning)."""
    to = _id(b.get("list_id")) if isinstance(b, dict) else None
    task = _thing(x, "tasks", tid, label=False)
    if to and cur is not None and to != cur["list_id"]:
        x.warn.add("move")
        return [_say(N_("Moves task {0} from {1} to {2}"), task, _thing(x, "lists", cur["list_id"]), _thing(x, "lists", to))]
    return [_say(N_("Moves task {0} within {1}"), task, _thing(x, "lists", cur["list_id"]) if cur is not None else x.unseen())]


def _elsewhere(x, fam, rule, pr, bd):
    """2.1269.0 (#6450): a list_id in the body of a route on an object that names another project than the object's own
    (a copy, a further list, a table moved) is a move -- whatever the family. A collection's POST (POST /tasks) creates
    in that project: its own. An opened channel lets anybody of the workspace in: a share."""
    if rule == "/team/rooms/{}" and bd.get("open") not in (None, False, 0, "0", "false", ""):
        x.warn.add("share")
    if "list_id" not in bd or not pr or fam in ("move", "task", "batch"):
        return
    to = _id(bd.get("list_id"))
    if to is None:  # no project named (the route's default)
        return
    seg, rid = pr[0]
    if seg == "lists":
        own = _id(rid)
    else:
        s = _seen(x, seg, rid)
        row = s[1] if s else None
        own = row["list_id"] if row is not None and "list_id" in row.keys() else None
    if own != to:
        x.warn.add("move")


def apvx_describe(c, uid, step, decided=False):
    """The description of a bound step for person uid (module docstring), or None (no step)."""
    if not isinstance(step, dict) or not isinstance(step.get("path"), str) or not step.get("method"):
        return None
    x = _Ctx(c, uid, decided)
    m = step["method"]
    b = step.get("body") if isinstance(step.get("body"), (dict, list)) else {}
    bd = b if isinstance(b, dict) else {}
    rule, sub, pr = _rule_of(step)
    fam = _fam(m, rule) if rule else "general"
    lines = []
    if fam == "share":
        seg, rid = pr[-1]
        role = bd.get("role") or "edit"
        rw = _w(ROLE_WORD[role]) if role in ROLE_WORD else [["v", apvx_clean(role, 30)]]
        whom = _thing(x, "groups", rid) if seg == "groups" else _who(x, rid)
        lines.append(_say(N_("Gives {0} access to {1} as {2}"), whom, _thing(x, *pr[0]), rw))
    elif fam == "unshare":
        seg, rid = pr[-1]
        whom = _thing(x, "groups", rid) if seg == "groups" else _who(x, rid)
        lines.append(_say(N_("Takes away the access of {0} to {1}"), whom, _thing(x, *pr[0])))
    elif fam == "owner":
        lines.append(_say(N_("Hands {0} over to {1}"), _thing(x, *pr[0]), _who(x, bd.get("user_id"))))
    elif fam == "join":
        lines.append(_say(N_("Joins {0} and sees its content"), _thing(x, *pr[0])))
    elif fam == "invite":
        if pr:
            whom = _thing(x, "groups", bd["group_id"]) if bd.get("group_id") is not None else _who(x, bd.get("user_id"))
            lines.append(_say(N_("Adds {0} to {1}"), whom, _thing(x, *pr[0])))
        elif rule == "/team/dm":
            lines.append(_say(N_("Starts a direct conversation with {0}"), _who(x, bd.get("user_id"))))
        else:
            lines.append(_say(N_("Creates the conversation {0} with {1}"), str(bd.get("name") or ""), _val(x, "members", bd.get("members") or [])))
            lines += _fields(x, bd, skip=("name", "members"))
    elif fam == "announce":
        lines.append(_say(N_("Shows every person a notice: {0}"), str(bd.get("text") or bd.get("message") or bd.get("body") or "")))
        lines += _fields(x, bd, skip=("text", "message", "body"))
    elif fam == "export":
        tgt = _target(x, rule, pr)
        url = bd.get("url") or bd.get("hook_url")
        if url:
            lines.append(_say(N_("Sends data out of Kalmido to {0}"), str(url)))
        if rule == "/life/karakeep/sync":
            lines.append(_say(N_("Sends data out of Kalmido to {0}"), "Karakeep"))
        elif rule.startswith("/forms/"):
            lines.append(_say(N_("Changes {0}"), tgt))
        elif rule.endswith("/test"):
            lines.append(_say(N_("Sends a test message to {0}"), tgt))
        elif rule.endswith("/secret"):
            lines.append(_say(N_("Makes a new secret for {0}"), tgt))
        elif m == "DELETE":
            lines.append(_say(N_("Deletes {0}"), tgt))
        elif re.search(r"/(tokens|app-passwords)$", rule):
            lines.append(_say(N_("Makes a new access key for the account: {0}"), str(bd.get("name") or bd.get("label") or "")))
        else:
            lines.append(_say(N_("Sets up a connection out of Kalmido: {0}"), tgt))
        lines += _fields(x, bd, skip=("url", "hook_url"))
    elif fam == "move":
        tid = pr[0][1]
        cur = _row(c, "SELECT list_id FROM tasks WHERE id=?", tid) if _seen(x, "tasks", tid) else None
        if rule.endswith("/to-shopping"):
            x.warn.add("move")
            lines.append(_say(N_("Moves task {0} to the shopping list"), _thing(x, "tasks", tid, label=False)))
        elif rule.endswith("/links"):
            x.warn.add("move")
            lines.append(_say(N_("Also shows task {0} in {1}"), _thing(x, "tasks", tid, label=False), _val(x, "list_id", bd.get("list_id"))))
        else:
            lines += _move(x, tid, cur, bd)
        lines += _fields(x, bd, skip=("list_id",))
    elif fam == "batch":
        lines += _batch(x, b, rule)
    elif fam == "task":
        tid = pr[0][1]
        s = _seen(x, "tasks", tid)
        cur = s[1] if s else None
        mv = "list_id" in bd and cur is not None and _id(bd["list_id"]) != cur["list_id"]
        if mv:
            lines += _move(x, tid, cur, bd)
        lines.append(_say(N_("Changes {0}"), _thing(x, "tasks", tid)))
        lines += _fields(x, bd, old=cur, skip=("list_id",) if mv else ())
    elif fam == "delete":
        if rule.endswith("/waiting"):  # ends a state, nothing is deleted
            lines.append(_say(N_("Ends the waiting of {0}"), _target(x, rule, pr)))
        elif rule == "/time/timer":
            lines.append(_say(N_("Stops the running timer")))
        elif rule == "/trash":
            lines.append(_say(N_("Empties the trash")))
        else:
            lines.append(_say(N_("Deletes {0}"), _target(x, rule, pr) if pr else _w(N_("Folder"))))
        lines += _fields(x, b)
    elif fam in ("update", "text"):
        tgt = _target(x, rule, pr)
        s = _seen(x, *pr[-1]) if fam == "update" and pr and not x.hidden else None  # a text: the diff shows it
        lines.append(_say(N_("Changes {0}"), tgt))
        lines += _fields(x, b, old=s[1] if s else None)
    elif fam == "create":
        tail = [s for s in rule.strip("/").split("/") if s != "{}"]
        what = _w(APVX_LABEL.get(tail[-1]) or tail[-1].replace("-", " ")) if tail else []
        lines.append(_say(N_("Creates {0} in {1}"), what, _thing(x, *pr[-1])) if pr else _say(N_("Creates {0}"), what))
        lines += _fields(x, b)
    elif fam == "link":
        lines.append(_say(N_("Links {0} with another object") if m == "POST" else N_("Removes a link of {0}"), _target(x, rule, pr)))
        lines += _fields(x, b)
    elif fam == "action":
        verb = rule.rstrip("/").rsplit("/", 1)[-1]
        tgt = _target(x, rule.rsplit("/", 1)[0], pr) if pr else None
        if tgt is None:
            lines.append(_say(N_("Writes ({0}) to {1}"), m, sub))
        elif verb in APVX_ACT:
            lines.append(_say(APVX_ACT[verb], tgt))
        else:
            lines.append(_say(N_("Runs {0} on {1}"), verb.replace("-", " "), tgt))
        lines += _fields(x, b)
    elif fam == "meta":
        lines.append(_say(N_("The agent's own channel: {0}"), f"{m} {sub}"))
        lines += _fields(x, b)
    else:  # general: method, target and every value
        lines.append(_say(N_("Writes ({0}) to {1}"), m, _target(x, rule, pr) if rule else [["v", apvx_clean(sub, 200)]]))
        lines += _fields(x, b)
    if fam in APVX_WARN_OF:
        x.warn.add(APVX_WARN_OF[fam])
    _elsewhere(x, fam, rule, pr, bd)
    if x.hidden:
        x.warn.add("hidden")
    if len(lines) > APVX_LINES_MAX:
        lines = lines[:APVX_LINES_MAX - 1] + [[["t", trn("and {0} more line", "and {0} more lines", len(lines) - APVX_LINES_MAX + 1)]]]
    warns = [w for w in APVX_WARN_RANK if w in x.warn]
    return {"fam": fam, "lines": lines, "warn": warns[0] if warns else None, "warns": [[w, tr(APVX_WARN[w])] for w in warns],
            "hidden": x.hidden}


apvdiff.APVD_DESC[0] = apvx_describe  # the route of the cards' diff (domain layer) answers with it
CTL_DESC[0] = apvx_describe  # 2.1269.0 (#6619): the approval deadline takes a recommendation only for a step without a warning
