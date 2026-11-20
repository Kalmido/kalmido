"""#6405 (decided 16.11.2026): the indexes the file store's read of "what may this account see" (files/store.py
fs_visible_sql_c) and its trash list ask for. fs_nodes(owner_id): the arm "own nodes" of every level (fs_nodes_owner holds
only the tops, WHERE parent_id IS NULL); fs_nodes(org_id) WHERE org_access IN ('view', 'edit'): the arm "everyone in the
organisation" folders, without reading every node of the organisation; fs_nodes(deleted_at) WHERE deleted_at IS NOT NULL:
the trash list newest first (files/web.py fs_trash_entries) over the nodes in the trash only. The old indexes stay.
Plain CREATE INDEX (the start runs schema and fragments in one transaction, CONCURRENTLY is not allowed there); indexes
only: an older version ignores them."""
AFTER = [
    "CREATE INDEX IF NOT EXISTS ix6405_fs_nodes_owner ON fs_nodes(owner_id)",
    "CREATE INDEX IF NOT EXISTS ix6405_fs_nodes_org_access ON fs_nodes(org_id) WHERE org_access IN ('view', 'edit')",
    "CREATE INDEX IF NOT EXISTS ix6405_fs_nodes_trash ON fs_nodes(deleted_at) WHERE deleted_at IS NOT NULL",
]
