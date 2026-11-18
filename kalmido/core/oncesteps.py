"""2.1356.0 (#6824): the one-shot data steps of the start (settings flag migr_* = "1") in ONE ordered list, out of core/db.py init_db.

STEPS  (phase, key, once, f(c)) in the order init_db ran them. init_db calls run_phase(c, clk, phase) at the place the blocks
       stood (a phase is named after the init_db step right before it), so nothing runs earlier or later than before. once:
       skipped while gsetting key is "1"; the step writes its flag itself (as the block did; the runner writes it after a step
       that did not). A step without once runs at every start (the three that were no plain one-shot: the setup's default
       modules, the internal hosts per purpose, the projects' state marker) and keeps its own flag writes.
       The settings flag stays the switch (an older version after a rollback reads it and runs nothing twice; deleting it
       repeats the step); core/db.py mig_flags_sync records every flag set during a start as "flag:migr_*" in
       kalmido_migrations; mig_apply's column check stays the judge of the column steps.
run_steps(c, steps, clk, label=None)  the one runner: also of the areas' start hooks (core/objhooks.START, same shape
       (key, once, f)); every step that ran ends its step of the start log (StartClock, clk(key)), a flag write ends it too.

The bodies are the blocks of init_db word for word (moved, not rewritten). A NEW one-shot of the start goes here: one function,
one entry at its place in STEPS (tools/check_migrations.py: gsetting(c, "migr_...") outside this module only in the
places named there, the keys unique, the phases in init_db's order). One-shots of an area that run inside its own start
function stay there (tools/check_migrations.py ONCE_ELSEWHERE says why).

2.1380.0 (#6826): a database is only updated from core/db.py MIN_FROM (2.1000.0) on, and every database of that version has
run every one-shot that stood here (all of them were in 2.1001.0's init_db, the first release from the floor on). They are
gone (but the three that change foreign keys a new database needs too); their flags stay in RETIRED: retired_flags writes the missing ones at every start, so a new database (where the
steps never ran, on empty tables) carries them too and the one step back to a version that still has the steps runs none
of them on data made since. A one-shot that is retired later moves its key into RETIRED the same way.
"""
import json

from .db import ALLOW_PURPOSES, gset, gsetting
from .pg import system_ctx as pg_system_ctx


# 2.1380.0 (#6826): the flags of the one-shots retired with MIN_FROM 2.1000.0 (features_rev 8-12 were one step, default_features)
RETIRED = ("migr_kind", "migr_kind272", "migr_time241", "migr_feat8", "migr_feat9", "migr_feat10", "migr_feat11", "migr_feat12",
           "migr_orgs2220", "migr_listen2300", "migr_folders2220", "migr_folder931", "migr_order988", "migr_lf2352",
           "migr_notiftpl2330", "migr_scopes215", "migr_completed_by", "migr_folder_path", "migr_tidy_agent", "migr_auditfix",
           "migr_brought2365", "migr_siglog2360", "migr_kind2352", "migr_agcl2380",
           "migr_tours2466", "migr_e2efree4372", "migr_e2etrash5549", "migr_e2etrash5562", "migr_e2eundo5550",
           "migr_e2etrashsec5565", "migr_e2etrashsec5588", "migr_e2ehist5564", "migr_offerlist4586")


def retired_flags(c):
    """Every start (2.1380.0, #6826): the flags of RETIRED that are missing (a new database) are written as "1"; one read."""
    have = {r[0] for r in c.execute("SELECT key FROM settings WHERE key IN (" + ",".join("?" * len(RETIRED)) + ") AND value='1'",
                                    RETIRED).fetchall()}
    for k in RETIRED:
        if k not in have:
            gset(c, k, "1")


# 2.1380.0 (#6826): these three stay: they change foreign keys (time entries, direct messages, timesheets, logbook months
# outlive an account / a vehicle) that CREATE TABLE still makes the old way, so a NEW database needs them at its first start too
def migr_upg2103(c):  # 2.152.0 A (#2164): time entries / direct messages outlive an account
    from ..accounts.orgretain import upg_fk_once
    upg_fk_once(c)
    gset(c, "migr_upg2103", "1")


def migr_upg2360(c):  # 2.360.2 D (#2561): an organisation's timesheets outlive the account
    from ..accounts.orgretain import upg_fk_once
    upg_fk_once(c)
    gset(c, "migr_upg2360", "1")


def migr_drt2239(c):  # 2.239.0 D (#2874): closed logbook months outlive their vehicle
    from ..admin.dataretention import drt_fk_once
    drt_fk_once(c)
    gset(c, "migr_drt2239", "1")


def migr_allow2380(c):
    """Every start: copies the old list of internal hosts again when it changed since (#3569); sets its flag itself."""
    # 2.380 G (#3389): the one list of internal hosts -> a copy per purpose. 2.473.0 (#3569): allow_hosts_copied_from = the
    # old list as last copied; it differs after a fallback to an older version changed the old list -> copy again, a host
    # removed there must not stay allowed. A server without the mark only gets it: nothing says the old list changed (so the
    # mark is no entry of GLOBAL_DEFAULTS, those are stored before this runs).
    old = gsetting(c, "cal_allow_hosts")
    was = c.execute("SELECT value FROM settings WHERE key='allow_hosts_copied_from'").fetchone()
    if gsetting(c, "migr_allow2380") != "1" or (was and was[0] != old):
        gset(c, "allow_hosts_by_purpose", json.dumps({p: old for p in ALLOW_PURPOSES}, sort_keys=True))
        gset(c, "migr_allow2380", "1")
    if not was or was[0] != old:
        gset(c, "allow_hosts_copied_from", old)


def migr_liststate5537(c):
    """Every start (a reconcile, not a one-shot); sets its flag itself."""
    # 2.1029.0 (#5537): every start, the projects' state marker agrees with archived_at / deleted_at (migrations.d/5537_a.py; the
    # trigger kalmido_list_state keeps it so; this reconcile covers a rollback that dropped the trigger -- review of 2.1029; touches
    # only rows that differ). 2.1231.0 (#5880): archived_at, the old column archived is gone; review 2.1231: a row marked archived
    # without its moment (the trigger off, hand-made SQL) gets one first, so it keeps its archive (flag migr_liststate5537)
    with pg_system_ctx(c):  # every organisation's projects (row-level security)
        c.execute("UPDATE lists SET archived_at=CURRENT_TIMESTAMP WHERE state='archived' AND archived_at IS NULL")
        c.execute("UPDATE lists SET state=state WHERE state IS DISTINCT FROM (CASE WHEN deleted_at IS NOT NULL THEN 'trash'"
                  " WHEN archived_at IS NOT NULL THEN 'archived' ELSE 'live' END)")
    gset(c, "migr_liststate5537", "1")


STEPS = [  # (phase, key, once, f): the order of init_db (2.1356.0, #6824); 2.1380.0 (#6826): the one-shots before MIN_FROM are gone
    ("cdn_backfill", "migr_upg2103", True, migr_upg2103),
    ("cdn_backfill", "migr_upg2360", True, migr_upg2360),
    ("cdn_backfill", "migr_drt2239", True, migr_drt2239),
    ("cdn_backfill", "retired_flags", False, retired_flags),
    ("cdn_backfill", "migr_allow2380", False, migr_allow2380),
    ("cdn_backfill", "migr_liststate5537", False, migr_liststate5537),
]


def run_steps(c, steps, clk, label=None):
    """Runs (key, once, f) in order: once = only while gsetting key is not "1", then the flag (if f did not write it);
    clk(key) after each step that ran. label: an area hook's result (a count, a dict or a list of counts) goes into the
    log as "<label> (<key>): <result>" (core/objhooks.START, as init_db's loop printed it)."""
    for key, once, f in list(steps):
        if once and gsetting(c, key) == "1":
            continue
        n = f(c)
        clk(key)
        if once and gsetting(c, key) != "1":
            gset(c, key, "1")
        if label and n and (any(n.values()) if isinstance(n, dict) else any(n) if isinstance(n, (list, tuple)) else n):
            print(f"{label} ({key}):", n, flush=True)


def run_phase(c, clk, phase):
    """The one-shots of STEPS that stand at this place of init_db."""
    run_steps(c, [(k, once, f) for p, k, once, f in STEPS if p == phase], clk)
