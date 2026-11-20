"""(#6332): a chat message sent again with its client_id is found at any time (collab/teamchat.py csd_dup, was: within 10
seconds over the conversation's newest rows) - one index per table on the conversation and the id. New indexes only: the version
before ignores them."""
AFTER = [
    "CREATE INDEX IF NOT EXISTS ix6332_tchat_msgs_cid ON tchat_msgs(room_id, client_id) WHERE client_id IS NOT NULL",
    "CREATE INDEX IF NOT EXISTS ix6332_agent_chat_cid ON agent_chat(agent_id, client_id) WHERE client_id IS NOT NULL",
]
