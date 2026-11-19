#!/usr/bin/env python3
# kalmido-suite: after=release_ci_gate nodata
"""#6893: tools/stamp_release.py derives VERSION, the shell cache number of static/sw.js, the CHANGELOG section and the
whatsnew entry of a release from its tag and the changelog.d fragments since the tag before (no server; a throwaway git
repository in a temp folder):
- fragments new since the tag before go into "## [V] - <tag date>" (changelog part only, never the readme / neu sections),
  the neu lines into static/whatsnew.json; a fragment already in the tag before stays out; i18n fragments stay untouched;
- tags between the newest CHANGELOG section and V get their own sections (oldest below), whatsnew entries as well;
- no effect when VERSION already says V (the train's version commit until #6894);
- the cache number grows with the version and never goes down (a tree with a higher number = refused);
- --changelog-only adds only the sections (weekly-release.yml);
- release.yml stamps before the image build (tags fetched) and checks tag = stamped VERSION; weekly-release.yml stamps the
  CHANGELOG before its notes and the tagged tree before the web manifest."""
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

N = os.path.dirname(os.path.abspath(__file__))
R = os.path.join(N, "..")
sys.path.insert(0, N)
from kt import FAILS, OKS, check  # noqa: E402

spec = importlib.util.spec_from_file_location("stamp_release", os.path.join(R, "tools", "stamp_release.py"))
st = importlib.util.module_from_spec(spec)
spec.loader.exec_module(st)

# the cache number: monotonic in the version, above every number the train counted by hand
cn = st.cache_number
check(cn("2.1405.0") > 579, "the derived cache number lies above the train's last one (v579 at 2.1405.0)")
seq = ["2.999.9999", "2.1405.0", "2.1405.1", "2.1406.0", "2.99999.0", "3.0.0", "3.1.0", "10.0.0"]
check(all(cn(a) < cn(b) for a, b in zip(seq, seq[1:])), "the cache number grows with every version (%s)" % [cn(x) for x in seq])
for bad in ("2.100000.0", "2.1.10000", "2.1", "x"):
    try:
        got = cn(bad)
    except st.Refused:
        got = "refused"
    check(got == "refused", "cache_number refuses %s (%s)" % (bad, got))

T = tempfile.mkdtemp(prefix="stamp6893-")
ENV = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.invalid", GIT_COMMITTER_NAME="t",
           GIT_COMMITTER_EMAIL="t@example.invalid", GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1")


def g(*a, date="2026-11-10T10:00:00Z"):
    return subprocess.run(["git", "-C", T, *a], check=True, capture_output=True, text=True,
                          env=dict(ENV, GIT_AUTHOR_DATE=date, GIT_COMMITTER_DATE=date)).stdout


def put(rel, text):
    os.makedirs(os.path.dirname(os.path.join(T, rel)), exist_ok=True)
    with open(os.path.join(T, rel), "w", encoding="utf-8") as f:
        f.write(text)


def get(rel):
    with open(os.path.join(T, rel), encoding="utf-8") as f:
        return f.read()


CL = ("# Changelog\n\nAll notable changes.\n\n## [2.10.0] - 2026-11-01\n\n- old\n\n"
      "[Unreleased]: https://github.com/Kalmido/kalmido/compare/v2.10.0...HEAD\n[2.10.0]: https://github.com/Kalmido/kalmido/releases/tag/v2.10.0\n")
SWJS = "// sw\nconst CACHE = 'tasks-shell-v579';  // app 2.10.0 (comment)\nconst X = 1;\n"
WN = json.dumps({"versions": [{"version": "2.10.0", "date": "2026-11-01", "items": [{"de": "alt", "en": "old"}]}]}, indent=1) + "\n"
FR_OLD = "Package 2.9 (old).\n\n### Fixed\n- folded before (#1)\n"
FR_A = ("Package 2.11 (A).\n\n### Added\n- thing A (#11)\n<!-- readme -->\nreadme note A\n<!-- neu -->\n"
        "- de: Neu A | en: New A\n- de: kaputt ohne Trenner\n")
FR_B = "Package 2.12 (B).\n\n### Fixed\n- fix B (#12)\n<!-- neu -->\n- de: Neu B | en: New B\n"
FR_C = "Package 2.13 (C).\n\n### Changed\n- change C (#13)\n"

g("init", "-q")
put("VERSION", "2.10.0\n")
put("CHANGELOG.md", CL)
put("static/sw.js", SWJS)
put("static/whatsnew.json", WN)
put("static/i18n/neu/7.json", '{"de": {"x": "y"}}\n')
put("changelog.d/1.md", FR_OLD)
g("add", "-A")
g("commit", "-qm", "base")
g("tag", "v2.10.0")
put("changelog.d/100.md", FR_A)  # a later package of 2.11.0 (no version commit: VERSION stays 2.10.0)
g("add", "-A")
g("commit", "-qm", "#11: A", date="2026-11-12T09:00:00Z")
g("tag", "v2.11.0")
put("changelog.d/20.md", FR_B)
put("changelog.d/300.md", FR_C)
g("add", "-A")
g("commit", "-qm", "#12 #13: B C", date="2026-11-14T09:00:00Z")
g("tag", "v2.12.0")
clean = g("rev-parse", "HEAD").strip()

logs = []
done = st.stamp(T, "2.12.0", log=logs.append)
cl = get("CHANGELOG.md")
check(get("VERSION") == "2.12.0\n", "VERSION stamped")
check("const CACHE = 'tasks-shell-v%d';  // app 2.12.0 (comment)" % cn("2.12.0") in get("static/sw.js"),
      "sw.js: the cache number of the version and the version in the comment, the rest of the line kept")
check(cl.index("## [2.12.0] - 2026-11-14") < cl.index("## [2.11.0] - 2026-11-12") < cl.index("## [2.10.0]"),
      "a section per tag since the newest one, newest first, dated by the tag")
s12 = cl[cl.index("## [2.12.0]"):cl.index("## [2.11.0]")]
s11 = cl[cl.index("## [2.11.0]"):cl.index("## [2.10.0]")]
check("fix B (#12)" in s12 and "change C (#13)" in s12 and s12.index("fix B") < s12.index("change C"),
      "2.12.0 holds the fragments new since v2.11.0, in KID order (20 before 300)")
check("thing A (#11)" in s11 and "fix B" not in s11, "2.11.0 holds only the fragment new since v2.10.0")
check("folded before" not in cl, "a fragment already in the tag before stays out")
check("readme note A" not in cl and "Neu A" not in cl and "<!--" not in cl, "readme and neu sections never go into the CHANGELOG")
check("[Unreleased]: https://github.com/Kalmido/kalmido/compare/v2.12.0...HEAD\n[2.12.0]: https://github.com/Kalmido/kalmido/releases/tag/v2.12.0\n"
      "[2.11.0]: https://github.com/Kalmido/kalmido/releases/tag/v2.11.0\n[2.10.0]:" in cl, "link lines moved along")
wn = json.loads(get("static/whatsnew.json"))["versions"]
check([x["version"] for x in wn] == ["2.12.0", "2.11.0", "2.10.0"], "whatsnew: the new versions on top (%s)" % [x["version"] for x in wn])
check(wn[0]["items"] == [{"de": "Neu B", "en": "New B"}] and wn[0]["date"] == "2026-11-14", "whatsnew 2.12.0: its neu line, the tag date")
check(wn[1]["items"] == [{"de": "Neu A", "en": "New A"}], "whatsnew 2.11.0: the valid neu line only (a broken line is left out)")
check(os.path.exists(os.path.join(T, "changelog.d", "100.md")) and get("static/i18n/neu/7.json") == '{"de": {"x": "y"}}\n',
      "fragments and i18n fragments stay where they are")
check(done and logs, "stamp reports what it wrote")

# a second stamp of the same version: VERSION says it already = no effect (also the train's version commit, until #6894)
before = {f: get(f) for f in ("VERSION", "CHANGELOG.md", "static/sw.js", "static/whatsnew.json")}
logs = []
done = st.stamp(T, "2.12.0", log=logs.append)
check(done == [] and all(get(f) == t for f, t in before.items()) and "nothing stamped" in logs[0],
      "VERSION already = the version: nothing changes (%s)" % logs)

# the train's version commit: the tree says the version already -> the stamp leaves its files exactly as the train wrote them
g("checkout", "-q", "--", ".")
put("VERSION", "2.12.0\n")
put("CHANGELOG.md", "TRAIN\n")
check(st.main(["2.12.0", "--root", T]) == 0 and get("CHANGELOG.md") == "TRAIN\n" and "v579" in get("static/sw.js"),
      "a tree the train's version commit stamped stays as it is (exit 0)")
g("checkout", "-q", "--", ".")

# deterministic: the same tag stamped in another clone gives the same bytes (release.yml, weekly web manifest, staging)
st.stamp(T, "2.12.0", log=lambda *_: None)
first = {f: get(f) for f in ("VERSION", "CHANGELOG.md", "static/sw.js", "static/whatsnew.json")}
T2 = tempfile.mkdtemp(prefix="stamp6893b-")
subprocess.run(["git", "clone", "-q", T, os.path.join(T2, "c")], check=True, env=ENV, capture_output=True)
subprocess.run(["git", "-C", os.path.join(T2, "c"), "checkout", "-q", "v2.12.0"], check=True, env=ENV, capture_output=True)
st.stamp(os.path.join(T2, "c"), "2.12.0", log=lambda *_: None)
same = all(open(os.path.join(T2, "c", f), encoding="utf-8").read() == t for f, t in first.items())
check(same, "the stamp of a tag gives the same bytes in another clone")
g("checkout", "-q", "--", ".")

# an untagged version (staging) reads the fragments of the working tree, dated --date
put("changelog.d/400.md", "Package 2.13 (D).\n\n### Added\n- staging D (#14)\n")
st.stamp(T, "2.13.0", datum="2026-11-19", log=lambda *_: None)
cl = get("CHANGELOG.md")
check("## [2.13.0] - 2026-11-19" in cl and "staging D (#14)" in cl.split("## [2.12.0]")[0] and "change C" not in cl.split("## [2.12.0]")[0],
      "untagged version: the fragments of the tree that the newest tag lacks, dated --date")
g("checkout", "-q", "--", ".")
os.remove(os.path.join(T, "changelog.d", "400.md"))

# the cache never goes down: a tree whose number is higher than the version's = refused, nothing written
put("static/sw.js", "const CACHE = 'tasks-shell-v%d';  // app 2.99.0\n" % (cn("2.12.0") + 1))
rc = st.main(["2.12.0", "--root", T])
check(rc == 2 and get("VERSION") == "2.10.0\n", "a cache number above the version's = refused, VERSION untouched (rc %s)" % rc)
g("checkout", "-q", "--", ".")

# a version below the newest section, a missing tag before it = refused
check(st.main(["2.9.0", "--root", T]) == 2, "a version older than the newest CHANGELOG section = refused")
g("tag", "-d", "v2.10.0")
g("tag", "-d", "v2.11.0")
check(st.main(["2.11.0", "--root", T]) == 2, "no tag below the version (a checkout without tags) = refused")
g("tag", "v2.10.0", clean + "~2")
g("tag", "v2.11.0", clean + "~1")

# --changelog-only: the sections only, up to a tag
logs = []
st.stamp(T, "2.11.0", changelog_only=True, log=logs.append)
check("## [2.11.0]" in get("CHANGELOG.md") and "## [2.12.0]" not in get("CHANGELOG.md") and get("VERSION") == "2.10.0\n"
      and "v579" in get("static/sw.js") and get("static/whatsnew.json") == WN, "--changelog-only: only the CHANGELOG, up to that tag")
st.stamp(T, "2.11.0", changelog_only=True, log=lambda *_: None)
check(get("CHANGELOG.md").count("## [2.11.0]") == 1, "--changelog-only twice: no second section")
g("checkout", "-q", "--", ".")
check(st.main(["2.13.0", "--root", T, "--changelog-only"]) == 2, "--changelog-only without the tag = refused")
check(g("status", "--porcelain").strip() == "", "refused runs left the tree clean")

shutil.rmtree(T, ignore_errors=True)
shutil.rmtree(T2, ignore_errors=True)

# the workflows: release.yml stamps the tagged tree before the image and checks tag = stamped VERSION
with open(os.path.join(R, ".github", "workflows", "release.yml"), encoding="utf-8") as f:
    rel = f.read()
r = re.search(r"^  release:\n((?:    .*\n|\n)+)", rel.split("\njobs:\n", 1)[1], re.M)
rt = r.group(1) if r else ""
check("fetch-depth: 0" in rt.split("Version from tag")[0], "release.yml: the release job fetches the tags (fragments since the tag before)")
i_st, i_ver, i_build = rt.find("tools/stamp_release.py"), rt.find('test "$(cat VERSION)" = "$ver"'), rt.find("docker/build-push-action")
check(-1 < i_st < i_ver < i_build, "release.yml: stamp, then tag = VERSION, then the image build")
check(rt.find("tools/stamp_release.py") < rt.find("CHANGELOG.md > section.md"), "release.yml: the notes come from the stamped CHANGELOG")
with open(os.path.join(R, ".github", "workflows", "weekly-release.yml"), encoding="utf-8") as f:
    wk = f.read()
check(wk.find("stamp_release.py") > -1 and wk.find("--changelog-only") < wk.find("python3 tools/weekly_release.py pick"),
      "weekly-release.yml: the CHANGELOG sections are stamped before the notes are picked")
check(wk.rfind("stamp_release.py") < wk.find("tools/web_manifest.py\" --root") and "static/sw.js static/whatsnew.json" in wk,
      "weekly-release.yml: the web manifest describes the stamped files the image serves")

print("p6893_stamp: %d ok, %d failed" % (OKS[0], len(FAILS)))
sys.exit(1 if FAILS else 0)
