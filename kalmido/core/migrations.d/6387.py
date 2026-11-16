"""2.1265.0 (#6387): office_inv_series.fail_count = watchdog runs of the series that failed in a row (office/recurring.py
rin_failed); the third pauses the series with a task, a made period sets it back to 0. mail_doc = the series invoice whose
customer mail is still due (set in the invoice's own commit, cleared once mailed or told; NULL = none), mail_try = 1 once the
one more try of the next run (rin_catchup) began. New columns, nullable or with a default only: an older version ignores them."""
MIGRATIONS = [
    ("office_inv_series", "fail_count", "ALTER TABLE office_inv_series ADD COLUMN IF NOT EXISTS fail_count BIGINT NOT NULL DEFAULT 0"),
    ("office_inv_series", "mail_doc", "ALTER TABLE office_inv_series ADD COLUMN IF NOT EXISTS mail_doc BIGINT"),
    ("office_inv_series", "mail_try", "ALTER TABLE office_inv_series ADD COLUMN IF NOT EXISTS mail_try BIGINT NOT NULL DEFAULT 0"),
]
