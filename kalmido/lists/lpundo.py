"""2.809.0 (#5476): undo across devices -- a project's settings (PATCH /api/lists/<id>) in the core's step groups
(core/undoareas.py, the pattern of events/evundo.py).

A project's row (table lists) is the tracked kind "listset" (core/writes.py obj_track; the kind "list" of lists/lmcore.py
stays the one of the shares and the trash): a change of its plain settings records a snap step of the person under the
project's lock (obj-list-<id>, lists.py lv_check), labelled with its name. Plain = a column of the row itself without side
effects elsewhere (LPU_COLS: name, colour, view, archive, sort, grouping, columns, sums, key figures, properties, ticket
templates, hourly rate, hours per day ...). A save that also changes something with side effects (folder, workspace,
project type, agents, client, family / Home & life, time tracking, ticket key, visibility) records no copy step here: since
2.1074.0 (#5493) it is a diff step of lists/lpside.py (kind "listside"), taken back through the project's own write path.
Only the plain columns go back (undo_keep = every other column), and only they and the lock's generation count for "changed
since" (undo_nofp): a new sidebar order or a description written meanwhile does not block the undo of a rename.
Taking back (core/undoweb.py): the person needs the role of today that may change those columns -- owner, or a project admin
when the step goes back only in columns an admin may change (name, colour, archive, completed at the bottom, mail for guests,
sort, grouping, columns, sums, key figures, properties); an agent records nothing (obj_undo_pre).

Interface:
  lpu_pre(c, uid, lid, b, role)   before the PATCH writes (after lv_check): a step when b holds only plain settings
  lpu_post(c) -> group id | None  right before its commit (a save of the same values leaves no step)

2.1184.0 (#6137): a step says what changed -- "<project>: Colour", "<project>: Renamed to <new name>", several fields
"<project>: Colour, Sorting" (LPU_NAMES; a field without a readable name keeps "Settings of <project>"). The project's view
(list / board / calendar ...) is a display switch, no step: a save of the view alone records nothing, a view saved along
with other settings is not part of their step (LPU_DISPLAY: not in the copy's columns, so an undo neither puts it back nor
counts a view switched since as "changed in the meantime")."""
from ..core.access import _list_role, list_out
from ..core.errors import Denied
from ..core.objhooks import GONE
from ..core.undoareas import ua_done, ua_plain, ua_pre
from ..core.undodiff import undo_quiet
from ..core.undoweb import undo_need_reg
from ..core.writes import obj_track
from ..core.errors import BadInput
from ..core.i18n import N_, stored_join
from .lists import LIST_FIELDS, clean_list_value

LPU_KIND = "listset"
LPU_LABEL = N_("Settings of {0}")  # the keys exist (static/js/dialogs.js)
LPU_ARCH = N_("Archived {0}")
LPU_UNARCH = N_("Restored {0} from the archive")
# body key -> column of the row; only these make a step (lists.py list_update writes them on the row alone)
LPU_KEYS = {"name": "name", "color": "color", "view": "view", "kind": "kind", "dep_shift": "dep_shift", "rate": "rate",
            "archived": "archived", "tickets": "tickets", "nag": "nag", "day_hours": "day_hours", "checklist": "checklist",
            "done_at_bottom": "checklist", "sort_mode": "sort_mode", "done_in_section": "done_in_section",
            "group_field": "group_field", "columns": "col_cfg", "col_sums": "tb_sums", "kpis": "fx_kpis", "props": "props",
            "ticket_tpl": "ticket_tpl", "tap_done": "tap_done", "points_on": "points_on",
            "irreversible_needs_yes": "irreversible_needs_yes", "two_eyes": "two_eyes", "mail_guests": "mail_guests",
            "def_ttype": "def_ttype", "ttypes": "ttypes"}
LPU_META = ("_prev", "expect_updated_at", "folder_adopt")
LPU_DISPLAY = ("view",)  # 2.1184.0 (#6137): display switches -- never a step of their own, never part of one
LPU_COLS = frozenset(v for k, v in LPU_KEYS.items() if k not in LPU_DISPLAY) | {"archived_at"}
LPU_RENAMED = N_("Renamed to {0}")  # the key exists
LPU_FIELD = N_("{0}: {1}")  # the key exists
LPU_Q = N_("“{0}”")  # the key exists (static/js/undo.js qn: the project's name in quotes, as the app's own entry)
# 2.1184.0 (#6137): the readable name of a changed setting in the step's label (the keys exist, the settings dialog's words)
LPU_NAMES = {"color": N_("Colour"), "kind": N_("Type"), "dep_shift": N_("Move dependent tasks along"), "rate": N_("Hourly rate"),
             "day_hours": N_("Hours per day"), "checklist": N_("Show completed at the bottom"),
             "sort_mode": N_("Sorting"), "group_field": N_("Grouping"),
             "columns": N_("Columns"), "kpis": N_("Key figures"), "props": N_("Properties"), "points_on": N_("Story points"),
             "irreversible_needs_yes": N_("One-way steps"), "two_eyes": N_("Approvals"), "tap_done": N_("Tap to complete"),
             "nag": N_("Reminders"), "archived": N_("Archived"),
             # the settings with side effects (lists/lpside.py)
             "folder": N_("Folder"), "time_tracking": N_("Time tracking"), "client_id": N_("Client")}
# what a project admin may change of them (list_update: adm, MANAGE_ROLES); the rest is the owner's
LPU_ADMIN = frozenset({"name", "color", "archived", "archived_at", "checklist", "mail_guests", "sort_mode", "group_field",
                       "done_in_section", "tap_done", "props", "col_cfg", "tb_sums", "fx_kpis"})
LPU_E2E = frozenset({"e2e", "e2e_gen", "e2e_rotate", "e2e_reenc"})  # a new key since: the copy's sealed name is old (409)


class AllBut(frozenset):
    """Every column name except the ones given -- for undo_keep / undo_nofp, which are only asked with `in` (core/writes.py
    _write_back, _fp): the row of a project has some 80 columns and gets new ones, the plain settings are the short list."""
    def __contains__(self, k):
        return not frozenset.__contains__(self, k)


def lpu_label(r):
    return LPU_LABEL, [ua_plain(r.get("name"), r.get("id"))]


# 2.905.0 (#5255): undo_free kind - the project's type (lists.kind) is one of the core's fixed columns (UNDO_FIXED, the
# object kind elsewhere): without it the step was listed and "undone", but the type stayed (the app's arrow goes through
# the server since stage 7)
obj_track(LPU_KIND, "lists", area="tasks", undo_keep={"lists": AllBut(LPU_COLS)},
          undo_nofp={"lists": AllBut(LPU_COLS | LPU_E2E)}, undo_label=lpu_label, undo_free=("kind",))
GONE[LPU_KIND] = "lists"  # an account's deletion takes its history / undo rows of the projects that went (core/objhooks.py)


def _keys(b):
    """The settings of the PATCH body b that may make a step (2.1184.0, #6137: not the display switches)."""
    return [k for k in b if k not in LPU_META and k not in LPU_DISPLAY]


def lpu_plain(b):
    """Does the PATCH body b change only plain settings (and at least one that is not a display switch)?"""
    keys = [k for k in b if k not in LPU_META]
    if not _keys(b):
        return False
    return bool(keys) and all(k in LPU_KEYS for k in keys)


def _same(r, b):
    """Does b only repeat the row's values (its plain columns, cleaned as list_update cleans them)? Then no step: opening a
    group would end the person's way forward (redo) for nothing. Columns with their own cleaning (columns, sums, key figures,
    properties, templates ...) count as a change."""
    return not _changed(r, b)


def lpu_pre(c, uid, lid, b, role):
    if undo_quiet() or role not in ("owner", "admin") or not lpu_plain(b):  # 2.1074.0 (#5493): not while a step goes back (lpside.py runs list_apply)
        return
    r = c.execute("SELECT * FROM lists WHERE id=?", (int(lid),)).fetchone()
    r = r and list_out(r)  # 2.1061.0 (#5867, stage 3): archived from the state marker, not the old column
    if r is None or _same(r, b):
        return
    if set(_keys(b)) == {"archived"} and bool(b["archived"]) != bool(r["archived"]):
        ua_pre(c, uid, LPU_KIND, lid, LPU_ARCH if b["archived"] else LPU_UNARCH, ua_plain(r["name"], lid))
        return
    ua_pre(c, uid, LPU_KIND, lid, *lpu_what(r, b))


def _changed(r, b):
    """The keys of b whose value differs from the row's (cleaned as list_update cleans them; one with its own cleaning counts)."""
    out = []
    for k in _keys(b):
        col = LPU_KEYS[k]
        if col in LIST_FIELDS:
            try:
                v = clean_list_value(col, b[k])
            except BadInput:
                out.append(k)  # the route refuses it
                continue
            if (v if v not in ("", None) else None) == (r[col] if r[col] not in ("", None) else None):
                continue
        out.append(k)
    return out


def lpu_what(r, b):
    """2.1184.0 (#6137): the step's label -- (key, *values): what of project r the body b changes."""
    ch = ["checklist" if k == "done_at_bottom" else k for k in _changed(r, b)]
    return lpu_named(r["name"], r["id"], ch, b.get("name")) or (LPU_LABEL, ua_plain(r["name"], r["id"]))


def lpu_named(name, lid, keys, new_name=None):
    """2.1184.0 (#6137): "“<project>”: Colour, Sorting" for the changed settings keys (also lists/lpside.py); None when one
    of them has no readable name (the caller's general label then, never a raw key) or nothing is left to name."""
    parts = []
    for k in dict.fromkeys(k for k in keys if k not in LPU_DISPLAY):
        if k == "name":
            new = ua_plain(new_name)
            parts.append([N_("Name")] if new == "#" else [LPU_RENAMED, new])  # a sealed new name (e2e): never in a label
        elif k in LPU_NAMES:
            parts.append([LPU_NAMES[k]])
        else:
            return None
    if not parts:
        return None
    return LPU_FIELD, [LPU_Q, ua_plain(name, lid)], parts[0] if len(parts) == 1 else list(stored_join(parts))


def lpu_post(c):
    return ua_done(c)


def lpu_need(c, uid, rid, oid):
    """Who may take a settings step back now: the owner, a project admin only for the columns an admin may change."""
    role = _list_role(c, int(rid), int(uid))
    if not role:
        raise Denied(404)
    if role not in ("owner", "admin"):
        raise Denied(403)
    if role == "owner":
        return {"lock": f"obj-list-{int(rid)}"}
    was = c.execute("SELECT * FROM lists WHERE id=?", (int(rid),)).fetchone()

    def fix(c):
        now = c.execute("SELECT * FROM lists WHERE id=?", (int(rid),)).fetchone()
        if any(now[k] != was[k] for k in LPU_COLS - LPU_ADMIN if k in now.keys()):
            raise Denied(403)  # the savepoint of the part takes the write back again
    return {"fix": fix, "lock": f"obj-list-{int(rid)}"}


undo_need_reg(LPU_KIND, lpu_need)
