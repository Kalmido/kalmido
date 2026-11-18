#!/usr/bin/env python3
# kalmido-suite: fresh
"""2.1381.0 (#6592): the household rule "everyone sees everyone" (accounts/orgs.py _visible_people: a server without any
organisation the instance admin made) never applies on a hosted server (KALMIDO_HOSTED=1). There people without a company
see only themselves and their connections, whatever organisations exist - the separation no longer hangs on the operator's
organisation existing. Invented names only.
freelancer-matrix: team (two people without an organisation on a hosted server do not see each other)
 - a hosted server without any organisation the admin made: two people without a company do not see each other in
   GET /api/users, each sees herself
 - a company one of them made herself (self_made) changes nothing for the other one
usage: p21381_6592_hosted_household_test.py <datadir>      (KMT_NOSTART=1 / P21381H_NOSTART=1: a running server)"""
import sys

from kt import B, check, dbx, docker_logs_on_first_fail, done, fresh
from freelancer_fixture import freelancer

fresh(env={"KALMIDO_HOSTED": "1"}, prefix="P21381H")
docker_logs_on_first_fail()
import kt  # noqa: E402
A = kt.setup()


def seen(s):
    r = s.get(B + "/api/users")
    check(r.ok, f"GET /api/users answers ({r.status_code})")
    return {u["username"] for u in r.json().get("users", [])}


check(dbx("SELECT COUNT(*) FROM orgs WHERE personal_of IS NULL AND retired_at IS NULL AND self_made=0") == [(0,)],
      "setup: a hosted server without an organisation the admin made")
FID, Fr = freelancer(B, A, "frida")
GID, Gr = freelancer(B, A, "gerd")
sf, sg = seen(Fr), seen(Gr)
check("frida" in sf and "gerd" in sg, f"each one sees herself {sf} {sg}")
check("gerd" not in sf, f"#6592: frida does not see gerd on a hosted server {sf}")
check("frida" not in sg, f"#6592: gerd does not see frida on a hosted server {sg}")

# a company frida makes herself (self_made) does not turn gerd's view into the household either
r = Fr.post(B + "/api/orgs", json={"name": "Frida Studio"})
if r.ok:
    sg = seen(Gr)
    check("frida" not in sg, f"#6592: a self-made company changes nothing for gerd {sg}")

sys.exit(done("p21381_6592_hosted_household"))
