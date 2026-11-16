"""2.1269 (#6386): a fetched mail is tried at most MAIL_TRIES times instead of being taken as final at once
(integrations/mail.py mail_fetch). mail_in_seen gets the state of its attempt: tries (how many started), state ('done' = taken
in or for nobody, 'open' = an attempt started and was not finished: the next round tries again, 'gave' = given up after the
last try, the mail stays in the mailbox) and imap_uid (the UID to fetch it again). Rows from before stay 'done' (the default);
an older version keeps inserting rows that count as done and ignores the columns."""
MIGRATIONS = [
    ("mail_in_seen", "tries", "ALTER TABLE mail_in_seen ADD COLUMN IF NOT EXISTS tries BIGINT NOT NULL DEFAULT 0"),
    ("mail_in_seen", "state", "ALTER TABLE mail_in_seen ADD COLUMN IF NOT EXISTS state TEXT NOT NULL DEFAULT 'done'"),
    ("mail_in_seen", "imap_uid", "ALTER TABLE mail_in_seen ADD COLUMN IF NOT EXISTS imap_uid TEXT"),
]
AFTER = [
    "CREATE INDEX IF NOT EXISTS ix6386_mail_in_seen_open ON mail_in_seen(box) WHERE state='open'",
]
