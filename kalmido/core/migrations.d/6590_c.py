"""2.1315.0 (#6590 c): one imported old document (office_archive, office/archiveedit.py) goes into the core's trash (kind
oarchive, office/okern.py ofk_register, core/writes.py obj_trash): the columns the core writes when a row goes into the trash or
comes back (deleted_at, deleted_by, rev, updated_by) and trash_number (its number, freed while it lies in the trash). New
nullable / defaulted columns only: an older version ignores them (it shows a trashed entry with an empty number)."""
MIGRATIONS = [
    ("office_archive", "deleted_at", "ALTER TABLE office_archive ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ"),
    ("office_archive", "deleted_by", "ALTER TABLE office_archive ADD COLUMN IF NOT EXISTS deleted_by BIGINT"),
    ("office_archive", "rev", "ALTER TABLE office_archive ADD COLUMN IF NOT EXISTS rev BIGINT NOT NULL DEFAULT 1"),
    ("office_archive", "updated_by", "ALTER TABLE office_archive ADD COLUMN IF NOT EXISTS updated_by BIGINT"),
    ("office_archive", "trash_number", "ALTER TABLE office_archive ADD COLUMN IF NOT EXISTS trash_number TEXT NOT NULL DEFAULT ''"),
]
AFTER = [
    "CREATE INDEX IF NOT EXISTS ix6590_office_archive_trash ON office_archive(deleted_at) WHERE deleted_at IS NOT NULL",
]
