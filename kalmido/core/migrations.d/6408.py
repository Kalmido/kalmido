"""(#6408): the usage of an agent per calendar month (local time) as ONE counter row, written with every usage report
(agents/usage.py usage_month_add) - the limit check of every agent API call reads it instead of summing the month's reports. The
first report of a month starts the row from the reports already there (so it also starts right in the middle of a month); a
month without a row is summed from the reports as before. New table only: an older version ignores it (its reports are then
missing from the row of that month; such a row is started again by deleting it). Two partial indexes for the unread agent
answers of a person and the waiting jobs."""
SCHEMA = """
CREATE TABLE IF NOT EXISTS agent_usage_month (
  agent_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE, month TEXT NOT NULL,
  input_tokens BIGINT NOT NULL DEFAULT 0, output_tokens BIGINT NOT NULL DEFAULT 0, cache_read_tokens BIGINT NOT NULL DEFAULT 0,
  cache_write_tokens BIGINT NOT NULL DEFAULT 0, cost_usd DOUBLE PRECISION, calls BIGINT NOT NULL DEFAULT 0,
  PRIMARY KEY (agent_id, month));
"""
MIGRATIONS = []
AFTER = [
    # the unread answers of agents per person (state / the Agents view / opening a chat: agents/core.py, agents/chat.py chat_read)
    "CREATE INDEX IF NOT EXISTS ix6408_agent_chat_unread ON agent_chat(user_id, agent_id) WHERE sender='agent' AND read_at IS NULL",
    # the waiting jobs, newest first (agents/waiting.py _jobs)
    "CREATE INDEX IF NOT EXISTS ix6408_agent_jobs_waiting ON agent_jobs(updated_at DESC, id DESC) WHERE state='waiting'",
]
