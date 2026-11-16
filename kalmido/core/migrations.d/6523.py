"""2.1294.0 (#6523, review F1): where a task came from. tasks.origin = 'person' only when its creator wrote it in the app or with
their own access token (tasks/tasks.py task_create); a webhook, a mail to a list or the inbox, a form, an import, a git sync,
an error report and tasks from before 2.1294.0 leave it empty. The API gives it as by_creator; the agent dispatcher of the app
builds only such tasks. A new column without a default value; older versions ignore it."""
MIGRATIONS = [
    ("tasks", "origin", "ALTER TABLE tasks ADD COLUMN IF NOT EXISTS origin TEXT"),
]
