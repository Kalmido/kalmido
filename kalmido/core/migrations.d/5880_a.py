"""2.1231.0 (#5880, stage 3b of the projects' state marker #5537 / #5794 / #5867, one-way): the old column lists.archived goes.

Every read of "the project is archived" asks the marker lists.state since 2.1061.0 (core/access.py list_archived_sql /
list_archived / list_out), every write sets it since 2.1054.0 (list_set_archived); the trigger kalmido_list_state
(migrations.d/5537_a.py) reads the archive from archived_at now. Before this AFTER, core/db.py init_db runs
core/liststate.py lst_move at every start while the column is there: archived_at filled where archived is set and it is
empty (projects archived before 1.6.1), cleared where archived is not set, the marker set from the column once more, and
the back limit raised to the minor of the image that moves (an older image reads and writes the column). The exports
(accounts/settings.py, admin/orgexport.py) still give the key archived, derived from the marker; the import of an older
file (admin/acctimport.py umz_row) takes the archive from its archived. A backup restores the old state.
"""
# drop-ok lists.archived: replaced by the state marker lists.state + archived_at (core/liststate.py moves it first, #5880, freed 14.11.2026)
AFTER = [
    "ALTER TABLE lists DROP COLUMN IF EXISTS archived",
]
