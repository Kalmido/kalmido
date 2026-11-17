"""2.1322.0 (#6560): two new columns, both ignored by an older version.
 - issue_hooks.paused_reason (point 4) = why the error-report webhook of a list is paused (integrations/errorreports.py
   ERR_PAUSE: 'creator' = the person who switched it on has no access to the project any more, 'role' = can no longer change
   it). NULL = working; switching it on or a new URL by a list admin empties it (that admin becomes its creator). An older
   version takes reports again, as before.
 - hub_mailboxes.docs_pos (point 2) = where the document rules of a mailbox stand in each folder (hub/mailrules.py mbr_run):
   JSON {folder: {uid: the highest UID looked at with every one below it done, sig: the state of the folder's rules, val: the
   folder's UIDVALIDITY, left: how many mails are not looked at yet}}. Empty = from the oldest mail within the rules' age. An
   older version looks at the newest 200 mails, as before."""
MIGRATIONS = [
    ("issue_hooks", "paused_reason", "ALTER TABLE issue_hooks ADD COLUMN IF NOT EXISTS paused_reason TEXT"),
    ("hub_mailboxes", "docs_pos", "ALTER TABLE hub_mailboxes ADD COLUMN IF NOT EXISTS docs_pos TEXT NOT NULL DEFAULT ''"),
]
