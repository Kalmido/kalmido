"""2.1265.0 (#6287, audit #4742 F2): do the rows of the old tables a core move retires arrive in their target?

The fragments of kalmido/core/migrations.d drop an old table (or column) in AFTER once the start's move (core/objhooks.py MOVE,
init_db) has copied its rows; the DROP itself checks nothing. A WHERE gone wrong in a move, or a move that falls out of the load
order, loses the rows on a live database while every start stays green. p2192_c_upgrade asks this table:

- before the start (after fill_old_tables): per old table that is still there, the rows the move has to take -- the move's own
  condition (the rows whose object / person still exist ...) as a key tuple (`old`)
- after the start: the same key tuples read from the target (`new`); every old one has to be there (a set: a move may merge
  rows, e.g. task_tags "Kunde" / "kunde" on one task -> one link, and the server may add rows of its own)

The guard against forgetting (guard()): every `# drop-ok <table>[.<column>]:` line of migrations.d (tools/check_migrations.py
demands one for each DROP TABLE / DROP COLUMN) needs an entry here -- in MOVES (checked by rows) or in OTHER with the reason
why no row check applies (the rows are no data: a search index rebuilt at the start; the table was dead; a start check of its
own keeps the table while rows are left, core/kernretire.py kern_retire). A new move without an entry is red.

An entry: (old table[.column], target, old SQL, new SQL). `old` may be a function has(table, column) -> SQL for an old table
whose columns differ between releases. Keys are lists of plain values (ids as int, names lower-cased).
"""
import os
import re

N = os.path.dirname(os.path.abspath(__file__))
FRAGMENTS = os.path.join(os.path.dirname(N), "kalmido", "core", "migrations.d")
DROP_OK = re.compile(r"^[ \t]*#[ \t]*drop-ok[ \t]+(\w+(?:\.\w+)?)[ \t]*:", re.M)  # = tools/check_migrations.py DROP_OK

# core/objtags.py otg_move_user: a personal tag's name trimmed (Python's strip: \s), a leading '#' off, trimmed again
_TRIM = r"regexp_replace({}, '^\s+|\s+$', '', 'g')"
_UNAME = _TRIM.format(f"ltrim({_TRIM.format('g.tag')}, '#')")
# docs/dtags.py / core/objtags.py otg_move_ws: a file store tag's name with its blanks folded
_WSNAME = r"btrim(regexp_replace(t.name, '\s+', ' ', 'g'))"
_OCM_Q4B_CUT = "2026-11-08"  # core/objcomments.py OCM_Q4B_CUT: review comments deleted before it were cleaned up (#5263)


def _rss_items(has):
    """core/objseen.py OSN_OLD_RSS_ITEMS: the owner's mark of a private feed (rss_feeds.org_id came after 2.101)."""
    priv = " AND f.org_id IS NULL" if has("rss_feeds", "org_id") else ""
    return f"SELECT i.id, f.user_id FROM rss_items i JOIN rss_feeds f ON f.id=i.feed_id WHERE i.read_at IS NOT NULL{priv}"


def _list_tags(has):
    """core/objtags.py otg_move: a project tag of its project (a label's copy becomes the label: see the new SQL)."""
    return "SELECT x.list_id, lower(x.name) FROM list_tags x JOIN lists l ON l.id=x.list_id"


MOVES = [
    # stage Q1 (#5269, core/objreact.py orx_move): only reactions whose target and person still exist
    ("comment_reactions", "obj_reactions",
     "SELECT x.comment_id, x.user_id, x.emoji FROM comment_reactions x JOIN comments p ON p.id=x.comment_id "
     "JOIN tasks t ON t.id=p.task_id JOIN users u ON u.id=x.user_id",
     "SELECT target_id, user_id, emoji FROM obj_reactions WHERE target_kind='comment'"),
    ("tchat_rx", "obj_reactions",
     "SELECT x.message_id, x.user_id, x.emoji FROM tchat_rx x JOIN tchat_msgs p ON p.id=x.message_id JOIN users u ON u.id=x.user_id",
     "SELECT target_id, user_id, emoji FROM obj_reactions WHERE target_kind='tchat'"),
    ("chat_reactions", "obj_reactions",
     "SELECT x.message_id, x.user_id, x.emoji FROM chat_reactions x JOIN agent_chat p ON p.id=x.message_id JOIN users u ON u.id=x.user_id",
     "SELECT target_id, user_id, emoji FROM obj_reactions WHERE target_kind='agent_chat'"),
    # stage Q3 (#5271, core/objlinks.py olnk_move)
    ("hub_mail_links", "obj_links",
     "SELECT mail_id, kind, ref_id FROM hub_mail_links WHERE kind IN ('task', 'event')",
     "SELECT src_id, dst_kind, dst_id FROM obj_links WHERE src_kind='hub_mail' AND rel='made'"),
    ("life_device_links", "obj_links",
     "SELECT task_id, equipment_id FROM life_device_links WHERE task_id IS NOT NULL AND equipment_id IS NOT NULL",
     "SELECT src_id, dst_id FROM obj_links WHERE src_kind='task' AND dst_kind='omd_equipment' AND rel='device'"),
    ("contact_tasks", "obj_links",
     "SELECT contact_id, task_id FROM contact_tasks",
     "SELECT src_id, dst_id FROM obj_links WHERE src_kind='contact' AND dst_kind='task' AND rel='contact'"),
    ("office_letter_links", "obj_links",
     "SELECT letter_id, node_id, kind FROM office_letter_links WHERE kind IN ('answers', 'reply')",
     "SELECT src_id, dst_id, rel FROM obj_links WHERE src_kind='office_letter' AND dst_kind='fs_entry'"),
    # stage Q4a (#5272, core/objcomments.py ocm_move): the comments keep their ids
    ("comments", "obj_comments",
     "SELECT k.id, k.task_id FROM comments k JOIN tasks t ON t.id=k.task_id",
     "SELECT id, ref_id FROM obj_comments WHERE kind='task'"),
    ("comment_trash_text", "obj_comment_trash",
     "SELECT x.comment_id FROM comment_trash_text x JOIN comments k ON k.id=x.comment_id JOIN tasks t ON t.id=k.task_id",
     "SELECT comment_id FROM obj_comment_trash WHERE kind='comment'"),
    # stage Q4b (#5273, ocm_move_q4b): new ids -> the review / node, the author and the text; a comment in the trash leaves
    # its text in obj_comment_trash, so only the ones not deleted are compared by text
    ("video_comments", "obj_comments",
     "SELECT v.review_id, v.author_id, v.body FROM video_comments v JOIN video_reviews r ON r.id=v.review_id "
     "WHERE COALESCE(v.deleted_at, '') = ''",
     "SELECT ref_id, user_id, body FROM obj_comments WHERE kind='video'"),
    ("doc_notes", "obj_comments",
     "SELECT d.node_id, COALESCE(d.text, '') FROM doc_notes d JOIN fs_nodes f ON f.id=d.node_id",
     "SELECT ref_id, body FROM obj_comments WHERE kind='doc_note'"),
    # stage Q4c (#5274, ocm_move_q4c): the kept text of a deleted team chat message
    ("tchat_trash_text", "obj_comment_trash",
     "SELECT x.message_id FROM tchat_trash_text x JOIN tchat_msgs m ON m.id=x.message_id WHERE COALESCE(CAST(m.deleted_at AS text), '') <> ''",
     "SELECT comment_id FROM obj_comment_trash WHERE kind='tchat'"),
    # stage Q5a (#5275, core/objtags.py otg_move): a label's copy in a project becomes the label, a project tag named like a
    # label of the project's organisation too -> the new side takes a project's tags and its organisation's labels
    ("org_tags", "obj_tags",
     "SELECT org_id, lower(name) FROM org_tags",
     "SELECT org_id, lower(name) FROM obj_tags WHERE scope_kind='org'"),
    ("list_tags", "obj_tags", _list_tags,
     "SELECT l.id, lower(t.name) FROM obj_tags t JOIN lists l ON (t.scope_kind='list' AND t.scope_id=CAST(l.id AS TEXT)) "
     "OR (t.scope_kind='org' AND t.org_id=l.org_id)"),
    ("task_list_tags", "obj_tag_links",
     "SELECT x.task_id, lower(g.name) FROM task_list_tags x JOIN list_tags g ON g.id=x.tag_id JOIN tasks t ON t.id=x.task_id AND t.list_id=g.list_id",
     "SELECT k.obj_id, lower(t.name) FROM obj_tag_links k JOIN obj_tags t ON t.id=k.tag_id WHERE k.kind='task' AND t.scope_kind IN ('list', 'org')"),
    # stage Q5b (#5276, otg_move_user): the person's own tags; a row of the single-user era (user 0) is adopted by the first
    # account later (otg_adopt_user) -- left out here
    ("task_tags", "obj_tag_links",
     f"SELECT g.user_id, g.task_id, lower({_UNAME}) FROM task_tags g JOIN users u ON u.id=g.user_id WHERE {_UNAME} <> ''",
     "SELECT CAST(t.scope_id AS BIGINT), k.obj_id, lower(t.name) FROM obj_tag_links k JOIN obj_tags t ON t.id=k.tag_id "
     "WHERE k.kind='task' AND t.scope_kind='user' AND t.scope_id ~ '^[0-9]+$'"),
    # stage Q5c (#5277, otg_move_ws): the file store's tags per workspace
    ("doc_tags", "obj_tags",
     f"SELECT t.ws, lower({_WSNAME}) FROM doc_tags t WHERE {_WSNAME} <> ''",
     "SELECT scope_id, lower(name) FROM obj_tags WHERE scope_kind='ws'"),
    ("doc_node_tags", "obj_tag_links",
     f"SELECT x.node_id, t.ws, lower({_WSNAME}) FROM doc_node_tags x JOIN doc_tags t ON t.id=x.tag_id WHERE {_WSNAME} <> ''",
     "SELECT k.obj_id, t.scope_id, lower(t.name) FROM obj_tag_links k JOIN obj_tags t ON t.id=k.tag_id "
     "WHERE k.kind='fs_entry' AND t.scope_kind='ws'"),
    # stage Q8a / Q8b (#5284, #5286, core/objseen.py osn_move*): read marks
    ("task_seen", "obj_seen",
     "SELECT s.task_id, s.user_id FROM task_seen s JOIN tasks t ON t.id=s.task_id JOIN users u ON u.id=s.user_id",
     "SELECT ref_id, user_id FROM obj_seen WHERE kind='task'"),
    ("rss_reads", "obj_seen",
     "SELECT r.item_id, r.user_id FROM rss_reads r JOIN rss_items i ON i.id=r.item_id JOIN users u ON u.id=r.user_id",
     "SELECT ref_id, user_id FROM obj_seen WHERE kind='rss'"),
    ("rss_items.read_at", "obj_seen", _rss_items,
     "SELECT ref_id, user_id FROM obj_seen WHERE kind='rss'"),
    ("tchat_reads", "obj_seen",
     "SELECT d.room_id, d.user_id FROM tchat_reads d JOIN tchat_rooms r ON r.id=d.room_id JOIN users u ON u.id=d.user_id WHERE d.last_id > 0",
     "SELECT ref_id, user_id FROM obj_seen WHERE kind='tchat'"),
    ("tchat_reads", "obj_follow",
     "SELECT d.room_id, d.user_id FROM tchat_reads d JOIN tchat_rooms r ON r.id=d.room_id JOIN users u ON u.id=d.user_id WHERE d.muted <> 0",
     "SELECT ref_id, user_id FROM obj_follow WHERE kind='tchat' AND mode='mute'"),
    ("tchat_thread_reads", "obj_seen",
     "SELECT t.root_id, t.user_id FROM tchat_thread_reads t JOIN tchat_msgs m ON m.id=t.root_id JOIN users u ON u.id=t.user_id WHERE t.last_id > 0",
     "SELECT ref_id, user_id FROM obj_seen WHERE kind='tchat_thread'"),
    ("tchat_thread_reads", "obj_follow",
     "SELECT t.root_id, t.user_id FROM tchat_thread_reads t JOIN tchat_msgs m ON m.id=t.root_id JOIN users u ON u.id=t.user_id WHERE t.follow <> 0",
     "SELECT ref_id, user_id FROM obj_follow WHERE kind='tchat_thread' AND mode='watch'"),
    # stage Q9a / Q9b (#5285, #5287, core/objfollow.py ofl_move, core/objnotifcap.py ncap_move): following, bells, templates
    ("task_watchers", "obj_follow",
     "SELECT w.task_id, w.user_id FROM task_watchers w JOIN tasks t ON t.id=w.task_id JOIN users u ON u.id=w.user_id",
     "SELECT ref_id, user_id FROM obj_follow WHERE kind='task' AND mode='watch'"),
    ("task_bell", "obj_follow",
     "SELECT b.task_id, b.user_id FROM task_bell b JOIN tasks t ON t.id=b.task_id JOIN users u ON u.id=b.user_id",
     "SELECT ref_id, user_id FROM obj_follow WHERE kind='task' AND mode IN ('list', 'mute', 'urgent')"),
    ("list_bell", "obj_follow",
     "SELECT b.list_id, b.user_id FROM list_bell b JOIN lists l ON l.id=b.list_id JOIN users u ON u.id=b.user_id",
     "SELECT ref_id, user_id FROM obj_follow WHERE kind='list'"),
    ("list_notif", "obj_notif_cap",
     "SELECT n.list_id, n.user_id FROM list_notif n JOIN lists l ON l.id=n.list_id",
     "SELECT ref_id, user_id FROM obj_notif_cap WHERE kind='list' AND path=''"),
    ("folder_notif", "obj_notif_cap",
     "SELECT n.owner_id, n.folder, n.user_id FROM folder_notif n JOIN users u ON u.id=n.owner_id",
     "SELECT ref_id, path, user_id FROM obj_notif_cap WHERE kind='folder'"),
    # stage Q10 (#5288, core/tplmove.py tpl_move)
    ("section_templates", "templates",
     "SELECT user_id, name FROM section_templates",
     "SELECT owner_id, name FROM templates WHERE kind='sections'"),
    # #5880 (core/liststate.py lst_move): the archive of a project -> the state marker (core/access.py list_archived_sql)
    ("lists.archived", "lists.state",
     "SELECT id, CASE WHEN COALESCE(CAST(archived AS text), '0') IN ('0', 'false', 'f') THEN 0 ELSE 1 END FROM lists",
     "SELECT id, CASE WHEN state='archived' OR (state='trash' AND archived_at IS NOT NULL) THEN 1 ELSE 0 END FROM lists"),
]

_REBUILT = "a search index, no data: rebuilt from its source at the start / by the watchdog (core/objsearch.py, core/objwords.py)"
_CHECKED = "a start check of its own drops it only when no row is left (core/kernretire.py kern_retire and the areas' *_retire)"
_DEAD = "no data any more: the feature was taken out / nothing read it (the fragment's drop-ok line)"
OTHER = {
    "task_fts": _REBUILT, "cmt_fts": _REBUILT, "contacts.search": _REBUILT,
    "doc_words": _REBUILT, "file_words": _REBUILT, "wiki_words": _REBUILT, "hub_words": _REBUILT,
    "ntfy_inboxes": _DEAD, "office_undo": _DEAD, "paperless_links": _DEAD,
    "tchat_members": _CHECKED, "ev_cal_members": _CHECKED, "book_members": _CHECKED, "folder_people": _CHECKED,
    "group_shares": _CHECKED, "wiki_versions": _CHECKED, "office_trash": _CHECKED,
    "wiki_shares.core_id": _CHECKED, "wiki_shares.core_id2": _CHECKED, "sheet_shares.core_id": _CHECKED,
    "playbooks.version": _CHECKED, "playbooks.body": _CHECKED, "playbooks.source": _CHECKED, "playbooks.author_id": _CHECKED,
    "playbooks.created_at": _CHECKED, "office_procdocs.version": _CHECKED, "office_procdocs.data": _CHECKED,
    "office_procdocs.created_by": _CHECKED, "office_procdocs.created_at": _CHECKED,
}


def drop_ok_keys(root=FRAGMENTS):
    """{table[.column]: fragment} of every drop-ok line of migrations.d."""
    out = {}
    for f in sorted(os.listdir(root)):
        if f.endswith(".py"):
            with open(os.path.join(root, f), encoding="utf-8") as fh:
                for m in DROP_OK.finditer(fh.read()):
                    out.setdefault(m.group(1), f)
    return out


def guard(root=FRAGMENTS):
    """-> (missing, stale): drop-ok keys without an entry here, entries without a drop-ok line (a typo / a removed fragment)."""
    keys = drop_ok_keys(root)
    known = {m[0] for m in MOVES} | set(OTHER)
    missing = sorted(f"{k} ({f})" for k, f in keys.items() if k not in known)
    stale = sorted(k for k in known if k not in keys)
    return missing, stale


def _has(q):
    def has(table, column=None):
        if column is None:
            return bool(q("SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name=?", (table,)))
        return bool(q("SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name=? AND column_name=?",
                      (table, column)))
    return has


def _keys(q, sql):
    return {tuple(str(v) if v is not None else None for v in r) for r in q(sql)}


def before(q):
    """Before the start: {index of MOVES: set of key tuples} for every old table / column still there. A query that fails is
    kept as its error text (the suite names it: this table's entry does not fit the old schema)."""
    has, out = _has(q), {}
    for i, (old, _target, sql, _new) in enumerate(MOVES):
        t, _, col = old.partition(".")
        if not has(t, col or None):
            continue
        try:
            out[i] = _keys(q, sql(has) if callable(sql) else sql)
        except Exception as e:  # noqa: BLE001 - reported by the suite
            out[i] = f"old query failed: {str(e)[-300:]}"
    return out


def after(q, got):
    """After the start: [(label, n to move, missing key tuples | error text)] for the entries of before()."""
    res = []
    for i, keys in sorted(got.items()):
        old, target, _sql, new = MOVES[i]
        label = f"{old} -> {target}"
        if isinstance(keys, str):
            res.append((label, 0, keys))
            continue
        try:
            have = _keys(q, new)
        except Exception as e:  # noqa: BLE001
            res.append((label, len(keys), f"new query failed: {str(e)[-300:]}"))
            continue
        res.append((label, len(keys), sorted(keys - have, key=str)))
    return res
