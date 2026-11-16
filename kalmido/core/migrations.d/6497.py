"""2.1271.0 (#6497): the support access a sign-in link was made through (user_invites.grant_id, set when it is made) and the
support session started with it (sessions.grant_id, inherited from the link). A session with a grant_id holds only while exactly
that grant is open (accounts/session.py authenticate); the support mark follows from it, not from the maker's admin right today.
NULL = no support link / an ordinary session. New nullable columns only: an older version ignores them. Support sessions and
links from before (via 'support' / an operator's link without grant_id) are refused in the code (supportgrant.py), no rows go."""
MIGRATIONS = [
    ("user_invites", "grant_id", "ALTER TABLE user_invites ADD COLUMN grant_id BIGINT REFERENCES support_grants(id) ON DELETE CASCADE"),
    ("sessions", "grant_id", "ALTER TABLE sessions ADD COLUMN grant_id BIGINT REFERENCES support_grants(id) ON DELETE CASCADE"),
]
AFTER = [
    "CREATE INDEX IF NOT EXISTS user_invites_grant ON user_invites(grant_id) WHERE grant_id IS NOT NULL",
    "CREATE INDEX IF NOT EXISTS sessions_grant ON sessions(grant_id) WHERE grant_id IS NOT NULL",
]
