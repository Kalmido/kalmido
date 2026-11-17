"""2.1313.0 (#6557): users.drop_agent = may the upload token (/drop) also send messages to the person's agents (form field
`to`): 1 = on, 0 = off (every new token starts off: accounts/tokenhash.py tkh_set_drop, core/db.py create_user). NULL = a
token from before this step: it keeps what it could do (on) and the person is told once that it can be switched off
(core/tokenhash.py drop_agent_of); after the hint it becomes 1. Nullable without a default on purpose: the rows that exist
are the ones from before, no UPDATE needed. An older version ignores the column; the way back is ALTER TABLE users DROP
COLUMN drop_agent."""
MIGRATIONS = [
    ("users", "drop_agent", "ALTER TABLE users ADD COLUMN drop_agent SMALLINT"),
]
