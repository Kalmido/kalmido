"""(#7528): "Confirm as an order" -- a decider's yes to the text of a task (tasks/boundyes.py, kind "confirm"): who, when and
the text state it belongs to (one hash per text: title | description). New nullable columns and a partial index: an older
version ignores them (its writes of title / description leave the hash behind, so the yes reads as ended -- never as given to
a text it did not see)."""
MIGRATIONS = [
    ("tasks", "confirmed_by", "ALTER TABLE tasks ADD COLUMN IF NOT EXISTS confirmed_by BIGINT REFERENCES users(id) ON DELETE SET NULL"),
    ("tasks", "confirmed_at", "ALTER TABLE tasks ADD COLUMN IF NOT EXISTS confirmed_at TIMESTAMPTZ"),
    ("tasks", "confirmed_sig", "ALTER TABLE tasks ADD COLUMN IF NOT EXISTS confirmed_sig TEXT"),
]
AFTER = [
    "CREATE INDEX IF NOT EXISTS ix7528_tasks_confirmed_by ON tasks(confirmed_by) WHERE confirmed_by IS NOT NULL",
]
