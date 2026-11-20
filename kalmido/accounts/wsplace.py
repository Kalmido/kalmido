"""(#7309): THE place for "is module X on for person P in a workspace" and "where does a new X of P go".

Two questions, one answer for the server and the browser (docs/dev/kern.md "Where does New go"):
  - wsp_spaces(c, uid, mod, write=False): the workspaces ("private", "org:<id>") in which module mod is on for uid --
    Private first, then the organisations in the order of user_orgs. Below the main switch (setting "features") come the
    organisation's switched-off areas (orgs.areas_off), the card's cap (module cards), my own ws_areas_off / ws_mods_off
    (modcards.mod_ws_on, the single question); write=True also needs a role that adds content (member / admin; never a
    guest, read-only or accounting person) and, in a support session, an organisation with support access.
  - wsp_new(c, uid, mod, named=None): the workspace of something new (an organisation's id, None = Private). The workspace
    the request names wins while mod is on and writable there; nothing named: the workspace on top (setting "workspace")
    while mod is on and writable there, else exactly ONE such workspace, else a 400 with code space_needed and the list
    to choose from -- never where mod is off, never silently Private, never "the only organisation" (#7385). An organisation I am not in = 403. Agents keep their own workspace.
/api/state carries wsp / wsp_w (wsp_all) so the browser's mod_spaces reads the same lists (areas.js wsp_list).
A person without an organisation (or an instance without workspaces) has Private only; nothing asks there (P4)."""
import json
import re

from flask import g, has_request_context, jsonify

from ..core.access import feat_has
from ..core.config import app
from ..core.db import usettings
from ..core.errors import BadInput, Denied
from ..core.i18n import N_, tr
from .modcards import mc_cap, mc_mods
from .orgroles import FULL_WRITE, org_roles_of
from .orgs import _org_name, agent_org, has_workspaces, user_orgs
from .supportgrant import sga_org_foreign
from .wsareas import wsa_org_off

# the area (wsareas.WSA_AREAS) a module belongs to -- the server's copy of areas.js MG_AREAS / wsa_areaOfMod; a module
# without an entry has no area (its own switch and the card only)
WSP_AREA = {"office": "office", "contacts": "office", "clients": "office", "time": "time", "pomo": "time",
            "review": "review", "stats": "review", "contracts": "life", "home": "life", "care": "life", "health": "life",
            "travel": "life", "family": "life", "budget": "life", "reading": "reading", "feeds": "reading",
            "files": "ablage", "docs": "ablage", "wiki": "wiki", "sheets": "sheets"}
# other names callers use for a module
WSP_ALIAS = {"calendar": "events", "ablage": "files"}
WSP_ASK = N_("Which workspace? Select where the new entry goes.")
WSP_NONE = N_("This module is switched off for you in every workspace you may add to.")
WSP_KEYS = ("ws_areas_off", "ws_mods_off", "features")  # the switches PATCH /api/settings answers with fresh lists
# (#7309 F8): what keeps running in my own personal office after "Also private" goes off: fn(c, uid) -> [{kind, count}]
# (office/recurring.py the invoice series, office/banknorc.py / cardnorc.py the reminders); registered by those modules
WSP_STILL = []
_WS_RE = re.compile(r"org:([1-9][0-9]{0,11})")


class SpaceNeeded(BadInput):
    """(#7309): a new entry needs its workspace named -- 400, code space_needed, spaces = [{ws, name}] to choose from.
    (#7385): API v1 answers {"error": {"code": "space_needed", "message", "spaces"}} (api/common.py v1_view)."""
    v1_name = "space_needed"

    def __init__(self, spaces):
        super().__init__(tr(WSP_ASK if spaces else WSP_NONE))
        self.spaces = spaces
        self.v1_extra = {"spaces": spaces}


@app.errorhandler(SpaceNeeded)
def _space_needed(e):
    # "workspaces" [{org_id, name}]: the form #7298 answered with (code ws_choose) for the clients, kept for API callers
    return jsonify(error=str(e), code="space_needed", spaces=e.spaces,
                   workspaces=[{"org_id": None if x["ws"] == "private" else int(x["ws"][4:]), "name": x["name"]} for x in e.spaces]), 400


def wsp_mod(mod):
    return WSP_ALIAS.get(mod, mod)


def _ws(oid):
    return "org:%d" % oid if oid else "private"


def _is_agent(c, uid):
    u = getattr(g, "user", None) if has_request_context() else None
    if u is not None and u["id"] == uid:
        return (u["kind"] or "user") == "agent"
    r = c.execute("SELECT kind FROM users WHERE id=?", (uid,)).fetchone()
    return bool(r) and (r["kind"] or "user") == "agent"


def _own(st, name):
    try:
        o = json.loads(st.get(name) or "{}")
    except (ValueError, TypeError):
        return {}
    return o if isinstance(o, dict) else {}


class _Ctx:
    """What one person's answers need, read once (settings, organisations, roles)."""

    def __init__(self, c, uid):
        self.c, self.uid = c, uid
        self.st = usettings(c, uid)
        self.agent = _is_agent(c, uid)
        self.alone = not has_workspaces(c)
        self.orgs = [] if self.alone or self.agent else list(user_orgs(c, uid))
        self.aoff, self.moff = _own(self.st, "ws_areas_off"), _own(self.st, "ws_mods_off")
        self._roles = None

    def roles(self):
        if self._roles is None:
            self._roles = org_roles_of(self.c, self.uid)
        return self._roles

    def main_on(self, mod):
        # the main switch (and an agent's data lock); a module outside the card list has none here
        return mod not in mc_mods() or feat_has(self.c, self.uid, mod, self.st)

    def on(self, mod, oid):
        """Below the main switch: on in workspace oid (None = Private) for me? (modcards.mod_ws_on, read from one settings dict)"""
        key, area = _ws(oid), WSP_AREA.get(mod)
        xs = self.aoff.get(key)
        if area and (isinstance(xs, list) and area in xs or oid and area in wsa_org_off(self.c, oid)):
            return False
        xs = self.moff.get(key)
        if isinstance(xs, list) and mod in xs:
            return False
        cap = mc_cap(self.c, self.uid, oid) if oid else None
        return cap is None or mod not in mc_mods() or mod in cap

    def writes(self, oid):
        return not oid or self.roles().get(oid) in FULL_WRITE and not sga_org_foreign(self.c, oid)

    def spaces(self, mod, write=False):
        mod = wsp_mod(mod)
        if not self.main_on(mod):
            return []
        if self.agent:
            a = agent_org(self.c, self.uid) if not self.alone else None
            return [_ws(a)]
        if self.alone or not self.orgs:
            return ["private"]  # alone (P4): Private is the main switches
        return [_ws(o) for o in [None, *self.orgs] if self.on(mod, o) and (not write or self.writes(o))]


def _ctx(c, uid):
    if not has_request_context():
        return _Ctx(c, uid)
    k = g.setdefault("wsp_ctx", {})
    if uid not in k:
        k[uid] = _Ctx(c, uid)
    return k[uid]


def wsp_drop():
    """Forget the request's answers after a switch changed (PATCH /api/settings answers with the new lists)."""
    if has_request_context():
        g.pop("wsp_ctx", None)


def wsp_spaces(c, uid, mod, write=False):
    """The workspaces in which module mod is on for uid (write: and uid may add there), Private first. See the module text."""
    return _ctx(c, uid).spaces(mod, write)


def wsp_on(c, uid, mod, oid, write=False):
    """Is module mod on for uid in workspace oid (None = Private)? (write: and may uid add there?)"""
    return _ws(oid) in wsp_spaces(c, uid, mod, write)


def wsp_private_off(c, uid, mod):
    """Is module mod switched off below the main switch in my Private while I have organisations (ws_areas_off /
    ws_mods_off "private")? Alone, Private is the main switches (never off here). modcards.mc_private_office_off asks it."""
    x = _ctx(c, uid)
    return bool(x.orgs) and not x.on(wsp_mod(mod), None)


def _priv_office_off(st):
    return any("office" in (x if isinstance(x := _own(st, k).get("private"), list) else []) for k in ("ws_areas_off", "ws_mods_off"))


def wsp_still_running(c, uid, vals):
    """(#7309 F8): the switch "Also private" of the office goes off with this PATCH (vals = the new values, the stored ones
    still old): [{kind, count}] of what keeps running there (series, reminders), [] otherwise. Nothing is stopped: the
    answer only names it (Settings > Modules shows it; a bell entry says it once)."""
    old = usettings(c, uid)
    if _priv_office_off(old) or not _priv_office_off({**old, **vals}) or not user_orgs(c, uid):
        return []
    out = []
    for fn in WSP_STILL:
        out += [x for x in fn(c, uid) if x.get("count")]
    return out


def wsp_all(c, uid):
    """/api/state and the answer of PATCH /api/settings: ({mod: [ws]}, {mod: [ws]}) -- on / on and writable, every module."""
    x = _ctx(c, uid)
    return {m: x.spaces(m) for m in mc_mods()}, {m: x.spaces(m, True) for m in mc_mods()}


def wsp_named(b):
    """The workspace a request body (dict) / form names: "space" ("private" | "org:<id>") or "org_id" (null / 0 = Private);
    None when it names none."""
    if not isinstance(b, dict) and not hasattr(b, "get"):
        return None
    sp = b.get("space")
    if sp not in (None, ""):
        return sp
    if "org_id" in b:
        v = b.get("org_id")
        return "private" if v in (None, "", 0, "0", "private") else v
    return None


def wsp_oid(v):
    """A named workspace ("private" | "org:<id>" | an id) -> an organisation's id or None (Private); 400 when unreadable."""
    if v in ("private", 0, "0") or v is None:
        return None
    if isinstance(v, bool):
        raise BadInput(tr("Invalid value: {0}", "space"))
    if isinstance(v, int):
        return v if v > 0 else None
    if isinstance(v, str):
        m = _WS_RE.fullmatch(v.strip())
        if m:
            return int(m.group(1))
        if v.strip().isdigit():
            return int(v.strip()) or None
    raise BadInput(tr("Invalid value: {0}", "space"))


def _need(c, uid, mod):
    w = wsp_spaces(c, uid, mod, True)
    raise SpaceNeeded([{"ws": s, "name": _org_name(c, None if s == "private" else int(s[4:]))} for s in w])


def wsp_new(c, uid, mod, named=None):
    """Where a new entry of module mod goes: an organisation's id or None (Private). named ("private" | "org:<id>" | an
    organisation's id; None = nothing named) wins while mod is on and writable there; an organisation uid is not in = 403;
    a member's workspace where mod is off / not writable = 400 space_needed. Nothing named: the only workspace of
    wsp_spaces(write=True) (the setting on top first), else 400 space_needed with the choice (#7385: no longer the only
    organisation I may add to). An agent: the named one or its own workspace."""
    x = _ctx(c, uid)
    oid = wsp_oid(named) if named is not None else None
    if x.alone:
        return None
    if x.agent:
        if named is None:
            return agent_org(c, uid)
        if oid and oid not in user_orgs(c, uid):
            raise Denied(403)
        return oid
    if oid and oid not in x.orgs:
        raise Denied(403)
    if not x.orgs:
        return None  # alone in no organisation (P4): Private, as always
    w = x.spaces(mod, True)
    if named is not None:
        if _ws(oid) in w:
            return oid
        _need(c, uid, mod)
    ws = str(x.st.get("workspace") or "")
    if ws in w:  # the workspace on top (setting) as the default of a call without a name, while mod is on and writable there
        return wsp_oid(ws)
    if len(w) == 1:
        return wsp_oid(w[0])
    _need(c, uid, mod)
