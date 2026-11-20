#!/usr/bin/env python3
# kalmido-suite: after=p2501_a_nosham nodata
"""2.1458.0 (#6593): tools/check_umz_v.py. Static, no container.
 - a fragment that drops or renames a column of a table of the account export: red while UMZ_V is not above the record;
   raised: red until --update records it; recorded: quiet
 - a DROP DEFAULT / DROP NOT NULL / DROP CONSTRAINT, a table rename, a docstring's sentence, a table outside the export: no step
 - UMZ_V lower than the record: red; the repository: no finding
usage: check_umz_v_test.py"""
import os
import sys

from kt import FAILS, OKS, check

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "tools"))
import check_umz_v as cu  # noqa: E402

T = {"lists", "contacts"}
DROP = ("9999_a.py", 'MIGRATIONS = [\n    "ALTER TABLE lists DROP COLUMN IF EXISTS colour",\n]\n')
RENAME = ("9999_b.py", 'AFTER = ["ALTER TABLE contacts RENAME COLUMN fn TO full_name"]\n')
QUIET = ("9999_c.py", '"""Once ALTER TABLE lists DROP COLUMN old happens, see below."""\n'
         'AFTER = ["ALTER TABLE lists ALTER COLUMN note DROP DEFAULT, ALTER COLUMN note DROP NOT NULL",\n'
         '         "ALTER TABLE lists DROP CONSTRAINT lists_x", "ALTER TABLE lists RENAME TO lists2",\n'
         '         "ALTER TABLE rss_items DROP COLUMN read_at"]  -- ALTER TABLE lists DROP COLUMN in_a_comment\n')

now = cu.steps([DROP, RENAME, QUIET], T)
check(now == {"9999_a.py: lists.colour drop", "9999_b.py: contacts.fn rename"}, f"a drop and a rename are steps, nothing else {sorted(now)}")
bad, _n = cu.findings(now, 1, 1, set())
check(len(bad) == 2 and all("raise UMZ_V" in b for b in bad), f"new steps with UMZ_V as recorded: red {bad}")
bad, _n = cu.findings(now, 2, 1, set())
check(len(bad) == 1 and "--update" in bad[0], f"UMZ_V raised: red until recorded {bad}")
bad, notes = cu.findings(now, 2, 2, set(now))
check(not bad and not notes, f"recorded: quiet {bad} {notes}")
bad, notes = cu.findings(set(), 2, 2, set(now))
check(not bad and len(notes) == 2, f"a recorded step that is gone: a note only {bad} {notes}")
bad, _n = cu.findings(set(now), 1, 2, set(now))
check(bad and "never goes down" in bad[0], f"UMZ_V below the record: red {bad}")
check(cu.main([]) == 0, "the repository: no finding")
print(f"check_umz_v: {OKS[0]} ok, {len(FAILS)} failed")
sys.exit(1 if FAILS else 0)
