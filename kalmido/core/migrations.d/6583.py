"""#6583: the warnings of an account import, whole (no cut at UMZ_WARN_MAX): imports.warnings = [{text: [key, *values],
count}] in the order of the run (the ones it must name first). The import's report file (GET /api/imports/<id>/report)
reads them after the upload folder is gone. New column with a default: an older version ignores it."""
MIGRATIONS = [
    ("imports", "warnings", "ALTER TABLE imports ADD COLUMN IF NOT EXISTS warnings JSONB NOT NULL DEFAULT '[]'"),
]
