"""2.1269.0 (#6451): agent_rules.card_id = the chat line (agent_chat, kind 'rule') in which the person of a rule's source confirms
or rejects a rule the agent proposed (state 'proposed', agents/agentrules.py). NULL = a rule a person added by hand, or one from
before. A nullable column only: an older version ignores it (and never counts a proposed rule as active)."""
AFTER = [  # agent_rules is made by core/schema.py after the steps (#4300): the column comes in AFTER
    # the chat keeps only its newest lines (agents/chat.py chat_add trims them); a trimmed card leaves the id behind and the
    # proposal then shows in the settings only (the owner can delete it there). no FK: trimmed chat lines
    "ALTER TABLE agent_rules ADD COLUMN IF NOT EXISTS card_id BIGINT",
]
