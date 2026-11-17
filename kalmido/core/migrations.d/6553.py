"""2.1342.0 (#6553 3): the secret of a person's absences link (abs_cal_feeds, hub/abscal.py) is kept only as a SHA-256 hash, as
the event calendars' links (#4708 6, core/tokenhash.py). The plain column stays (NOT NULL, written '') so the version before
still runs on the database; core/tokenhash.py tkh_migrate turns the plain secrets left into hashes at every start, so existing
subscriptions keep working. New nullable column only."""
MIGRATIONS = [
    ("abs_cal_feeds", "secret_hash", "ALTER TABLE abs_cal_feeds ADD COLUMN IF NOT EXISTS secret_hash TEXT"),
]
