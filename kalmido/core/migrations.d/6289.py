"""(#6289): kalmido_otg_rekey (5275_a.py) renames the once-markers ltag:<id> of the own rules of My tasks when a project tag gets a
new id - by key, over this index instead of the whole table. New index only: the version before ignores it."""
AFTER = [
    "CREATE INDEX IF NOT EXISTS ix6289_user_mine_rule_runs_key ON user_mine_rule_runs(key)",
]
