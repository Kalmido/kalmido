#!/usr/bin/env python3
"""#7352 (step 4 of audit #5731): no new special way of My tasks beside the drop core.

Where a dragged task or a selection lands is read once (static/js/dragmulti.js dropAt / dropRun / dropTo) and what a place
means belongs to the adapter of the container (DROP_ADAPTERS; docs/dev/kern.md "Dropping tasks: the drop core"). My tasks'
adapters live in static/js/mineorder.js and static/js/mineboard.js. A drop / move / menu / keyboard path elsewhere that asks
"is this My tasks?" itself grows the branches back the audit removed (dnd.js 160 / 161 / 201, dragmulti.js 382 / 405 / 411-413),
so in static/js/*.js outside ALLOW every one of

  moActive(          mseOn(          mbcol          data-key^="ms:"   (or ^='ms: / ^=ms:)

is counted per file (comment lines and trailing // comments do not count). The places that were there when the rule came are
the baseline (tools/drop_core_baseline.json, "file" -> count): it only ever shrinks; a count above it is red (exit 1),
--update writes the lower counts (never adds; without a baseline file it writes the first one).

(#7519) render.js draws My tasks (ALLOW) but the head of a section comes from the adapters' section side (dragmulti.js
sh_head / sh_menu, DROP_ADAPTERS sec): there HEAD_PAT counts instead - mseOn(, .mosec, mseHeadHtml, mseMenu (a head that asks
"is this an own section of My tasks?" itself again).

The way out: a file that only draws My tasks (not a drop path) or a new adapter file is an entry of ALLOW with its reason -
the reason is read in the review. A drop path asks the adapter (DROP_ADAPTERS on() / where() / put()) instead.

usage: python3 tools/check_drop_core.py [-v] [--update] [--root DIR]      exit 1 on a new place. Standard library only.
"""
import glob
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE_REL = os.path.join("tools", "drop_core_baseline.json")
ALLOW = {
    "static/js/mineorder.js": "the adapter of My tasks (moWhere / moPut / mbWhere) and the home of moActive / mseOn",
    "static/js/mineboard.js": "the board of My tasks: its columns (.mbcol) and its adapter part mb_drop / mb_dropMany",
    "static/js/render.js": "draws the view: My tasks as a board or a list (no drop path)",
    "static/js/views.js": "draws the groups of My tasks' own sections (no drop path)",
}
PAT = re.compile(r"\bmoActive\s*\(|\bmseOn\s*\(|\bmbcol\b|data-key\^=[\"']?ms:")
# (#7519): files of ALLOW that still may not draw a section's head on their own (they ask sh_head of the adapters)
HEAD = {"static/js/render.js": "draws the section heads from the adapters' section side (dragmulti.js sh_head)"}
HEAD_PAT = re.compile(r"\bmseOn\s*\(|\.mosec\b|\bmseHeadHtml\b|\bmseMenu\b")
HEAD_HELP = "draw the head from the adapter's section side (dragmulti.js sh_head / sh_menu, DROP_ADAPTERS sec)"
HELP = "ask the drop core's adapter (DROP_ADAPTERS on / where / put in dragmulti.js, My tasks in mineorder.js) instead"


def code_part(line):
    """The line without a trailing // comment ('' for a comment line); a // inside a quote or a URL stays code."""
    s = line.strip()
    if s.startswith(("//", "*", "/*")):
        return ""
    i = line.find(" // ")
    return line if i < 0 else line[:i]


def pat_of(rel):
    """The pattern a file is counted with: HEAD_PAT for the drawing files of HEAD, else PAT."""
    return HEAD_PAT if rel in HEAD else PAT


def counts(root=ROOT):
    """{file: number of places} of static/js/*.js outside ALLOW."""
    out = {}
    for p in sorted(glob.glob(os.path.join(root, "static", "js", "*.js"))):
        rel = os.path.relpath(p, root).replace(os.sep, "/")
        if rel in ALLOW and rel not in HEAD:
            continue
        pat = pat_of(rel)
        with open(p, encoding="utf-8", errors="replace") as f:
            n = sum(len(pat.findall(code_part(ln))) for ln in f)
        if n:
            out[rel] = n
    return out


def places(root, rel):
    """[(line number, text)] of the places in one file (for the message)."""
    with open(os.path.join(root, rel), encoding="utf-8", errors="replace") as f:
        return [(i, ln.strip()[:120]) for i, ln in enumerate(f, 1) if pat_of(rel).search(code_part(ln))]


def main(argv):
    root = argv[argv.index("--root") + 1] if "--root" in argv else ROOT
    base_path = os.path.join(root, BASE_REL)
    have = counts(root)
    if not os.path.exists(base_path):
        if "--update" in argv:
            with open(base_path, "w", encoding="utf-8") as f:
                json.dump(have, f, indent=1, sort_keys=True)
                f.write("\n")
            print(f"check_drop_core: first baseline, {sum(have.values())} place(s) in {len(have)} file(s)")
            return 0
        print(f"check_drop_core: {BASE_REL} is missing (--update writes the first one)")
        return 1
    with open(base_path, encoding="utf-8") as f:
        base = json.load(f)
    err = []
    for rel, n in sorted(have.items()):
        if n > base.get(rel, 0):
            what = "mseOn / .mosec / mseHeadHtml / mseMenu at a section's head" if rel in HEAD else "moActive / mseOn / mbcol / data-key^=ms:"
            err.append(f"{rel}: {n} place(s) of {what}, {base.get(rel, 0)} allowed - {HELP if rel not in HEAD else HEAD_HELP}")
            err += [f"  {rel}:{i}: {t}" for i, t in places(root, rel)]
    fewer = {rel: n for rel, n in base.items() if have.get(rel, 0) < n}
    if "--update" in argv and not err:
        new = {rel: min(n, have.get(rel, 0)) for rel, n in base.items() if have.get(rel, 0)}
        with open(base_path + ".new", "w", encoding="utf-8") as f:
            json.dump(new, f, indent=1, sort_keys=True)
            f.write("\n")
        os.replace(base_path + ".new", base_path)
    for m in err:
        print(m)
    if "-v" in argv or err:
        print(f"check_drop_core: {sum(have.values())} place(s) in {len(have)} file(s) outside the adapters, "
              f"{len([e for e in err if not e.startswith('  ')])} file(s) above the baseline")
        if fewer and "--update" not in argv:
            print(f"  {len(fewer)} file(s) below the baseline (good) -- python3 tools/check_drop_core.py --update shrinks it")
    return 1 if err else 0


LINT_WHY = "a drop, menu or keyboard path that asks 'is this My tasks?' itself grows the special branches back beside the drop core"
LINT_INSTEAD = "the adapter of the container: DROP_ADAPTERS on() / where() / put() (dragmulti.js; My tasks in mineorder.js)"


if __name__ == "__main__":
    import lintmsg  # tools/ is the script's folder, so it is on the path
    with lintmsg.red_hint("check_drop_core", LINT_WHY, LINT_INSTEAD):
        sys.exit(main(sys.argv))
