#!/usr/bin/env python3
# kalmido-suite: fresh nodata
"""(#6872, rest of #6560 point 7): the "last four characters" of server agents' API keys (agent_server.key_hint) and of
newsletter tokens (nl_conns.hint) that rows from before 2.1322.0 kept in plain text are emptied once at the start
(core/oncesteps.py migr_hint6872, flag migr_hint6872). One-way: the hints are gone, the sealed key / token stays untouched.
 - rows with an old hint (one personal, one of a person without an organisation) -> after a restart both are empty, the sealed
   value and the other columns unchanged, the flag set
 - a second start does not run it again (flag), a hint written after it (hand-made) stays
 - the server agent's key field no longer promises "its last four characters" (static/js/srvagent.js)
usage: p6872_hint_purge_test.py <datadir>      (needs restarts: no NOSTART)"""
import os
import sys

import kt
from kt import B, check, dbx, me_id
from freelancer_fixture import freelancer

N = os.path.dirname(os.path.abspath(__file__))
kt.fresh(prefix="P6872")
kt.docker_logs_on_first_fail()
A = kt.setup()
AID = me_id(A)
FID, Fr = freelancer(B, A)

# rows as a version before 2.1322.0 left them (FK to users only; the sealed value is a stand-in, never opened here)
dbx("INSERT INTO agent_server(agent_id, key_sealed, key_hint) VALUES(?, 'SEALED-A', 'wxyz')", (AID,))
dbx("INSERT INTO agent_server(agent_id, key_sealed, key_hint) VALUES(?, 'SEALED-F', 'qrst')", (FID,))
dbx("INSERT INTO nl_conns(owner_id, ws, kind, secret, hint, created_at, updated_at) "
    "VALUES(?, 'p6872:u', 'brevo', 'SEALED-NL', '…9a8b', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)", (FID,))
dbx("DELETE FROM settings WHERE key='migr_hint6872'")
check(dbx("SELECT COUNT(*) FROM agent_server WHERE key_hint<>''")[0][0] == 2 and dbx("SELECT hint FROM nl_conns WHERE ws='p6872:u'")[0][0],
      "setup: two agent rows and one newsletter connection with an old hint")

kt.fresh(keep=True, prefix="P6872")
rows = dbx("SELECT agent_id, key_hint, key_sealed FROM agent_server ORDER BY agent_id")
check(sorted((r[1], r[2]) for r in rows) == [("", "SEALED-A"), ("", "SEALED-F")],
      f"#6872: the start empties every key_hint, the sealed key stays {rows}")
nl = dbx("SELECT hint, secret, kind FROM nl_conns WHERE ws='p6872:u'")
check(nl and tuple(nl[0]) == ("", "SEALED-NL", "brevo"), f"#6872: the newsletter connection's hint is empty, its token stays {nl}")
check([tuple(r) for r in dbx("SELECT value FROM settings WHERE key='migr_hint6872'")] == [("1",)],
      "#6872: the one-shot's flag is set")

dbx("UPDATE agent_server SET key_hint='hand' WHERE agent_id=?", (AID,))
kt.fresh(keep=True, prefix="P6872")
check(dbx("SELECT key_hint FROM agent_server WHERE agent_id=?", (AID,))[0][0] == "hand", "#6872: a second start does not run the step again")

with open(os.path.join(os.path.dirname(N), "static", "js", "srvagent.js"), encoding="utf-8") as f:
    js = f.read()
check("last four characters" not in js, "#6872: the key field's hint names no last four characters any more")

sys.exit(kt.done("p6872_hint_purge"))
