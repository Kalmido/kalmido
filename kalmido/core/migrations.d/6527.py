"""#6527: the office rights group a NEW member of an organisation starts with (office/rights.py ofr_join_default, called by
accounts/orgs.py org_member_add and the role changes). orgs.office_new_tpl = the key of a built-in group (TEMPLATES), '' = no
row, the implicit "Previous access" as before 2.187. A company a person creates herself (POST /api/orgs, every hosted customer)
gets 'staff' from now on: a member sees only their own receipts, travel, drives, entertainment receipts and times in the office
until its admins give more. Organisations of before keep '' (an update changes nothing).
New defaulted column: an older version ignores it (its new members then start on "Previous access" again)."""
MIGRATIONS = [
    ("orgs", "office_new_tpl", "ALTER TABLE orgs ADD COLUMN IF NOT EXISTS office_new_tpl TEXT NOT NULL DEFAULT ''"),
]
