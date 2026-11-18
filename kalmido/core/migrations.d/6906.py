"""2.1391.0 (#6906): attachments.outside = 1 for a file that came from a source a stranger can fill (a mail, a public form):
its name was typed outside Kalmido, although user_id names the owner whose storage it counts against. The API then gives no
uploader (by) but untrusted: true, and the MCP fences the name as data. New column with a default only: an older version
ignores it."""
MIGRATIONS = [
    ("attachments", "outside", "ALTER TABLE attachments ADD COLUMN IF NOT EXISTS outside SMALLINT NOT NULL DEFAULT 0"),
]
