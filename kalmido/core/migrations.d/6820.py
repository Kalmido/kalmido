"""(#6820): the delivery state of a document's e-mail (office/mailstate.py): office_docs.mail_state none | sent | failed |
bounced and office_docs.mail_at, the time of the last change. sent / failed are set by Kalmido when it hands the mail to the
mail server, bounced by a person of the office (the menu "Delivery failed"). Free columns of a finalised document
(migrations.d/4598.py). New columns with a default / nullable only: an
older version ignores them."""
MIGRATIONS = [
    ("office_docs", "mail_state", "ALTER TABLE office_docs ADD COLUMN IF NOT EXISTS mail_state TEXT NOT NULL DEFAULT 'none'"),
    ("office_docs", "mail_at", "ALTER TABLE office_docs ADD COLUMN IF NOT EXISTS mail_at TIMESTAMPTZ"),
]
