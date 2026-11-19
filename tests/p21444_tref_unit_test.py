#!/usr/bin/env python3
# kalmido-suite: after=p248_b_unit nodata
"""(#6584): the rewriter of task references of an account / organisation import (kalmido/admin/acctimport.py umz_task_refs),
pure Python, no server: taken from the source by name, so the module's imports are not needed.
 - a number of a task that came along gets its new number, any other one is no link any more, code / links / "job #12" stay
 - the keep patterns are linear: 300,000 characters of unclosed "[", "<" or "<a" take well under a second (reader F1 / F4 of
   job/5756: quadratic, then bounded but 500 steps per character)
usage: python3 tests/p21444_tref_unit_test.py   (KALMIDO_SRC=<dir with kalmido/> to test another tree)"""
import ast
import os
import re
import sys
import time

N = os.path.dirname(os.path.abspath(__file__))
SRC = os.environ.get("KALMIDO_SRC") or os.path.join(N, "..")
sys.path.insert(0, N)
from kt import FAILS, OKS, check  # noqa: E402

PATH = os.path.join(SRC, "kalmido", "admin", "acctimport.py")
TREE = ast.parse(open(PATH, encoding="utf-8").read())
WANT = {"UMZ_TREF_RE", "UMZ_TREF_KEEP", "UMZ_TREF_OFF", "umz_task_refs"}
NODES = [n for n in TREE.body if (isinstance(n, ast.Assign) and {getattr(t, "id", None) for t in n.targets} & WANT)
         or (isinstance(n, ast.FunctionDef) and n.name in WANT)]
NS = {"re": re, "WIKI_TASK_RE": re.compile(r"\[\[#(\d{1,9})(\|[^\]\n]*)?\]\]")}
exec(compile(ast.Module(body=NODES, type_ignores=[]), PATH, "exec"), NS)
refs, OFF = NS["umz_task_refs"], NS["UMZ_TREF_OFF"]
check(len(NODES) == 4, "the rewriter and its patterns are in acctimport.py")

came = {"12": 5012, "7": 5007}.get
check(refs("see #12 and #7", came) == "see #5012 and #5007", "#6584: a task that came along gets its new number")
check(refs("see #99", came) == "see #" + OFF + "99", "#6584: a task outside the file is no link any more")
check(refs("job #12, `#12`, [x](https://e.x/#12)", came) == "job #12, `#12`, [x](https://e.x/#12)",
      "job #12, code and links stay as they are")
check(refs("<a href='#12'>#12</a> #12", came) == "<a href='#12'>#12</a> #5012", "an HTML link stays, the text after it is rewritten")
check(refs("[a #12](x) <b title='#7'>", came) == "[a #12](x) <b title='#7'>", "a link text and a tag stay")

for name, text in (("[", "[" * 300000 + " #12"), ("<", "<" * 300000 + " #12"), ("<a", "<a " * 100000 + " #12"),
                   ("[x](", "[x](" * 75000 + " #12"), ("[ + 400 letters", ("[" + "a" * 400) * 750 + " #12"),
                   ("<a> + 400 letters", ("<a>" + "a" * 400) * 750 + " #12"), ("`", "x`" * 150000 + "\n #12")):
    t0 = time.monotonic()
    out = refs(text, came)
    dt = time.monotonic() - t0
    check(dt < 1.0 and out.endswith("#5012"), f"F4: 300,000 characters of unclosed {name!r} in one text: {dt:.2f} s (one pass)")

print(f"{OKS[0]} ok, {len(FAILS)} failed")
sys.exit(1 if FAILS else 0)
