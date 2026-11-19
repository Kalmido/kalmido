"""(#6546): sending through a workspace mailbox's own SMTP (hub/mailbox.py mbx_send_result). hub_mailboxes.send_fails = failed
sends in a row (only a successful send sets it back, never a successful fetch: fails of the fetching is set back every round),
send_error = the code of the last failure ('' = the last send worked), send_error_at = since when sending fails (the first
failure of this outage), send_told_at = when its owners last heard of it (from MBX_SEND_FAILS failures in a row, again after
3 days while it lasts). New columns only: an older version ignores them (it counts nothing for sending, as before)."""
MIGRATIONS = [
    ("hub_mailboxes", "send_fails", "ALTER TABLE hub_mailboxes ADD COLUMN IF NOT EXISTS send_fails BIGINT NOT NULL DEFAULT 0"),
    ("hub_mailboxes", "send_error", "ALTER TABLE hub_mailboxes ADD COLUMN IF NOT EXISTS send_error TEXT NOT NULL DEFAULT ''"),
    ("hub_mailboxes", "send_error_at", "ALTER TABLE hub_mailboxes ADD COLUMN IF NOT EXISTS send_error_at TIMESTAMPTZ"),
    ("hub_mailboxes", "send_told_at", "ALTER TABLE hub_mailboxes ADD COLUMN IF NOT EXISTS send_told_at TIMESTAMPTZ"),
]
