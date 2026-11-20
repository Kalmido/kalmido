"""(#6500): did a sign-in ask for "Stay signed in" (sessions.remember, written by start_session)? The client keeps its offline
copies only then (accounts/session.py session_remember). NULL = a session of an older version: read from its length as before.
New nullable column: an older version ignores it."""
MIGRATIONS = [
    ("sessions", "remember", "ALTER TABLE sessions ADD COLUMN IF NOT EXISTS remember BOOLEAN"),
]
