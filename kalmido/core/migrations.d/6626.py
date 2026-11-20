"""(#6626): the end of a ticket's status link (portal_tickets.revoked_at, kalmido/team/portal.py): the team ended the link at the
task (the page /p/<token> is the one 404 at once; a new link clears it). The link also ends 90 days after the task was done
(derived from tasks.completed_at, PT_LINK_DAYS: reopened = valid again), so no expiry column. New nullable column: an older
version ignores it."""
MIGRATIONS = [
    ("portal_tickets", "revoked_at", "ALTER TABLE portal_tickets ADD COLUMN IF NOT EXISTS revoked_at TIMESTAMPTZ"),
]
