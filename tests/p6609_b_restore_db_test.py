#!/usr/bin/env python3
"""2.1431.0 (#6609, audit #4817 finding 1): the restore script of update.sh --restore (RESTORE_SQL of install.sh) for real, in
the database container of the test group, on a database of its own (p6609, removed at the end; the app's database is untouched).
The case of the audit: a copy of the "old version", then the "new version" adds a table with a foreign key to users, a column
and rows. The bare pg_restore --clean of the old docs trips over that key (shown, not judged: it is the old way); the script
empties the schema and loads the copy in one transaction: the old state comes back exactly (newer table and column gone,
extension unaccent there again, the rows of the copy), and a cut copy changes nothing at all."""
# kalmido-suite: after=p2273_a_backup
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kt  # noqa: E402
from kt import check, done  # noqa: E402

with open(os.path.join(kt.DATA, ".kalmido-db"), encoding="utf-8") as f:
    DBC = f.read().split()[0]
with open(os.path.join(ROOT, "install.sh"), encoding="utf-8") as f:
    SH = f.read()
r = subprocess.run(["sh", "-c", '. /dev/stdin; printf "%s" "$RESTORE_SQL"'], input=SH.rstrip()[:-len('main "$@"')], capture_output=True, text=True)
RESTORE_SQL = r.stdout
check(r.returncode == 0 and "DROP SCHEMA public CASCADE" in RESTORE_SQL, f"the restore script of install.sh: {r.stderr[:200]}")
DB = "p6609"


def ex(cmd, inp=None, db=DB):
    """sh -c CMD in the database container with POSTGRES_DB=db; -> CompletedProcess (bytes)."""
    return subprocess.run(["docker", "exec", "-i", "-e", f"POSTGRES_DB={db}", DBC, "sh", "-c", cmd], input=inp, capture_output=True, timeout=300)


def sql(q):
    r = ex('psql -X -q -t -A -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB"', q.encode())
    if r.returncode:
        raise RuntimeError(r.stderr.decode(errors="replace"))
    return r.stdout.decode().strip()


ex('dropdb --if-exists -U "$POSTGRES_USER" p6609', db="postgres")
r = ex('createdb -U "$POSTGRES_USER" p6609', db="postgres")
check(r.returncode == 0, f"a database of its own: {r.stderr[:200]}")
try:
    # ---- the "old version"
    sql("""CREATE EXTENSION IF NOT EXISTS unaccent;
CREATE TABLE kalmido_meta (key text PRIMARY KEY, value text);
CREATE TABLE users (id int PRIMARY KEY, name text NOT NULL);
CREATE TABLE tasks (id int PRIMARY KEY, user_id int NOT NULL REFERENCES users(id), title text);
INSERT INTO kalmido_meta VALUES ('app_version', '2.1300.0');
INSERT INTO users VALUES (1, 'alice'), (2, 'bob');
INSERT INTO tasks VALUES (10, 1, 'Grüße'), (11, 2, 'zwei');""")
    r = ex('PGOPTIONS="-c app.role=system" pg_dump -Fc --enable-row-security -U "$POSTGRES_USER" -d "$POSTGRES_DB"')
    copy = r.stdout
    check(r.returncode == 0 and copy[:5] == b"PGDMP", f"the copy of update.sh (pg_dump -Fc): {r.stderr[:200]}")

    def newer():
        """the "new version": a table with a key to users, a column, rows, a newer stamp"""
        sql("""CREATE TABLE IF NOT EXISTS obj_comments (id int PRIMARY KEY, user_id int NOT NULL REFERENCES users(id), body text);
ALTER TABLE tasks ADD COLUMN IF NOT EXISTS done boolean DEFAULT false;
INSERT INTO users VALUES (3, 'carol') ON CONFLICT DO NOTHING;
INSERT INTO obj_comments VALUES (100, 3, 'after the update') ON CONFLICT DO NOTHING;
UPDATE kalmido_meta SET value='2.1431.0' WHERE key='app_version';""")
    newer()

    # ---- the old way of the docs (only shown: the cause of the audit)
    old = ex('PGOPTIONS="-c app.role=system" pg_restore --clean --if-exists --no-owner --no-privileges --single-transaction '
             '--enable-row-security -U "$POSTGRES_USER" -d "$POSTGRES_DB"', copy)
    print(f"   info: the old pg_restore --clean: exit {old.returncode}: {old.stderr.decode(errors='replace').strip()[:300]}", flush=True)
    newer()  # whatever the old way did (it is one transaction), the newer state again

    # ---- update.sh --restore: the script
    r = ex(RESTORE_SQL, copy)
    out = r.stdout.decode(errors="replace")
    check(re.search(r"^kalmido-restore-ok$", out, re.M) is not None, f"the restore went through (last line): {out[-200:]} {r.stderr[-400:]}")
    check(sql("SELECT to_regclass('public.obj_comments') IS NULL") == "t", "the newer table (key to users) is gone")
    check(sql("SELECT count(*) FROM information_schema.columns WHERE table_name='tasks' AND column_name='done'") == "0", "the newer column is gone")
    check(sql("SELECT string_agg(id || ':' || name, ',' ORDER BY id) FROM users") == "1:alice,2:bob", "the users of the copy, carol gone")
    check(sql("SELECT string_agg(id || ':' || user_id || ':' || title, ',' ORDER BY id) FROM tasks") == "10:1:Grüße,11:2:zwei", "the tasks of the copy")
    check(sql("SELECT value FROM kalmido_meta WHERE key='app_version'") == "2.1300.0", "the version stamp of the copy (the version before starts)")
    check(sql("SELECT unaccent('Café')") == "Cafe", "the extension unaccent is back")
    check(sql("SELECT count(*) FROM pg_constraint WHERE conname='tasks_user_id_fkey'") == "1", "the foreign keys of the copy are back")
    check(sql("SELECT pg_get_userbyid(nspowner) FROM pg_namespace WHERE nspname='public'") == "pg_database_owner", "public belongs to pg_database_owner as before")

    # ---- a cut copy: nothing changes
    newer()
    r = ex(RESTORE_SQL, copy[:len(copy) // 2])
    out = r.stdout.decode(errors="replace")
    check("kalmido-restore-ok" not in out, f"a cut copy does not go through: {r.stderr[-300:]}")
    check(sql("SELECT count(*) FROM obj_comments") == "1" and sql("SELECT count(*) FROM users") == "3"
          and sql("SELECT value FROM kalmido_meta WHERE key='app_version'") == "2.1431.0",
          "a cut copy: the database is exactly as before (the transaction never committed)")
    # ---- a broken statement in the middle: nothing changes either
    r = ex(RESTORE_SQL, b"PGDMP not really a dump")
    check("kalmido-restore-ok" not in r.stdout.decode(errors="replace") and sql("SELECT count(*) FROM users") == "3",
          "an unreadable copy: no change")
finally:
    ex('dropdb --if-exists -U "$POSTGRES_USER" p6609', db="postgres")

sys.exit(done("p6609_b_restore_db"))
