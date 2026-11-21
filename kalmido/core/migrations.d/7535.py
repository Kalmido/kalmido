"""(#7535): tasks.retest_person = this task is retested by a person although its project's retest (lists.review_cfg retest) is a
review job of the starter (tasks/review.py action retest_person, set only by a person). New column with a default only: an
older version ignores it."""
MIGRATIONS = [
    ("tasks", "retest_person", "ALTER TABLE tasks ADD COLUMN IF NOT EXISTS retest_person BIGINT NOT NULL DEFAULT 0"),
]
