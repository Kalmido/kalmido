#!/usr/bin/env python3
# kalmido-suite: fresh
"""2.1269.0 A (#6421): a crafted mail cannot hold the server while it is shown.
 - the HTML cleaner (hub/mailview.py mh_clean) ends fast on hostile CSS at the full shown size (500.000 characters): long runs
   without ; { } in style attributes and blocks, a long data: picture in the CSS, many short declarations, many url('...) without
   their end, many open @font-face {, deeply nested dropped elements; a style attribute / block over 20.000 characters goes
   whole, one just below stays (with its data: picture)
 - the cleaner still takes out what it took out before (expression(, javascript:, vbscript:, behavior:, -moz-binding, image-set(,
   an url( without its end, backslash escapes, @import / @namespace / @charset / @font-face, external pictures), also across
   declaration borders and when /* comments */ split the word
 - the forwarding shortener (integrations/mailtrim.py, also mailtrim_html) ends fast on long hostile lines: "From: a" + 190.000
   spaces, a sender line of many "[mailto:" / one long word, many "From:" lines, a "regards" / marker / quote line with a long
   run of spaces; normal forwarded mails are shortened as before
Each case runs in its own process in the test container, killed after LIMIT seconds (the code before ran for minutes to hours).
usage: p21269_a_mailredos_test.py <datadir>"""
import json
import os
import subprocess
import sys

N = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, N)
from kt import CT, check, done  # noqa: E402

LIMIT = 120   # kill a case after this (the quadratic code needs hours for these inputs)
FAST = 20     # a case must end within this (the linear code needs well under 3 s, also on a slow CI machine)

PRE = r"""
import json, time, app
from kalmido.hub import mailview as MV
from kalmido.integrations import mailtrim as MT
from kalmido.integrations import mailtrim_html as MTH
def clean(h, cids=None, images=False):
    t = time.monotonic(); doc, ext = MV.mh_clean(h, cids or {}, images); return doc, round(time.monotonic() - t, 2)
def body(doc):
    return doc.split("</head>", 1)[1]
def sheet(doc):
    return doc.split("</style>", 1)[1].split("</head>", 1)[0]
"""


def py(code, limit=LIMIT):
    """code (after PRE) in the container, killed there after limit seconds -> the last JSON line it printed, or {}."""
    try:
        r = subprocess.run(["docker", "exec", "-i", "-w", "/app", "-e", "TASKS_WATCHDOG=0", CT, "timeout", str(limit), "python", "-c",
                            PRE + code], capture_output=True, text=True, timeout=limit + 60)
    except subprocess.TimeoutExpired:
        return {}
    if r.returncode:
        print("PY FAILED:", r.returncode, r.stdout[-2000:], r.stderr[-3000:], flush=True)
    for ln in reversed((r.stdout or "").splitlines()):
        if ln.startswith("{"):
            return json.loads(ln)
    return {}


def fast(name, code):
    j = py(code)
    dt = j.get("dt", 999)
    check(j and dt < FAST, f"{name}: ends fast ({dt} s < {FAST} s)")
    return j


# ================================================================ 1. the HTML cleaner at the full shown size
j = fast("long runs in 25 style attributes of 19.900 characters (500 kB)", r"""
h = "".join('<p style="' + "a" * 19900 + '">x</p>' for _ in range(25))
doc, dt = clean(h)
print(json.dumps({"dt": dt, "kept": body(doc).count("a" * 19900)}))
""")
check(j.get("kept") == 25, f"a style attribute just below 20.000 characters stays {j.get('kept')}")

j = fast("one style block of 499.000 characters without ; { }", r"""
doc, dt = clean("<style>" + "a" * 499000 + "</style><p>Hallo</p>")
print(json.dumps({"dt": dt, "sheet": len(sheet(doc)), "text": "<p>Hallo</p>" in doc}))
""")
check(j.get("sheet") == 0 and j.get("text"), f"a style block over 20.000 characters goes whole, the text stays {j}")

j = fast("long data: picture in the CSS (block and attribute)", r"""
img = "data:image/png;base64," + "A" * 19000
doc, dt = clean("<style>p{background:url(" + img + ");color:red}</style><p style='background:url(" + img + ")'>x</p>")
big = "<style>p{background:url(data:image/png;base64," + "A" * 499000 + ")}</style><p>x</p>"
doc2, dt2 = clean(big)
print(json.dumps({"dt": dt + dt2, "block": "url('" + img + "')" in sheet(doc), "attr": body(doc).count("url(&#x27;" + img), "red": "color:red" in doc,
                  "big": len(sheet(doc2))}))
""")
check(j.get("block") and j.get("attr") == 1 and j.get("red"), f"a data: picture just below the limit stays in block and attribute {j}")
check(j.get("big") == 0, f"a data: picture over the limit takes its block with it {j.get('big')}")

j = fast("many short declarations (25 blocks of 4.900)", r"""
h = "".join("<style>p{" + "a:b;" * 4900 + "}</style>" for _ in range(25)) + "<p>x</p>"
doc, dt = clean(h)
print(json.dumps({"dt": dt, "n": sheet(doc).count("a:b;")}))
""")
check(j.get("n") == 25 * 4900, f"short declarations stay {j.get('n')}")

j = fast("many url('... without their end (25 attributes)", r"""
h = "".join('<p style="' + "x:url('a) " * 1990 + '">x</p>' for _ in range(25))
doc, dt = clean(h)
print(json.dumps({"dt": dt}))
""")

j = fast("many open @font-face { and url( (25 blocks / attributes of 19.800 characters)", r"""
doc, dt = clean("".join("<style>" + "@font-face{" * 1800 + "</style>" for _ in range(25)))
doc2, dt2 = clean("".join("<style>" + "url(" * 4950 + "</style>" for _ in range(25)))
doc3, dt3 = clean("".join('<p style="' + "url(" * 4950 + '">x</p>' for _ in range(25)))
print(json.dumps({"dt": dt + dt2 + dt3}))
""")

j = fast("deeply nested dropped elements (500 kB)", r"""
doc, dt = clean("<object>" + "<b>" * 70000 + "</i>" * 50000 + "</object><p>after</p>")
print(json.dumps({"dt": dt, "after": "<p>after</p>" in doc}))
""")

j = fast("the shortened view (mh_short) of 500 kB hostile HTML", r"""
t = time.monotonic()
a = MV.mh_short("<div>forwarded message" + " " * 499000 + "x</div>")
b = MV.mh_short("<div>" + "From: a<br>" * 40000 + "</div>")
c = MV.mh_short("<style>" + "<" * 499000)
print(json.dumps({"dt": round(time.monotonic() - t, 2)}))
""")

# ---- hostile markup for the parser itself (HTMLParser has had quadratic spots of its own, depending on the version)
j = py(r"""
import sys
n = 499000
cases = {
 "comments": "<!--" * (n // 4), "cdata": "<![CDATA[" * (n // 9), "decl": "<!x" * (n // 3), "pi": "<?" * (n // 2),
 "open_attr_quote": "<a b='" * (n // 6), "open_attr_dquote": '<a b="c' + " d=e" * (n // 4), "open_tags": "<a " * (n // 3),
 "end_series": "</" * (n // 2), "end_names": "</a" * (n // 3), "amp": "&amp" * (n // 4), "amp_num": "&#" * (n // 2),
 "amp_hex": "&#x" * (n // 3), "deep_div": "<div>" * (n // 5), "deep_table": "<table><tr><td>" * (n // 15),
 "short_styles": '<b style="a:b">' * (n // 15), "fontface_no_brace": "".join("<style>" + "@font-face " * 1800 + "</style>" for _ in range(25)),
 "lt_letters": "<b" * (n // 2), "lt_only": "<" * n,
}
out = {"py": sys.version.split()[0]}
for k, h in cases.items():
    doc, dt = clean(h)
    out[k] = dt
print(json.dumps(out))
""", limit=600)
print("container python", j.get("py"), flush=True)
check(len(j) == 19, f"all parser cases ran {len(j)}")
for k, v in j.items():
    if k != "py":
        check(v < FAST, f"parser case {k} (500 kB) ends fast ({v} s < {FAST} s)")

# ================================================================ 2. the cleaner takes out what it took out before
j = py(r"""
cases = {
 "expression": '<p style="width:expression(alert(1));color:red">x</p>',
 "expression_comment": '<p style="width:expr/**/ession(alert(1));color:red">x</p>',
 "expression_escape": '<p style="width:\\65xpression(alert(1));color:red">x</p>',
 "javascript": '<p style="background:url(javascript:alert(1));color:red">x</p>',
 "javascript_comment": '<p style="x:java/* a */script:alert(1);color:red">x</p>',
 "vbscript": '<p style="x:vbscript:msgbox(1);color:red">x</p>',
 "behavior": '<p style="behavior:url(x.htc);color:red">x</p>',
 "behavior_comment": '<p style="beha/**/vior:url(x.htc);color:red">x</p>',
 "binding": '<p style="-moz-binding:url(https://evil.example.com/x.xml#x);color:red">x</p>',
 "binding_comment": '<p style="-moz-/**/binding:url(https://evil.example.com/x.xml#x);color:red">x</p>',
 "imageset": '<p style="background:image-set(\'https://evil.example.com/a.png\' 1x);color:red">x</p>',
 "url_open_border": '<p style="color:red;a:url(https://evil.example.com/a.png;b:\\x)">x</p>',
 "url_comment": '<p style="color:red;background:url/**/(https://evil.example.com/a.png)">x</p>',
 "url_external": '<p style="color:red;background:url(  \'https://evil.example.com/a.png\'  )">x</p>',
 "url_quoted_semicolon": '<p style="color:red;background:url(\'https://evil.example.com/a.png;x\')">x</p>',
 "import": '<style>@import url(https://evil.example.com/x.css);p{color:red}</style><p>x</p>',
 "import_comment": '<style>@im/**/port url(https://evil.example.com/x.css);p{color:red}</style><p>x</p>',
 "namespace": '<style>@namespace x url(https://evil.example.com/);p{color:red}</style><p>x</p>',
 "charset": '<style>@charset "evil";p{color:red}</style><p>x</p>',
 "fontface": '<style>@font-face{font-family:e;src:url(https://evil.example.com/f.woff)}p{color:red}</style><p>x</p>',
 "fontface_open": '<style>p{color:red}@font-face{font-family:e;src:url(https://evil.example.com/f.woff)</style><p>x</p>',
 "block_pieces": '<style>p{color:red}</b>q{x:1;width:expression(1)}</i>r{y:2}</style><p>x</p>',
 "block_border": '<style>p{color:red}q{x:1;y:expression(1)}r{background:url(https://evil.example.com/a.png)}</style><p>x</p>',
 "comment_open": '<style>p{color:red}/* q{width:expression(1)}</style><p>x</p>',
}
out = {}
for k, h in cases.items():
    doc, dt = clean(h)
    out[k] = doc.split("</style>", 1)[1].lower()
print(json.dumps(out))
""")
BAD = ("expression", "ession(", "javascript", "script:", "vbscript", "behavior", "vior:", "binding", "image-set", "\\", "@import", "port url",
       "@namespace", "@charset", "@font-face", "evil.example.com", "alert")
check(len(j) == 24, f"all bypass cases ran {len(j)}")
for k, v in j.items():
    hit = [b for b in BAD if b in v]
    check(not hit, f"bypass {k}: nothing dangerous left {hit} {v[:300]}")
    check("color:red" in v, f"bypass {k}: the harmless declaration stays {v[:300]}")
j = py(r"""
doc, dt = clean('<p style="background:url(cid:pic1) no-repeat;color:blue">x</p>', {"pic1": "data:image/png;base64,QUJD"})
doc2, dt2 = clean('<p style="background:url(https://img.example.com/a.png)">x</p>', {}, True)
print(json.dumps({"cid": body(doc), "img": body(doc2)}))
""")
check("url(&#x27;data:image/png;base64,QUJD&#x27;) no-repeat;color:blue" in j.get("cid", ""), f"cid: pictures in CSS still work {j.get('cid')}")
check("url(&#x27;https://img.example.com/a.png&#x27;)" in j.get("img", ""), f"Load images still loads CSS pictures {j.get('img')}")

# ================================================================ 3. the forwarding shortener (text) at hostile lines
j = fast("'From: a' + 190.000 spaces (forward, view, sender)", r"""
t = time.monotonic()
for v in ("From: a" + " " * 190000, "From: a" + " " * 190000 + "b", "From: a" + " " * 190000 + "<b@example.com>"):
    x = "Hallo\n\n" + v + "\nDate: Mon, 5 Oct 2026\nSubject: Test\n\nText"
    MT.md_trim_forward(x); MT.md_trim_view(x + "\n"); MT.md_forward_from(x)
    MTH.md_trim_html("<div>---------- Forwarded message ---------<br>" + v + "<br>Date: Mon<br>Subject: x<br></div><p>Text</p>")
print(json.dumps({"dt": round(time.monotonic() - t, 2)}))
""")
j = fast("many '[mailto:' / one long word as sender", r"""
t = time.monotonic()
for v in ("[mailto:" * 24000, "a" * 190000, "<" * 190000 + ">"):
    x = "Hi\n\nFrom: " + v + "\nDate: x\nSubject: y\n\nT"
    MT.md_trim_forward(x); MT.md_forward_from(x); MT.md_trim_view(x + " ")
print(json.dumps({"dt": round(time.monotonic() - t, 2)}))
""")
j = fast("25.000 'From:' lines", r"""
t = time.monotonic()
x = "Text\n" + "From: a\n" * 25000
MT.md_trim_forward(x); MT.md_trim_view(x); MT.md_forward_from(x)
print(json.dumps({"dt": round(time.monotonic() - t, 2)}))
""")
j = fast("signature / marker / quote lines with 190.000 spaces", r"""
t = time.monotonic()
for x in ("Hallo\nregards" + " " * 190000 + "x\n", "Hallo\nforwarded message" + " " * 190000 + "x\n",
          "Hallo\nOn a b c\n" + " " * 190000 + "x\n", "Hallo\n" + ("am " + "schrieb" * 40 + " " * 700 + "x\n") * 190,
          "Hallo\n" + ("On " + "x" * 300 + " wrote" + " " * 600 + "y\n") * 190):
    MT.md_trim_forward(x); MT.md_trim_view(x + "."); MT.md_forward_from(x)
print(json.dumps({"dt": round(time.monotonic() - t, 2)}))
""")
j = py(r"""
x = ("Bitte erledigen.\n\n---------- Forwarded message ---------\nFrom: Jane Doe <jane@example.com>\nDate: Mon, 5 Oct 2026\n"
     "Subject: Termin\nTo: <me@example.com>\n\nHallo,\nFreitag 10 Uhr.\n\nBest regards  ,\nJane\n\nOn Fri, Oct 2, 2026 Bob <bob@example.com> wrote:\n> alt\n")
y = "Text\n\nFrom: \"Max Muster\" [mailto:max@example.com]\nSent: Mon\nTo: a\nSubject: b\n\nInhalt"
print(json.dumps({"fwd": MT.md_trim_forward(x), "from": MT.md_forward_from(x), "y": MT.md_trim_forward(y), "yf": MT.md_forward_from(y),
                  "s": [MT._sender(v) for v in ("Jane <j@x.de>", "<j@x.de>", '"A <b" <c@d.de>', "a <b> <c@d.de>", "plain", "x > y <z@w.de>")]}))
""")
check(j.get("fwd") == "Bitte erledigen.\n\nFrom Jane Doe, Mon, 5 Oct 2026\n\nHallo,\nFreitag 10 Uhr.", f"a normal forward is shortened as before {j.get('fwd')!r}")
check(j.get("from") == ["Jane Doe", "jane@example.com"], f"the original sender is read as before {j.get('from')}")
check(j.get("y") == "Text\n\nFrom Max Muster, Mon\n\nInhalt" and j.get("yf") == ["Max Muster", "max@example.com"], f"Outlook [mailto:] as before {j.get('y')!r} {j.get('yf')}")
x2 = j
j = py(r"""
x = ("Bitte.\n\n-----Original Message-----\nFrom: Jane Doe <jane@example.com>\nSent: Mon, 5 Oct 2026\nTo: a@example.com\nTo: b@example.com\n"
     "Cc: c@example.com\nCc: d@example.com\nSubject: Termin\n\nHallo,\nFreitag.\n")
big = "Text\n" * 12000
r1 = MT.md_trim_view("Hallo\n\n-- \nJane\n")
for i in range(100):
    MT.md_trim_view("Text %d\n-- \nsig" % i)
n_after = len(MT._VIEW_CACHE)
MT.md_trim_view(big)
print(json.dumps({"x": MT.md_trim_forward(x), "xf": MT.md_forward_from(x), "r1": r1, "again": MT.md_trim_view("Hallo\n\n-- \nJane\n"),
                  "n": n_after, "max": MT.VIEW_CACHE_N, "big_in": big in MT._VIEW_CACHE, "cap": MT.VIEW_CACHE_TEXT}))
""")
check(j.get("x") == "Bitte.\n\nFrom Jane Doe, Mon, 5 Oct 2026\n\nHallo,\nFreitag.", f"a header with two To: / Cc: lines is shortened as before {j.get('x')!r}")
check(j.get("xf") == ["Jane Doe", "jane@example.com"], f"... and its sender read {j.get('xf')}")
check(j.get("r1") == "Hallo" == j.get("again"), f"md_trim_view gives the same result from its memory {j.get('r1')!r} {j.get('again')!r}")
check(j.get("n") == j.get("max") == 32 and j.get("big_in") is False and j.get("cap") == 50000,
      f"md_trim_view remembers at most 32 texts of at most 50.000 characters {j}")
j = py(r"""
to = "To: a0@example.com,\n" + "".join(" a%d@example.com,\n" % i for i in range(1, 61)) + " last@example.com\n"
x = "Bitte.\n\nFrom: Jane Doe <jane@example.com>\n" + to + "Sent: Mon, 5 Oct 2026\nSubject: Termin\n\nHallo,\nFreitag.\n"
bad = "Hallo\n\n" + "From: a\n x\n x\n" * 60000
t = time.monotonic()
MT.md_trim_forward(bad); MT.md_forward_from(bad); MT.md_trim_view(bad)
print(json.dumps({"x": MT.md_trim_forward(x), "xf": MT.md_forward_from(x), "dt": round(time.monotonic() - t, 2)}))
""")
check(j.get("x") == "Bitte.\n\nFrom Jane Doe, Mon, 5 Oct 2026\n\nHallo,\nFreitag." and j.get("xf") == ["Jane Doe", "jane@example.com"],
      f"a header whose To: is folded over 60 lines keeps its date and sender (continuation lines do not count as header lines) {j.get('x')!r} {j.get('xf')}")
check(j.get("dt") is not None and j["dt"] < FAST, f"From: lines with continuation lines, 180.000 lines: under {FAST} s {j.get('dt')}")
j = x2
check(j.get("s") == ["Jane", "j@x.de", "A", "a <b>", "plain", "x > y"], f"_sender reads 'Name <address>' as the regex did {j.get('s')}")

sys.exit(done("p21269_a_mailredos"))
