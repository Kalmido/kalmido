#!/usr/bin/env python3
# kalmido-suite: nodata
"""2.1284.0 (#6606): self-hosting on a Raspberry Pi / ARM server. clamav/clamav:1.4 was published for linux/amd64 only, the
standard installation (COMPOSE_PROFILES=localdb,clamav) stopped there at "no matching manifest for linux/arm64".
 1. docker-compose.yml pulls clamav/clamav-debian:1.4 (amd64 + arm64) with the same volume path, health check and port
 2. the evaluation of tools/install_upgrade_check.py arches with fixed manifests (as the registry gave them on 16.11.2026):
    the Debian index is green, the Alpine index (amd64 + an attestation entry) is red with linux/arm64, a single manifest is red
 3. the command end to end with a stand-in docker on the PATH: green for both, red with the image and what it lacks,
    red when the manifest cannot be read; images the machine builds itself are not asked
 4. the nightly CI job runs it; the uninstall text names the new image (and the old one an update leaves behind)
Temporary files only, standard library only. usage: python3 tests/p6606_a_arch_test.py"""
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "tools"))
from kt import check, done  # noqa: E402
import install_upgrade_check as iuc  # noqa: E402


def read(*rel):
    with open(os.path.join(ROOT, *rel), encoding="utf-8") as f:
        return f.read()


def entry(os_, arch):
    return {"mediaType": "application/vnd.oci.image.manifest.v1+json", "digest": "sha256:" + "0" * 64,
            "platform": {"os": os_, "architecture": arch}}


INDEX = "application/vnd.oci.image.index.v1+json"
DEBIAN = {"schemaVersion": 2, "mediaType": INDEX, "manifests": [entry("linux", "amd64"), entry("linux", "arm64"),
          entry("linux", "ppc64le"), entry("unknown", "unknown"), entry("unknown", "unknown"), entry("unknown", "unknown")]}
ALPINE = {"schemaVersion": 2, "mediaType": INDEX, "manifests": [entry("linux", "amd64"), entry("unknown", "unknown")]}
SINGLE = {"schemaVersion": 2, "mediaType": "application/vnd.oci.image.manifest.v1+json", "config": {"digest": "sha256:" + "1" * 64}, "layers": []}
ARMONLY = {"schemaVersion": 2, "manifests": [entry("linux", "arm64"), entry("linux", "arm")]}

# 1. the compose file
compose = read("docker-compose.yml")
imgs = iuc.compose_images(compose)
check("clamav/clamav-debian:1.4" in imgs, f"1: the scanner image is clamav/clamav-debian:1.4 ({imgs})")
check(not any(re.fullmatch(r"clamav/clamav(:.*)?", i) for i in imgs), "1: the amd64-only clamav/clamav is gone")
blk = compose[compose.index("\n  clamav:\n"):]
check("- clamav-db:/var/lib/clamav" in blk and '"CMD", "clamdcheck.sh"' in blk and 'profiles: ["clamav"]' in blk,
      "1: same volume path, health check and profile as before (the Debian image has them too)")
check("${KALMIDO_CLAMD-clamav:3310}" in compose, "1: Kalmido still talks to clamav:3310")
check([i for i in imgs if not iuc.built_here(i)] == ["postgres:" + re.search(r"image: postgres:(\S+)", compose).group(1), "clamav/clamav-debian:1.4"],
      f"1: the pulled images are read, the built ones skipped ({imgs})")
check(iuc.compose_images('services:\n  a:\n    image: "x/y:1"  # pinned\n  b:\n    image: x/y:1\n') == ["x/y:1"], "1: quotes, comments, each image once")

# 2. the evaluation
check(iuc.arch_missing(DEBIAN) == [], "2: clamav-debian (amd64, arm64, ppc64le + attestations) is green")
check(iuc.platforms(DEBIAN) == {"linux/amd64", "linux/arm64", "linux/ppc64le"}, f"2: attestation entries do not count ({iuc.platforms(DEBIAN)})")
check(iuc.arch_missing(ALPINE) == ["linux/arm64"], f"2: clamav/clamav:1.4 (amd64 + attestation) lacks arm64 ({iuc.arch_missing(ALPINE)})")
check(iuc.arch_missing(SINGLE) == ["linux/amd64", "linux/arm64"], "2: a single image manifest serves one platform only: red")
check(iuc.arch_missing(ARMONLY) == ["linux/amd64"], "2: arm64 without amd64 is red too")
check(iuc.arch_missing({}) == ["linux/amd64", "linux/arm64"] and iuc.arch_missing(None) == ["linux/amd64", "linux/arm64"], "2: nothing read = red")

# 3. the command with a stand-in docker
TMP = tempfile.mkdtemp(prefix="p6606-")
BIN = os.path.join(TMP, "bin")
os.makedirs(BIN)
for name, man in (("good", DEBIAN), ("amd", ALPINE), ("pg", DEBIAN)):
    with open(os.path.join(TMP, name + ".json"), "w", encoding="utf-8") as f:
        json.dump(man, f)
with open(os.path.join(BIN, "docker"), "w", encoding="utf-8") as f:
    f.write('#!/bin/sh\necho "$*" >> "%s/calls"\ncase "$3" in\n  good/*) cat "%s/good.json" ;;\n  amd/*) cat "%s/amd.json" ;;\n'
            '  postgres:*) cat "%s/pg.json" ;;\n  *) echo "no such manifest: $3" >&2; exit 1 ;;\nesac\n' % (TMP, TMP, TMP, TMP))
os.chmod(os.path.join(BIN, "docker"), 0o755 | stat.S_IXUSR)


def arches(text):
    p = os.path.join(TMP, "compose.yml")
    with open(p, "w", encoding="utf-8") as f:
        f.write(text)
    if os.path.exists(os.path.join(TMP, "calls")):
        os.remove(os.path.join(TMP, "calls"))
    env = dict(os.environ, PATH=BIN + os.pathsep + os.environ["PATH"])
    r = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "install_upgrade_check.py"), "arches", "--compose", p],
                       env=env, capture_output=True, text=True, timeout=60)
    calls = open(os.path.join(TMP, "calls"), encoding="utf-8").read() if os.path.exists(os.path.join(TMP, "calls")) else ""
    return r.returncode, r.stdout + r.stderr, calls


SVC = "services:\n  app:\n    image: ${KALMIDO_IMAGE:-kalmido:local}\n  e:\n    image: kalmido-embed:local\n  db:\n    image: postgres:17.12\n"
rc, out, calls = arches(SVC + "  s:\n    image: good/scan:1.4\n")
check(rc == 0 and "good/scan:1.4: linux/amd64, linux/arm64" in out, f"3: both architectures = green ({rc} {out})")
check("manifest inspect postgres:17.12" in calls and "manifest inspect good/scan:1.4" in calls and "local" not in calls and "KALMIDO_IMAGE" not in calls,
      f"3: only the pulled images are asked ({calls})")
rc, out, _ = arches(SVC + "  s:\n    image: amd/scan:1.4\n")
check(rc == 1 and "RED amd/scan:1.4: not published for linux/arm64" in out, f"3: amd64 only = red with image and architecture ({rc} {out})")
rc, out, _ = arches(SVC + "  s:\n    image: gone/scan:1.4\n")
check(rc == 1 and "RED gone/scan:1.4: the manifest could not be read" in out and "no such manifest" in out, f"3: an unreadable manifest is red ({rc} {out})")
rc, out, _ = arches("services: {}\n")
check(rc == 1 and "no image found" in out, f"3: a compose file without images is red ({rc} {out})")
shutil.rmtree(TMP, ignore_errors=True)

# 4. CI and texts
ci = read(".github", "workflows", "ci.yml")
job = ci[ci.index("\n  install-upgrade:\n"):]
nxt = re.search(r"\n  [A-Za-z][\w-]*:\n", job[1:])
job = job[:nxt.start() + 1] if nxt else job
check("run: python3 tools/install_upgrade_check.py arches" in job, "4: the nightly install job runs the check")
for name in ("install.sh", "install.ps1"):
    t = read(name)
    check("clamav/clamav-debian:1.4" in t and "clamav/clamav:1.4" in t, f"4: {name} uninstall names the new image and the one an update leaves behind")
doc = read("docs", "SELF-HOSTING.md")
check("clamav/clamav-debian" in doc and "linux/arm64" in doc, "4: SELF-HOSTING.md names the image and arm64")

sys.exit(done("p6606_a_arch"))
