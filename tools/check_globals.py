#!/usr/bin/env python3
"""(#6831): a ratchet on the coupling of the web client's shared global scope (architecture review #2522, point 6).

The classic scripts static/i18n.js + static/js/*.js share ONE global scope (tools/eslint_globals.py), and the app state
S (static/js/core.js `const S = {...}`) is written from many files. Two measures, each compared with a base revision
(--base REV: the merge queue's base, a pull request's base, the commit before a push):

  s_writers  per key of S the files that write it, without the file that makes the key (core.js for every key of its
             `const S = {...}`; a key not in it: the first file in load order that writes it). A write: S.key (or a member
             of it: S.key.x / S.key[i]) followed by =, +=, ..., ||=, ??=, ++ / -- around it, or `delete S.key...`;
             reading, calling and comparing are no writes. A file that newly writes a key another file makes is RED:
             write it through a setter of the file that makes it. So the pairs only stay or shrink.
  names      the top-level names of static/i18n.js + static/js/*.js (tools/eslint_globals.py names()). Shown with the
             change against the base, never red: the client grows by about 100 names a day (measured 10. - 17.11.2026),
             a frozen count would stop every package with new client code.

No baseline file (decided while building, #6831): a stored list goes stale as soon as another package lands first, the
comparison with the base revision cannot.

usage: python3 tools/check_globals.py --base REV [-v]   exit 1 on a new foreign writer of S, 2 when REV cannot be read
       python3 tools/check_globals.py [-v]              the current numbers only (exit 0)
       python3 tools/check_globals.py --selftest
Standard library only (git for --base).
"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import eslint_globals as EG  # noqa: E402  (scanner: tokens(), names(), FILES)
import lintmsg  # noqa: E402 -- tools/ is not a package; the line above puts it on the path

WHY = ("every file that writes a key of the shared state S makes the client harder to change: who set a value can no longer "
       "be told from one place")
INSTEAD = "write the key through a setter of the file that makes it (core.js for the keys of its `const S = {...}`)"

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OWNER = "static/js/core.js"
ASSIGN2 = {"+=", "-=", "*=", "/=", "%=", "&=", "|=", "^="}
ASSIGN3 = {"**=", "&&=", "||=", "??=", "<<=", ">>="}


def _chain_end(toks, k):
    """From the token after S.key: skip member accesses (.x, [..]) -> index of the first token after the chain."""
    n = len(toks)
    while k < n:
        if toks[k][1] == "." and k + 1 < n and toks[k + 1][0] == "id":
            k += 2
        elif toks[k][1] == "?" and k + 2 < n and toks[k + 1][1] == "." and toks[k + 2][0] == "id":
            return k  # optional chaining cannot be assigned to
        elif toks[k][1] == "[":
            d = toks[k][2]
            k += 1
            while k < n and not (toks[k][1] == "]" and toks[k][2] == d):
                k += 1
            k += 1
        else:
            return k
    return k


def _assigns(toks, k):
    """True when the punctuation from k is an assignment (or ++ / --)."""
    p = "".join(t[1] if t[0] == "punct" else " " for t in toks[k:k + 4])
    if p[:1] == "=" and p[1:2] not in ("=", ">"):
        return True
    return p[:2] in ASSIGN2 or p[:3] in ASSIGN3 or p[:4] == ">>>=" or p[:2] in ("++", "--")


def s_writes(src):
    """The keys of S one script writes (set)."""
    toks = list(EG.tokens(src))
    out = set()
    for k in range(len(toks) - 2):
        if not (toks[k] == ("id", "S", toks[k][2]) and toks[k + 1][1] == "." and toks[k + 2][0] == "id"):
            continue
        if k and toks[k - 1][1] == ".":
            continue  # x.S.key: another object's S
        key = toks[k + 2][1]
        pre = "".join(t[1] for t in toks[max(0, k - 2):k] if t[0] == "punct")
        if _assigns(toks, _chain_end(toks, k + 3)) or pre.endswith(("++", "--")) or (k and toks[k - 1][1] == "delete"):
            out.add(key)
    return out


def s_keys(src):
    """The keys of the literal `const S = {...}` (top level of the object)."""
    toks = list(EG.tokens(src))
    for k in range(len(toks) - 3):
        if toks[k][1] == "const" and toks[k + 1][1] == "S" and toks[k + 2][1] == "=" and toks[k + 3][1] == "{":
            d, keys, j = toks[k + 3][2], set(), k + 4
            while j < len(toks) and not (toks[j][1] == "}" and toks[j][2] == d):
                if toks[j][2] == d + 1 and toks[j][0] == "id" and j + 1 < len(toks) and toks[j + 1][1] in (":", ",", "}") \
                        and toks[j - 1][1] in ("{", ","):
                    keys.add(toks[j][1])
                j += 1
            return keys
    return set()


def measure(sources):
    """sources: {file: source} in load order -> {"names": n, "s_writers": {key: [file, ...]}}."""
    names = set()
    for src in sources.values():
        names |= EG.names(src)
    made = s_keys(sources.get(OWNER, ""))
    writers = {}
    for rel, src in sources.items():
        for key in s_writes(src):
            writers.setdefault(key, []).append(rel)
    out = {}
    for key, files in writers.items():
        owner = OWNER if key in made else files[0]
        foreign = sorted(f for f in files if f != owner)
        if foreign:
            out[key] = foreign
    return {"names": len(names), "s_writers": dict(sorted(out.items()))}


def collect(rev=None):
    """The measures of the working tree, or of revision rev (git show)."""
    if rev is None:
        files = EG.FILES
        def read(rel):
            with open(os.path.join(ROOT, rel), encoding="utf-8") as fh:
                return fh.read()
    else:
        ls = subprocess.run(["git", "-C", ROOT, "ls-tree", "--name-only", rev, "static/js/"], capture_output=True, text=True)
        if ls.returncode:
            raise RuntimeError(ls.stderr.strip() or "git ls-tree failed")
        files = ["static/i18n.js"] + sorted(x for x in ls.stdout.split() if x.endswith(".js") and x.count("/") == 2)
        def read(rel):
            return subprocess.run(["git", "-C", ROOT, "show", f"{rev}:{rel}"], capture_output=True, text=True, check=True).stdout
    return measure({rel: read(rel) for rel in files})


def compare(cur, base):
    """-> (new foreign writers [line], gone ones [line])."""
    bad, fixed = [], []
    bw = base.get("s_writers", {})
    for key, files in cur["s_writers"].items():
        for f in sorted(set(files) - set(bw.get(key, []))):
            bad.append(f"{f}: writes S.{key}, which another file makes - write it through a setter of that file "
                       f"(tools/check_globals.py, #6831: no new file writes a key of S it does not make)")
    for key, files in bw.items():
        for f in sorted(set(files) - set(cur["s_writers"].get(key, []))):
            fixed.append(f"S.{key}: {f} no longer writes it")
    return bad, fixed


def selftest():
    f = 0
    core = "const S = {route: {}, v: 0, me: null, lists: []};\nfunction setRoute(r) { S.route = r; }\nconst a = 1, b = 2;\n"
    other = ("function go() { S.route.mod = 'x'; if (S.v === 1 && S.me) S.lists.push(1); S.v++; }\n"
             "const t = S.v == 2 ? S.v >= 1 : S.v <= 0; S.extra ??= 3; delete S.me.x; x.S.route = 1;\n"
             "S.lists[0] = 2; S.v += 1; const f = () => S.route; window.goAll = go; S?.v;\n")
    third = "S.extra = 1; S.lists = []; let q = S.lists.length;\n"
    m = measure({"static/js/core.js": core, "static/js/a.js": other, "static/js/b.js": third})
    want = {"route": ["static/js/a.js"], "v": ["static/js/a.js"], "me": ["static/js/a.js"], "lists": ["static/js/a.js", "static/js/b.js"],
            "extra": ["static/js/b.js"]}
    if m["s_writers"] != want:
        print("selftest: writers", m["s_writers"], "want", want)
        f += 1
    if m["names"] != 9:  # S setRoute a b | go t f goAll (window.goAll =) | q
        print("selftest: names", m["names"], "want 9")
        f += 1
    bad, fixed = compare(m, {"s_writers": {**want, "lists": ["static/js/a.js"]}})
    if len(bad) != 1 or "b.js: writes S.lists" not in bad[0] or fixed:
        print("selftest: a new writer is red", bad, fixed)
        f += 1
    bad, fixed = compare(m, {"s_writers": {**want, "pomo": ["static/js/c.js"]}})
    if bad or len(fixed) != 1:
        print("selftest: a gone writer is a note, not red", bad, fixed)
        f += 1
    print("check_globals selftest:", "FAILED %d" % f if f else "ok")
    return 1 if f else 0


def main(argv):
    if "--selftest" in argv:
        return selftest()
    cur = collect()
    nw = sum(len(v) for v in cur["s_writers"].values())
    nf = len({f for v in cur["s_writers"].values() for f in v})
    if "--base" not in argv:
        print(f"check_globals: {cur['names']} top-level names, {nw} foreign writers of S in {nf} files (no --base: nothing compared)")
        return 0
    rev = argv[argv.index("--base") + 1] if argv.index("--base") + 1 < len(argv) else ""
    try:
        base = collect(rev)
    except (RuntimeError, subprocess.CalledProcessError, ValueError, OSError) as e:  # OSError: no git
        print(f"check_globals: the base {rev!r} cannot be read: {e}")
        return 2
    bad, fixed = compare(cur, base)
    for x in bad:
        print(x)
    if bad:
        import lintmsg  # tools/ is on the path (above)
        lintmsg.say("check_globals", LINT_WHY, LINT_INSTEAD)
    if "-v" in argv:
        for x in fixed:
            print(f"fewer than in the base (good): {x}")
    d = cur["names"] - base["names"]
    print(f"check_globals: {cur['names']} top-level names ({d:+d} against {rev[:12]}, shown only), {nw} foreign writers of S in {nf} files; "
          f"{len(bad)} new, {len(fixed)} gone")
    return 1 if bad else 0


LINT_WHY = ("a file that writes a key of S another file makes couples the two: the state changes from places the owner does "
            "not see, and a redraw or a cache of the owner misses it")
LINT_INSTEAD = ("write it through a setter (a function) of the file that makes the key, or let the key belong to this file "
                "when only it uses it")


if __name__ == "__main__":
    with lintmsg.red_hint("check_globals", WHY, INSTEAD):
        sys.exit(main(sys.argv[1:]))
