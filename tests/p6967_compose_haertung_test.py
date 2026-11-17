#!/usr/bin/env python3
# kalmido-suite: nodata
"""2.1356.0 (#6967): docker-compose.yml hardens ClamAV and the database.
 - clamav: cap_drop ALL + five rights, pids_limit 256, networks scan + out (not default, where db lives)
 - db: cap_drop ALL + the same five rights, pids_limit 512, not in scan
 - kalmido stays in default and joins scan; scan is internal; profiles clamav / localdb kept
Static check of the file, standard library only. usage: python3 tests/p6967_compose_haertung_test.py"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from kt import check, done  # noqa: E402

with open(os.path.join(os.path.dirname(HERE), "docker-compose.yml"), encoding="utf-8") as f:
    C = f.read()


def block(name, text=C, indent="  "):
    m = re.search(r"^%s%s:\n(.*?)(?=^%s[A-Za-z0-9_-]+:\n|^\S|\Z)" % (indent, re.escape(name), indent), text, re.M | re.S)
    return m.group(1) if m else ""


def lines(b):
    return [re.sub(r"\s+#.*$", "", ln).strip() for ln in b.splitlines() if not ln.strip().startswith("#")]


FIVE = {"CHOWN", "DAC_OVERRIDE", "FOWNER", "SETUID", "SETGID"}
for svc, pids, prof in (("clamav", "256", "clamav"), ("db", "512", "localdb")):
    L = lines(block(svc))
    check("cap_drop: [ALL]" in L, f"{svc}: cap_drop ALL")
    cap = [ln for ln in L if ln.startswith("cap_add:")]
    got = set(re.findall(r"[A-Z_]+", cap[0].split(":", 1)[1])) if cap else set()
    check(got == FIVE, f"{svc}: exactly the five rights ({got})")
    check(f"pids_limit: {pids}" in L, f"{svc}: pids_limit {pids}")
    check(f'profiles: ["{prof}"]' in L, f"{svc}: profile {prof} kept")
    check("- no-new-privileges:true" in L, f"{svc}: no-new-privileges kept")

check("networks: [scan, out]" in lines(block("clamav")), "clamav: networks scan + out only (no default)")
check(not any(ln.startswith("networks:") for ln in lines(block("db"))), "db: no networks line (default only)")
check("networks: [default, embed, scan]" in lines(block("kalmido")), "kalmido: default + embed + scan")
nets = block("networks", indent="")
check("internal: true" in block("scan", nets), "scan is internal")
check("scan:" in nets and "out:" in nets and "internal" not in block("out", nets), "out exists and has a way out")
sys.exit(done("p6967_compose_haertung"))
