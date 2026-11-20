"""(#6500): did a sign-in ask for "Stay signed in" (sessions.remember, written by start_session; a support session FALSE)? The
client keeps its offline copies only then (accounts/session.py session_remember). The sessions of before get it once from
core/oncesteps.d/6500.py. New nullable column: an older version ignores it."""
MIGRATIONS = [
    ("sessions", "remember", "ALTER TABLE sessions ADD COLUMN IF NOT EXISTS remember BOOLEAN"),
]
