"""(#7325): doc_meta.area_to = the office a document of the general input was brought in for ('' = none was clear |
'private' = the own office | 'org:<id>'), written once by docs/ingest.py docs_ingest and only read by the queue
(docs/area.py ar_sort_queued). doc_meta.area_sort gets the value 'ask' (a recognised invoice without a clear office: it stays in
the own documents and "New in the office" offers it to the person). A new column only: older versions ignore it."""
MIGRATIONS = [
    ("doc_meta", "area_to", "ALTER TABLE doc_meta ADD COLUMN IF NOT EXISTS area_to TEXT NOT NULL DEFAULT ''"),
]
