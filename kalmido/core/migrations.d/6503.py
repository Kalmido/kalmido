"""2.1385.0 (#6503 6): the lock of a kid's PIN grows (family/pin.py): kid_pins.locks = how many locks in a row since the last
right PIN; each further lock doubles the time (from PIN_LOCK up to PIN_LOCK_MAX), a right PIN or a new PIN starts at 0 again.
New column with a default only: an older version ignores it and locks for PIN_LOCK as before."""
MIGRATIONS = [
    ("kid_pins", "locks", "ALTER TABLE kid_pins ADD COLUMN IF NOT EXISTS locks BIGINT NOT NULL DEFAULT 0"),
]
