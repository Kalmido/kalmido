"""2.1315.0 (#6403, part 3): rc_receipts was only indexed on node_id (primary key) and list_id, but the office reads and writes it
by area (ws=?) and by the invoice a receipt was billed on (billed_doc_id=?), e.g. office/docs.py, office/outlays.py,
receipts/suggest.py: every such statement scanned the receipts of every organisation. ws gets its own index; billed_doc_id a
partial one (most receipts were never billed). New indexes only: the version before ignores them."""
AFTER = [
    "CREATE INDEX IF NOT EXISTS ix6403_rc_receipts_ws ON rc_receipts(ws)",
    "CREATE INDEX IF NOT EXISTS ix6403_rc_receipts_billed ON rc_receipts(billed_doc_id) WHERE billed_doc_id IS NOT NULL",
]
