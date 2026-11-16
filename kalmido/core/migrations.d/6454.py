"""2.1287.0 (#6454): the run of a team agent works with the rights of the person who asked (agents/srvteam.py srv_run_cut).
api_tokens.asked_by: NULL = an ordinary token; a person's id = the run token of a team agent working for that person;
0 = a team agent's run without a person (a project's own automation). api_tokens.run_lists: the projects of that run (csv,
'' = none; NULL = no cut) -- the agent's own projects cut to the person's (core/access.py token_lists). New columns only: an
older version ignores them (its run tokens have the agent's whole reach, as before)."""
MIGRATIONS = [
    ("api_tokens", "asked_by", "ALTER TABLE api_tokens ADD COLUMN IF NOT EXISTS asked_by BIGINT"),
    ("api_tokens", "run_lists", "ALTER TABLE api_tokens ADD COLUMN IF NOT EXISTS run_lists TEXT"),
]
