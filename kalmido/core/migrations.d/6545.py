"""2.1333.0 (#6545): the fetching of a workspace mailbox (hub/mailbox.py). hub_mailboxes.ok_at = the last successful fetch
(polled_at stays the last attempt), told_at = when its owners last heard of the outage (again after 3 days while it lasts),
mailed_at (review F1) = when its owners last got the outage by e-mail (never reset by saving or a check: at most one
mail per mailbox in 3 days), skipped / skipped_at = how many mails were left in the mailbox as too large (or without a size) and when the last one was.
New columns only: an older version ignores them (it fetches on every round and tells once, as before)."""
MIGRATIONS = [
    ("hub_mailboxes", "ok_at", "ALTER TABLE hub_mailboxes ADD COLUMN IF NOT EXISTS ok_at TIMESTAMPTZ"),
    ("hub_mailboxes", "told_at", "ALTER TABLE hub_mailboxes ADD COLUMN IF NOT EXISTS told_at TIMESTAMPTZ"),
    ("hub_mailboxes", "mailed_at", "ALTER TABLE hub_mailboxes ADD COLUMN IF NOT EXISTS mailed_at TIMESTAMPTZ"),
    ("hub_mailboxes", "skipped", "ALTER TABLE hub_mailboxes ADD COLUMN IF NOT EXISTS skipped BIGINT NOT NULL DEFAULT 0"),
    ("hub_mailboxes", "skipped_at", "ALTER TABLE hub_mailboxes ADD COLUMN IF NOT EXISTS skipped_at TIMESTAMPTZ"),
]
