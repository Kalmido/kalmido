"""2.1231.0 (#5880, stage 3b of the projects' state marker, one-way, decided 12.11.2026 / freed 14.11.2026): the old column
archived of lists goes. Since 2.1061.0 (#5867) every read of "the project is archived" asks the marker lists.state
(core/access.py list_archived_sql / list_archived / list_out), since 2.1054.0 (#5794) every write sets it
(list_set_archived); the column only fed the way back to a version before. The fragment migrations.d/5880_a.py drops it in
its AFTER; this move runs before that (core/db.py init_db, after the areas' MOVE, before the fragments' AFTER) at every
start while the column is there (a database of before, a dump of before played in):

- archived_at is the archive from now on (the trigger kalmido_list_state, migrations.d/5537_a.py, reads it): a project
  archived before 1.6.1 has archived = true and no archived_at -- it gets the moment of this move (when it went into the
  archive is not known; not created_at, a clean-up that counts from archived_at would take it at once); one not archived
  whose archived_at stayed (a restore before 2.1054.0 kept it) loses it. The old column decides, it was kept equal to the
  marker by the trigger of 2.1054.0, in the trash too.
- the marker is set from it once more (the reconcile of 2.1029.0, for a dump from before the marker: its rows came in
  with state 'live').
- the database's back limit rises to the minor of this image (core/kernretire.py kern_retire_floor): an older image would
  read and write the dropped column.

Nothing to do once the column is gone (one catalog read)."""
from .kernretire import kern_retire_floor
from .pg import table_columns, table_exists

LST_FLOOR_HOW = ("the old column archived of lists went (#5880): a project's archive is its state marker and archived_at - an "
                 "older version would read and write the dropped column; go back only with a backup from before")


def lst_move(c):
    """Before the fragment 5880_a drops the column archived of lists (module text). Returns the number of rows set, None
    when the column is gone already."""
    cols = table_columns(c, "lists") if table_exists(c, "lists") else set()
    if "archived" not in cols:
        return None
    if "archived_at" not in cols or "state" not in cols:  # a database of before 1.6.1 / 2.1029 that missed a step: the start stops
        raise RuntimeError("migrations: 5880: lists.archived_at / lists.state missing before the old column goes")
    # migr_liststate5537: the old column names on purpose here (tools/check_list_state.py)
    n = c.execute("UPDATE lists SET archived_at=CURRENT_TIMESTAMP WHERE archived AND archived_at IS NULL").rowcount
    n += c.execute("UPDATE lists SET archived_at=NULL WHERE NOT archived AND archived_at IS NOT NULL").rowcount
    n += c.execute("UPDATE lists SET state=CASE WHEN deleted_at IS NOT NULL THEN 'trash' WHEN archived THEN 'archived' ELSE 'live' END"
                   " WHERE state IS DISTINCT FROM (CASE WHEN deleted_at IS NOT NULL THEN 'trash' WHEN archived THEN 'archived' ELSE 'live' END)").rowcount
    kern_retire_floor(c, how=LST_FLOOR_HOW)
    if n:
        print(f"migrations: 5880: {n} project row(s) set from the old column archived before it goes", flush=True)
    return n
