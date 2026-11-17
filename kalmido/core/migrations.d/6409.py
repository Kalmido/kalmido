"""2.1315.0 (#6409): the idempotency keys are tidied by the watchdog (core/idem.py idem_prune, hourly) instead of in every
write request with a key: one DELETE of the keys older than IDEM_DAYS over this index, then the cap per person. New index
only: the version before ignores it (it still tidies in the request)."""
AFTER = [
    "CREATE INDEX IF NOT EXISTS ix6409_idem_keys_created ON idem_keys(created_at)",
]
