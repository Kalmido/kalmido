"""(#7534): agent_chat.intent = the kind of a person's message to the agent: question | instruction | proposal | note (NULL =
none chosen, as before; agents/chat.py chat_post, the same values as a comment's extra.intent, core/objcomments.py OCM_INTENTS).
New column only: an older version ignores it."""
MIGRATIONS = [
    ("agent_chat", "intent", "ALTER TABLE agent_chat ADD COLUMN IF NOT EXISTS intent TEXT"),
]
