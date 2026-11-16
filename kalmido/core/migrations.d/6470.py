"""2.1287.0 (#6470): the name of the person behind an office log entry (office_doc_log.user_name), written with the entry
(office/ledger.py ofx_log_name) and sealed like its detail (core/orgcrypt.py FIELDS). user_id stays ON DELETE SET NULL: a
deleted account keeps its name in the log for the retention period (GoBD: who changed what when; decided 16.11.2026). The
entries from before are filled once from users (office/ledger.py ofx_log_names_fill). New column only: an older version
ignores it."""
MIGRATIONS = [
    ("office_doc_log", "user_name", "ALTER TABLE office_doc_log ADD COLUMN IF NOT EXISTS user_name TEXT NOT NULL DEFAULT ''"),
]
