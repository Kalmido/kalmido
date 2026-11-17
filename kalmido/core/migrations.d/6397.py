"""2.1321.0 (#6397): indexes for the scopes of the shared search index obj_search (core/objsearch.py osr_scope_*): every
reader narrows to its own rows over an index before the words are tested and ranked (audit #4765: the GIN index alone read
and ranked the hits of every organisation). ix6397_obj_search_org: (kind, org_ref) with NULL (private rows) for the scope of
the row-level security's organisations (osr_scope_org; ix5278_obj_search_org leaves the NULL rows out and has no kind);
ix6397_obj_search_owner: (kind, owner_id) for an agent chat's person (osr_scope_owner); ix6397_obj_search_names: the rows with
names (a task's ticket key, a contact's names, a bookmark's site) for the second arm of osr_ids_sql(names=True), which tests
the part of a word with LIKE. Indexes only: an older version ignores them."""
AFTER = [
    "CREATE INDEX IF NOT EXISTS ix6397_obj_search_org ON obj_search(kind, org_ref)",
    "CREATE INDEX IF NOT EXISTS ix6397_obj_search_owner ON obj_search(kind, owner_id) WHERE owner_id IS NOT NULL",
    "CREATE INDEX IF NOT EXISTS ix6397_obj_search_names ON obj_search(kind, node_id) WHERE names <> ''",
]
