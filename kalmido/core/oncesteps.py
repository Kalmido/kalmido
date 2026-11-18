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
"""
import json

from .db import ALLOW_PURPOSES, FEATS_2480, FEATS_2623, brought_backfill, gset, gsetting, insert_id, iso, now_utc, repair_data
from .i18n import LANGS, tr
from .pg import qi, system_ctx as pg_system_ctx, table_exists


def _lff():
    """lists/lffolder.py for #931 and #2748 below: one import (layers budget, tools/layers_baseline.json)."""
    from ..lists import lffolder
    return lffolder


def _le2b():
    """collab/liste2eguard.py for the locked projects' steps below (#4372, #5549, #5562, #5550, #5565, #5564, #5588): one
    import (layers budget)."""
    from ..collab import liste2eguard
    return liste2eguard


def migr_kind(c):
    # list types (package D2, once): checklists stay checklists; lists that already hold project data (time entries,
    # dependencies, custom fields or values, a project status; time only from 5 minutes tracked in total, so a
    # misclicked timer of a few seconds does not turn a household list into a project) become projects; the rest: list
    c.execute("UPDATE lists SET kind='checklist' WHERE checklist=1")
    n = c.execute("""UPDATE lists SET kind='project' WHERE checklist=0 AND (
                       id IN (SELECT list_id FROM time_entries WHERE list_id IS NOT NULL
                              GROUP BY list_id HAVING SUM(seconds) >= 300)
                       OR id IN (SELECT t.list_id FROM task_deps d JOIN tasks t ON t.id=d.task_id)
                       OR id IN (SELECT t.list_id FROM task_deps d JOIN tasks t ON t.id=d.blocker_id)
                       OR id IN (SELECT list_id FROM list_fields)
                       OR id IN (SELECT t.list_id FROM task_field_values v JOIN tasks t ON t.id=v.task_id)
                       OR status!='')""").rowcount
    gset(c, "migr_kind", "1")
    print("list types:", n, "lists with project data became projects", flush=True)


def migr_kind272(c):
    # 2.7.2 (#414), once: the type "checklist" is gone; such lists become plain lists with "Show completed at the
    # bottom" on (the column checklist stays 1), so nothing changes for their items
    n = c.execute("UPDATE lists SET kind='list', checklist=1 WHERE kind='checklist'").rowcount
    gset(c, "migr_kind272", "1")
    if n:
        print("list types:", n, "checklists became lists with 'Show completed at the bottom'", flush=True)


def migr_time241(c):
    # 2.41.0 (#1471), once: time tracking became a switch of each list (default off); every list that already holds time
    # entries gets it on, so no list loses its timer or its tracked time
    n = c.execute("UPDATE lists SET time_tracking=1 WHERE time_tracking=0 AND id IN "
                  "(SELECT DISTINCT list_id FROM time_entries WHERE list_id IS NOT NULL)").rowcount
    gset(c, "migr_time241", "1")
    if n:
        print("time tracking:", n, "lists with time entries keep it (switched on)", flush=True)


def default_features(c):
    """features_rev 8 to 12 of the setup's default modules: one step, as before (dfs is read once for all five)."""
    # features_rev 8: the setup's default modules (from before 1.2) get "deps" / "fields" like the users below
    dfs = gsetting(c, "default_features")
    if dfs and gsetting(c, "migr_feat8") != "1":
        d = [x for x in dfs.split(",") if x]
        d += [f for f in ("deps", "fields") if f not in d and ("timeline" in d or "progress" in d)]
        gset(c, "default_features", ",".join(d))
    gset(c, "migr_feat8", "1")
    # features_rev 9 (2.0.6): comments became a module of their own, on by default (also in the setup's default)
    if dfs and gsetting(c, "migr_feat9") != "1":
        d = [x for x in (gsetting(c, "default_features") or "").split(",") if x]
        if "comments" not in d:
            gset(c, "default_features", ",".join(d + ["comments"]))
    gset(c, "migr_feat9", "1")
    # features_rev 10 (2.21.0, #659 / #658): events and contacts are modules of their own, on by default
    if dfs and gsetting(c, "migr_feat10") != "1":
        d = [x for x in (gsetting(c, "default_features") or "").split(",") if x]
        gset(c, "default_features", ",".join(d + [f for f in ("events", "contacts") if f not in d]))
    gset(c, "migr_feat10", "1")
    # features_rev 11 (2.48.0, #1207): the new modules of 2.48 in the setup's default too
    if dfs and gsetting(c, "migr_feat11") != "1":
        d = [x for x in (gsetting(c, "default_features") or "").split(",") if x]
        gset(c, "default_features", ",".join(d + [f for f in FEATS_2480 if f not in d]))
    gset(c, "migr_feat11", "1")
    # features_rev 12 (2.623.0, #4765): the module Approval in the setup's default too
    if dfs and gsetting(c, "migr_feat12") != "1":
        d = [x for x in (gsetting(c, "default_features") or "").split(",") if x]
        gset(c, "default_features", ",".join(d + [f for f in FEATS_2623 if f not in d]))
    gset(c, "migr_feat12", "1")


def migr_orgs2220(c):
    # 2.22.0 (#752), once: one organisation (named after the instance's domain, e.g. kalmido.example.com -> "Example")
    # with every account (agents too); people see only people of their organisations
    from ..accounts.orgs import INSTANCE_ENV
    # 2.46.0 (#1592): only an existing instance from before 2.22 (accounts, no organisation); a new one starts without
    if not c.execute("SELECT 1 FROM orgs WHERE personal_of IS NULL").fetchone() and INSTANCE_ENV != "shared" and c.execute("SELECT 1 FROM users LIMIT 1").fetchone():
        from ..core.config import PUBLIC_URL
        host = PUBLIC_URL.split("://", 1)[-1].split("/")[0].split(":")[0]
        parts = [p for p in host.split(".") if p and not p.isdigit()]
        name = (parts[-2] if len(parts) >= 2 else (parts[0] if parts else "Kalmido")).capitalize()
        oid = insert_id(c, "INSERT INTO orgs(name,icon,created_at) VALUES(?,?,?)", (name, "", iso(now_utc())))
        c.execute("INSERT INTO org_members(org_id,user_id) SELECT ?, id FROM users WHERE true ON CONFLICT DO NOTHING", (oid,))
        if gsetting(c, "people_visibility") in (None, ""):
            gset(c, "people_visibility", "org")
        print("organisations:", name, "with every account", flush=True)
    gset(c, "migr_orgs2220", "1")


def migr_listen2300(c):  # 2.30.0 (#1034), once: "listens in" keeps who listened before
    from ..agents.core import listen_migrate
    n = listen_migrate(c)
    gset(c, "migr_listen2300", "1")
    if n:
        print("agents listening in:", n, "lists written explicitly", flush=True)


def migr_folders2220(c):
    # 2.22.0 (#740), once: lists shared before go into the folder of the same name as with their owner (created when
    # missing) -- only where the person has not put the list into a folder of their own
    from ..lists.lists import member_folder_adopt
    n = sum(1 for r in c.execute("""SELECT m.list_id, m.user_id FROM list_members m JOIN lists l ON l.id=m.list_id
                                    WHERE COALESCE(m.folder,'')='' AND l.folder!=''""").fetchall() if member_folder_adopt(c, r[0], r[1]))
    gset(c, "migr_folders2220", "1")
    if n:
        print("shared lists:", n, "sorted into the folders of their owners", flush=True)


def migr_folder931(c):
    # 2.25.0 (#931), once: lists created in a shared folder by a project type / template, an agent's briefing, an import,
    # family or life were not shared with the folder's people. Only lists created AFTER the folder was shared and
    # without that person get it now (one shared before and missing now was taken away on purpose); idempotent.
    lf_people_rows, lf_resync = _lff().lf_people_rows, _lff().lf_resync
    from ..lists.lists import _folder_member_add, _in_folder, collab_all as _ca
    n = 0
    if _ca() and table_exists(c, "folder_people"):  # 2.958.0 (#5245): gone on a new database
        for fp in c.execute("SELECT * FROM folder_people").fetchall():
            for fl in c.execute("SELECT id, folder FROM lists WHERE owner_id=? AND NOT is_inbox AND COALESCE(folder,'')!='' AND created_at>?",
                               (fp["owner_id"], fp["created_at"])).fetchall():
                if _in_folder(fl["folder"], fp["folder"]) and _folder_member_add(c, fl["id"], fp["user_id"], fp["role"], fp["owner_id"]):
                    n += 1
    elif _ca():  # 2.997.0 (#5677): folder_people is gone since 2.958.0 (#5245) -- the folders' shares (fs_shares, read as
        # its old rows by lf_people_rows) reach a list as a folder role (frole) once it lies under the folder: grp_sync places
        # it (lf_place) and computes its roles, a person taken off by hand stays off (list_folder_skip)
        lids = set()
        with pg_system_ctx(c):  # every owner's lists and folders (as lf_migrate)
            for fp in lf_people_rows(c):
                for lr in c.execute("SELECT id, folder FROM lists WHERE owner_id=? AND NOT is_inbox AND COALESCE(folder,'')!='' AND created_at>?",
                                   (fp["owner_id"], fp["created_at"])).fetchall():
                    if _in_folder(lr["folder"], fp["folder"]) and not c.execute("SELECT 1 FROM list_members WHERE list_id=? AND user_id=?",
                                                                               (lr["id"], fp["user_id"])).fetchone():
                        lids.add(lr["id"])
            lf_resync(c, lids, 0)
        n = len(lids)
    gset(c, "migr_folder931", "1")
    if n:
        print("lists in shared folders shared afterwards (#931):", n, flush=True)


def migr_order988(c):
    # 2.27.0 (#988), once: every member's copy of a list in its owner's folder is put where the owner has it (folder +
    # place); from now on the owner's arrangement is mirrored for everyone (visible_lists, list_reorder)
    n = c.execute("""UPDATE list_members SET folder=(SELECT l.folder FROM lists l WHERE l.id=list_members.list_id),
                         sort=(SELECT l.sort FROM lists l WHERE l.id=list_members.list_id)
                     WHERE list_id IN (SELECT id FROM lists WHERE COALESCE(folder,'')!='')
                       AND (folder IS DISTINCT FROM (SELECT l.folder FROM lists l WHERE l.id=list_members.list_id)
                            OR sort IS DISTINCT FROM (SELECT l.sort FROM lists l WHERE l.id=list_members.list_id))""").rowcount
    gset(c, "migr_order988", "1")
    if n:
        print("shared lists arranged like their owners have them (#988):", n, flush=True)


def migr_lf2352(c):
    # 2.352.0 A (#2748), once (one-way): the folders of the lists go into the file store's projects trees, folder shares
    # become shares of those folders (rights at runtime, list_members.frole); folder_people stays readable
    lf_migrate = _lff().lf_migrate
    n = lf_migrate(c)
    gset(c, "migr_lf2352", "1")
    if any(n.values()):
        print("list folders into the projects trees (#2748):", n, flush=True)


def migr_notiftpl2330(c):
    # 2.33.0 (#927), once: lists / folders shared so far keep every notification ("all", written explicitly; new shares
    # start with "read"), their owners are asked once in the app
    from ..notify.caps import notif_tpl_migrate
    nl, nf = notif_tpl_migrate(c)
    gset(c, "migr_notiftpl2330", "1")
    if nl or nf:
        print("notification templates: shared lists", nl, "and folders", nf, "kept on \"all\" (#927)", flush=True)


def migr_scopes215(c):
    # 2.15.0 (#479), once: fine scopes. Old read tokens could download files (now attachments:read), old agents had
    # read + write (stored "write" = every scope but admin-read, so they keep what they could do)
    n = c.execute("""UPDATE api_tokens SET scopes=scopes || ',attachments:read'
                     WHERE ',' || scopes || ',' NOT ILIKE '%,write,%' AND ',' || scopes || ',' NOT ILIKE '%,attachments:read,%'""").rowcount
    m = c.execute("UPDATE agents SET scopes='read,write' WHERE scopes=''").rowcount
    gset(c, "migr_scopes215", "1")
    print("scopes: attachments:read for", n, "read tokens,", m, "agents keep read + write", flush=True)


def migr_completed_by(c):
    # one-shot: completions from before completed_by existed belong to the task's creator (else the list owner)
    n = c.execute("""UPDATE tasks SET completed_by=COALESCE(created_by, (SELECT owner_id FROM lists WHERE lists.id=tasks.list_id))
                     WHERE completed_by IS NULL AND status!=0 AND completed_at IS NOT NULL""").rowcount
    gset(c, "migr_completed_by", "1")
    print("completed_by: attributed", n, "earlier completions", flush=True)


def migr_folder_path(c):
    # 2.4.0 (#361): folders nest one level ("Clients/Company X", FOLDER_SEP). A "/" in an existing folder name would now
    # mean a subfolder, so it becomes the look-alike U+2215 once: every existing folder stays top-level, as it was
    from ..lists.lists import folder_path_migration
    n = folder_path_migration(c)
    gset(c, "migr_folder_path", "1")
    if n:
        print("folders: kept", n, "folder names with a slash top-level", flush=True)


def migr_tidy_agent(c):
    # 2.4.1 (#379): tidying up is done by exactly one agent per list. Lists with tidy on get the agent that already
    # received their tidy events first (the first agent with edit rights), once
    from ..agents.core import tidy_agent_of
    n = 0
    for (lid,) in c.execute("SELECT id FROM lists WHERE agent_tidy!='off' AND tidy_agent IS NULL").fetchall():
        aid = tidy_agent_of(c, lid)
        if aid:
            c.execute("UPDATE lists SET tidy_agent=? WHERE id=?", (aid, lid))
            n += 1
    gset(c, "migr_tidy_agent", "1")
    if n:
        print("tidy: assigned the tidy agent of", n, "list(s)", flush=True)


def migr_auditfix(c):  # security audit 2026-09-28, one-shot
    n = c.execute("UPDATE users SET paperless_access=1 WHERE is_admin AND paperless_access=0").rowcount
    counts = repair_data(c)
    gset(c, "migr_auditfix", "1")
    print("audit migration: Paperless access granted to", n, "admin(s); repaired:", counts, flush=True)


def migr_brought2365(c):  # 2.365.1 (#3395): who brought what in, from the history of the moves
    n = brought_backfill(c)
    gset(c, "migr_brought2365", "1")
    print("organisations: noted who brought in", n, "item(s)", flush=True)


def migr_upg2103(c):  # 2.152.0 A (#2164): time entries / direct messages outlive an account
    from ..accounts.orgretain import upg_fk_once
    upg_fk_once(c)
    gset(c, "migr_upg2103", "1")


def migr_upg2360(c):  # 2.360.2 D (#2561): an organisation's timesheets outlive the account
    from ..accounts.orgretain import upg_fk_once
    upg_fk_once(c)
    gset(c, "migr_upg2360", "1")


def migr_siglog2360(c):  # 2.360.2 D (#2561): one way -- old approval log entries lose e-mail, address, device
    from ..office.signoff import sig_log_trim
    n, left = sig_log_trim(c)
    gset(c, "migr_siglog2360", "1")
    print(f"office log: {n} approval entries shortened, {left} sealed one(s) without a key left as they are", flush=True)


def migr_drt2239(c):  # 2.239.0 D (#2874): closed logbook months outlive their vehicle
    from ..admin.dataretention import drt_fk_once
    drt_fk_once(c)
    gset(c, "migr_drt2239", "1")


def migr_kind2352(c):  # 2.352.0 B (#2752): list = project, tracked = has a status; kind stays unused
    n = c.execute("UPDATE lists SET status='on_track' WHERE kind='project' AND NOT is_inbox AND COALESCE(status,'')=''").rowcount
    gset(c, "migr_kind2352", "1")  # once: a status cleared later (= not tracked) stays cleared
    if n:
        print("list types:", n, "projects without a status became 'on track'", flush=True)


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


def migr_agcl2380(c):  # 2.380 F (#3438): one way -- the agency projects' "Client" text fields go
    # when no task has a value in them (the client is the project's, lists.client_id); a field with a value stays
    names = sorted({tr("Client", lg=x).strip().lower() for x in LANGS} | {"client"})
    ids = [r[0] for r in c.execute(
        f"SELECT f.id FROM list_fields f JOIN lists l ON l.id=f.list_id WHERE l.ptype='agency' AND f.type='text' "
        f"AND LOWER(TRIM(f.name)) IN ({','.join('?' * len(names))}) AND NOT EXISTS (SELECT 1 FROM task_field_values v "
        f"WHERE v.field_id=f.id AND v.value<>'')", names).fetchall()]
    for fid in ids:
        c.execute("DELETE FROM task_field_values WHERE field_id=?", (fid,))
        c.execute("DELETE FROM list_fields WHERE id=?", (fid,))
        c.execute("UPDATE lists SET group_field='' WHERE group_field=?", (f"cf:{fid}",))
    gset(c, "migr_agcl2380", "1")
    if ids:
        print("agency projects:", len(ids), "empty field(s) \"Client\" removed", flush=True)


def migr_tours2466(c):  # 2.466.0 (#3314): an area an existing account has content in counts as
    # opened: its introduction shows only for areas never used. Nothing is lost: a later start skips this, an older
    # version ignores the setting
    seen = {}
    for area, sql in (("cal", "SELECT DISTINCT created_by FROM events"), ("office", "SELECT DISTINCT created_by FROM clients"),
                      ("time", "SELECT DISTINCT user_id FROM time_entries"), ("review", "SELECT DISTINCT user_id FROM journal"),
                      ("wiki", "SELECT DISTINCT owner_id FROM wiki_pages"), ("sheets", "SELECT DISTINCT owner_id FROM sheets"),
                      ("habits", "SELECT DISTINCT user_id FROM habits")):
        for r in c.execute(sql).fetchall():
            if r[0] is not None:
                seen.setdefault(r[0], []).append(area)
    for uid, areas in seen.items():
        c.execute("INSERT INTO user_settings(user_id,key,value) SELECT id,'tours_seen',? FROM users WHERE id=? "
                  "ON CONFLICT(user_id,key) DO UPDATE SET value=excluded.value WHERE user_settings.value=''",  # the start fills in defaults first
                  (",".join(areas), uid))
    gset(c, "migr_tours2466", "1")


def migr_e2efree4372(c):  # 2.538.0 (#4372, review 2646 finding 1): one way -- a project locked before
    le2b_scrub_free = _le2b().le2b_scrub_free
    # 2.538 loses its time notes, status notes and descriptions as a project locked now does (le2b_scrub). Only 'on': one
    # still 'encrypting' gets the whole scrub at its finish, one 'decrypting' shows its texts again
    n = {}
    for r in c.execute("SELECT id FROM lists WHERE e2e='on' ORDER BY id").fetchall():
        for k, v in le2b_scrub_free(c, r[0]).items():
            n[k] = n.get(k, 0) + v
    gset(c, "migr_e2efree4372", "1")
    if any(n.values()):
        print("locked projects: plain texts emptied " + ", ".join(f"{k} {v}" for k, v in sorted(n.items())), flush=True)


def migr_e2etrash5549(c):  # #5549: one way -- a project locked before loses the trash copies of its
    le2b_scrub_trash = _le2b().le2b_scrub_trash
    # sections and custom fields deleted before the lock (plain text) and the notes of its "Delete all times" copies, as
    # a project locked now does (le2b_scrub_trash). Only 'on', as migr_e2efree4372
    n = {}
    for r in c.execute("SELECT id FROM lists WHERE e2e='on' ORDER BY id").fetchall():
        for k, v in le2b_scrub_trash(c, r[0], plain_only=True).items():
            n[k] = n.get(k, 0) + v
    gset(c, "migr_e2etrash5549", "1")
    if any(n.values()):
        print("locked projects: plain trash copies removed " + ", ".join(f"{k} {v}" for k, v in sorted(n.items())), flush=True)


def migr_e2etrash5562(c):  # 2.898.0 (#5562, review 2): one way -- the tasks of a project locked before
    le2b_scrub_trash_tasks = _le2b().le2b_scrub_trash_tasks
    # lose their title, note and field values in the trash copies of OTHER projects, as tasks moved in now do
    n = {}
    for r in c.execute("SELECT id FROM lists WHERE e2e='on' ORDER BY id").fetchall():
        tids = {x[0] for x in c.execute("SELECT id FROM tasks WHERE list_id=?", (r[0],))}
        for k, v in le2b_scrub_trash_tasks(c, tids).items():
            n[k] = n.get(k, 0) + v
    gset(c, "migr_e2etrash5562", "1")
    if any(n.values()):
        print("locked projects: task texts removed from other projects' trash copies " + ", ".join(f"{k} {v}" for k, v in sorted(n.items())), flush=True)


def migr_e2eundo5550(c):  # 2.900.0 (#5550, #5551): one way -- a project locked before loses the undo
    le2b_scrub_undo_free = _le2b().le2b_scrub_undo_free
    # steps whose copy keeps a time entry's note / task title, its settings' description / status note or its notepads'
    # texts, as a project locked now does (le2b_scrub_undo_free). Only 'on', as migr_e2efree4372
    n = {}
    for r in c.execute("SELECT id FROM lists WHERE e2e='on' ORDER BY id").fetchall():
        for k, v in le2b_scrub_undo_free(c, r[0]).items():
            n[k] = n.get(k, 0) + v
    gset(c, "migr_e2eundo5550", "1")
    if any(n.values()):
        print("locked projects: undo copies dropped " + ", ".join(f"{k} {v}" for k, v in sorted(n.items())), flush=True)


def migr_e2etrashsec5565(c):  # #5565: one way -- the tasks in the trash of a project locked before
    le2b_trash_section_fit = _le2b().le2b_trash_section_fit
    # #5552 kept their section's plain name (tasks.trash_section; a project switching now forgets it, lists/parttrash.py
    # lpt_section_purge_list), one unlocked again a ciphertext. Their restore no longer makes such a section (#5552
    # rt_e2e_ok); the name goes once. Only 'on' and open, as migr_e2etrash5549: a switch still running empties it at its finish
    n = le2b_trash_section_fit(c)
    gset(c, "migr_e2etrashsec5565", "1")
    if n:
        print(f"projects with a lock switched before: section names of tasks in the trash removed {n}", flush=True)


def migr_e2etrashsec5588(c):  # #5588 (b): one way -- the plain-named section copies in the trash of a
    le2b_trash_sec_plain = _le2b().le2b_trash_sec_plain
    # project locked before #5552 go once (was migrations.d/5552_a.py with a fixed cut-off: an instance updating later kept them)
    n = le2b_trash_sec_plain(c)
    gset(c, "migr_e2etrashsec5588", "1")
    if n:
        print(f"locked projects: plain section names removed from the trash {n}", flush=True)


def migr_e2ehist5564(c):  # #5564: one way -- the history rows of time entries / notepads deleted
    le2b_hist_gone = _le2b().le2b_hist_gone
    # before a lock kept their note / text; migr_e2eundo5550 took the copies that named their project, so the rows no
    # step can bring back go for every project (le2b_hist_gone: read per object only, nobody sees them any more)
    n = le2b_hist_gone(c)  # across organisations itself (system_ctx)
    gset(c, "migr_e2ehist5564", "1")
    if n:
        print(f"history rows of deleted time entries / notepads removed {n}", flush=True)


def migr_offerlist4586(c):  # 2.620.0 (#4586, review C M1): the links of tasks moved before the trigger
    # kalmido_offer_link_list (migrations.d/4586_a.py) follow their task's list once
    c.execute("UPDATE task_offer_links l SET list_id=t.list_id FROM tasks t WHERE t.id=l.task_id AND l.list_id<>t.list_id")
    gset(c, "migr_offerlist4586", "1")


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


def migr_textby6677(c):  # 2.1375.0 (#6677): tasks.title_by / content_by of the tasks changed before, once from their history
    # (the newest title resp. content / md_subtasks line; a hand without a person -- via webhook, public link, CalDAV, support,
    # a rule, no user -- is 0, as tasks/validation.py text_hand). A task whose history was purged keeps NULL (the creator's).
    with pg_system_ctx(c):  # every organisation's tasks (row-level security)
        for name, kinds in (("title_by", ("title",)), ("content_by", ("content", "md_subtasks"))):
            col = qi(name, ("title_by", "content_by"))
            c.execute(f"""UPDATE tasks t SET {col} = CASE WHEN a.user_id IS NULL OR a.user_id = 0 OR a.rule IS NOT NULL
                                                         OR COALESCE(a.via, 'api') <> 'api' THEN 0 ELSE a.user_id END
                          FROM (SELECT DISTINCT ON (task_id) task_id, user_id, data->>'via' AS via, data->>'rule' AS rule
                                FROM activity WHERE kind = ANY(CAST(? AS TEXT[])) ORDER BY task_id, id DESC) a
                          WHERE t.id = a.task_id AND t.{col} IS NULL""", ("{" + ",".join(kinds) + "}",))
    gset(c, "migr_textby6677", "1")


STEPS = [  # (phase, key, once, f): the order of init_db (2.1356.0, #6824)
    ("adopt_orphans", "migr_kind", True, migr_kind),
    ("adopt_orphans", "migr_kind272", True, migr_kind272),
    ("adopt_orphans", "migr_time241", True, migr_time241),
    ("adopt_orphans", "default_features", False, default_features),
    ("adopt_orphans", "migr_orgs2220", True, migr_orgs2220),
    ("ws_migrate_objs", "migr_listen2300", True, migr_listen2300),
    ("ws_migrate_objs", "migr_folders2220", True, migr_folders2220),
    ("ws_migrate_objs", "migr_folder931", True, migr_folder931),
    ("ws_migrate_objs", "migr_order988", True, migr_order988),
    ("ws_migrate_objs", "migr_lf2352", True, migr_lf2352),
    ("core_start", "migr_notiftpl2330", True, migr_notiftpl2330),
    ("users", "migr_scopes215", True, migr_scopes215),
    ("secrets", "migr_completed_by", True, migr_completed_by),
    ("show_completed", "migr_folder_path", True, migr_folder_path),
    ("show_completed", "migr_tidy_agent", True, migr_tidy_agent),
    ("folder_agents_sync", "migr_auditfix", True, migr_auditfix),
    ("cdn_backfill", "migr_brought2365", True, migr_brought2365),
    ("cdn_backfill", "migr_upg2103", True, migr_upg2103),
    ("cdn_backfill", "migr_upg2360", True, migr_upg2360),
    ("cdn_backfill", "migr_siglog2360", True, migr_siglog2360),
    ("cdn_backfill", "migr_drt2239", True, migr_drt2239),
    ("cdn_backfill", "migr_kind2352", True, migr_kind2352),
    ("cdn_backfill", "migr_allow2380", False, migr_allow2380),
    ("cdn_backfill", "migr_agcl2380", True, migr_agcl2380),
    ("cdn_backfill", "migr_tours2466", True, migr_tours2466),
    ("cdn_backfill", "migr_e2efree4372", True, migr_e2efree4372),
    ("cdn_backfill", "migr_e2etrash5549", True, migr_e2etrash5549),
    ("cdn_backfill", "migr_e2etrash5562", True, migr_e2etrash5562),
    ("cdn_backfill", "migr_e2eundo5550", True, migr_e2eundo5550),
    ("cdn_backfill", "migr_e2etrashsec5565", True, migr_e2etrashsec5565),
    ("cdn_backfill", "migr_e2etrashsec5588", True, migr_e2etrashsec5588),
    ("cdn_backfill", "migr_e2ehist5564", True, migr_e2ehist5564),
    ("cdn_backfill", "migr_offerlist4586", True, migr_offerlist4586),
    ("cdn_backfill", "migr_liststate5537", False, migr_liststate5537),
    ("cdn_backfill", "migr_textby6677", True, migr_textby6677),
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
