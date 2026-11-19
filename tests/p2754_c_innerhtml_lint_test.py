#!/usr/bin/env python3
# kalmido-suite: nodata
"""2.754.0 (#5297) tools/check_innerhtml.py: every ${} in an HTML template is escaped, a safe helper, or marked.
 1. the web client as it is: no finding beyond tools/innerhtml_baseline.json
 2. the rule on small sources (selftest of the tool): a bare value, a ternary with a bare branch, a join of bare values are
    findings; esc(), tr(), trh(), numbers, x.length, constants, markup built on purpose, the mark are not
 3. a NEW unescaped value in a file is red (a copy of a start file with one added line), a fixed one is not
 4. the key leaves comments out (#7173): a comment next to an old finding changed or removed is no new finding (static/js/
    office_docs.js with its version marks taken out stays inside the baseline); '//' and '/*' inside a string, a template
    or a regex literal stay part of the key, so two different findings never share one
usage: python3 tests/p2754_c_innerhtml_lint_test.py"""
import os
import subprocess
import sys

N = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(N, "..")
sys.path.insert(0, N)
sys.path.insert(0, os.path.join(ROOT, "tools"))
from kt import check, done  # noqa: E402
import check_innerhtml as C  # noqa: E402

TOOL = os.path.join(ROOT, "tools", "check_innerhtml.py")
r = subprocess.run([sys.executable, TOOL], capture_output=True, text=True, timeout=300)
check(r.returncode == 0, "the web client: no new unescaped ${} in an HTML template: " + (r.stdout + r.stderr)[-800:])
r = subprocess.run([sys.executable, TOOL, "--selftest"], capture_output=True, text=True, timeout=60)
check(r.returncode == 0, "selftest: " + (r.stdout + r.stderr)[-800:])

new = "el.innerHTML = `<b>${userName}</b>`;\n"
check(len(list(C.scan(new))) == 1, "a new bare value in an HTML template is found")
check(not list(C.scan("el.innerHTML = `<b>${esc(userName)}</b>`;\n")), "esc() is clean")
check(not list(C.scan("el.innerHTML = `<b>${/*html-ok*/ built}</b>`;\n")), "the mark is clean")
# the baseline counts per file|expression: one more of a known pair is new, the known number is not
k = next(iter(C.json.load(open(C.BASE, encoding="utf-8"))))
check(isinstance(k, str) and "|" in k, "baseline keys are file|expression")

# 4. comments are no part of the key (#7173)
import collections  # noqa: E402
import re  # noqa: E402
one = list(C.scan("el.innerHTML = `<b>${x ? rinBox(d) : '' /* 2.91.0 A (#1923) */}</b>`;\n"))
two = list(C.scan("el.innerHTML = `<b>${x ? rinBox(d) /* the box */ : ''}</b>`;\n"))
three = list(C.scan("el.innerHTML = `<b>${x ? rinBox(d) // a line comment\n : ''}</b>`;\n"))
check(one and [e for _l, e in one] == [e for _l, e in two] == [e for _l, e in three] == ["x ? rinBox(d) : ''"],
      f"a block or line comment changes no key: {one} {two} {three}")
check(not list(C.scan("el.innerHTML = `<b>${/* why */ /*html-ok*/ h}</b>`;\n")), "the mark next to another comment is still the mark")
keys = {C.key(a) for a in ("f('https://a')", "f('https:/')", "f('a/*b')", "f('a')", "f(/a\\/\\//g)", "f(/a/g)", "f(`<i>//x</i>`)", "f(`<i></i>`)")}
check(len(keys) == 8, f"'//' and '/*' in strings, regex literals and templates stay in the key: {sorted(keys)}")
check(C.key("a / b // c\n + d") == "a / b + d" and C.key("x ? /class=\"on\"/.test(b) : c") == 'x ? /class="on"/.test(b) : c',
      "a division is no regex, a regex holding a quote is read whole")
REL = "static/js/office_docs.js"
src = open(os.path.join(ROOT, REL), encoding="utf-8").read()
VMARK = re.compile(r"\b2\.\d+(?:\.\d+)?(?: [A-Z]\d*)? \((#\d+[^)]*)\)")
plain = re.sub(r"/\*.*?\*/", lambda m: VMARK.sub(r"(\1)", m.group(0)), src, flags=re.S)
check(plain != src, "office_docs.js holds version marks in comments (else this part proves nothing)")
base = C.json.load(open(C.BASE, encoding="utf-8"))
cnt = collections.Counter(f"{REL}|{e}" for _l, e in C.scan(plain))
over = [k for k, n in cnt.items() if n > base.get(k, 0)]
check(not over, f"office_docs.js without its version marks: no new finding {over[:3]}")
sys.exit(done("p2754_c_innerhtml_lint"))
