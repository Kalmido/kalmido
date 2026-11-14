"""2.1175.0 (#6165): "Recent steps" marks the steps written over a personal API key (Authorization: Bearer, api/v1.py) --
undo_groups.via = 'token' for such a step ('' = the app / a sync), set by kalmido/core/undogroups.py _open. The device of
such a step is the key's name. The list hides them unless the person shows them (user setting undo_show_api), and
"Undo up to here" leaves them where they are (kalmido/core/undoweb.py undo_group_to hide_api). New column only: older
versions ignore it."""
MIGRATIONS = [
    ("undo_groups", "via", "ALTER TABLE undo_groups ADD COLUMN IF NOT EXISTS via TEXT NOT NULL DEFAULT ''"),
]
