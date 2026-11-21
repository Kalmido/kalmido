#!/usr/bin/env python3
"""#6500: every store of the browser that holds something of an account stands in ONE register - a new one is red.

The web client keeps the data of an account on the device in localStorage, sessionStorage, IndexedDB, the Cache Storage and
the push subscription. Which of them goes when an account's time on the device ends (sign-out, another account, a backup
restored, the session ended, another sign-in mark / 14 days / no "Stay signed in") is ONE table in static/js/icons.js:
DEV_STORES (kind, name, class own | view | copy | secret | device) and DEV_END (event -> classes), run by devEnd(why)
(docs/dev/kern.md "Data of the account on this device"). Before, every event had its own hand list and every new store
had to be added at each of them; a forgotten one was a bug (the fix series of #7515).

This check finds in static/js/*.js and static/sw.js every

  indexedDB.open('<name>'                 kind idb      caches.open('<name>'      kind cache
  localStorage.setItem('<key>' / `<key>   kind ls       sessionStorage.setItem(   kind ss
  const CACHE = '<name>' (sw.js)          kind cache

and is red when no entry of DEV_STORES of that kind covers the literal (the same name, or an entry ending in '.' or '-'
that is its start; a template literal counts up to its first ${). LS.set / LS.get of icons.js write tasks.* keys: covered
by the entry 'tasks.'. A name that is not a literal (a variable) is not checked. Comment lines do not count.

The places that were there before the rule are the baseline (tools/devstore_baseline.json, "kind|name" -> count). It only
ever shrinks: a NEW place is red (exit 1); --update writes the lower counts (never adds). Pattern of check_drop_core.py.

#7595, the owner of a second place: an entry of DEV_STORES with a 4th field ("feed of kalmido-outbox", "fallback of
kalmido-start") is the second place of one store; which place holds it is the browser's mode, and only its owner writes
it (OWNERS below: file -> top-level functions). Red (no baseline): a write of such a key - localStorage.setItem /
removeItem('<key>', LS.set / LS.del('<key without tasks.>') - outside its owner, and an entry with a role that OWNERS
does not know (or an owner of a key that has no role in the register). Before, tasks.cache had 3 writers with 3 reasons and
tasks.outbox 4 roles at once (the fix series of #7515).

usage: python3 tools/check_devstore.py [-v] [--update] [--root DIR]      exit 1 on a new place. Standard library only.
"""
import argparse
import glob
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REG_RE = re.compile(r"\[\s*'(ls|ss|idb|cache|push)'\s*,\s*'([^']+)'\s*,\s*'(own|view|copy|secret|device)'\s*(?:,\s*'([^']+)'\s*)?\]")
# (#7595): the one owner of each second place (file -> its top-level functions that may write the key)
OWNERS = {
    "tasks.outbox": {"static/js/core.js": {"outSync", "outSave", "obxFeedSet"}},
    "tasks.cache": {"static/js/core.js": {"startSave"}, "static/js/offcache.js": {"oc_lsDrop"}},
}
TOP_FN = re.compile(r"^(?:async\s+)?function\s*\*?\s*(\w+)|^(?:const|let|var)\s+(\w+)\s*=")
Q = r"""(['"`])([^'"`$]*)"""  # a literal up to its end or its first ${
PATS = [("idb", re.compile(r"\bindexedDB\.open\(\s*" + Q)),
        ("cache", re.compile(r"\bcaches\.open\(\s*" + Q)),
        ("ls", re.compile(r"\blocalStorage\.setItem\(\s*" + Q)),
        ("ss", re.compile(r"\bsessionStorage\.setItem\(\s*" + Q)),
        ("cache", re.compile(r"^const CACHE\s*=\s*" + Q))]
COMMENT = re.compile(r"^\s*(//|/\*|\*)")


def files(root):
    return sorted(glob.glob(os.path.join(root, "static", "js", "*.js"))) + [os.path.join(root, "static", "sw.js")]


def register(root, full=False):
    """[(kind, name)] of DEV_STORES (static/js/icons.js); full: [(kind, name, class, role)]."""
    try:
        src = open(os.path.join(root, "static", "js", "icons.js"), encoding="utf-8").read()
    except OSError:
        return []
    i = src.find("const DEV_STORES")
    if i < 0:
        return []
    j = src.find("];", i)
    rows = REG_RE.findall(src[i:j])
    return rows if full else [(k, n) for k, n, _, _ in rows]


def owner_faults(root, owners=None):
    """#7595: ["file:line: text"] - writes of a second place outside its owner, roles without an owner and back."""
    owners = OWNERS if owners is None else owners
    roles = {n for k, n, _, r in register(root, True) if k == "ls" and r}
    out = [f"static/js/icons.js: '{n}' has a role in DEV_STORES but no owner in tools/check_devstore.py OWNERS" for n in sorted(roles - set(owners))]
    out += [f"tools/check_devstore.py: OWNERS names '{n}', the register gives it no role" for n in sorted(set(owners) - roles)]
    pats = []
    for key in sorted(roles & set(owners)):
        alts = [r"\blocalStorage\.(?:setItem|removeItem)\(\s*['\"`]" + re.escape(key) + r"['\"`]"]
        if key.startswith("tasks."):
            alts.append(r"\bLS\.(?:set|del)\(\s*['\"`]" + re.escape(key[len("tasks."):]) + r"['\"`]")
        pats.append((key, re.compile("|".join(alts))))
    for f in files(root):
        if not os.path.exists(f):
            continue
        rel = os.path.relpath(f, root).replace(os.sep, "/")
        fn = None
        for n, line in enumerate(open(f, encoding="utf-8"), 1):
            m = TOP_FN.match(line)
            if m:
                fn = m.group(1) or m.group(2)
            if COMMENT.match(line):
                continue
            for key, rx in pats:
                if rx.search(line) and fn not in owners[key].get(rel, set()):
                    who = ", ".join(f"{p} {'/'.join(sorted(fs))}" for p, fs in sorted(owners[key].items()))
                    out.append(f"{rel}:{n}: '{key}' written outside its owner (in {fn or 'the top level'}; owner: {who})")
    return out


def fits(key, name):
    return key == name or (name[-1:] in ".-" and key.startswith(name))


def places(root):
    """{"kind|name": [(file, line)]} of the stores no entry covers."""
    reg, out = register(root), {}
    for f in files(root):
        if not os.path.exists(f):
            continue
        rel = os.path.relpath(f, root)
        for n, line in enumerate(open(f, encoding="utf-8"), 1):
            if COMMENT.match(line):
                continue
            for kind, rx in PATS:
                for m in rx.finditer(line):
                    name = m.group(2)
                    if not name or any(k == kind and fits(name, r) for k, r in reg):
                        continue
                    out.setdefault(f"{kind}|{name}", []).append((rel, n))
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("-v", action="store_true", help="list every place")
    ap.add_argument("--update", action="store_true", help="write the lower counts into the baseline (never adds)")
    ap.add_argument("--root", default=ROOT)
    a = ap.parse_args()
    base_f = os.path.join(a.root, "tools", "devstore_baseline.json")
    try:
        base = json.load(open(base_f, encoding="utf-8"))
    except (OSError, ValueError) as e:
        print(f"check_devstore: the baseline tools/devstore_baseline.json is missing or broken ({e})")
        return 1
    if not register(a.root):
        print("check_devstore: no DEV_STORES in static/js/icons.js - the register is gone?")
        return 1
    found = places(a.root)
    new = {k: v for k, v in found.items() if len(v) > base.get(k, 0)}
    own = owner_faults(a.root)
    if a.v:
        for k, v in sorted(found.items()):
            print(f"  {k}: {len(v)} (baseline {base.get(k, 0)}) " + ", ".join(f"{f}:{n}" for f, n in v))
    if a.update:
        low = {k: min(c, len(found.get(k, []))) for k, c in base.items() if found.get(k)}
        json.dump(low, open(base_f, "w", encoding="utf-8"), indent=1, sort_keys=True)
        open(base_f, "a", encoding="utf-8").write("\n")
    for k, v in sorted(new.items()):
        kind, name = k.split("|", 1)
        for f, n in v:
            print(f"{f}:{n}: a store of the browser without its entry in the register: {kind} '{name}'")
    for x in own:
        print(x)
    if own:
        print("check_devstore: Why (#7595): a second place of one store (the feed of the queue, the fallback of the start state) "
              "has ONE writer; every other writer decided again which place holds the store, and the states drifted apart.\n"
              "check_devstore: Instead: go through the owner (core.js outSave / outStash for the queue, core.js startSave for the "
              "start state) - or, a new second place, its role in DEV_STORES and its owner in OWNERS.")
    if new:
        print("check_devstore: Why: what the device keeps of an account must go with the right event (sign-out, the session "
              "ended, another sign-in); a store outside the register stays for the next person on a shared computer.\n"
              "check_devstore: Instead: one line in DEV_STORES (static/js/icons.js) with its class (own / view / copy / secret / "
              "device) and, if it is no key, its drop with devDrop(name, fn) where the store lives (docs/dev/kern.md "
              "\"Data of the account on this device\").")
        return 1
    if own:
        return 1
    print(f"check_devstore: {len(register(a.root))} entries in the register, {sum(len(v) for v in found.values())} place(s) "
          f"outside it (baseline {sum(base.values())}), 0 new")
    return 0


if __name__ == "__main__":
    sys.exit(main())
