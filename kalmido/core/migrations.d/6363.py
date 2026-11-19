"""2.1409.0 (#6363): the Kalmido AI (server agent) per organisation - orgs.srv_agents, 1 = its admin switched it on.
Default 0 = off: a server agent of the organisation does not run and no content of the organisation goes to the model provider
(agents/srvagent.py srv_org_on). Organisations that already used it keep it on once (core/oncesteps.py migr_srvorg6363).
A column with a default only: an older version ignores it (its server agents run as before)."""
MIGRATIONS = [
    ("orgs", "srv_agents", "ALTER TABLE orgs ADD COLUMN IF NOT EXISTS srv_agents BIGINT NOT NULL DEFAULT 0"),
]
