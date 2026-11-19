"""(#6951, Fable review of job/5128 F1): a queue row remembers whether the request that added it met the lock of a moving
organisation (core/movelock.py mv_strict_now) - bg_jobs.strict. The worker runs such a row inside mv_strict, so the background
work a writing request starts (emptying a big trash) never writes into a moving organisation; the export's own row (added after
mv_allow) stays free. New column with a default: an older version ignores it (its rows run free, as before)."""
AFTER = [
    "ALTER TABLE bg_jobs ADD COLUMN IF NOT EXISTS strict BOOLEAN NOT NULL DEFAULT false",
]
