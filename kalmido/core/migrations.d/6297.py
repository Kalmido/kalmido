"""(#6297 3, audit #4741): who put a team chat message into the trash (tchat_msgs.deleted_by, like
obj_comments.deleted_by): its author may restore only what they deleted themselves, a delete by a list owner / channel
manager stays theirs to undo. New nullable column only: an older version ignores it."""
MIGRATIONS = [
    # no FK: who put it into the trash (the account may be gone by then), like obj_comments.deleted_by
    ("tchat_msgs", "deleted_by", "ALTER TABLE tchat_msgs ADD COLUMN IF NOT EXISTS deleted_by BIGINT"),
]
