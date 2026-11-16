"""2.1306.0 (#6554, audit #4804 D2/D5): the issue sync's way out is bounded per connection and day, and the person whose token
a connection uses is known. git_conns: token_by = the account that stored the token (connect / PATCH token; NULL on rows from
before = created_by counts, integrations/git.py git_token_owner); out_day = the UTC day the counters below belong to ('' = none
yet), out_issues / out_comments = issues / comments the sync created in the repository that day, out_told = the day the
connector was told that a limit held (once a day). An older version ignores the columns."""
MIGRATIONS = [
    ("git_conns", "token_by", "ALTER TABLE git_conns ADD COLUMN IF NOT EXISTS token_by BIGINT"),
    ("git_conns", "out_day", "ALTER TABLE git_conns ADD COLUMN IF NOT EXISTS out_day TEXT NOT NULL DEFAULT ''"),
    ("git_conns", "out_issues", "ALTER TABLE git_conns ADD COLUMN IF NOT EXISTS out_issues BIGINT NOT NULL DEFAULT 0"),
    ("git_conns", "out_comments", "ALTER TABLE git_conns ADD COLUMN IF NOT EXISTS out_comments BIGINT NOT NULL DEFAULT 0"),
    ("git_conns", "out_told", "ALTER TABLE git_conns ADD COLUMN IF NOT EXISTS out_told TEXT NOT NULL DEFAULT ''"),
]
