"""2.1321.0 (#6555): the webhook state of a document flow (doc_rules, docs/flows.py fl_hook_off). hook_state '' = the webhook
goes out; 'failures' = switched off after its last retry failed (the flow's other actions run on); 'admin' = the flow paused
because its author is no admin of the workspace any more. hook_fails = failed calls in a row (a delivered call empties it),
hook_error / hook_error_at = the last failure, shown at the flow. Saving the flow again empties hook_state.
New columns with defaults: an older version ignores them."""
MIGRATIONS = [
    ("doc_rules", "hook_state", "ALTER TABLE doc_rules ADD COLUMN IF NOT EXISTS hook_state TEXT NOT NULL DEFAULT ''"),
    ("doc_rules", "hook_fails", "ALTER TABLE doc_rules ADD COLUMN IF NOT EXISTS hook_fails INTEGER NOT NULL DEFAULT 0"),
    ("doc_rules", "hook_error", "ALTER TABLE doc_rules ADD COLUMN IF NOT EXISTS hook_error TEXT NOT NULL DEFAULT ''"),
    ("doc_rules", "hook_error_at", "ALTER TABLE doc_rules ADD COLUMN IF NOT EXISTS hook_error_at TIMESTAMPTZ"),
]
