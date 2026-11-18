"""2.1386.0 (#6668): agents.per_request -- a team agent with its own token works per request (agents/reqtoken.py): set with its
first request token (for good), its long-lived token then reaches only its own channel. api_tokens.req_slot (review F4): the
place of a request token (kind + asking computer, agents/reqtoken.py req_slot). New columns with a default only: an older
version ignores them (its team agents keep their whole reach, as before)."""
MIGRATIONS = [
    ("agents", "per_request", "ALTER TABLE agents ADD COLUMN IF NOT EXISTS per_request BOOLEAN NOT NULL DEFAULT false"),
    ("api_tokens", "req_slot", "ALTER TABLE api_tokens ADD COLUMN IF NOT EXISTS req_slot TEXT NOT NULL DEFAULT ''"),
]
