"""2.1398.0 (#6883): a project that leaves its workspace keeps the invoice reference of its billed time.
time_entries.billed_moved_doc_id / billed_moved_item_id = the finalised document (and position) an entry was billed on in
the office the project left (office/timebill.py tbill_list_moved); the project comes back -> billed_doc_id / billed_item_id
again. New nullable columns only, no foreign key (like billed_item_id, #3012): an older version ignores them and shows the
entry "billed in an earlier organisation" as before."""
MIGRATIONS = [
    ("time_entries", "billed_moved_doc_id", "ALTER TABLE time_entries ADD COLUMN IF NOT EXISTS billed_moved_doc_id BIGINT"),  # no FK: a finalised document of another office, checked on return (#6883)
    ("time_entries", "billed_moved_item_id", "ALTER TABLE time_entries ADD COLUMN IF NOT EXISTS billed_moved_item_id BIGINT"),  # no FK: its position, like billed_item_id (#3012)
]
