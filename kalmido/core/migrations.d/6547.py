"""(#6547): returned mails (delivery reports) are matched to the mail Kalmido sent by its Message-ID (integrations/mail.py
mail_bounce_take). office_docs.mail_msg_id = the Message-ID of the document's last mail, office_docs.mail_why = the status
code of a returned one ('5.1.1'; the state itself stays office_docs.mail_state 'bounced', #6820); office_letters.mail_state
'' | bounced with mail_why / mail_at (its Message-ID is office_letters.msg_id since #2029); user_invites.msg_id = the
Message-ID of the invitation mail. hub_mails keeps its message_id and says 'bounced' in send_state (no column). New columns
with a default / nullable only: an older version ignores them."""
MIGRATIONS = [
    ("office_docs", "mail_msg_id", "ALTER TABLE office_docs ADD COLUMN IF NOT EXISTS mail_msg_id TEXT NOT NULL DEFAULT ''"),
    ("office_docs", "mail_why", "ALTER TABLE office_docs ADD COLUMN IF NOT EXISTS mail_why TEXT NOT NULL DEFAULT ''"),
    ("office_letters", "mail_state", "ALTER TABLE office_letters ADD COLUMN IF NOT EXISTS mail_state TEXT NOT NULL DEFAULT ''"),
    ("office_letters", "mail_why", "ALTER TABLE office_letters ADD COLUMN IF NOT EXISTS mail_why TEXT NOT NULL DEFAULT ''"),
    ("office_letters", "mail_at", "ALTER TABLE office_letters ADD COLUMN IF NOT EXISTS mail_at TIMESTAMPTZ"),
    ("user_invites", "msg_id", "ALTER TABLE user_invites ADD COLUMN IF NOT EXISTS msg_id TEXT NOT NULL DEFAULT ''"),
]
AFTER = [
    "CREATE INDEX IF NOT EXISTS office_docs_mail_msg ON office_docs(mail_msg_id) WHERE mail_msg_id <> ''",
    "CREATE INDEX IF NOT EXISTS user_invites_msg ON user_invites(msg_id) WHERE msg_id <> ''",
    "CREATE INDEX IF NOT EXISTS hub_mails_out_msg ON hub_mails(message_id) WHERE direction = 'out'",
]
