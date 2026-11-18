"""2.1396.0 (#6701): the invoice drafts of an invoice issuer (office/issdocs.py). office_docs.issuer_id = the issuer (office_issuers)
whose key made the draft (kept for good; a correction a person makes of it inherits it, a copy never), issuer_wish = what the
outside system asked for along with it (payment, sending, due date, bank account, its VAT and business checks, the sums it
expected): an unconfirmed statement, sealed as one text with the area's key (core/orgcrypt.py FIELDS), never printed; issuer_rev =
the fingerprints of what the key delivered (the document with its positions, the client's fields): the key's PDF preview only
while they still match (a person's change: 409 edited_by_human). office_docs.ref_sha256 = the hash of an agent's draft request
with its client_ref (office/agentdocs.py): the same ref with another body is 409 ref_conflict. Nullable columns and a partial
index only: an older version ignores all of it."""
MIGRATIONS = [
    ("office_docs", "issuer_id", "ALTER TABLE office_docs ADD COLUMN IF NOT EXISTS issuer_id BIGINT"),  # no FK: a revoked issuer's row stays, its documents keep the id
    ("office_docs", "issuer_wish", "ALTER TABLE office_docs ADD COLUMN IF NOT EXISTS issuer_wish TEXT"),  # coltype-ok: sealed as one text ("kenc1:...") when the area's encryption is on
    ("office_docs", "issuer_rev", "ALTER TABLE office_docs ADD COLUMN IF NOT EXISTS issuer_rev TEXT"),  # coltype-ok: two SHA-256 fingerprints as JSON text, compared as a whole, never queried
    ("office_docs", "ref_sha256", "ALTER TABLE office_docs ADD COLUMN IF NOT EXISTS ref_sha256 TEXT"),
]
AFTER = [
    "CREATE INDEX IF NOT EXISTS ix6701_office_docs_issuer ON office_docs(issuer_id, updated_at) WHERE issuer_id IS NOT NULL",
]
