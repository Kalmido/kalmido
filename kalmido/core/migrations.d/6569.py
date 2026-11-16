"""2.1292.0 (#6569): agent_server.wait_note = the newest event of the last "waits for a free place" note of a server agent
(agents/srvagent_run.py _wait_note): the people who asked are told once per wait, not on every try. 0 = no note yet. New column
with a default only: an older version ignores it."""
MIGRATIONS = [
    ("agent_server", "wait_note", "ALTER TABLE agent_server ADD COLUMN IF NOT EXISTS wait_note BIGINT NOT NULL DEFAULT 0"),
]
