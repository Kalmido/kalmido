#!/usr/bin/env python3
"""#6372: no toast shows the raw text of an error - every one says first what did not work.

A failed request or step tells the person what did not work: `toast(errText(e, tr('The page could not be saved')))` (core.js
errText: "<what> (<the server's text>)", offline = "Only available online."). A toast whose message is the bare error text
(`toast(e.message)`, `toast(x.message || ...)`, `toast(r.statusText)`) showed a raw server or Python text ("Payload Too Large",
"Testfehler") without saying what failed. Where the view already shows an error block, there is no toast at all.

Finding: in static/js/*.js a call toast(...) whose first argument reads `.message` or `.statusText` outside errText(...).

usage: python3 tools/check_errtext.py [-v] [--selftest]      exit 1 on a finding
Standard library only.
"""
import glob
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lintmsg  # noqa: E402 -- tools/ is not a package; the line above puts it on the path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CALL = re.compile(r"(?<![\w.$])toast\(")
RAW = re.compile(r"(?:\?\.|\.)(?:message|statusText)\b")
WHY = "a toast with the bare error text says nothing about what failed (#6372)"
INSTEAD = "toast(errText(e, tr('What did not work'))) - core.js errText; where the view shows an error block, no toast"


def first_arg(src, i):
    """the text of the first argument of the call whose '(' is at src[i-1] (strings, template literals, nesting skipped)."""
    depth, j, q = 0, i, None
    while j < len(src):
        ch = src[j]
        if q:
            if ch == "\\":
                j += 2
                continue
            if ch == q:
                q = None
        elif ch in "'\"`":
            q = ch
        elif ch in "([{":
            depth += 1
        elif ch in ")]}":
            if depth == 0:
                return src[i:j]
            depth -= 1
        elif ch == "," and depth == 0:
            return src[i:j]
        j += 1
    return src[i:j]


def blank_errtext(arg):
    """arg with every errText(...) / httpErrText(...) call removed (what they wrap is the allowed form)."""
    out = arg
    for name in ("httpErrText(", "errText("):
        while True:
            k = out.find(name)
            if k < 0:
                break
            a = k + len(name)

            # skip the rest of the call (more arguments) up to its ')'
            end, depth, q = a, 0, None
            while end < len(out):
                ch = out[end]
                if q:
                    if ch == "\\":
                        end += 2
                        continue
                    if ch == q:
                        q = None
                elif ch in "'\"`":
                    q = ch
                elif ch in "([{":
                    depth += 1
                elif ch in ")]}":
                    if depth == 0:
                        break
                    depth -= 1
                end += 1
            out = out[:k] + "0" + out[end + 1:]
    return out


def findings_in(src):
    res = []
    for m in CALL.finditer(src):
        arg = first_arg(src, m.end())
        if RAW.search(blank_errtext(arg)):
            res.append((src.count("\n", 0, m.start()) + 1, ("toast(" + arg + ")").replace("\n", " ")[:140]))
    return res


def selftest():
    bad = ["toast(e.message)", "toast(e?.message || tr('x'))", "toast(j.error || r.statusText)", "toast(err.message, null, 5000)"]
    good = ["toast(errText(e, tr('The page could not be saved')))", "toast(tr('Saved'))", "x.toast(e.message)",
            "toast(errText(e, tr('a {0}', x.message)))", "toast(httpErrText(r.status))", "mytoast(e.message)"]
    ok = all(findings_in(s) for s in bad) and not any(findings_in(s) for s in good)
    if not ok or "--selftest" in sys.argv:
        print("check_errtext selftest:", "ok" if ok else "FAILED")
    return ok


def main():
    if "--selftest" in sys.argv:
        return 0 if selftest() else 1
    verbose = "-v" in sys.argv
    if not selftest():  # the checker's own cases first (a broken parser must not pass everything)
        return 1
    bad = []
    files = sorted(glob.glob(os.path.join(ROOT, "static", "js", "*.js")))
    for p in files:
        with open(p, encoding="utf-8") as f:
            src = f.read()
        for ln, txt in findings_in(src):
            bad.append(f"{os.path.relpath(p, ROOT)}:{ln}: {txt}")
    for b in bad:
        print(b)
    if bad:
        print(f"check_errtext: {len(bad)} toast(s) with the raw error text")
        lintmsg.say("check_errtext", WHY, INSTEAD)  # Why / Instead / do not suppress it, as every check (#7143)
        return 1
    if verbose:
        print(f"check_errtext: {len(files)} client files, 0 toasts with the raw error text")
    return 0


if __name__ == "__main__":
    sys.exit(main())
