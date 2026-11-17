"""2.1322.0 (#6560 4): issue_hooks.paused_reason = why the error-report webhook of a list is paused (integrations/errorreports.py
ERR_PAUSE: 'creator' = the person who switched it on has no access to the project any more, 'role' = can no longer change it).
NULL = working; switching it on or a new URL by a list admin empties it (that admin becomes its creator). New column, nullable:
an older version ignores it (and takes reports again, as before)."""
MIGRATIONS = [
    ("issue_hooks", "paused_reason", "ALTER TABLE issue_hooks ADD COLUMN IF NOT EXISTS paused_reason TEXT"),
]
