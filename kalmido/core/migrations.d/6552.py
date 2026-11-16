"""2.1271.0 (#6552): app_passwords.pw_ident = the id in front of an app password made since 2.1271 (calendars/caldav.py
apppw_new, "<8 symbols>-<secret>"), stored in clear: the DAV sign-in checks the one row of that id (one hash per request,
known name or not). NULL = a password made before (no id; still valid, checked as before). New column only: an older
version ignores it (it writes NULL and checks every row of the person, which still finds a password with an id)."""
MIGRATIONS = [
    ("app_passwords", "pw_ident", "ALTER TABLE app_passwords ADD COLUMN IF NOT EXISTS pw_ident TEXT"),
]
AFTER = [
    "CREATE INDEX IF NOT EXISTS ix6552_app_passwords_ident ON app_passwords(user_id, pw_ident) WHERE pw_ident IS NOT NULL",
]
