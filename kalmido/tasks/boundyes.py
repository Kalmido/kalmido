"""(#7528): the writing of THE yes of a person bound to a text state: give it, take it off, the hook after a write
of the bound texts. The kinds, the rules and the reading stand in core/boundyes.py (docs/dev/kern.md "A person's yes bound to
a text")."""
from flask import g, has_request_context

from ..core.boundyes import BY_KINDS, by_sig, by_valid
from ..core.db import iso, now_utc
from ..core.pg import qi
from .validation import log_act

BY_COLS = {x for k in BY_KINDS.values() for x in k[:3] if x}  # the only names qi lets into the SQL below


def by_give(c, tid, kind, uid, seen=None):
    """The yes of uid to the text as it is now; logged. The caller checked by_decider and commits. seen = the text state the
    caller compared (by_sig): that one is written, so a write between the caller's read and this one ends the yes."""
    by, at, sig, _, _, act = BY_KINDS[kind]
    row = c.execute("SELECT * FROM tasks WHERE id=?", (tid,)).fetchone() if sig and seen is None else None
    now = iso(now_utc())
    cols, vals = (by, at, sig) if sig else (by, at), (uid, now, seen or by_sig(row, kind)) if sig else (uid, now)
    c.execute(f"UPDATE tasks SET {', '.join(qi(x, BY_COLS) + '=?' for x in cols)}, updated_at=? WHERE id=?", (*vals, now, tid))
    log_act(c, tid, act, {})


def by_drop(c, tid, kind, log=None):
    """Takes the yes off (no-op without one); log: the history kind to write, None = none (the caller logs its own step)."""
    by, at, sig = BY_KINDS[kind][:3]
    if not c.execute(f"SELECT 1 FROM tasks WHERE id=? AND {qi(at, BY_COLS)} IS NOT NULL", (tid,)).fetchone():
        return False
    cols = (by, at, sig) if sig else (by, at)
    c.execute(f"UPDATE tasks SET {', '.join(qi(x, BY_COLS) + '=?' for x in cols)} WHERE id=?", (*([None] * len(cols)), tid))
    if log:
        log_act(c, tid, log, {})
    return True


def by_person():
    """(#7528, reader F4): the write comes from the person in the app (session or proxy), not from their token: only such a
    change carries a yes along -- a token cannot give the yes, so it cannot move it onto a new text either."""
    return not has_request_context() or g.get("auth_via") in (None, "session", "proxy")


def by_text_written(c, tid, old, new, hand, carry=False):
    """After a write of the bound texts (tasks/validation.py log_changes; old / new = the rows): per kind with its own sig, a yes
    that was valid before stays only when carrying it is allowed explicitly -- carry = the person's direct edit
    (tasks/lifecycle.py apply_update carry_yes: PATCH /api/tasks/<id>, the multi-select edit), by the confirmer (hand) in
    session or proxy; then it is bound to the new text. Every other write ends it (history line "<kind>_lapsed"): applied
    agent proposals, merges, tidy, list rules, undo / redo, imports, tokens -- one rule here, no fix per caller."""
    for kind, (by, at, sig, texts, own_keeps, act) in BY_KINDS.items():
        if not sig or sig not in new.keys() or not new[at] or all((old[k] or "") == (new[k] or "") for k in texts):
            continue
        if carry and own_keeps and hand and new[by] == hand and by_person() and by_valid(old, kind):
            c.execute(f"UPDATE tasks SET {qi(sig, BY_COLS)}=? WHERE id=?", (by_sig(new, kind), tid))
        else:
            by_drop(c, tid, kind, log=act + "_lapsed")
