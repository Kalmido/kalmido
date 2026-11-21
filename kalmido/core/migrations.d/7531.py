"""(#7531): task_reports = who reported which task from the app ("Report a problem", integrations/meldung.py):
  task_id = the task the report made (the row goes with it); list_id = the project it went to (the chosen one at that time);
  reporter_id = the person who reported (the row goes with the account);
  kind = bug | wish; place = the page it was reported on (path only, no query); title = the reporter's own title (the reporter
  sees this and the state, never the task's later title - the task may lie in another organisation's project);
  created_at = when.
No organisation column: a row hangs on its task and project like form_entries; read only through the reporter (GET /api/reports).
New table only: an older version ignores it."""
SCHEMA = """
CREATE TABLE IF NOT EXISTS task_reports (  -- (#7531): who reported which task from the app, and where
  task_id BIGINT PRIMARY KEY REFERENCES tasks(id) ON DELETE CASCADE,
  list_id BIGINT NOT NULL REFERENCES lists(id) ON DELETE CASCADE,  -- the project the report went to (the workspace boundary)
  reporter_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  kind TEXT NOT NULL DEFAULT 'bug', place TEXT NOT NULL DEFAULT '', title TEXT NOT NULL DEFAULT '',
  created_at TIMESTAMPTZ NOT NULL);
CREATE INDEX IF NOT EXISTS ix7531_task_reports_reporter ON task_reports(reporter_id, created_at);
CREATE INDEX IF NOT EXISTS ix7531_task_reports_list ON task_reports(list_id);
CREATE INDEX IF NOT EXISTS ix7531_task_reports_place ON task_reports(place, created_at) WHERE place <> '';
"""
