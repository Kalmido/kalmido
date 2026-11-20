"""(#6342): an absence gets a version (hub/absence.py abs_edit): its dialog sends the updated_at it read back as
expect_updated_at and another device's change in between is a 409 instead of being overwritten. A row of before has none
(NULL): its version is its created_at until the first change. New nullable column: an older version ignores it."""
MIGRATIONS = [
    ("hub_absences", "updated_at", "ALTER TABLE hub_absences ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ"),
]
