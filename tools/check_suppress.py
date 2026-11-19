#!/usr/bin/env python3
"""Suppressions only with a reason, and fewer, never more (#7143).

A suppression marker turns a check off for one line: `# noqa: CODE` (ruff), `nosemgrep` (semgrep), `eslint-disable`
(ESLint) and the "-ok" markers of the own checks (`sprung-ok:`, `lazy-ok`, `coltype-ok:` ... see MARKS). Each one is a place
where a rule found something and the code stayed as it was. Two rules hold for them:

  1. A new marker carries its reason in the same comment: `# noqa: BLE001 -- the worker never dies on one run`,
     `// eslint-disable-line no-new -- the instance registers itself`, `/* sprung-ok: the person asked for it */`.
     A reason is at least two words beside the marker and its codes (a version mark like "2.755.0 (#5294)" is none).
  2. The number per marker kind only falls. tools/suppress_baseline.json holds it per kind ("noqa:BLE001", "nosemgrep",
     "mark:sprung-ok", ...) and per file; a kind whose TOTAL rises is red (moving code between files is no finding).
     Rule 1 is the same ratchet on the kinds "<kind> without reason": a new marker without its reason raises that count.

Rule 2 is red for every kind but SOFT (import order / lambda style / re-exports of ruff and the own check markers - those
are counted and named, a rise is a notice; a kind turns sharp when it leaves SOFT). Rule 1 is red for every kind but
NO_REASON_SYNTAX (a marker whose form has no room for a reason).

Read: the product code - app.py, kalmido/, mcp/, tools/, embed/, static/*.js, static/js/ (not static/vendor, not tests/:
test scaffolding has its own check, tools/check_nosham.py). Python by its comment tokens (and the SQL "--" comments inside
its strings), JavaScript by its // and /* */ comments, so a docstring that names a marker is no marker.

usage: python3 tools/check_suppress.py [-v] [--notice] [--root DIR] [--update] [--list KIND]     exit 1 = red
  --update   lowers the baseline to today's numbers (never raises one, never adds a kind)
  --list K   every place of kind K (e.g. --list "noqa:BLE001 without reason")
Standard library only.
"""
import io
import os
import re
import sys
import tokenize

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lintmsg  # noqa: E402 -- tools/ is not a package; the line above puts it on the path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASELINE = os.path.join("tools", "suppress_baseline.json")
ABOUT = ("tools/check_suppress.py (#7143): suppression markers per kind and file, and the ones without a reason; "
         "a total only falls (--update lowers, never raises)")
SCOPE = ("app.py", "kalmido/", "mcp/", "tools/", "embed/", "static/js/")
SKIP_DIRS = {".git", "node_modules", "__pycache__", "vendor", ".data"}
# the own checks' markers; each check is the place that defines it (its docstring names the marker, that is no use)
MARKS = ("sprung-ok", "lazy-ok", "task-insert-ok", "drop-ok", "widen-ok", "unique-ok", "nullable-ok", "purge-ok", "menu-ok",
         "arity-ok", "coltype-ok", "canwrite-ok", "html-ok")
SOFT = {"noqa:E402", "noqa:E731", "noqa:F401"} | {f"mark:{m}" for m in MARKS}
NO_REASON_SYNTAX = {"mark:html-ok"}  # ${/*html-ok*/ expr}: tools/check_innerhtml.py matches the exact text
NOQA = re.compile(r"#\s*noqa\b(?::\s*(?P<codes>[A-Z]+[0-9]+(?:\s*,\s*[A-Z]+[0-9]+)*))?", re.I)
NOSEMGREP = re.compile(r"\bnosemgrep\b(?::\s*[\w.\-]+(?:\s*,\s*[\w.\-]+)*)?")
ESLINT = re.compile(r"\beslint-disable(?:-next-line|-line)?\b(?:\s+[@\w/\-]+(?:\s*,\s*[@\w/\-]+)*)?")
MARK = re.compile(r"(?<![\w-])(?P<m>" + "|".join(re.escape(m) for m in MARKS) + r")(?![\w-]):?")
VERSION = re.compile(r"\b2\.\d+(?:\.\d+)?(?:\s+[A-Z]\d?)?\s*(?:\(#\d+\)|,\s*#\d+)?")
ANY = re.compile(r"noqa|nosemgrep|eslint-disable|-ok\b", re.I)  # a file without any of these has no marker
WORD = re.compile(r"[A-Za-zÄÖÜäöüß]{2,}")
WHY = ("a marker hides a finding for good; without its reason nobody can tell later whether it still holds, and every "
       "marker makes the next one look normal")
INSTEAD = ("fix what the rule found (ruff BLE001: the narrowest exception class plus a log line; the own checks name their "
           "helper); a marker that must stay gets its reason in the same comment: '# noqa: BLE001 -- <why>'")


def has_reason(comment, marker_span):
    """At least two words in the comment beside the marker (and its codes) and beside version marks."""
    a, b = marker_span
    rest = VERSION.sub(" ", comment[:a] + " " + comment[b:])
    rest = re.sub(r"\b(?:noqa|nosemgrep|eslint-disable[\w-]*)\b", " ", rest)
    return len(WORD.findall(rest)) >= 2


def found_in(comment):
    """[(kind, has reason)] of one comment's text."""
    out = []
    for m in NOQA.finditer(comment):
        codes = [c.upper() for c in re.split(r"\s*,\s*", m.group("codes"))] if m.group("codes") else [""]
        for c in codes:
            out.append(("noqa:" + c if c else "noqa", has_reason(comment, m.span())))
    for rx, kind in ((NOSEMGREP, "nosemgrep"), (ESLINT, "eslint-disable")):
        for m in rx.finditer(comment):
            out.append((kind, has_reason(comment, m.span())))
    for m in MARK.finditer(comment):
        out.append(("mark:" + m.group("m"), has_reason(comment, m.span())))
    return out


def py_comments(text):
    """[(line, comment text)] of Python source: comment tokens and the SQL '-- ...' comments inside string literals."""
    out = []
    try:
        for t in tokenize.generate_tokens(io.StringIO(text).readline):
            if t.type == tokenize.COMMENT:
                out.append((t.start[0], t.string))
            elif t.type == tokenize.STRING and "--" in t.string:
                for i, ln in enumerate(t.string.split("\n")):
                    k = ln.find("--")
                    if k >= 0 and not ln[:k].rstrip().endswith(("<!", "-")):
                        out.append((t.start[0] + i, ln[k:]))
    except (tokenize.TokenError, IndentationError, SyntaxError):
        # not valid Python (py_compile reports it): every '#' to the end of a line counts as a comment
        out = [(i, ln[ln.index("#"):]) for i, ln in enumerate(text.split("\n"), 1) if "#" in ln]
    return out


JS_LINE = re.compile(r"(?<![:\\'\"])//(.*)$")
JS_BLOCK = re.compile(r"/\*(.*?)(?:\*/|$)")


def js_comments(text):
    """[(line, comment text)] of JavaScript: // to the end of the line and /* ... */ on one line (a // inside a string is
    rare and only counts when a marker follows it)."""
    out = []
    for i, ln in enumerate(text.split("\n"), 1):
        for m in JS_BLOCK.finditer(ln):
            out.append((i, m.group(1)))
        rest = JS_BLOCK.sub(" ", ln)
        m = JS_LINE.search(rest)
        if m:
            out.append((i, m.group(1)))
    return out


def files(root):
    for top in SCOPE:
        p = os.path.join(root, top)
        if os.path.isfile(p):
            yield top
            continue
        for d, dirs, names in os.walk(p):
            dirs[:] = sorted(x for x in dirs if x not in SKIP_DIRS)
            for n in sorted(names):
                if n.endswith((".py", ".js", ".mjs")):
                    yield os.path.relpath(os.path.join(d, n), root).replace(os.sep, "/")
    sd = os.path.join(root, "static")
    for n in sorted(os.listdir(sd)) if os.path.isdir(sd) else []:
        if n.endswith(".js"):
            yield "static/" + n


def places(root=ROOT):
    """[(kind, path, line, has reason, comment)] of the product code."""
    out = []
    for rel in files(root):
        if rel in ("tools/check_suppress.py", "tools/lintmsg.py"):
            continue
        with open(os.path.join(root, rel), encoding="utf-8", errors="replace") as f:
            text = f.read()
        if not ANY.search(text):
            continue
        comments = py_comments(text) if rel.endswith(".py") else js_comments(text)
        own_check = rel.startswith("tools/check_")
        for line, c in comments:
            for kind, ok in found_in(c):
                if own_check and kind.startswith("mark:"):
                    continue  # the check that defines the marker names it in its messages and comments
                out.append((kind, rel, line, ok, c.strip()))
    return out


def counts(pl):
    """The ratchet's counts: per kind, and per "<kind> without reason"."""
    per = {}
    for kind, rel, _line, ok, _c in pl:
        per.setdefault(kind, {}).setdefault(rel, 0)
        per[kind][rel] += 1
        if not ok:
            k2 = kind + " without reason"
            per.setdefault(k2, {}).setdefault(rel, 0)
            per[k2][rel] += 1
    return lintmsg.as_counts(per)


def sharp(rule):
    if rule.endswith(" without reason"):
        return rule[: -len(" without reason")] not in NO_REASON_SYNTAX
    return rule not in SOFT


def label(rule):
    if rule.endswith(" without reason"):
        return f"new '{rule[:-len(' without reason')]}' without its reason in the same comment"
    return f"'{rule}' markers"


def main(argv):
    root = argv[argv.index("--root") + 1] if "--root" in argv else ROOT
    pl = places(root)
    if "--list" in argv:
        want = argv[argv.index("--list") + 1]
        for kind, rel, line, ok, c in pl:
            if kind == want or (want.endswith(" without reason") and not ok and kind == want[:-len(" without reason")]):
                print(f"{rel}:{line}: {c[:160]}")
        return 0
    now, path = counts(pl), os.path.join(root, BASELINE)
    base = lintmsg.load(path)
    if "--update" in argv:
        new = lintmsg.lowered(now, base)
        lintmsg.save(path, ABOUT, new)
        print(f"check_suppress: baseline {sum(v['total'] for v in base.values())} -> {sum(v['total'] for v in new.values())}")
        base = new
    # --notice (the lint job): every rise is a notice - the total moves with every package merged meanwhile, so the ratchet
    # per change is tools/pr_lint.py suppress (net per kind of the lines a change adds and removes)
    rose, fell = lintmsg.compare(now, base, (lambda r: False) if "--notice" in argv else sharp)
    red = lintmsg.report("check_suppress", rose, fell, label, "python3 tools/check_suppress.py --update")
    if red:
        print("check_suppress: the places: python3 tools/check_suppress.py --list '<kind>' (e.g. 'noqa:BLE001 without reason')")
    if "-v" in argv or red:
        tot = sum(v["total"] for k, v in now.items() if not k.endswith(" without reason"))
        nr = sum(v["total"] for k, v in now.items() if k.endswith(" without reason"))
        print(f"check_suppress: {tot} marker(s), {nr} without a reason, {red} red rule(s)")
    return 1 if red else 0


if __name__ == "__main__":
    with lintmsg.red_hint("check_suppress", WHY, INSTEAD):
        sys.exit(main(sys.argv))
