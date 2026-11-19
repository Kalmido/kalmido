#!/usr/bin/env python3
# kalmido-suite: fresh
"""2.1443 (#6433): imports and DAV queries no longer hold the server on long cells or many filters. Own container (start.sh).
Invented names only; every hostile input is made here and sized so that the old code needs several seconds (the measured
growth of the audit #4780), the fixed code a fraction of one - a red run costs seconds, not minutes.
freelancer-matrix: pim
 A. inside the app container, the app's own functions, each with its hostile input and a time limit (FAST):
    - task import: csv.field_size_limit is no longer raised for the whole process (the default holds outside an import,
      and comes back after one); a description of 300 000 characters is still read (the CSV of tasks with long texts)
    - dates longer than IMP_DATE_MAX are no date (imp_anydate with "(((...", imp_numdate, the Todoist date text, the
      Notion range, the ClickUp text); names are cut to IMP_NAME_MAX before the patterns (Todoist author / responsible,
      the file name of a list, the Notion page name); the Todoist attachment marks are linear ("[[file {" many times)
    - contacts CSV: more than CTX_COLS_MAX columns is refused with a clear message; the separators (:::) are linear on
      long blanks; the sibling columns of Google's export are found once per file (500 rows x 200 columns), and the
      type of the sibling column still reaches the e-mail
    - CardDAV addressbook-query / CalDAV calendar-query: more than DAV_FILTERS_MAX prop-filters or DAV_TEXTMATCH_MAX
      text-matches answer 403 supported-filter; the matches still hold (contains / equals / starts-with / ends-with,
      negate, is-not-defined, anyof / allof)
    - the bounded ones: a subscribed event's HTML description (comments, open tags), an agent's proposal text with long
      blanks, the first line of a chat message saved as a task ("[](" many times); their ordinary results stay
 B. over HTTP as a person without an organisation: a contacts CSV of 201 columns is refused with the message, 200 columns
    are read (preview)
usage: p21443_6433_import_regex_test.py <datadir>      (P21443_NOSTART=1 = the server already runs)"""
import json
import os
import subprocess
import sys

N = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, N)
import kt  # noqa: E402
from kt import B, CT, check  # noqa: E402
from freelancer_fixture import freelancer  # noqa: E402

FAST = 2.0  # seconds: the fixed code needs a fraction of this; the old one several seconds (the Mac must not flutter)

PROBE = r'''
import csv, json, time
from xml.etree import ElementTree as ET
from kalmido.core.config import app
from kalmido.core.errors import BadInput
from kalmido.integrations import importers as I
from kalmido.contacts import ctxlist as X, carddav as CD
from kalmido.calendars import caldav as CA, subscriptions as SU
from kalmido.agents import proposals as PR
from kalmido.collab import chatsave as CS

out = {}
def run(key, fn):
    t0 = time.monotonic()
    try:
        r = "ok:" + repr(fn())[:400]
    except BaseException as e:
        r = type(e).__name__ + ":" + str(getattr(e, "text", "") or e)[:300]
    out[key] = [r, round(time.monotonic() - t0, 3)]

with app.test_request_context("/", headers={"Accept-Language": "en"}):
    # ---- task import: the cell limit only while reading
    out["csv_limit_before"] = csv.field_size_limit()
    out["csv_cell_max"] = I.IMP_CSV_CELL_MAX
    long_desc = "x" * 300000
    run("csv_long_desc", lambda: len(I.imp_csv("title,description\nA," + long_desc + "\n")[1][0]["description"]))
    out["csv_limit_after"] = csv.field_size_limit()
    # ---- dates
    run("anydate_parens", lambda: I.imp_anydate("(" * 60000))
    run("anydate_ok", lambda: I.imp_anydate("Wednesday, January 15th 2025 (GMT+1)"))
    run("numdate_long", lambda: I.imp_numdate("15.01.2025" + " " * 200 + "x"))
    run("nl_date_long", lambda: I.imp_nl_date("every " + " " * 60000 + "x", "en"))
    run("nl_date_ok", lambda: (I.imp_nl_date("every monday", "en") or {}).get("repeat"))
    run("notion_long", lambda: I._notion_date("January 15, 2025" + " " * 60000 + "x"))
    run("notion_ok", lambda: I._notion_date("January 15, 2025 → January 17, 2025"))
    run("cu_long", lambda: I._cu_date("", "1/15/2025" + " " * 60000 + "x"))
    # ---- names
    sp = " " * 40000
    run("stem_long", lambda: I.imp_stem("a" + sp + "b.csv"))
    run("stem_ok", lambda: I.imp_stem("Haushalt [2203306141].csv"))
    run("notion_name_long", lambda: I._notion_name("Seite" + sp + "x.md"))
    run("notion_name_ok", lambda: I._notion_name("Projekte 0123456789abcdef0123456789abcdef.csv"))
    import io
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerows([["TYPE", "CONTENT", "DESCRIPTION", "PRIORITY", "INDENT", "AUTHOR", "RESPONSIBLE", "DATE", "DATE_LANG", "TIMEZONE"],
                 ["task", "Einkaufen", "", "4", "1", "Max (38121)", "Max" + sp + "x", "", "en", ""],
                 ["note", "Kommentar", "", "", "", "Max" + sp + "x", "", "", "", ""],
                 ["task", "Zweite", "", "4", "1", "Max (38121)", "Ida (42)", "", "en", ""],
                 ["note", 'Mit Anhang [[file {"file_name": "beleg.pdf", "file_url": "https://files.example.com/beleg.pdf"}]]', "", "", "",
                  "Ida (42)", "", "", "", ""]])
    td = buf.getvalue()
    def todoist():
        plan = I.imp_plan("todoist")
        I.parse_todoist(td.encode(), "Inbox.csv", {}, plan)
        ts = plan["lists"][0]["tasks"]
        return [(t["assignee"] or {}).get("name", "")[:20] for t in ts], [t["notes"][-120:] for t in ts]
    run("todoist_names", todoist)
    run("todoist_files", lambda: I._todoist_files("[[file {" * 8000))
    run("todoist_files_ok", lambda: I._todoist_files('Vorher [[file {"file_name": "a.pdf", "file_url": "https://files.example.com/a.pdf"}]]'))
    # ---- contacts CSV
    def cols(n):
        return ";".join(f"Feld {k}" for k in range(n)) + "\n" + ";".join("v" for _ in range(n)) + "\n"
    run("ctx_201", lambda: X.ctx_read(cols(201).encode())["headers"][-1])
    run("ctx_200", lambda: len(X.ctx_read(cols(200).encode())["headers"]))
    run("ctx_split_blank", lambda: len(X.ctx_split("a" + " " * 25000 + "b")))
    run("ctx_split_ok", lambda: (X.ctx_split(" x ::: y "), X.ctx_split("a, b; c ::: d", True)))
    head = ["Name"] + [f"E-mail {k} - {w}" for k in range(1, 100) for w in ("Type", "Value")]
    rows = [";".join([f"Person {i}"] + [x for k in range(1, 100) for x in ("* Work", f"p{i}.{k}@example.com")]) for i in range(500)]
    google = (";".join(head) + "\n" + "\n".join(rows) + "\n").encode()
    run("ctx_google", lambda: (lambda cs: (len(cs), [ln for ln in cs[0].split("\r\n") if ln.startswith("EMAIL")][:1]))(X.ctx_cards(google)))
    # ---- CardDAV / CalDAV queries
    CRN, CN = "urn:ietf:params:xml:ns:carddav", "urn:ietf:params:xml:ns:caldav"
    def abq(pfs, test="anyof"):
        return ET.fromstring(f'<CR:addressbook-query xmlns:D="DAV:" xmlns:CR="{CRN}"><D:prop><D:getetag/></D:prop>'
                             f'<CR:filter test="{test}">{pfs}</CR:filter></CR:addressbook-query>')
    tm = lambda t, how="contains", neg="no": f'<CR:text-match match-type="{how}" negate-condition="{neg}">{t}</CR:text-match>'
    pf = lambda name, inner, test="anyof": f'<CR:prop-filter name="{name}" test="{test}">{inner}</CR:prop-filter>'
    run("ab_21", lambda: CD._filter(abq(pf("FN", tm("a")) * 21)))
    run("ab_51", lambda: CD._filter(abq(pf("FN", tm("a") * 3) * 17)))
    run("ab_20", lambda: len(CD._filter(abq(pf("FN", tm("a") * 2) * 20))[1]))
    card = "BEGIN:VCARD\r\nVERSION:3.0\r\nFN:Ida Beispiel\r\nitem1.EMAIL;TYPE=work:ida@example.com\r\nNOTE:lang\r\n zeile\r\nEND:VCARD\r\n"
    cases = {"contains": abq(pf("FN", tm("beisp"))), "equals": abq(pf("FN", tm("ida beispiel", "equals"))),
             "starts": abq(pf("EMAIL", tm("ida@", "starts-with"))), "ends": abq(pf("EMAIL", tm(".com", "ends-with"))),
             "negate": abq(pf("FN", tm("ida", neg="yes"))), "notdef": abq(pf("TEL", "<CR:is-not-defined/>")),
             "allof_no": abq(pf("FN", tm("ida")) + pf("TEL", ""), "allof"), "anyof_yes": abq(pf("FN", tm("zzz")) + pf("EMAIL", "")),
             "folded": abq(pf("NOTE", tm("langzeile"))), "none": abq("")}
    run("ab_match", lambda: {k: CD._match(card, CD._filter(q)) for k, q in cases.items()})
    def calq(n, tms=1):
        pfs = ('<C:prop-filter name="STATUS">' + '<C:text-match>NEEDS-ACTION</C:text-match>' * tms + '</C:prop-filter>') * n
        return ET.fromstring(f'<C:calendar-query xmlns:D="DAV:" xmlns:C="{CN}"><C:filter><C:comp-filter name="VCALENDAR">'
                             f'<C:comp-filter name="VTODO">{pfs}</C:comp-filter></C:comp-filter></C:filter></C:calendar-query>')
    run("cal_21", lambda: CA.dav_query_filter(calq(21)))
    run("cal_51", lambda: CA.dav_query_filter(calq(17, 3)))
    run("cal_20", lambda: CA.dav_query_filter(calq(20))({4: {"status": 0}}))
    # ---- the bounded ones
    run("cal_plain", lambda: [SU._cal_plain("<!--<a" * 3333, 8000) for _ in range(10)][0][:40])
    run("cal_plain_ok", lambda: SU._cal_plain("<p>Hallo<!-- weg --></p><br>Welt <b>fett</b> &amp; gut", 8000))
    run("prop_blank", lambda: PR._p_str("a" + " " * 25000 + "b", "text", 10))
    run("prop_ok", lambda: PR._p_str("  a \n\n  b\nc  d ", "text", 100))
    run("chat_links", lambda: CS.chat_save_title("[](" * 30000))
    run("chat_ok", lambda: CS.chat_save_title("\n## Plan [Link](https://example.com) *jetzt*\nmehr"))
print(json.dumps(out))
'''

kt.fresh(prefix="P21443")
A = kt.setup()

r = subprocess.run(["docker", "exec", "-i", CT, "python", "-"], input=PROBE, capture_output=True, text=True, encoding="utf-8", timeout=900)
check(r.returncode == 0, "#6433 the probe runs in the app container " + r.stderr[-1500:])
P = json.loads(r.stdout.strip().splitlines()[-1]) if r.returncode == 0 else {}
print("measured:", json.dumps(P, ensure_ascii=False)[:6000])


def got(key, want):
    """The probe's line key starts with want and came within FAST seconds."""
    res, secs = P.get(key) or ["missing", 0]
    check(res.startswith(want) and secs < FAST, f"#6433 {key}: {want!r} within {FAST} s (got {res[:200]!r}, {secs} s)")
    return res


# task import: the cell limit
check(P.get("csv_limit_before", 0) < P.get("csv_cell_max", 0), f"#6433 the CSV cell limit is not raised for the whole process ({P.get('csv_limit_before')})")
got("csv_long_desc", "ok:300000")
check(P.get("csv_limit_after") == P.get("csv_limit_before"), f"#6433 the old CSV cell limit is back after an import ({P.get('csv_limit_after')})")
# dates
got("anydate_parens", "ok:(None, None)")
got("anydate_ok", "ok:('2025-01-15', None)")
got("numdate_long", "ok:(None, None)")
got("nl_date_long", "ok:None")
check(got("nl_date_ok", "ok:") != "ok:None", "#6433 a Todoist date text is still understood")
got("notion_long", "ok:(None, None, None)")
got("notion_ok", "ok:('2025-01-15', '2025-01-17', None)")
got("cu_long", "ok:(None, None)")
# names
got("stem_long", "ok:'a")
got("stem_ok", "ok:'Haushalt'")
got("notion_name_long", "ok:'x'")  # the end of a long name is kept (the page id sits there)
got("notion_name_ok", "ok:'Projekte'")
res = got("todoist_names", "ok:")
check("'Max'" in res and "'Ida'" in res and "**Max**" in res and "beleg.pdf (https://files.example.com/beleg.pdf)" in res,
      f"#6433 Todoist: long names cut, short ones as before, the attachment still a line ({res[:300]})")
got("todoist_files", "ok:'[[file {")
check("a.pdf (https://files.example.com/a.pdf)" in got("todoist_files_ok", "ok:"), "#6433 a Todoist attachment mark is still read")
# contacts CSV
check("Too many columns (at most 200)" in got("ctx_201", "BadInput:"), "#6433 a contacts CSV of 201 columns: refused with the message")
got("ctx_200", "ok:200")
got("ctx_split_blank", "ok:1")
got("ctx_split_ok", "ok:(['x', 'y'], ['a', 'b', 'c', 'd'])")
res = got("ctx_google", "ok:(500, ")
check("WORK" in res.upper() and "p0.1@example.com" in res, f"#6433 Google's sibling type column still reaches the e-mail ({res[:200]})")
# DAV queries
got("ab_21", "DavError:Too many filters")
got("ab_51", "DavError:")
got("ab_20", "ok:20")
want = {"contains": True, "equals": True, "starts": True, "ends": True, "negate": False, "notdef": True, "allof_no": False,
        "anyof_yes": True, "folded": True, "none": True}
check(got("ab_match", "ok:") == "ok:" + repr(want), f"#6433 CardDAV: the matches hold ({P.get('ab_match')})")
got("cal_21", "DavError:")
got("cal_51", "DavError:")
got("cal_20", "ok:True")
# the bounded ones
got("cal_plain", "ok:")
got("cal_plain_ok", "ok:'Hallo\\n\\nWelt fett & gut'")
check("Too long" in got("prop_blank", "BadInput:"), "#6433 a proposal text with long blanks: refused as too long, quickly")
got("prop_ok", "ok:'a b c  d'")
got("chat_links", "ok:")
got("chat_ok", "ok:'Plan Link jetzt'")

# ---------------------------------------------------------------- B. HTTP as a person without an organisation
FID, Fr = freelancer(B, A)
BK = Fr.post(B + "/api/books", json={"name": "Import 6433"}).json()["id"]


def csv_cols(n):
    return (";".join(f"Feld {k}" for k in range(n)) + "\r\n" + ";".join("v" for _ in range(n)) + "\r\n").encode()


r = Fr.post(B + f"/api/books/{BK}/import", params={"preview": 1}, files={"file": ("c.csv", csv_cols(201), "text/csv")})
check(r.status_code == 400 and "Too many columns (at most 200)" in r.text, f"#6433 HTTP: 201 columns refused with the message ({r.status_code} {r.text[:200]})")
r = Fr.post(B + f"/api/books/{BK}/import", params={"preview": 1}, files={"file": ("c.csv", csv_cols(200), "text/csv")})
check(r.ok and len(r.json().get("columns") or []) == 200, f"#6433 HTTP: 200 columns are read ({r.status_code} {r.text[:200]})")

sys.exit(kt.done("p21443_6433_import_regex"))
