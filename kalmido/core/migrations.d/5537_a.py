"""2.1029.0 (#5537, stage 1): a project (lists) carries ONE state marker -- lists.state = 'live' | 'archived' | 'trash' -- next to
the old columns archived / deleted_at. Reads ask for the state through core/access.py list_state_sql() (otr_live too); the
columns archived / archived_at / deleted_at stay the ones the write paths set in this stage.

The database keeps the marker equal to them: the trigger kalmido_list_state sets it before every INSERT and every UPDATE
(no column list: SCHEMA runs before the MIGRATIONS step that adds state, and Postgres checks an UPDATE OF list when it creates
the trigger -- review of 2.1029; the function reads the row as JSON, so a database whose lists still lack state / deleted_at
during its first start breaks nothing): 'trash' while deleted_at is set, else
'archived' while archived <> 0, else 'live'. So no write path changes, a copy of all columns (merges, account import, undo of a row) can never write a wrong marker, and the rows
of before get theirs at the start (core/db.py, the reconcile next to migr_liststate5537 runs at every start: after a restore
of a dump, or a rollback that dropped the trigger, a row never stays with a wrong marker).

Not a column Postgres computes (GENERATED ALWAYS AS): such a column refuses every INSERT / UPDATE that names it, and the generic
copies of rows (core/merges.py, core/undoareas.py, admin/acctimport.py) name every column of the table.

Additive only: a new column with a DEFAULT, a new function and trigger. An older version ignores the column; its writes still
get the right marker from the trigger, so the way forward again needs nothing.

2.1054.0 (#5794, stage 2): the write paths of the archive set the marker (core/access.py list_set_archived), and the trigger
works both ways: an UPDATE that changes state to 'live' / 'archived' (an INSERT that names 'archived') decides the archive, and
the trigger writes the old column archived from it -- the way back for a version before that may still run on the database
and reads archived. A write that leaves state as it was (a version before, the undo of the settings, which writes archived
back and never the marker -- lists/lmcore.py undo_skip) still sets the marker from archived, as in stage 1. 'trash' stays
derived from deleted_at: that is the trash column of the core for every kind (obj_trash / obj_restore / obj_purge,
live_sql); a write of state='trash' decides nothing. Still additive: CREATE OR REPLACE of the same function, the version
before puts its own back on its start and finds archived written by this one.

2.1118.0 (#5952): lists.archived is BOOLEAN (core/colbool.py); the function reads 'true' / 'false' from the JSON of the row
as well and writes the column in its own type.

2.1231.0 (#5880, stage 3b, one-way): the old column archived is gone (migrations.d/5880_a.py drops it after the start's
move, core/liststate.py lst_move). The trigger is one-sided again, as in stage 1, but from archived_at: 'trash' while
deleted_at is set, else 'archived' while archived_at is set, else 'live' -- a write that changes state to 'live' /
'archived' on purpose (core/access.py list_set_archived; an INSERT that names 'archived') decides, and the trigger keeps
archived_at with it (set when it is missing, cleared on 'live'), so marker and archived_at never part. A project in the
trash keeps its archive in archived_at (core/access.py list_archived_sql). A write that leaves state as it was (the undo of
the settings writes archived_at back, never the marker -- lists/lmcore.py undo_skip) sets the marker from archived_at."""
SCHEMA = """
CREATE OR REPLACE FUNCTION kalmido_list_state() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
  j JSONB := to_jsonb(NEW);
  a BOOLEAN := COALESCE(j->>'archived_at', '') <> '';  -- 2.1231.0 (#5880): the archive is archived_at (the column archived is gone)
BEGIN
  IF NOT j ? 'state' THEN RETURN NEW; END IF;  -- an older database during its first start (a step before the column, e.g. tap_done)
  IF NEW.state IN ('live', 'archived') THEN  -- 2.1054.0 (#5794): the marker written on purpose decides the archive
    IF TG_OP = 'INSERT' THEN
      IF NEW.state = 'archived' THEN a := TRUE; END IF;
    ELSIF NEW.state IS DISTINCT FROM OLD.state THEN
      a := NEW.state = 'archived';
    END IF;
  END IF;
  IF j ? 'archived_at' THEN  -- 2.1231.0 (#5880): archived_at goes with the marker (when it went into the archive, kept while there)
    IF NOT a THEN NEW.archived_at := NULL; ELSIF NEW.archived_at IS NULL THEN NEW.archived_at := CURRENT_TIMESTAMP; END IF;
  END IF;
  NEW.state := CASE WHEN COALESCE(j->>'deleted_at', '') <> '' THEN 'trash' WHEN a THEN 'archived' ELSE 'live' END;
  RETURN NEW;
END $$;
CREATE OR REPLACE TRIGGER kalmido_list_state BEFORE INSERT OR UPDATE ON lists FOR EACH ROW EXECUTE FUNCTION kalmido_list_state();
"""
MIGRATIONS = [
    ("lists", "state", "ALTER TABLE lists ADD COLUMN IF NOT EXISTS state TEXT NOT NULL DEFAULT 'live'"),
]
# the archive view and the trash read the few rows that are not live
AFTER = [
    "CREATE INDEX IF NOT EXISTS ix5537_lists_state ON lists(state) WHERE state <> 'live'",
]
