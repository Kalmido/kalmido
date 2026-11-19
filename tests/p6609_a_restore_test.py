#!/usr/bin/env python3
"""2.1431.0 (#6609, audit #4817): the way back after a failed or bad update of a self-hosted installation.
install.sh runs for real (its last line main "$@" left out) with stubs for curl, docker and git on the PATH.
- update.sh passes its arguments to the installer (before: `| sh` dropped them, so no option could reach it)
- update.sh --restore COPY: finds the copy, takes the version noted beside it (KALMIDO_VERSION wins), refuses a missing or
  foreign file, a copy without a noted version and an installation on its own database server - each before anything changes
- the database copy of an update notes its version; a restore keeps every old copy (the copy it loads may be the oldest)
- the load: success only with the last line of the restore script, else a clear stop "the database is as it was"
- a start that fails after an update: the container is stopped (restart: unless-stopped would run the migration again and
  again) and the ready --restore command with the version before and the copy is printed
- the "Previous" line names the image-only way only when the version before is not below the database's format limit
- a release whose release page is pruned is built from its git tag with KALMIDO_BUILD=1; without it the stop names that way
- docs/SELF-HOSTING.md names update.sh --restore and no longer the bare pg_restore --clean
The real load against PostgreSQL: tests/p6609_b_restore_db_test.py."""
# kalmido-suite: nodata
import os
import shutil
import stat
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from kt import check, done  # noqa: E402

with open(os.path.join(ROOT, "install.sh"), encoding="utf-8") as f:
    SH = f.read()
with open(os.path.join(ROOT, "docs", "SELF-HOSTING.md"), encoding="utf-8") as f:
    DOC = f.read()
assert SH.rstrip().endswith('main "$@"')
TMP = tempfile.mkdtemp(prefix="p6609-")
LIB = os.path.join(TMP, "lib.sh")
with open(LIB, "w", encoding="utf-8") as f:
    f.write(SH.rstrip()[:-len('main "$@"')])
STUB = os.path.join(TMP, "bin")
os.makedirs(STUB)
CALLS = os.path.join(TMP, "calls")


def stub(name, body):
    p = os.path.join(STUB, name)
    with open(p, "w", encoding="utf-8") as f:
        f.write('#!/bin/sh\necho "%s $*" >> "%s"\n%s\n' % (name, CALLS, body))
    os.chmod(p, os.stat(p).st_mode | stat.S_IXUSR)


def run(code, **env):
    """The functions of install.sh, then CODE; -> (exit code, stdout, stderr)."""
    if os.path.exists(CALLS):
        os.remove(CALLS)
    e = {k: v for k, v in os.environ.items() if not k.startswith(("KALMIDO_", "SSH_"))}
    e.update(PATH=STUB + os.pathsep + e["PATH"], **env)
    r = subprocess.run(["sh", "-c", '. "%s"\nCOMPOSE=plugin\n%s' % (LIB, code)], env=e, capture_output=True, text=True, timeout=60)
    return r.returncode, r.stdout, r.stderr


def calls():
    if not os.path.exists(CALLS):
        return ""
    with open(CALLS, encoding="utf-8") as f:
        return f.read()


def write(path, text, mode="w"):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, mode, encoding=None if "b" in mode else "utf-8") as f:
        f.write(text)


def install(env="COMPOSE_PROFILES=localdb,clamav\n", version="v2.1431.0", prev="v2.1300.0"):
    """An installation folder: docker-compose.yml, .env, .kalmido-version(.prev)."""
    d = tempfile.mkdtemp(dir=TMP)
    write(os.path.join(d, "docker-compose.yml"), "services:\n  kalmido:\n    profiles: [x]\n")
    write(os.path.join(d, ".env"), env)
    if version:
        write(os.path.join(d, ".kalmido-version"), version + "\n")
    if prev:
        write(os.path.join(d, ".kalmido-version.prev"), prev + "\n")
    return d


DUMP = b"PGDMP\x01\x0e\x00 a copy"

# ------------------------------------------------------------------ update.sh passes its arguments
d = install()
rc, _, err = run('DIR="%s"; write_update_script' % d)
upd = open(os.path.join(d, "update.sh"), encoding="utf-8").read()
check(rc == 0 and '| sh -s -- "$@"' in upd, f"update.sh hands its arguments to the installer ({rc} {err[:200]})")
stub("curl", 'printf \'%s\\n\' \'echo "ARGS:$*"\'')
r = subprocess.run(["sh", os.path.join(d, "update.sh"), "--restore", "data/backups/kalmido-1.dump"], capture_output=True, text=True,
                   env=dict(os.environ, PATH=STUB + os.pathsep + os.environ["PATH"]), timeout=60)
check(r.returncode == 0 and "ARGS:--restore data/backups/kalmido-1.dump" in r.stdout, f"update.sh --restore X reaches the installer as --restore X: {r.stdout} {r.stderr[:200]}")

# ------------------------------------------------------------------ the options
rc, out, _ = run('parse_args --restore data/backups/x.dump; echo "R=$RESTORE"')
check(rc == 0 and "R=data/backups/x.dump" in out, f"--restore FILE ({rc} {out})")
rc, out, _ = run('parse_args --restore=/abs/x.dump; echo "R=$RESTORE"')
check(rc == 0 and "R=/abs/x.dump" in out, f"--restore=FILE ({rc} {out})")
rc, _, err = run("parse_args --restore")
check(rc == 1 and "--restore needs the database copy" in err, f"--restore without a file stops ({rc} {err[:200]})")
rc, _, err = run("parse_args --frobnicate")
check(rc == 1 and "Unknown option --frobnicate" in err, f"an unknown option stops ({rc} {err[:200]})")
rc, out, _ = run('parse_args; echo "R=[$RESTORE]"')
check(rc == 0 and "R=[]" in out, "no option: an ordinary run")

# ------------------------------------------------------------------ restore_locate (before anything changes)
d = install()
write(os.path.join(d, "data/backups/kalmido-20261118-120000.dump"), DUMP, "wb")
write(os.path.join(d, "data/backups/kalmido-20261118-120000.dump.version"), "v2.1300.0\n")
loc = 'DIR="%s"; RESTORE="%s"; restore_locate; echo "V=$KALMIDO_VERSION F=$RESTORE_FILE"'
rc, out, err = run(loc % (d, "data/backups/kalmido-20261118-120000.dump"))
check(rc == 0 and "V=v2.1300.0" in out and f"F={d}/data/backups/kalmido-20261118-120000.dump" in out,
      f"the copy relative to the install folder, the version noted beside it ({rc} {out} {err[:200]})")
rc, out, _ = run(loc % (d, d + "/data/backups/kalmido-20261118-120000.dump"), KALMIDO_VERSION="v2.1200.0")
check(rc == 0 and "V=v2.1200.0" in out, f"an absolute path; KALMIDO_VERSION wins over the note ({rc} {out})")
rc, _, err = run(loc % (d, "data/backups/nope.dump"))
check(rc == 1 and "was not found" in err and "Nothing was changed" in err and calls() == "", f"a missing copy stops, nothing called ({rc} {err[:200]})")
write(os.path.join(d, "data/backups/backup.kbk"), b"KBK1 not a dump", "wb")
rc, _, err = run(loc % (d, "data/backups/backup.kbk"))
check(rc == 1 and "no database copy of update.sh" in err, f"a file that is no pg_dump copy stops ({rc} {err[:200]})")
write(os.path.join(d, "data/backups/kalmido-old.dump"), DUMP, "wb")
rc, _, err = run(loc % (d, "data/backups/kalmido-old.dump"))
check(rc == 1 and "not noted beside it" in err and "KALMIDO_VERSION=vX.Y.Z" in err and "v2.1300.0" in err,
      f"a copy without a noted version: the command with KALMIDO_VERSION, the version before named ({rc} {err[:300]})")
rc, out, _ = run(loc % (d, "data/backups/kalmido-old.dump"), KALMIDO_VERSION="v2.1300.0")
check(rc == 0 and "V=v2.1300.0" in out, f"... and with it named it goes ({rc} {out})")
# reader F1: the note lies in data/backups/ (writable by the app) - only vX.Y.Z / latest-ok/X.Y.Z count
for bad in ("../../../other/repo/archive/refs/heads/main", "main", "v2.1300.0/../../x", "v2.1300", "-x"):
    write(os.path.join(d, "data/backups/kalmido-20261118-120000.dump.version"), bad + "\n")
    rc, out, err = run(loc % (d, "data/backups/kalmido-20261118-120000.dump"))
    check(rc == 1 and "is no release" in err and "KALMIDO_VERSION=vX.Y.Z" in err and calls() == "", f"F1: a note {bad!r} stops before anything ({rc} {out} {err[:200]})")
write(os.path.join(d, "data/backups/kalmido-20261118-120000.dump.version"), "latest-ok/2.1300.0\r\n")
rc, out, _ = run(loc % (d, "data/backups/kalmido-20261118-120000.dump"))
check(rc == 0 and "V=latest-ok/2.1300.0 " in out, f"F1: a live tag counts ({rc} {out})")
for bad in ("../../x/y", "v1/../main", "/abs", "x/"):
    rc, _, err = run('resolve_version', KALMIDO_VERSION=bad)
    check(rc == 1 and "must be a tag or branch name" in err, f"F1: KALMIDO_VERSION={bad} is refused ({rc})")
rc, out, _ = run('resolve_version; echo "V=$VERSION"', KALMIDO_VERSION="latest-ok/2.1300.0")
check(rc == 0 and "V=latest-ok/2.1300.0" in out, "F1: latest-ok/X.Y.Z still passes")
ext = install(env="DATABASE_URL=postgresql://k:p@db.example.com/k\nCOMPOSE_PROFILES=clamav\n")
write(os.path.join(ext, "data/backups/kalmido-1.dump"), DUMP, "wb")
rc, _, err = run(loc % (ext, "data/backups/kalmido-1.dump"), KALMIDO_VERSION="v2.1300.0")
check(rc == 1 and "own database server" in err and "Nothing was changed" in err, f"an own database server: restored by hand, said before anything ({rc} {err[:200]})")
rc, _, err = run(loc % (TMP + "/empty-not-there", "x.dump"))
check(rc == 1 and "no Kalmido installation" in err, f"no installation: stop ({rc} {err[:200]})")

# ------------------------------------------------------------------ the copy of an update notes its version; a restore keeps the old copies
stub("docker", 'case "$*" in *"ps -q db"*) echo abc123 ;; *"exec -T db"*) printf "PGDMP-copy" ;; esac; exit 0')
d = install()
bk = os.path.join(d, "data", "backups")
for i in range(10):
    write(os.path.join(bk, f"kalmido-2026010{i}-000000.dump"), DUMP, "wb")
    os.utime(os.path.join(bk, f"kalmido-2026010{i}-000000.dump"), (1000 + i, 1000 + i))
write(os.path.join(bk, "kalmido-20260100-000000.dump.version"), "v2.1000.0\n")
rc, out, err = run('DIR="%s"; backup_db keep; echo "C=$DBCOPY"' % d)
dumps = sorted(x for x in os.listdir(bk) if x.endswith(".dump"))
new = [x for x in dumps if not x.startswith("kalmido-2026010")]
check(rc == 0 and len(dumps) == 11 and new, f"backup_db keep: a new copy, none of the 10 old ones removed ({rc} {dumps} {err[:200]})")
check(new and open(os.path.join(bk, new[0] + ".version"), encoding="utf-8").read().strip() == "v2.1431.0",
      "the copy notes the version that made it (.dump.version)")
os.utime(os.path.join(bk, new[0]), (5000, 5000))
rc, out, err = run('DIR="%s"; backup_db; echo "C=$DBCOPY"' % d)
left = sorted(os.listdir(bk))
check(rc == 0 and len([x for x in left if x.endswith(".dump")]) == 10 and "kalmido-20260100-000000.dump" not in left
      and "kalmido-20260100-000000.dump.version" not in left, f"an update keeps the last 10 copies, an old note goes with its copy ({left})")

# ------------------------------------------------------------------ the load: success only with the last line
d = install()
write(os.path.join(d, "data/backups/.dropped-fks.json"), "[]")
write(os.path.join(d, "x.dump"), DUMP, "wb")
stub("docker", 'cat >/dev/null; printf "\\n\\nkalmido-restore-ok\\n"')
rc, out, err = run('DIR="%s"; RESTORE=x.dump; RESTORE_FILE="$DIR/x.dump"; SAFETY=data/backups/s.dump; restore_load' % d)
check(rc == 0 and "Loaded x.dump" in out and "data/backups/s.dump" in out and not os.path.exists(os.path.join(d, "data/backups/.dropped-fks.json")),
      f"a load that went through: said, the note of a cut in-app restore removed ({rc} {out} {err[:200]})")
check("exec -T db sh -c" in calls() and "DROP SCHEMA public CASCADE" in calls() and "pg_restore" in calls(), f"the load runs the restore script in the db container: {calls()[:300]}")
stub("docker", 'cat >/dev/null; echo "pg_restore: error: could not read input file: end of file" >&2; printf "\\n"')
rc, out, err = run('DIR="%s"; RESTORE=x.dump; RESTORE_FILE="$DIR/x.dump"; SAFETY=s; restore_load' % d)
check(rc == 1 and "the database is as it was before" in err and "docker compose up -d" in err, f"no last line = a clear stop, the database unchanged ({rc} {err[:300]})")
# the script itself: COMMIT only after pg_restore read the whole copy, schema emptied inside the same transaction
rc, out, _ = run('printf "%s" "$RESTORE_SQL"')
check(out.index("BEGIN;") < out.index("DROP SCHEMA public CASCADE;") < out.index("pg_restore") < out.index("&& printf") < out.index("COMMIT;")
      and "--single-transaction" not in out and "ON_ERROR_STOP=1" in out and "app.role=system" in out,
      f"the restore script: one transaction, the COMMIT only after a complete pg_restore: {out}")

# ------------------------------------------------------------------ a start that fails after an update
stub("docker", 'case "$*" in *inspect*) echo "exited 0" ;; *"ps -q kalmido"*) echo cid1 ;; esac; exit 0')
stub("curl", "exit 7")
stub("sleep", "exit 0")
d = install()
code = 'DIR="%s"; PORT=3040; UPDATE=%s; RESTORE=""; DBCOPY="%s"; wait_health'
rc, out, err = run(code % (d, "1", "data/backups/kalmido-20261119-101010.dump"))
check(rc == 1 and "stop kalmido" in calls(), f"an update whose start fails: the container is stopped ({rc} {calls()})")
check(f'KALMIDO_VERSION=v2.1300.0 "{d}/update.sh" --restore "{d}/data/backups/kalmido-20261119-101010.dump"' in err
      and "is stopped now" in err and "docker compose logs --tail 50 kalmido" in err,
      f"... and the ready command back: version before + copy: {err[-600:]}")
rc, out, err = run(code % (d, "1", ""))
check(rc == 1 and 'KALMIDO_VERSION=v2.1300.0 "%s/update.sh"' % d in err and "--restore" not in err,
      f"no copy (external database): back with the image alone, the failed update changed nothing: {err[-400:]}")
rc, out, err = run(code % (d, '""', ""))
check(rc == 1 and "stop kalmido" not in calls() and "update.sh" not in err, f"a new installation: no stop, no way back ({rc} {err[-300:]})")
rc, out, err = run('DIR="%s"; PORT=3040; UPDATE=1; RESTORE=x.dump; DBCOPY=y; wait_health' % d)
check(rc == 1 and "stop kalmido" not in calls() and "--restore" not in err, f"a failed start of a restore does not point to itself ({rc} {err[-300:]})")

# ------------------------------------------------------------------ the "Previous" line
def prev_line(floor, dbcopy="data/backups/kalmido-1.dump", prev="v2.1300.0"):
    stub("docker", 'cat >/dev/null; printf "%s\\n"' % floor)
    d = install(prev=prev)
    rc, out, err = run('DIR="%s"; UPDATE=1; RESTORE=""; VERSION=v2.1431.0; DBCOPY="%s"; prev_note' % (d, dbcopy))
    return rc, out.replace("\n", " "), d


rc, out, d = prev_line("2.1118.0")
check(rc == 0 and "KALMIDO_VERSION=v2.1300.0 \"%s/update.sh\"" % d in out and "the data as it is now" in out and "--restore" in out,
      f"version before above the format limit: the image alone (and the copy as a second way): {out}")
rc, out, d = prev_line("2.1431.0")
check(rc == 0 and "format limit at 2.1431.0" in out and "--restore \"%s/data/backups/kalmido-1.dump\"" % d in out and "the data as it is now" not in out,
      f"version before below the limit (after a jump): only the way with the copy: {out}")
rc, out, d = prev_line("")
check(rc == 0 and "--restore" in out and "the data as it is now" not in out, f"limit not known: the safe way with the copy: {out}")
rc, out, d = prev_line("2.1431.0", dbcopy="")
check(rc == 0 and "no copy of the database was made" in out and "Back to the previous version" in out, f"no copy: the docs: {out}")
rc, out, d = prev_line("2.1118.0", prev="latest-ok/2.1300.0")
check(rc == 0 and "KALMIDO_VERSION=latest-ok/2.1300.0" in out and "the data as it is now" in out, f"a version installed from its tag: {out}")
check('back to it: KALMIDO_VERSION=$prev \\"$DIR/update.sh\\"${DBCOPY:+; the database of before' not in SH, "the old unconditional Previous line is gone")

# ------------------------------------------------------------------ a release whose page is pruned
with open(os.path.join(STUB, "curl"), "w", encoding="utf-8") as f:
    f.write('#!/bin/sh\necho "curl $*" >> "%s"\nout=""; prev=""\nfor a in "$@"; do [ "$prev" = "-o" ] && out="$a"; prev="$a"; done\n'
            '[ -n "$out" ] && : > "$out"\nprintf "%%s" "${CURL_CODE:-404}"\nexit 0\n' % CALLS)
stub("git", 'exit "${GIT_RC:-0}"')
assets = 'GH=https://github.invalid/x/y; VERSION=v2.1300.0; release_assets; if [ -n "$SUMS" ]; then echo SUMS=set; else echo SUMS=none; fi'
rc, out, err = run(assets, KALMIDO_BUILD="1")
check(rc == 0 and "SUMS=none" in out and "from its git tag" in err and "ls-remote --exit-code --tags https://github.invalid/x/y.git refs/tags/v2.1300.0" in calls(),
      f"pruned release + KALMIDO_BUILD=1 + the tag exists: built from the tag, said ({rc} {out} {err[:300]} {calls()})")
rc, out, err = run(assets, KALMIDO_BUILD="1", GIT_RC="2")
check(rc == 1 and "Could not fetch the checksum list" in err, f"... no such tag: the stop stays ({rc} {err[:200]})")
rc, out, err = run(assets)
check(rc == 1 and "Could not fetch the checksum list" in err and "KALMIDO_BUILD=1 builds it from its git tag" in err and "git " not in calls(),
      f"without KALMIDO_BUILD=1 the stop stays and names the way ({rc} {err[-300:]})")
rc, out, err = run(assets, KALMIDO_BUILD="1", CURL_CODE="000")
check(rc == 1 and "Could not fetch the checksum list" in err and "git " not in calls(), f"no network is no 404: the stop stays ({rc} {err[:200]})")

# ------------------------------------------------------------------ the order in main
main_body = SH[SH.index("\nmain() {"):]
check(main_body.index("parse_args") < main_body.index("restore_locate") < main_body.index("resolve_version") < main_body.index("check_docker"),
      "the copy and its version are checked before anything changes")
check(main_body.index("restore_prepare") < main_body.index("fetch_code") < main_body.index("restore_load") < main_body.index("compose_up"),
      "copy of now -> code of the version before -> load -> start")
check(main_body.index('if [ -n "$UPDATE" ]; then write_update_script; fi') < main_body.index("compose_up"),
      "an update writes update.sh before the start: a failed start already has --restore")

# ------------------------------------------------------------------ docs
back = DOC[DOC.index("### Back to the previous version"):DOC.index("### Update, downgrade and restore")]
check("update.sh --restore data/backups/kalmido-YYYYMMDD-HHMMSS.dump" in back and "pg_restore" not in back,
      "SELF-HOSTING.md: the way back is the one command, no pg_restore by hand")
check("pg_restore --clean --if-exists" not in DOC, "SELF-HOSTING.md: the bare pg_restore --clean (fails on newer tables) is gone")
check("The container stops with exit code 3" not in DOC and "docker compose stop kalmido" in DOC,
      "SELF-HOSTING.md: a failed database update does not claim the container stops by itself")
check("KALMIDO_BUILD=1" in back and "git tag" in back, "SELF-HOSTING.md: a version whose release page is gone")

shutil.rmtree(TMP, ignore_errors=True)
sys.exit(done("p6609_a_restore"))
