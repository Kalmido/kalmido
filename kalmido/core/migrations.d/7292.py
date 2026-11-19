"""#7292: a client's locations -- clients.parent_id = the main client a location (itself a normal client with its own address,
currency, e-invoice, contact persons, projects and documents) belongs to. One level only (a main client has no main client of
its own), the main client in the same workspace (team/clients.py cl_parent_check). The main client deleted for good: SET NULL,
the location stays a client of its own. New nullable column: an older version ignores it."""
MIGRATIONS = [
    ("clients", "parent_id", "ALTER TABLE clients ADD COLUMN IF NOT EXISTS parent_id BIGINT REFERENCES clients(id) ON DELETE SET NULL"),
]
AFTER = [
    "CREATE INDEX IF NOT EXISTS ix7292_clients_parent ON clients(parent_id)",
]
