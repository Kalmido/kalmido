#!/usr/bin/env python3
# kalmido-suite: fresh
"""2.1280.0 (#6423): one line of Markdown must not hold the server. The heading pattern of the public knowledge link, the Word
export and the Markdown / Notion import took cubic time on a heading line with a long run of blanks, the table line of the
public link, the Notion import's checkbox probe and two rules of the search snippet quadratic time -- one request held every
thread of the process. Invented names only.
 - every way in answers quickly with such a text: the public link of a page (no login), the page's Word export, the Markdown
   import's preview, the Notion import, the knowledge search's snippet
 - first with a size the old patterns needed many seconds for (the fallback proof: red without the fix), then -- only when
   those passed -- with the largest text a page takes
 - what the readers gave before they still give: "## Plan ##" is the heading "Plan", "# C#" keeps its hash, a table needs its
   line of dashes, a list stays a list, the import names its lists and sections after the headings
 - the snippet of a long page is cut around the hit first and cleaned then: plain text, "…" on both sides, the word marked;
   a word that stands only in a link's address gives no snippet from there (the next hit does)
 - 2.1300.0 (#6652): a list indented one step deeper on every line is imported quickly; levels below 5 move up
 - freelancer-matrix: wiki, tasks (a person without an organisation: her private pages, her link, her export, her import)
usage: p21280_a_md_freeze_test.py <datadir>"""
import io
import re
import time
import zipfile

import requests

from freelancer_fixture import freelancer
from kt import B, check, done, fresh, setup

LIMIT = 6  # seconds one request may take (the old patterns: 15 s and far more for the small sizes below)
fresh(prefix="P21280A")
A = setup()
A.patch(B + "/api/settings", json={"lang": "en", "tour": "done"})
FID, F = freelancer(B, A)
SLOW = []


def timed(what, fn):
    """fn() with the time limit -> its response | None (too slow: a failed check, the large sizes are skipped then)."""
    t = time.monotonic()
    try:
        r = fn()
    except requests.exceptions.Timeout:
        r = None
    secs = time.monotonic() - t
    ok = r is not None and secs < LIMIT
    check(ok, f"{what}: answered within {LIMIT} s ({secs:.1f} s)")
    if not ok:
        SLOW.append(what)
    return r if ok else None


def page(path, text):
    r = F.post(B + "/api/wiki/pages", json={"space": "private", "path": path, "body": text})
    assert r.status_code == 201, (path, r.status_code, r.text[:200])
    return r.json()["id"]


def link(pid):
    r = F.post(B + "/api/wiki/shares", json={"page_id": pid, "kind": "link"})
    assert r.status_code == 201, (r.status_code, r.text[:200])
    return "/s/w/" + r.json()["url"].rsplit("/", 1)[-1]


def anon(path):
    return requests.get(B + path, allow_redirects=False, timeout=LIMIT)


def docx(pid):
    r = F.get(B + f"/api/wiki/pages/{pid}/export", params={"format": "docx"}, timeout=LIMIT)
    return r


def doc_text(r):
    return zipfile.ZipFile(io.BytesIO(r.content)).read("word/document.xml").decode()


def imp(src, name, data):
    return F.post(B + f"/api/import/{src}", files={"file": (name, data)}, data={"dry_run": "1"}, timeout=LIMIT)


def search(q):
    r = F.get(B + "/api/search?kind=wiki", params={"q": q}, timeout=LIMIT)
    return r


def hit(r, pid):
    return next((p for p in (r.json().get("pages", []) if r is not None and r.ok else []) if p["id"] == pid), None)


def nzip(text, more=""):
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("Export/Seite 0123456789abcdef0123456789abcdef.md", text)
        if more:
            z.writestr("Export/Zweite 1123456789abcdef0123456789abcdef.md", more)
    return b.getvalue()


def attack(tag, blanks, long_line, run, lines):
    """Every way in with one size: blanks = the run of blanks in a heading line (cubic before), long_line = a line of blanks
    below a table row (quadratic), run = a run of underscores / blanks in a searched text, lines = empty lines of a Notion page."""
    head = "# x" + " " * blanks + "y"  # the blanks between two words: the old pattern tried every split of them
    pid = page(f"Frost/{tag}/Kopf", "Anfang\n\n" + head + "\n\nEnde kopfwort\n")
    url = link(pid)
    r = timed(f"{tag}: the public link of a page with a heading line of {blanks} blanks", lambda: anon(url))
    check(r is not None and r.status_code == 200 and "kopfwort" in r.text, f"{tag}: the public page shows its text")
    r = timed(f"{tag}: the Word export of that page", lambda: docx(pid))
    check(r is not None and r.status_code == 200 and "kopfwort" in doc_text(r), f"{tag}: the Word file holds its text")
    r = timed(f"{tag}: the Markdown import's preview of such a heading", lambda: imp("markdown", "frost.md", (head + "\n- [ ] Aufgabe eins\n").encode()))
    check(r is not None and r.status_code == 200, f"{tag}: the preview comes ({r is not None and r.status_code})")
    # review: a run of half pictures / links (the Word export's inline pattern started 2000 characters again at every "[")
    pi = page(f"Frost/{tag}/Bilder", "\n\n".join("![![a](" * 2857 for _ in range(8 if tag == "klein" else 24)) + "\n\nEnde bildwort\n")
    r = timed(f"{tag}: the Word export of a page of half pictures", lambda: docx(pi))
    check(r is not None and r.status_code == 200 and "bildwort" in doc_text(r), f"{tag}: the Word file holds its text")
    pt = page(f"Frost/{tag}/Tabelle", "| a | b |\n" + " " * long_line + "x\n\nEnde tabwort\n")
    ut = link(pt)
    r = timed(f"{tag}: the public link of a table row above a line of {long_line} blanks", lambda: anon(ut))
    check(r is not None and r.status_code == 200 and "tabwort" in r.text and "<table" not in r.text, f"{tag}: no table without its line of dashes")
    r = timed(f"{tag}: the Notion import of a page with {lines} empty lines", lambda: imp("notion", "notion.zip", nzip("# Seite\n" + "\n" * lines + "kein Kasten\n", "# Zweite\n\n- [ ] Kasten drei\n")))
    check(r is not None and r.status_code == 200 and "Kasten drei" in r.text, f"{tag}: the Notion import reads the other page's task ({r is not None and r.status_code})")
    pu = page(f"Frost/{tag}/Striche", "strichwort" + tag + " a" + "_" * run + "b danach\n")
    r = timed(f"{tag}: the search's snippet of a text with {run} underscores in a row", lambda: search("strichwort" + tag))
    p = hit(r, pu)
    check(bool(p and "strichwort" in (p.get("snippet") or "")), f"{tag}: the hit has its snippet " + str(p)[:160])
    pb = page(f"Frost/{tag}/Leer", "leerwort" + tag + " a" + " " * run + "b danach\n")
    r = timed(f"{tag}: the search's snippet of a text with {run} blanks in a row", lambda: search("leerwort" + tag))
    p = hit(r, pb)
    check(bool(p and "leerwort" in (p.get("snippet") or "")), f"{tag}: the hit has its snippet " + str(p)[:160])


# ================================================================ what the readers gave before
MD = ("Einleitung mit **fett**.\n\n## Plan ##\n\n# C#\n\n#kein Titel\n\n- eins\n- [x] zwei\n\n1. erstens\n\n"
      "| Name | Wert |\n|---|:--:|\n| a | b |\n\n| keine | Tabelle |\n| - | x |\n\n> Zitat\n\n---\n\nSchluss\n")
P0 = page("Lesen/Alles", MD)
U0 = link(P0)
t = anon(U0).text
check("<h3>Plan</h3>" in t, "the public page: '## Plan ##' is the heading Plan")
check(re.search(r"<h2>C#</h2>", t) is not None, "the public page: '# C#' keeps its hash")
check("<p>#kein Titel</p>" in t, "the public page: a hash without a blank is text")
check(t.count("<table") == 1 and "<th>Name</th>" in t and "<td>b</td>" in t, "the public page: one table (the rows without a line of dashes are text)")
check("<ul>" in t and "<ol>" in t and 'type="checkbox" disabled checked' in t and "<blockquote>" in t and "<hr>" in t,
      "the public page: list, numbered list, check box, quote and rule as before")
d = doc_text(docx(P0))
check("Plan" in d and "Plan ##" not in d and "C#" in d and "Heading2" in d and "Heading1" in d, "the Word file: the headings as before")
r = imp("markdown", "plan.md", "# Liste Eins ##\n## Abschnitt A\n- [ ] Erste\n- [x] Zweite\n# Liste Zwei\n- [ ] Dritte\n".encode())
j = r.json() if r.ok else {}
names = re.findall(r"Liste (?:Eins|Zwei)", r.text)
check(r.ok and "Liste Eins" in names and "Liste Zwei" in names and "Liste Eins #" not in r.text and "Abschnitt A" in r.text,
      f"the Markdown import: lists and sections named after the headings {r.status_code} {str(j)[:200]}")
r = imp("notion", "n.zip", nzip("# Seite\n\n- [ ] Kasten eins\n- [x] Kasten zwei\n"))
check(r.ok and "Kasten eins" in r.text, f"the Notion import: a page with check boxes becomes tasks {r.status_code} {r.text[:160]}")

# ================================================================ the snippet of a long page: cut around the hit, then cleaned
FILL = " ".join(f"wort{i % 150:03d}" for i in range(3500))  # about 28,000 characters in one line, few distinct words (the index keeps 4000)
# review: an empty table cell leaves no pipe
PT = page("Lesen/Zellen", "| zellwort |  | zwei |\n|---|---|---|\n| a |  | b |\n")
sn = (hit(search("zellwort"), PT) or {}).get("snippet") or ""
check(sn == "zellwort zwei --- --- --- a b", "a table with empty cells: the snippet has no pipe " + repr(sn))
r = imp("markdown", "notiz.md", "# Liste\n- [ ] Aufgabe\n  # Schritt eins\n  mehr Text\n- [ ] Zweite\n".encode())
j = r.json() if r.ok else {}
check(r.ok and j.get("created", {}).get("sections") == 0 and j.get("created", {}).get("tasks") == 2,
      f"the Markdown import: an indented '# ...' below a task is its note, no section {r.status_code} {r.text[:300]}")
LONG = ("---\ntags: [frontwort]\n---\n# Lang\n\n" + FILL + "\n\n[Verweis](https://example.com/linkwort) davor\n\n" + FILL.replace("wort", "satz")
        + "\n\n## Ziel\n\n- Hier steht das **Zielwort** in einer [[Ordner/Seite|Liste]] und linkwort als Text.\n\n" + FILL.replace("wort", "rest"))
PL = page("Lesen/Lang", LONG)
p = hit(search("zielwort"), PL)
sn = (p or {}).get("snippet") or ""
check("Zielwort" in sn and sn.startswith("…") and sn.endswith("…"), "a long page: the snippet around the hit, cut on both sides " + sn[:200])
check(not re.search(r"[*\[\]#|]", sn) and "Liste" in sn, "a long page: the snippet is plain text (marks gone, the link's label stays) " + sn[:200])
check([sn[a:b] for a, b in (p or {}).get("marks", [])] == ["Zielwort"], "a long page: the word is marked " + str((p or {}).get("marks")))
check(len(sn) <= 200, f"a long page: about two lines ({len(sn)})")
p = hit(search("linkwort"), PL)
sn = (p or {}).get("snippet") or ""
check("linkwort als Text" in sn and "example.com" not in sn, "a word in a link's address gives no snippet there, its next place does " + sn[:200])
p = hit(search("frontwort"), PL)
check(not (p or {}).get("snippet"), "a word of the frontmatter only: no snippet " + str(p)[:160])
p = hit(search("wort001"), PL)
sn = (p or {}).get("snippet") or ""
check(sn.startswith("Lang wort000 wort001") and sn.endswith("…"), "a hit at the beginning of a long page: from the start on " + sn[:80])

# ================================================================ the sizes the old patterns needed many seconds for
attack("klein", 3000, 60000, 150000, 40000)
# ================================================================ the largest texts (only when the small ones were quick)
if SLOW:
    check(False, "the largest sizes were skipped: " + "; ".join(SLOW))
else:
    attack("gross", 450000, 450000, 190000, 400000)
    # many such lines in one page: the time grows with the text, not faster
    many = "\n".join("# x" + " " * 9000 + "y" for _ in range(50)) + "\nEnde vielwort\n"
    pm = page("Frost/Viele", many)
    um = link(pm)
    r = timed("the public link of a page with 50 heading lines of 9000 blanks", lambda: anon(um))
    check(r is not None and r.status_code == 200 and "vielwort" in r.text and r.text.count("<h2>x ") == 50, "they are 50 headings")
    r = timed("the Word export of that page", lambda: docx(pm))
    check(r is not None and r.status_code == 200, "the Word file comes")

# ================================================================ 2.1300.0 (#6652): a list indented one step deeper on every line
# the import built the whole chain of parent titles again for every task (2000 lines: 5 s and 1 GB, 4000: 23 s and 4 GB)
DEEP = 2300  # about 3.8 MB: below the request limit of the test server
deep = "".join(" " * i + f"- [ ] Tief {i} " + "x" * 480 + "\n" for i in range(DEEP))
# the same lines without nesting first: what the preview of so many tasks takes anyway
t0 = time.monotonic()
r = timed(f"the Markdown import's preview of {DEEP} lines side by side", lambda: imp("markdown", "flach.md", "".join(x.lstrip() + "\n" for x in deep.splitlines()).encode()))
t_flat = time.monotonic() - t0
t0 = time.monotonic()
r = timed(f"the Markdown import's preview of {DEEP} lines, each one step deeper", lambda: imp("markdown", "tief.md", deep.encode()))
t_deep = time.monotonic() - t0
# the time grows with the lines, not with lines x depth (before: the deep list took many times the flat one, on any machine)
print(f"deep {t_deep:.2f} s, flat {t_flat:.2f} s")
check(t_deep < 2 * t_flat + 0.5, f"the deep list takes about as long as the flat one ({t_deep:.2f} s, flat {t_flat:.2f} s)")
j = r.json() if r is not None and r.ok else {}
w = next((x for x in j.get("warnings", []) if "Nested deeper than 5" in (x.get("text") or "")), {})
check(j.get("created", {}).get("tasks") == DEEP and w.get("count") == DEEP - 5,
      f"the deep list: every line a task, the ones below level 5 moved up with one warning {r is not None and r.status_code} {str(j.get('created'))[:160]} {w.get('count')} {(r.text[:200] if r is not None and not r.ok else '')}")
# what the levels give: five kept, deeper lines hang below level 4 (on level 5), a shallower line after them finds its parent
nest = "".join("  " * i + f"- [ ] Nest {i + 1}\n" for i in range(7)) + "  - [ ] Nest Zwei\n"
r = F.post(B + "/api/import/markdown", files={"file": ("Nest.md", nest.encode())}, data={}, timeout=LIMIT)
check(r.ok, f"the nested list is imported {r.status_code} {r.text[:160]}")
st = {t["title"]: t for t in F.get(B + "/api/state").json()["tasks"] if t["title"].startswith("Nest ")}
pid = lambda k: (st.get(k) or {}).get("parent_id")
check(len(st) == 8 and pid("Nest 1") is None and all(pid(f"Nest {i}") == st[f"Nest {i - 1}"]["id"] for i in range(2, 6)),
      "the nested list: five levels kept " + str({k: pid(k) for k in st}))
check(pid("Nest 6") == st["Nest 4"]["id"] and pid("Nest 7") == st["Nest 4"]["id"] and pid("Nest Zwei") == st["Nest 1"]["id"],
      "the nested list: levels 6 and 7 hang below level 4, the line back on level 2 below level 1 " + str({k: pid(k) for k in st}))

# the server still answers everybody
check(requests.get(B + "/api/health", timeout=LIMIT).ok and A.get(B + "/api/state", timeout=LIMIT).ok, "the server answers afterwards")
raise SystemExit(done("p21280_a_md_freeze"))
