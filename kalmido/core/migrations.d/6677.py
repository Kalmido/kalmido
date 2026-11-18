"""2.1375.0 (#6677, review F1-F3): who last wrote a task's title (title_by) and its description (content_by), kept on the task
itself so that a purge of the history (dataretention, activity after ret_days("logs")) cannot make a rewritten task the
creator's again. NULL = nobody changed it since it was created (the creator's text), 0 = a hand without a person (an inbound
webhook, a public link, CalDAV, a list rule, a support session, the git issue sync, a merge of other people's text), else the
account. Set where the history line is written (tasks/validation.py log_act) and where texts are written without one
(collab/liste2e.py le2a_task_set). No foreign key on purpose: a deleted writer must stay "someone else", ON DELETE SET NULL
would turn the text into the creator's again. The API gives both as updated_by; older versions ignore the columns."""
MIGRATIONS = [
    ("tasks", "title_by", "ALTER TABLE tasks ADD COLUMN IF NOT EXISTS title_by BIGINT"),
    ("tasks", "content_by", "ALTER TABLE tasks ADD COLUMN IF NOT EXISTS content_by BIGINT"),
]
