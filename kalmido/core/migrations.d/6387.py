"""2.1265.0 (#6387): office_inv_series.fail_count = watchdog runs of the series that failed in a row (office/recurring.py
rin_failed); the third pauses the series with a task, a made period sets it back to 0. New column with a default only: an
older version ignores it."""
MIGRATIONS = [
    ("office_inv_series", "fail_count", "ALTER TABLE office_inv_series ADD COLUMN IF NOT EXISTS fail_count BIGINT NOT NULL DEFAULT 0"),
]
