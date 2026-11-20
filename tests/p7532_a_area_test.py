#!/usr/bin/env python3
# kalmido-suite: fresh
"""(#7532) API test: the approval for many images. Own container (start.sh, workspaces). Invented people and files only.
tenant-matrix: video
freelancer-matrix: videos
 - a comment marks an AREA: pos {x, y, w, h} (image) / {page, x, y, w, h} (PDF) is stored and comes back as it was; mark
   counts points and areas together (1, 2, 3 in order); an area outside the image (x + w > 1, y + h > 1), with one side
   only, without a corner, of size 0, w on a video or a negative value: 400, nothing stored
 - the old points stay as they were: {x, y} comes back without w / h, the export names the point's number as before
 - the open comments per approval (the overview's counter): open_comments counts the open top-level comments
 - many files at once through the API (POST /api/v1/videos, scope tasks:write): one approval per file at a task, its title
   (given or the file's name); all or none: one file of another workspace (409) or not an image (400) creates nothing;
   51 files 400, a client_id 400, a scope without tasks:write 403; an agent (level free) creates them at a project shared
   with it and reads them back
 - a person without an organisation: an area on her own image, the batch at her own task; a stranger 404
usage: p7532_a_area_test.py <datadir>      (P7532A_NOSTART=1: a running server, no start.sh)"""
import os
import struct
import subprocess
import sys
import time
import zlib

import requests

N = os.path.dirname(os.path.abspath(__file__))
DATA = sys.argv[1] if len(sys.argv) > 1 else os.path.join(N, ".data")
B = "http://127.0.0.1:" + os.environ.get("KALMIDO_TEST_PORT", "3048")
H = {"X-Requested-With": "kalmido"}
import kt  # noqa: E402
from kt import check, sess  # noqa: E402
from freelancer_fixture import freelancer  # noqa: E402
FEAT = "cal,comments,collab,videos,files"
V = "/api/videos"


def png(w=4, h=3, rgb=(30, 120, 200)):
    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xffffffff)
    raw = b"".join(b"\x00" + bytes(rgb) * w for _ in range(h))
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b"")


def up(s, place, name, data, mime="image/png"):
    return s.post(B + V, files={"file": (name, data, mime)}, data={k: str(v) for k, v in place.items()})


def store(s, name, data, mime="image/png", space=None):
    """A file in the file store (top level of the person's current workspace) -> its id."""
    r = s.post(B + "/api/files/upload", files={"file": (name, data, mime)}, data={"space": space} if space else {})
    assert r.ok, r.text[:300]
    j = r.json()
    return (j.get("items") or [j])[0]["id"]


def bearer(tok):
    s = requests.Session()
    s.headers.update({"Authorization": "Bearer " + tok, "X-Requested-With": "kalmido"})
    return s


if os.environ.get("P7532A_NOSTART") != "1":
    env = dict(os.environ, EXTRA=os.environ.get("EXTRA", "") + " -e KALMIDO_INSTANCE_MODE=workspaces")
    r = subprocess.run(["bash", os.path.join(N, "start.sh"), DATA], env=env, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    time.sleep(0.8)
s0 = requests.Session()
s0.headers.update(H)
assert s0.post(B + "/api/auth/setup", json={"username": "alice", "display_name": "Alice Admin", "password": "password123"}).ok
A = sess("alice")
A.post(B + "/api/admin/setup", json={"lang": "en", "collab_all": True})
A.patch(B + "/api/settings", json={"lang": "en", "features": FEAT, "tour": "done"})
ALICE = A.get(B + "/api/state").json()["me"]["id"]
ORG = A.post(B + "/api/admin/orgs", json={"name": "Alpha", "admin_id": ALICE}).json()["id"]
A.patch(B + "/api/settings", json={"workspace": f"org:{ORG}"})
L = A.post(B + "/api/lists", json={"name": "Website Relaunch", "org_id": ORG}).json()["id"]
T = A.post(B + "/api/tasks", json={"title": "Screens Rundgang", "list_id": L}).json()["id"]

# ---- an area on an image
r = up(A, {"task_id": T}, "start.png", png())
check(r.ok, f"an image approval at a task {r.status_code} {r.text[:200]}")
R = r.json()
RID, VER = R["id"], R["versions"][0]["id"]
P = f"{V}/{RID}/comments"
r1 = A.post(B + P, json={"version_id": VER, "pos": {"x": 0.1, "y": 0.2}, "body": "Logo kleiner"})
r2 = A.post(B + P, json={"version_id": VER, "pos": {"x": 0.25, "y": 0.3, "w": 0.5, "h": 0.4}, "body": "Dieser Block zu voll"})
r3 = A.post(B + P, json={"version_id": VER, "pos": {"x": 0.6, "y": 0.6}, "body": "Farbe"})
check(r1.ok and r2.ok and r3.ok, f"a point, an area, a point {r1.status_code} {r2.status_code} {r3.status_code} {r2.text[:200]}")
cs = {c["body"]: c for c in A.get(B + f"{V}/{RID}").json()["comments"]}
check(cs["Dieser Block zu voll"]["pos"] == {"x": 0.25, "y": 0.3, "w": 0.5, "h": 0.4}, f"the area comes back as it was {cs['Dieser Block zu voll'].get('pos')}")
check(cs["Logo kleiner"]["pos"] == {"x": 0.1, "y": 0.2} and "w" not in cs["Farbe"]["pos"], f"the points stay points (no w / h) {cs['Logo kleiner'].get('pos')}")
check([cs[b]["mark"] for b in ("Logo kleiner", "Dieser Block zu voll", "Farbe")] == [1, 2, 3], "mark counts points and areas together as before")
bad = [{"x": 0.6, "y": 0.1, "w": 0.5, "h": 0.2}, {"x": 0.1, "y": 0.7, "w": 0.2, "h": 0.4}, {"x": 0.1, "y": 0.1, "w": 0.2},
       {"w": 0.2, "h": 0.2}, {"x": 0.1, "y": 0.1, "w": 0, "h": 0.2}, {"x": 0.1, "y": 0.1, "w": -0.1, "h": 0.2},
       {"x": 0.1, "y": 0.1, "w": "0.2", "h": 0.2}, {"x": 0.1, "y": 0.1, "w": True, "h": 0.2}]
n0 = len(A.get(B + f"{V}/{RID}").json()["comments"])
codes = [A.post(B + P, json={"version_id": VER, "pos": p, "body": "x"}).status_code for p in bad]
check(codes == [400] * len(bad), f"an area outside the image / one side / no corner / size 0 / negative / text / bool: 400 {codes}")
check(len(A.get(B + f"{V}/{RID}").json()["comments"]) == n0, "nothing stored for the refused areas")
check(A.post(B + P, json={"version_id": VER, "pos": {"x": 0, "y": 0, "w": 1, "h": 1}, "body": "Ganzes Bild"}).ok, "the whole image as an area: ok (bounds 0..1)")
exp = A.get(B + f"{V}/{RID}/export?version_id={VER}")
check(exp.ok and "Logo kleiner" in exp.text, "the export still lists the comments")
# a video link takes no area
rv = A.post(B + V, json={"task_id": T, "url": "https://vimeo.com/76979871", "title": "Film"})
check(rv.ok and A.post(B + f"{V}/{rv.json()['id']}/comments", json={"pos": {"t": 3, "w": 0.1, "h": 0.1}, "body": "x"}).status_code == 400,
      "an area on a video: 400")
# the overview's counter: open top-level comments
A.patch(B + f"{P}/{cs['Farbe']['id']}", json={"done": True})
rows = A.get(B + f"{V}?task_id={T}").json()["reviews"]
img = next(x for x in rows if x["id"] == RID)
check(img["open_comments"] == 3 and img["kind"] == "image", f"open_comments counts the open ones (4 - 1 done) {img.get('open_comments')}")

# ---- many files at once (API)
tok = A.post(B + "/api/me/tokens", json={"name": "rundgang", "scopes": ["read", "tasks:write"]}).json().get("token")
ro = A.post(B + "/api/me/tokens", json={"name": "lesen", "scopes": ["read", "comments"]}).json().get("token")
K, RO = bearer(tok), bearer(ro)
F = [store(A, f"screen-{i}.png", png(rgb=(i * 40, 10, 10)), space=f"org:{ORG}") for i in range(1, 4)]
r = K.post(B + "/api/v1/videos", json={"task_id": T, "files": [{"file_id": F[0], "title": "Startseite"}, {"file_id": F[1]}, {"file_id": F[2]}]})
check(r.status_code == 201 and len(r.json().get("data", [])) == 3, f"three approvals in one call {r.status_code} {r.text[:300]}")
made = r.json().get("data", []) if r.status_code == 201 else []
check([x["title"] for x in made] == ["Startseite", "screen-2.png", "screen-3.png"] and all(x["kind"] == "image" for x in made),
      f"titles given or the file's name, kind image {[x.get('title') for x in made]}")
check(all(K.get(B + f"/api/v1/videos/{x['id']}").ok for x in made), "each is readable through the API")
n_before = len(A.get(B + f"{V}?task_id={T}").json()["reviews"])
PRIV = None
A.patch(B + "/api/settings", json={"workspace": "private"})
PRIV = store(A, "privat.png", png(), space="private")
A.patch(B + "/api/settings", json={"workspace": f"org:{ORG}"})
TXT = store(A, "notiz.txt", b"just text", "text/plain", space=f"org:{ORG}")
c1 = K.post(B + "/api/v1/videos", json={"task_id": T, "files": [{"file_id": F[0]}, {"file_id": PRIV}]}).status_code
c2 = K.post(B + "/api/v1/videos", json={"task_id": T, "files": [{"file_id": F[0]}, {"file_id": TXT}]}).status_code
check(c1 == 409 and c2 == 400, f"one file of another workspace 409, one that is no image 400 {c1} {c2}")
check(len(A.get(B + f"{V}?task_id={T}").json()["reviews"]) == n_before, "all or none: nothing created by the refused batches")
codes = [K.post(B + "/api/v1/videos", json={"task_id": T, "files": [{"file_id": F[0]}] * 51}).status_code,
         K.post(B + "/api/v1/videos", json={"task_id": T, "files": []}).status_code,
         K.post(B + "/api/v1/videos", json={"client_id": 1, "files": [{"file_id": F[0]}]}).status_code,
         K.post(B + "/api/v1/videos", json={"task_id": T, "files": [{"file_id": F[0], "x": 1}]}).status_code,
         RO.post(B + "/api/v1/videos", json={"task_id": T, "files": [{"file_id": F[0]}]}).status_code]
check(codes[:4] == [400, 400, 400, 400] and codes[4] == 403, f"51 files / none / a client / an unknown field 400, without tasks:write 403 {codes}")
# an agent: the project and the files shared with it, level free
ra = A.post(B + "/api/admin/agents", json={"scopes": ["read", "tasks:write", "comments"], "username": "rundbot", "display_name": "Rundbot", "org_id": ORG})
check(ra.status_code in (200, 201), f"an agent {ra.status_code} {ra.text[:200]}")
AG, ag = ra.json()["id"], bearer(ra.json()["token"])
A.put(B + f"/api/lists/{L}/members", json={"user_id": AG, "role": "edit"})
A.patch(B + f"/api/agents/{AG}/control", json={"level": "free"})
for f in F:
    A.post(B + f"/api/files/nodes/{f}/shares", json={"agent_id": AG, "role": "view"})
r = ag.post(B + "/api/v1/videos", json={"list_id": L, "files": [{"file_id": F[1], "title": "Kontakt"}, {"file_id": F[2], "title": "Impressum"}]})
check(r.status_code == 201 and [x["title"] for x in r.json().get("data", [])] == ["Kontakt", "Impressum"], f"the agent creates two at the project {r.status_code} {r.text[:300]}")
if r.status_code == 201:
    aid = r.json()["data"][0]["id"]
    ra2 = ag.post(B + f"/api/v1/videos/{aid}/comments", json={"pos": {"x": 0.1, "y": 0.1, "w": 0.3, "h": 0.2}, "body": "Bereich vom Agenten"})
    check(ra2.status_code == 201 and ra2.json()["comment"]["pos"] == {"x": 0.1, "y": 0.1, "w": 0.3, "h": 0.2}, f"the agent marks an area {ra2.status_code} {ra2.text[:200]}")
# (reader F2): with task_id the gate knows the task's project too - the project's own level (approve_all) holds there
check(A.patch(B + f"/api/agents/{AG}/control", json={"projects": {str(L): "approve_all"}}).ok, "setup: the project asks for every change")
r = ag.post(B + "/api/v1/videos", json={"task_id": T, "files": [{"file_id": F[0]}]})
check(r.status_code == 409 and "approval" in r.text, f"F2: sign-offs at a task of that project wait for a card {r.status_code} {r.text[:200]}")
check(A.patch(B + f"/api/agents/{AG}/control", json={"projects": {str(L): None}}).ok, "setup: the project's level back")
r = ag.post(B + "/api/v1/videos", json={"task_id": T, "files": [{"file_id": F[0], "title": "Start"}]})
check(r.status_code == 201, f"F2: level free again - the agent creates at the task {r.status_code} {r.text[:200]}")

# ---- a person without an organisation (P4) and a stranger
FID, Fr = freelancer(B, A)
Fr.patch(B + "/api/settings", json={"lang": "en", "features": FEAT, "tour": "done"})
st = Fr.get(B + "/api/state").json()
inbox = next(x for x in st["lists"] if x.get("is_inbox"))
FT = Fr.post(B + "/api/tasks", json={"title": "Fotos Wohnung", "list_id": inbox["id"]}).json()["id"]
r = up(Fr, {"task_id": FT}, "flur.png", png())
check(r.ok, f"frida: an image approval at her own task {r.status_code}")
FR = r.json()["id"]
rr = Fr.post(B + f"{V}/{FR}/comments", json={"pos": {"x": 0.5, "y": 0.5, "w": 0.5, "h": 0.5}, "body": "Ecke"})
check(rr.ok, f"frida marks an area {rr.status_code} {rr.text[:200]}")
ftok = Fr.post(B + "/api/me/tokens", json={"name": "f", "scopes": ["read", "tasks:write"]}).json().get("token")
FF = [store(Fr, f"raum-{i}.png", png(), space="private") for i in (1, 2)]
r = bearer(ftok).post(B + "/api/v1/videos", json={"task_id": FT, "files": [{"file_id": FF[0]}, {"file_id": FF[1]}]})
check(r.status_code == 201 and len(r.json()["data"]) == 2, f"frida: the batch at her own task {r.status_code} {r.text[:200]}")
# reader F10: a person's token like the app - the module Approval off = 409, on again = fine
Fr.patch(B + "/api/settings", json={"features": FEAT.replace(",videos", "")})
r = bearer(ftok).post(B + "/api/v1/videos", json={"task_id": FT, "files": [{"file_id": FF[0]}]})
check(r.status_code == 409, f"F10: the module Approval off: no new sign-off by token {r.status_code} {r.text[:160]}")
Fr.patch(B + "/api/settings", json={"features": FEAT})
# reader F13: frida's own agent makes sign-offs in her private space - they belong to her (export, trash, signer data), the
# agent stays their creator
assert A.put(B + "/api/admin/agent-policy", json={"user_agents": True}).ok
ra = Fr.post(B + "/api/my/agents", json={"username": "fotobot", "display_name": "Fotobot", "scopes": ["read", "tasks:write", "comments"]})
check(ra.status_code in (200, 201), f"setup: frida's agent {ra.status_code} {ra.text[:200]}")
FAG, fag = ra.json()["id"], bearer(ra.json()["token"])
FL = Fr.post(B + "/api/lists", json={"name": "Wohnung"}).json()["id"]
assert Fr.put(B + f"/api/lists/{FL}/members", json={"user_id": FAG, "role": "edit"}).ok
FT2 = Fr.post(B + "/api/tasks", json={"title": "Bilder Bad", "list_id": FL}).json()["id"]
Fr.patch(B + f"/api/agents/{FAG}/control", json={"level": "free"})
for f in FF:
    Fr.post(B + f"/api/files/nodes/{f}/shares", json={"agent_id": FAG, "role": "view"})
r = fag.post(B + "/api/v1/videos", json={"task_id": FT2, "files": [{"file_id": FF[0], "title": "Bad"}]})
check(r.status_code == 201, f"F13: frida's agent creates at her task {r.status_code} {r.text[:200]}")
if r.status_code == 201:
    own = kt.dbx("SELECT owner_id, created_by, org_id FROM video_reviews WHERE id=?", (r.json()["data"][0]["id"],))
    check(own and own[0][0] == FID and own[0][1] == FAG and own[0][2] is None, f"F13: owner = frida, creator = her agent {own}")
    check(Fr.get(B + f"{V}/{r.json()['data'][0]['id']}").ok, "F13: frida opens it in the app")
check(A.get(B + f"{V}/{FR}").status_code == 404, "a stranger (the admin) does not see frida's approval")
check(K.post(B + "/api/v1/videos", json={"task_id": FT, "files": [{"file_id": F[0]}]}).status_code == 404, "a stranger cannot add to frida's task")
sys.exit(kt.done("p7532_a_area"))
