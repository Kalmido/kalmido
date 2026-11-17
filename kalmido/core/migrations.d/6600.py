"""2.1337.0 (#6600): the move of an organisation (accounts/orgmove.py, core/movelock.py): orgs.moving_at = since when it is moving
(NULL = not), moving_by = the admin who switched it on, moving_by_name = their name then (shown to every member in the bar, also
after the account went), moving_why = the reason they gave. New nullable / defaulted columns only: an older version ignores them
(its triggers, made by core/movelock.py at the start, let everything through while no organisation is moving)."""
MIGRATIONS = [
    ("orgs", "moving_at", "ALTER TABLE orgs ADD COLUMN IF NOT EXISTS moving_at TIMESTAMPTZ"),
    ("orgs", "moving_by", "ALTER TABLE orgs ADD COLUMN IF NOT EXISTS moving_by BIGINT"),
    ("orgs", "moving_by_name", "ALTER TABLE orgs ADD COLUMN IF NOT EXISTS moving_by_name TEXT NOT NULL DEFAULT ''"),
    ("orgs", "moving_why", "ALTER TABLE orgs ADD COLUMN IF NOT EXISTS moving_why TEXT NOT NULL DEFAULT ''"),
]
