"""2.1325.0 (#6502): obj_history.via = how a change was made when that is not the person's own hand: 'support' = in a support
session of the person's account (accounts/supportgrant.py, the operator working as the client); NULL = the person (or an agent,
its own column). The history shows such an entry as done by support. support_grants.uses_dropped = how many of the grant's
oldest log entries went beyond the log's limits (sga_flush: readings above SGA_USES_MAX, changes only above SGA_CHANGES_MAX);
the client sees the number. New columns only: an older version ignores them."""
MIGRATIONS = [
    ("obj_history", "via", "ALTER TABLE obj_history ADD COLUMN IF NOT EXISTS via TEXT"),
    ("support_grants", "uses_dropped", "ALTER TABLE support_grants ADD COLUMN IF NOT EXISTS uses_dropped INTEGER NOT NULL DEFAULT 0"),
]
