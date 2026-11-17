"""2.1358.0 (#6825): the one way a new row gets into tasks - task_insert().

Before, 26 files wrote their own `INSERT INTO tasks(...)` (mail, templates, agents' proposals, office reminders, family,
onboarding, imports ...), each with its own idea of the columns every task needs. Now they all call task_insert, which sets
at one place what every new task has:
 - the required columns: list_id, title, created_by (the creating account; None = no person, e.g. a mail, a Git issue, an
   error report), created_at / updated_at (ts, default now; a caller may pass its own created_at / updated_at, e.g. the
   date of an imported task),
 - the sort order: sort=TOP (default: above its siblings - the list's top-level tasks, or the subtasks of parent_id -, MIN-1),
   sort=END (below them, MAX+1) or a number (a caller that places a batch itself; the callers of before keep their own),
 - the ticket number (tasks.ticket_no) and the search stay in the database: the trigger TICKET_NO_TRIGGER (core/schema.py)
   numbers every new row of a project, the search reads the row itself (tasks/ftsearch.py) - nothing to do here, and no
   caller may set ticket_no.
Everything else (section, notes, due, repeat, assignee, url, fam, ...) the caller passes as columns, unchanged. The rights stay
with the caller and the core (core/objlight.py, kind 'task'); this only bundles the writing of the row.

The ratchet tools/check_task_insert.py (in tools/check_layout.py) keeps it that way: no new `INSERT INTO tasks(` outside this
file. Reading (SELECT * FROM tasks) is not affected.
"""
import re

from ..core.db import iso, now_utc
from ..core.pg import insert_id

TOP, END = "top", "end"
_COL = re.compile(r"[a-z_][a-z0-9_]*\Z")


def task_sort(c, list_id, where=TOP, parent_id=None):
    """The sort value of a new task of list list_id: TOP = above its siblings, END = below them (siblings = the top-level
    tasks, or the subtasks of parent_id)."""
    q = "COALESCE(MIN(sort),0)-1" if where == TOP else "COALESCE(MAX(sort),0)+1"
    if parent_id:
        return c.execute(f"SELECT {q} FROM tasks WHERE parent_id=?", (parent_id,)).fetchone()[0]
    return c.execute(f"SELECT {q} FROM tasks WHERE list_id=? AND parent_id IS NULL", (list_id,)).fetchone()[0]


def task_insert(c, uid, list_id, *, title, sort=TOP, ts=None, **fields):
    """Inserts one task and returns its id. uid = created_by (None: no account made it), sort = TOP / END / a number,
    ts = created_at and updated_at (default now; fields may set either of them on their own). Further columns as keywords."""
    if "ticket_no" in fields:
        raise ValueError("task_insert: ticket_no is set by the database trigger")
    if sort in (TOP, END):
        sort = task_sort(c, list_id, sort, fields.get("parent_id"))
    ts = ts or iso(now_utc())
    row = {"list_id": list_id, "title": title, "sort": sort, "created_by": uid, "created_at": ts, "updated_at": ts}
    row.update(fields)
    for k in row:
        if not _COL.match(k):
            raise ValueError(f"task_insert: invalid column {k!r}")
    return insert_id(c, f"INSERT INTO tasks({','.join(row)}) VALUES({','.join('?' * len(row))})", list(row.values()))
