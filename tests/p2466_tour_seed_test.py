#!/usr/bin/env python3
# kalmido-suite: fresh
"""2.466.0 (#3314) API: the areas' introductions and accounts that exist already.
 - a start changes nothing in tours_seen (2.1380.0 #6826: the start's one-shot that marked areas with content as opened,
   migr_tours2466, is retired)
 - KALMIDO_ONBOARDING=0: a new account has them off (tours_more 0), tours_seen takes only a list of ids
freelancer-matrix: onboarding (alice has no organisation)
usage: p2466_tour_seed_test.py <datadir>"""
import os
import subprocess
import sys

import requests

import kt
from kt import B, check, sess

kt.fresh()
kt.setup("alice")
A = sess("alice")
s = A.get(B + "/api/state").json()["settings"]
check(s["tours_more"] == "0" and s["tours_seen"] == "", "KALMIDO_ONBOARDING=0: introductions off, nothing seen")
check(A.patch(B + "/api/settings", json={"tours_seen": "cal,office"}).ok, "tours_seen: a list of ids")
check(A.patch(B + "/api/settings", json={"tours_seen": "cal;<x>"}).status_code == 400, "tours_seen: nothing else")
check(A.patch(B + "/api/settings", json={"tours_seen": "a," * 200}).status_code == 400, "tours_seen: not endless")
A.patch(B + "/api/settings", json={"tours_seen": ""})

# 2.1380.0 (#6826): an account with content (a journal entry) was set up here to be marked by the start's one-shot
CT = os.environ.get("KALMIDO_TEST_CONTAINER", "kalmido-test")


def restart():
    subprocess.run(["docker", "restart", CT], capture_output=True)
    def up():
        try:
            return requests.get(B + "/api/health", timeout=2).ok
        except requests.RequestException:
            return False
    check(kt.until(up, timeout=60), "the container is back")


def seen():
    return A.get(B + "/api/state").json()["settings"]["tours_seen"]


# 2.1380.0 (#6826): the start's one-shot (flag migr_tours2466 deleted, restart: the area with content counted as opened) is
# retired (core/oncesteps.py RETIRED), the start no longer runs it; what stays: a start keeps tours_seen as stored
A.patch(B + "/api/settings", json={"tours_seen": "review,cal"})
restart()
check(seen() == "review,cal", "a start changes nothing: " + seen())

sys.exit(kt.done("p2466_tour_seed"))
