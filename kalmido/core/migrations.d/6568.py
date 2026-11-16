"""2.1308.0 (#6568): runs of a server agent nobody asked for (a form, the mail inbox, a webhook, listening in: no person behind
its events). agent_runs.no_person / agent_usage.no_person mark them: on a hosted server they count against their own share of the
agent's day limit (agents/srvteam.py srv_nobody_block). New columns with a default only; older versions ignore them."""
MIGRATIONS = [
    ("agent_runs", "no_person", "ALTER TABLE agent_runs ADD COLUMN IF NOT EXISTS no_person BOOLEAN NOT NULL DEFAULT FALSE"),
    ("agent_usage", "no_person", "ALTER TABLE agent_usage ADD COLUMN IF NOT EXISTS no_person BOOLEAN NOT NULL DEFAULT FALSE"),
]
AFTER = [
    "CREATE INDEX IF NOT EXISTS ix6568_agent_usage_nobody ON agent_usage(agent_id, day) WHERE no_person",
]
