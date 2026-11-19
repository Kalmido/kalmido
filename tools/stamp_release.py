#!/usr/bin/env python3
"""#6893 (audit #5112, decision 17.11.2026): the version data of a release are derived when the image is built, not written into
main by a version commit of the live train.

    python3 tools/stamp_release.py X.Y.Z [--root DIR] [--date YYYY-MM-DD]     stamp the tree DIR (default: this checkout)
    python3 tools/stamp_release.py X.Y.Z --changelog-only [--root DIR]        only the CHANGELOG sections (weekly-release.yml)

Stamping writes into the tree (never commits):
  - VERSION = X.Y.Z;
  - static/sw.js: the line `const CACHE = 'tasks-shell-vN';  // app X.Y.Z` with N = cache_number(X.Y.Z). sw.js and
    static/js/codecheck.js compare these numbers numerically, so N must grow with every version: it is derived from the
    version itself (major * 10^9 + minor * 10^4 + patch) and lies far above every number the train counted up by hand (v579
    at 2.1405.0). A number in the tree that is already as high or higher = refused (exit 2), never a lower cache;
  - CHANGELOG.md: a section "## [V] - date" for every release tag vV above the newest section the CHANGELOG (or
    docs/changelog/) already has, up to X.Y.Z, plus the link lines; the body is the changelog part of the fragments
    changelog.d/<KID>.md that came in since the tag before (in the tree of V, not in the tree of the tag before);
  - static/whatsnew.json: the "neu" lines of the same fragments (de / en, at most 3 per fragment, at most 60 versions kept).
Fragments are read like the live train folds them (~/server-data/bin/kalmido-livezug.py fragment_teile / neu_punkte /
whatsnew_einfuegen): first line "Package ...", Keep a Changelog sections, then the optional markers <!-- readme --> and
<!-- neu -->; neither marker section goes into the CHANGELOG. They are read, never deleted; the language fragments
static/i18n/neu/ stay as they are (the app reads them at run time).
The tree of a version that is tagged comes from git (git show vV:...), so a stamp gives the same bytes in release.yml, in the
weekly release (web manifest) and on staging; the date of a section is the date of its tag (today only for an untagged one).

No effect when VERSION already says X.Y.Z (#6893 duty 1): the train's version commit wrote VERSION, the cache line, the
CHANGELOG and whatsnew.json itself - that way stays until #6894 switches it off. --changelog-only adds missing sections only.
Exit 0 = stamped / nothing to do, 2 = refused (bad version, no tag before it, a lower cache number, unreadable files).
Standard library only."""
import argparse
import datetime
import json
import os
import re
import subprocess
import sys

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
FRAG = "changelog.d"
ARCHIV = "docs/changelog"
WHATSNEW = "static/whatsnew.json"
SW = "static/sw.js"
NEU_MAX = 3  # lines per fragment (kalmido-livezug.py NEU_MAX)
NEU_VERSIONEN = 60  # versions whatsnew.json keeps (kalmido-livezug.py NEU_VERSIONEN)
NEU_ZEILE = re.compile(r"^-\s*de:\s*(?P<de>.+?)\s*\|\s*en:\s*(?P<en>.+?)\s*$")
FRAG_MARKE = re.compile(r"(?mi)^\s*<!--\s*(readme|neu)\s*-->\s*$")
VSEC = re.compile(r"(?m)^## \[(\d+)\.(\d+)\.(\d+)\][^\n]*$")
CACHE_RE = re.compile(r"const CACHE = 'tasks-shell-v(\d+)';(\s*// app )(\S+)")
VER_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")
EMPTY_BODY = "- Maintenance release without change notes."


class Refused(Exception):
    pass


def vt(v):
    m = VER_RE.match(v or "")
    if not m:
        raise Refused("no version X.Y.Z: %r" % v)
    return tuple(int(x) for x in m.groups())


def cache_number(v):
    """The shell cache number of version V: monotonic in the version (major, minor, patch compared in that order)."""
    ma, mi, pa = vt(v)
    if mi >= 10 ** 5 or pa >= 10 ** 4:
        raise Refused("version %s: minor >= 100000 or patch >= 10000 does not fit the cache number" % v)
    return ma * 10 ** 9 + mi * 10 ** 4 + pa


# ------------------------------------------------------------------ fragments (the same reading as the train's fold)
def fragment_teile(text):
    """A fragment -> {"changelog", "readme", "neu"}: the text before the first marker, then each marker's section."""
    out = {"changelog": "", "readme": "", "neu": ""}
    ms = list(FRAG_MARKE.finditer(text))
    out["changelog"] = text[:ms[0].start() if ms else len(text)].strip()
    for i, m in enumerate(ms):
        teil = text[m.end():ms[i + 1].start() if i + 1 < len(ms) else len(text)].strip()
        k = m.group(1).lower()
        out[k] = (out[k] + "\n" + teil).strip() if out[k] else teil
    return out


def neu_punkte(text):
    """The neu lines of a fragment -> [{"de", "en"}], at most NEU_MAX; lines not in the form or with a #number are left out
    (einreihen refuses them before; the stamp never stops a build for a text)."""
    items = []
    for z in fragment_teile(text)["neu"].splitlines():
        m = NEU_ZEILE.match(z.strip())
        if m and not re.search(r"#\d", z):
            items.append({"de": m["de"], "en": m["en"]})
    return items[:NEU_MAX]


def whatsnew_einfuegen(alt, v, datum, items):
    """whatsnew.json text with V on top (an entry of V already there is replaced), at most NEU_VERSIONEN; no items = None."""
    if not items:
        return None
    try:
        d = json.loads(alt) if alt and alt.strip() else {}
    except ValueError:
        d = {}
    vs = [x for x in (d.get("versions") if isinstance(d, dict) else None) or [] if isinstance(x, dict) and x.get("version") != v]
    vs.insert(0, {"version": v, "date": datum, "items": items})
    return json.dumps({"versions": vs[:NEU_VERSIONEN]}, ensure_ascii=False, indent=1) + "\n"


def frag_key(name):
    stem = name[:-3]
    return (0, int(stem), name) if stem.isdigit() else (1, 0, name)


# ------------------------------------------------------------------ git
def git(root, *args):
    p = subprocess.run(["git", "-C", root, *args], capture_output=True, text=True, encoding="utf-8")
    if p.returncode != 0:
        raise Refused("git %s: %s" % (" ".join(args), (p.stderr or "").strip()[:300]))
    return p.stdout


def tags(root):
    """{version: tag name} of the release tags vX.Y.Z of the repository at ROOT."""
    try:
        out = git(root, "tag", "-l", "v*.*.*")
    except Refused:
        return {}
    return {t[1:]: t for t in out.split() if VER_RE.match(t[1:])}


def tag_date(root, tag):
    out = git(root, "for-each-ref", "refs/tags/" + tag, "--format=%(creatordate:short)").strip()
    return out or None


def frag_names_tag(root, tag):
    out = git(root, "ls-tree", "--name-only", tag, FRAG + "/")
    return {os.path.basename(x) for x in out.split("\n") if x.endswith(".md")}


def frag_names_dir(root):
    d = os.path.join(root, FRAG)
    return {x for x in os.listdir(d) if x.endswith(".md")} if os.path.isdir(d) else set()


def frag_text(root, name, tag):
    if tag:
        return git(root, "show", "%s:%s/%s" % (tag, FRAG, name))
    with open(os.path.join(root, FRAG, name), encoding="utf-8") as f:
        return f.read()


# ------------------------------------------------------------------ the parts
def read(root, rel):
    p = os.path.join(root, rel)
    if not os.path.exists(p):
        return None
    with open(p, encoding="utf-8") as f:
        return f.read()


def write(root, rel, text):
    with open(os.path.join(root, rel), "w", encoding="utf-8") as f:
        f.write(text)


def newest_section(root):
    """The newest version with a section in CHANGELOG.md or the archive docs/changelog/*.md; (0, 0, 0) = none."""
    texts = [read(root, "CHANGELOG.md") or ""]
    ad = os.path.join(root, ARCHIV)
    if os.path.isdir(ad):
        texts += [read(root, os.path.join(ARCHIV, n)) or "" for n in sorted(os.listdir(ad)) if n.endswith(".md")]
    vs = [tuple(int(x) for x in m.groups()) for t in texts for m in VSEC.finditer(t)]
    return max(vs) if vs else (0, 0, 0)


def pending(root, v, tg):
    """The versions that get a section, oldest first: the tags above the newest section up to V, and V itself."""
    top = newest_section(root)
    want = vt(v)
    if want < top:
        raise Refused("version %s is older than the newest CHANGELOG section %d.%d.%d" % ((v,) + top))
    vs = sorted({x for x in tg if top < vt(x) < want}, key=vt)
    return vs + ([v] if want > top else [])


def version_parts(root, v, tg):
    """-> (date, changelog body, neu items) of version V from the fragments since the tag before it."""
    before = sorted((x for x in tg if vt(x) < vt(v)), key=vt)
    if not before:
        raise Refused("no release tag below %s in %s - the fragments since the tag before cannot be told (fetch the tags: "
                      "actions/checkout with fetch-depth: 0)" % (v, root))
    tag = tg.get(v)
    have = frag_names_tag(root, tag) if tag else frag_names_dir(root)
    new = sorted(have - frag_names_tag(root, tg[before[-1]]), key=frag_key)
    body, items = [], []
    for name in new:
        text = frag_text(root, name, tag)
        c = fragment_teile(text)["changelog"]
        if c:
            body.append(c)
        items += neu_punkte(text)
    datum = (tag_date(root, tag) if tag else None) or None
    return datum, "\n\n".join(body) or EMPTY_BODY, items


def changelog_add(s, v, datum, body):
    """CHANGELOG text S with "## [V] - DATUM" above the newest version section and its link line under [Unreleased]."""
    if re.search(r"(?m)^## \[%s\]" % re.escape(v), s):
        return s
    m = VSEC.search(s)
    sec = "## [%s] - %s\n\n%s\n\n" % (v, datum, body.strip())
    if m:
        s = s[:m.start()] + sec + s[m.start():]
    else:
        tail = re.search(r"(?m)^\[[^\]]+\]: http", s)
        at = tail.start() if tail else len(s)
        s = s[:at].rstrip("\n") + "\n\n" + sec + s[at:]
    u = re.search(r"(?m)^\[Unreleased\]: (https?://\S+?)/compare/v\S+\.\.\.HEAD$", s)
    if u:
        gh = u.group(1)
        s = s[:u.start()] + "[Unreleased]: %s/compare/v%s...HEAD\n[%s]: %s/releases/tag/v%s" % (gh, v, v, gh, v) + s[u.end():]
    return s


def sw_stamp(s, v):
    m = CACHE_RE.search(s)
    if not m:
        raise Refused("static/sw.js: no line const CACHE = 'tasks-shell-vN';  // app X")
    n = cache_number(v)
    if n <= int(m.group(1)):
        raise Refused("static/sw.js: cache v%s of the tree is not below v%d of %s - a cache number never goes down" % (m.group(1), n, v))
    return s[:m.start()] + "const CACHE = 'tasks-shell-v%d';%s%s" % (n, m.group(2), v) + s[m.end():]


def stamp(root, v, datum=None, changelog_only=False, log=print):
    """Stamp the tree ROOT with version V (see the head comment). -> the list of what was written ([] = nothing)."""
    vt(v)
    if not changelog_only and (read(root, "VERSION") or "").strip() == v:
        log("stamp_release: VERSION is already %s - nothing stamped (the version commit of the train wrote it)" % v)
        return []
    tg = tags(root)
    if changelog_only and v not in tg:
        raise Refused("--changelog-only needs a tag v%s" % v)
    if changelog_only and vt(v) <= newest_section(root):
        log("stamp_release: the CHANGELOG has a section for %s or a newer one - nothing to add" % v)
        return []
    today = datum or datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
    parts = [(x,) + version_parts(root, x, tg) for x in pending(root, v, tg)]
    sw = None
    if not changelog_only:  # every refusal before the first write: a refused stamp leaves the tree as it was
        sw = read(root, SW)
        if sw is None:
            raise Refused("no %s in %s" % (SW, root))
        sw = sw_stamp(sw, v)
    done = []
    if parts:
        s = read(root, "CHANGELOG.md")
        if s is None:
            raise Refused("no CHANGELOG.md in %s" % root)
        for x, d, body, _ in parts:
            s = changelog_add(s, x, d or today, body)
        if not changelog_only:
            wn = read(root, WHATSNEW)
            for x, d, _, items in parts:
                neu = whatsnew_einfuegen(wn, x, d or today, items)
                if neu is not None:
                    wn = neu
            if wn is not None and wn != read(root, WHATSNEW):
                os.makedirs(os.path.join(root, os.path.dirname(WHATSNEW)), exist_ok=True)
                write(root, WHATSNEW, wn)
                done.append(WHATSNEW)
        write(root, "CHANGELOG.md", s)
        done.append("CHANGELOG.md (%s)" % ", ".join(x for x, *_ in parts))
    if sw is not None:
        write(root, SW, sw)
        write(root, "VERSION", v + "\n")
        done += [SW + " (tasks-shell-v%d)" % cache_number(v), "VERSION"]
    log("stamp_release %s: %s" % (v, "; ".join(done) if done else "nothing to add"))
    return done


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("version", help="X.Y.Z (a tag vX.Y.Z may be given as well)")
    ap.add_argument("--root", default=ROOT, help="the tree to stamp (a git checkout with the tags; default: this checkout)")
    ap.add_argument("--date", help="date of an untagged version's section (default: today, UTC)")
    ap.add_argument("--changelog-only", action="store_true", help="only the missing CHANGELOG sections up to the tag vX.Y.Z")
    a = ap.parse_args(argv)
    v = a.version[1:] if a.version.startswith("v") else a.version
    try:
        stamp(os.path.abspath(a.root), v, a.date, a.changelog_only)
    except (Refused, OSError, UnicodeDecodeError) as e:
        print("stamp_release: refused - %s" % e, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
