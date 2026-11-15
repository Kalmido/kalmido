"""2.1239.0 (#6261): agent_chat.run_meta = which model wrote an agent's message ({model?, effort?, klasse?, grund?}, short
texts, agents/chat.py chat_run_meta): the app shows it as a small grey line under the bubble. NULL = none. New column only:
an older version ignores it."""
MIGRATIONS = [
    ("agent_chat", "run_meta", "ALTER TABLE agent_chat ADD COLUMN IF NOT EXISTS run_meta JSONB"),
]
