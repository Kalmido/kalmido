"""2.1407.0 (#6945): the PO number of a project (lists.po_number, at most 80 characters, '' = none). It flows into the order
reference of the project's documents (office_docs.order_ref) and back (kalmido/lists/projpo.py). New column with a default
only: an older version ignores it."""
MIGRATIONS = [
    ("lists", "po_number", "ALTER TABLE lists ADD COLUMN IF NOT EXISTS po_number TEXT NOT NULL DEFAULT ''"),
]
