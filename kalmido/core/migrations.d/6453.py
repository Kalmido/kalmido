"""2.1284.0 (#6453, Fable review G5): the circles of people a bridge was approved for. agent_bridges keeps, per approved
pair of projects, who read list_a (circle_a) and list_b (circle_b) at the moment of the approval -- the ids of the people,
sorted, comma separated ("3,7,12"). The approval holds only while both projects' circles of today lie inside them
(agents/circle.py bridge_holds): a person who joined later was never approved, so the share asks again
(agents/safety.py bridge_conflicts) and the control gate asks for a card. NULL = a row from before 2.1284 (or written by
an older version after a rollback): it holds nothing until the start step fills it with the circles of then
(agents/safety.py bridge_circles_start, core/objhooks.START, every start: only rows still NULL).
New columns only, nullable: an older version ignores them."""
MIGRATIONS = [
    ("agent_bridges", "circle_a", "ALTER TABLE agent_bridges ADD COLUMN IF NOT EXISTS circle_a TEXT"),
    ("agent_bridges", "circle_b", "ALTER TABLE agent_bridges ADD COLUMN IF NOT EXISTS circle_b TEXT"),
]
