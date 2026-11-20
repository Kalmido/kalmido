"""(#7528): the rules and the reading of THE yes of a person bound to a text state (docs/dev/kern.md "A person's yes
bound to a text"); the writing (give, drop, the hook after a text change) is tasks/boundyes.py. Core layer: the serializers
and the API read the yes with by_view, the routes ask by_decider. One block for every "a decider said yes to exactly this
text" of a task.

Two kinds use it:
- "irreversible" (2.392.0 C, #3370, tasks/oneway.py): the yes to a one-way step, bound to its reason. A new reason or a new mark
  takes it back, whoever writes it (own_keeps False). Columns tasks.irreversible_yes_by / _at (the gates read _at in SQL).
- "confirm" (#7528): "Confirm as an order" -- a decider makes a text someone else wrote into an order. Bound to title +
  description: a change by anyone but the confirmer takes it back (with a line in the history), the confirmer's own change
  keeps it (bound to the new text). Columns tasks.confirmed_by / _at / _sig; _sig holds a hash per text, so a write on a path
  that never reaches the hook (by_text_written) still ends the yes: by_valid compares with the text as it is now.

Who may say yes (by_decider): a person (never an agent, an agent's token, a child account or a support session in the person's
account, never by an access token or a public link) who sees the whole task and is project owner, project admin or an
instance admin. Only the web routes of the person write a yes (agents/taskdec.py); the API shows it read-only."""
import hashlib

from flask import g, has_request_context

from .access import MANAGE_ROLES, list_role, task_visible

# kind -> (by column, at column, sig column or None, the bound texts, the confirmer's own change keeps the yes, history kind)
BY_KINDS = {
    "irreversible": ("irreversible_yes_by", "irreversible_yes_at", None, ("irreversible_reason",), False, "irreversible_yes"),
    "confirm": ("confirmed_by", "confirmed_at", "confirmed_sig", ("title", "content"), True, "confirmed"),
}


def _h(v):
    return hashlib.sha256((v or "").encode()).hexdigest()[:16]


def by_sig(row, kind):
    """The text state of row for kind: one hash per bound text, joined with '|'."""
    return "|".join(_h(row[k]) for k in BY_KINDS[kind][3])


def by_valid(row, kind):
    """True when row carries a yes of kind that still belongs to its text."""
    by, at, sig = BY_KINDS[kind][:3]
    if by not in row.keys() or not row[at]:
        return False
    return sig is None or (row[sig] or "") == by_sig(row, kind)


def by_view(row, kind):
    """{by, at} of a valid yes, else None (the API's field, the panel's line)."""
    by, at = BY_KINDS[kind][:2]
    return {"by": row[by], "at": row[at]} if by_valid(row, kind) else None


def by_decider(c, t, user):
    """May user say yes / no to task row t? (module docstring)"""
    try:
        if not user or (user["kind"] or "user") != "user" or user["kid"] or user["disabled"]:
            return False
    except (KeyError, IndexError):
        return False
    if has_request_context() and (g.get("auth_via") not in (None, "session", "proxy") or g.get("acx_sup_uid") == user["id"]):
        return False  # a token, a public link, a webhook, CalDAV, a support session: never a decider's yes
    if not task_visible(c, t["id"], user["id"], full=True):
        return False
    return list_role(c, t["list_id"], user["id"]) in MANAGE_ROLES or bool(user["is_admin"])


