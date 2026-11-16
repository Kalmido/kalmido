"""2.1265.0 (#6389): a scheduled document flow that fails on one document no longer holds the tick for every workspace.
doc_flow_runs.fails = the failed tries in a row of that flow on that document (state 'error' while it keeps failing),
retry_at = Unix second of the next try (backoff as the calendar subscriptions). New columns with defaults only: an older
version ignores them (it reads only state 'done' rows and never retries an 'error' row)."""
MIGRATIONS = [
    ("doc_flow_runs", "fails", "ALTER TABLE doc_flow_runs ADD COLUMN IF NOT EXISTS fails BIGINT NOT NULL DEFAULT 0"),
    ("doc_flow_runs", "retry_at", "ALTER TABLE doc_flow_runs ADD COLUMN IF NOT EXISTS retry_at DOUBLE PRECISION NOT NULL DEFAULT 0"),
]
