"""2.1384.0 (#6700): the clients of an invoice issuer (office/issclients.py). clients.issuer_id = the issuer (office_issuers) that
set the client up through its key, external_ref = the outside system's own id of it (the key reaches the client only by it,
PUT / GET /api/v1/issuer/clients/by-ref/<external_ref>); unique per issuer (not per organisation: a personal office's clients
carry org_id NULL). issuer_hold = the hold mark (JSON: the fields the key set or changed, old -> new, when): while it stands,
finalising and sending need a person's explicit confirmation and every sending without a dialog is refused (office/isshold.py);
only a person takes it away. Nullable columns and a partial index of them only: an older version ignores all of it (it would
not refuse a send while a mark stands; the mark stays and works again after the way forward)."""
MIGRATIONS = [
    ("clients", "issuer_id", "ALTER TABLE clients ADD COLUMN IF NOT EXISTS issuer_id BIGINT"),  # no FK: a revoked issuer's row stays, its clients keep the id
    ("clients", "external_ref", "ALTER TABLE clients ADD COLUMN IF NOT EXISTS external_ref TEXT"),
    ("clients", "issuer_hold", "ALTER TABLE clients ADD COLUMN IF NOT EXISTS issuer_hold TEXT"),
]
AFTER = [
    # unique-ok ix6700_clients_issuer_ref: both columns are new (NULL in every existing row) and the index takes only rows with an external_ref
    "CREATE UNIQUE INDEX IF NOT EXISTS ix6700_clients_issuer_ref ON clients(issuer_id, external_ref) WHERE external_ref IS NOT NULL",
]
