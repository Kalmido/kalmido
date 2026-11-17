#!/usr/bin/env python3
# kalmido-suite: fresh
"""2.1327.0 (#6823): one reading of the module switches (core/access.py feat_has) behind every surface - the status codes
of each surface stay (API contract). A person WITHOUT an organisation (tests/freelancer_fixture.py) and her token:
 - modules on: web route of contacts (need_feat) 200, /api/state has her address book, API v1 time entries
   (v1_feature) 200, /api/v1/me features.time_tracking true
 - contacts and time off: the web route 409, /api/state books [] (contacts_on), API v1 time entries 403, /api/v1/me
   time_tracking false; the other switches (comments) unchanged
 - the value empty: every module off - 409 / 403, /api/v1/me all false (not the default)
 - no row: the instance default of USER_DEFAULTS (collaboration, time, contacts on: 200 / true)
 - on again: everything back
 - freelancer-matrix: contacts, time (web and API v1 of a person without an organisation)
usage: p21327_d_feathas_test.py <datadir>      (KMT_NOSTART=1 / P21327D_NOSTART=1: a running server)"""
import sys

import requests

from freelancer_fixture import FEATURES, freelancer
from kt import B, check, dbx, done, fresh, setup

V = B + "/api/v1"

fresh(prefix="P21327D")
A = setup()
A.patch(B + "/api/settings", json={"lang": "en", "tour": "done"})
FID, F = freelancer(B, A)
r = F.post(B + "/api/me/tokens", json={"name": "feat", "scopes": ["read", "time"]})
check(r.status_code in (200, 201), f"her token {r.status_code} {r.text[:120]}")
T = requests.Session()
T.headers.update({"Authorization": "Bearer " + r.json()["token"]})
r = F.post(B + "/api/books", json={"name": "Clients"})
check(r.status_code == 201, f"her address book {r.status_code} {r.text[:120]}")


def switches(v):
    """Her stored value of the setting "features" (None: no row - the instance default)."""
    if v is None:
        dbx("DELETE FROM user_settings WHERE user_id=? AND key='features'", (FID,))
    else:
        dbx("INSERT INTO user_settings(user_id,key,value) VALUES(?,'features',?) ON CONFLICT(user_id,key) DO UPDATE SET value=excluded.value",
            (FID, v))


def surfaces():
    st = F.get(B + "/api/state").json()
    me = T.get(V + "/me").json()["features"]
    return {"web": F.get(B + "/api/contacts/groups").status_code, "books": len(st.get("books") or []),
            "v1": T.get(V + "/time/entries").status_code, "time": me["time_tracking"], "collab": me["collaboration"],
            "comments": me["comments"]}


# ---- every module on (the fixture's FEATURES)
s = surfaces()
check(s["web"] == 200 and s["books"] >= 1, f"contacts on: the web route answers, /api/state has her address book {s}")
check(s["v1"] == 200 and s["time"] is True and s["comments"] is True, f"time on: API v1 time entries 200, /me says on {s}")

# ---- contacts and time off, the rest as it was
switches(",".join(x for x in FEATURES.split(",") if x not in ("contacts", "time")))
s = surfaces()
check(s["web"] == 409, f"contacts off: the web route 409 (need_feat) {s}")
check(s["books"] == 0, f"contacts off: no address book in /api/state (contacts_on) {s}")
check(s["v1"] == 403 and s["time"] is False, f"time off: API v1 403 (v1_feature), /me says off {s}")
check(s["comments"] is True and s["collab"] is True, f"the other switches stay {s}")

# ---- an empty value: everything off
switches("")
s = surfaces()
check(s["web"] == 409 and s["v1"] == 403 and s["books"] == 0, f"empty: every module off {s}")
check(not any((s["time"], s["collab"], s["comments"])), f"empty: /me all off, not the default {s}")

# ---- no row: the instance default
switches(None)
s = surfaces()
check(s["collab"] is True and s["time"] is True and s["web"] == 200 and s["v1"] == 200,
      f"no row: the instance default (USER_DEFAULTS: collaboration, time, contacts on) {s}")

# ---- on again
switches(FEATURES)
s = surfaces()
check(s["web"] == 200 and s["v1"] == 200 and s["books"] >= 1 and s["time"] is True, f"on again: everything back {s}")
sys.exit(done("p21327_d_feathas"))
