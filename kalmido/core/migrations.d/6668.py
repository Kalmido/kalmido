"""2.1348.0 (#6668): agents.per_request -- a team agent with its own token works per request (agents/reqtoken.py): set with its
first request token (for good), its long-lived token then reaches only its own channel. A new column
with a default only: an older version ignores it (its team agents keep their whole reach, as before)."""
MIGRATIONS = [
    ("agents", "per_request", "ALTER TABLE agents ADD COLUMN IF NOT EXISTS per_request BOOLEAN NOT NULL DEFAULT false"),
]
