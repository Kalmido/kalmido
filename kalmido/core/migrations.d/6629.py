"""2.1289.0 (#6629, #6576): office_inv_series.pause_why = why the watchdog or an import switched the series off (office/recurring.py
RIN_PAUSE_WHY): 'nobody' = paused because the area had no admin with the office on, its admin is told once there is one again
('nobody_told' after that); 'fails' / 'template' = paused with a task already; 'import' = arrived paused from an organisation
import (admin/oi_office.py _p_series), never a task. NULL = running or switched off by a person; switching it on empties it.
New column, nullable: an older version ignores it."""
MIGRATIONS = [
    ("office_inv_series", "pause_why", "ALTER TABLE office_inv_series ADD COLUMN IF NOT EXISTS pause_why TEXT"),
]
