#!/usr/bin/env python3
# kalmido-suite: fresh
"""2.1272.0 (#6422): one reader for XML from outside (kalmido/core/safexml.py) and every place that uses it. Own container
(start.sh). Invented names only; the hostile files are made here and stay small enough that a red run (the fix taken
back) costs seconds and some hundred MB, not the machine.

 A. the reader itself (loaded here as a single file, standard library only):
    - the audit's finding: UTF-16 without a byte order mark decodes as UTF-8 text with NUL bytes, the old text search sees
      no DOCTYPE in it (shown here as the reference), expat detects UTF-16 on its own and unfolds the entity -- the reader
      refuses it (NUL) as bytes and as decoded text
    - a DOCTYPE anywhere: behind 100 KB of comment, cut between two read pieces, with ATTLIST only (no ENTITY)
    - the parser's own check: a DOCTYPE the byte search is made blind for is still refused, at the declaration
    - limits while reading: a document of a million elements is left after a few thousand; depth; size
    - what stays readable: declared encodings, a UTF-8 byte order mark, decoded text with a stale declaration, a stream
 B. inside the app container, the app's own functions, each with its hostile file and a time limit: e-invoice (reader,
    the check in its own process with the memory limit, a whole file), CAMT rows and balances, DATEV document.xml, mind
    map (OPML, FreeMind), .xlsx (table import and legacy import; a DOCTYPE behind the first 4 KB with an ATTLIST
    default), DAV request body, CalDAV answer, feed and OPML import, the off-site listing, SVG (also nested too deep for
    the writer). And the same places still read an ordinary file (UTF-16 with a byte order mark where it was read before).
usage: p21272_a_xml_test.py <datadir>      (P21272A_NOSTART=1 = the server already runs)"""
import importlib.util
import json
import os
import re
import subprocess
import sys
import time
from xml.etree import ElementTree as ET

N = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, N)
import kt  # noqa: E402
from kt import CT, check  # noqa: E402

SRC = os.environ.get("KALMIDO_SRC") or os.path.join(N, "..")
_spec = importlib.util.spec_from_file_location("sf_safexml", os.path.join(SRC, "kalmido", "core", "safexml.py"))
SX = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(SX)

# the hostile documents, used here and inside the container (the same text)
GEN = r'''
def laughs(root_open, root_close, levels=5, name="x"):
    """A document whose one entity reference unfolds to 10 ** levels elements <i/> (billion laughs, kept small)."""
    ents = '<!ENTITY e0 "<i/>">' + "".join(f'<!ENTITY e{n} "{("&e%d;" % (n - 1)) * 10}">' for n in range(1, levels + 1))
    return f'<?xml version="1.0"?><!DOCTYPE {name} [{ents}]>{root_open}&e{levels};{root_close}'

def attlist(root_open, root_close, el="c", n=2000, size=20000, pad=0, name="x"):
    """No ENTITY at all: an ATTLIST default of size characters lands on every one of the n elements; pad bytes of
    comment stand in front of the DOCTYPE."""
    lead = ("<!--" + "p" * pad + "-->") if pad else ""
    return (f'<?xml version="1.0"?>{lead}<!DOCTYPE {name} [<!ATTLIST {el} d CDATA "{"A" * size}">]>'
            + root_open + f"<{el}/>" * n + root_close)

OLD = __import__("re").compile(r"<!\s*(DOCTYPE|ENTITY)", __import__("re").I)  # the search every reader had before 2.1272.0
'''
exec(GEN)  # noqa: S102 - our own text above


def reason(src, **kw):
    """What the reader says to src: the reason of XmlRefused, "broken" for ET.ParseError, else the number of elements."""
    lim = {"max_bytes": 50_000_000, "max_elements": 5_000_000, "max_depth": 100, **kw}
    try:
        return sum(1 for _e in SX.sx_tree(src, **lim).iter())
    except SX.XmlRefused as e:
        return e.reason
    except ET.ParseError:
        return "broken"


def timed(fn):
    t0 = time.monotonic()
    r = fn()
    return r, time.monotonic() - t0


# ---------------------------------------------------------------- A. the reader
doc = laughs("<a>", "</a>", levels=3)  # noqa: F821 - from GEN
u16 = doc.encode("utf-16-le")  # no byte order mark
as_text = u16.decode("utf-8")  # decodes without an error: every second character is NUL
check(OLD.search(as_text) is None, "#6422 reference: the old text search sees no DOCTYPE in UTF-16 without a mark")  # noqa: F821
check(sum(1 for _e in ET.fromstring(u16).iter()) == 1001, "#6422 reference: expat reads that UTF-16 on its own and unfolds the entity")
check(reason(u16) == "nul", f"#6422 UTF-16 without a mark is refused as bytes ({reason(u16)})")
check(reason(as_text) == "nul", f"#6422 ... and as the text a caller decoded ({reason(as_text)})")
check(reason(doc.encode("utf-16")) == "nul", "#6422 UTF-16 with a mark is refused as bytes too (a caller decodes it first)")
check(reason(doc.encode("utf-16").decode("utf-16")) == "dtd", "#6422 ... decoded, its DOCTYPE is seen")
check(reason(doc.encode("utf-32")) == "nul", "#6422 UTF-32 is refused")
check(reason(doc.encode()) == "dtd" and reason(doc) == "dtd", "#6422 a DOCTYPE in UTF-8 is refused (bytes and text)")
late = "<?xml version='1.0'?><!--" + "c" * 100_000 + "-->" + doc.split("?>", 1)[1]
check(reason(late.encode()) == "dtd", "#6422 a DOCTYPE behind 100 KB of comment is refused")
check(reason(attlist("<s>", "</s>", n=5, size=10).encode()) == "dtd", "#6422 a DOCTYPE with an ATTLIST only (no ENTITY) is refused")  # noqa: F821
for cut in range(1, 9):  # "<!DOCTYPE" cut between two pieces at every place
    pad = "<!--" + "c" * (SX.SX_CHUNK - 7 - cut) + "-->"
    d = pad + "<!DOCTYPE a [<!ENTITY e 'x'>]><a>&e;</a>"
    assert d.encode()[SX.SX_CHUNK - cut:SX.SX_CHUNK - cut + 9] == b"<!DOCTYPE", cut
    check(reason(d.encode()) == "dtd", f"#6422 a DOCTYPE cut {cut} bytes before the end of a piece is refused")
check(reason("<a><![CDATA[ <!ENTITY x> ]]></a>") == "dtd", "#6422 the words inside the content are refused as before (no DTD at all)")

# the parser's own check: the byte search made blind, the DOCTYPE is still refused -- and at its declaration
keep = SX._DTD
SX._DTD = re.compile(rb"(?!x)x")  # matches nothing
try:
    r, secs = timed(lambda: reason(laughs("<a>", "</a>", levels=6).encode()))  # noqa: F821
    check(r == "dtd" and secs < 1, f"#6422 without the byte search the prolog parser refuses the DOCTYPE at once ({r}, {secs:.2f} s)")
    check(reason(late.encode()) == "dtd", "#6422 ... also behind 100 KB of comment")
finally:
    SX._DTD = keep

# limits while reading
million = b"<r>" + b"<i/>" * 1_000_000 + b"</r>"
seen = {"n": 0}


def count_until_refused():
    try:
        for ev, _el in SX.sx_events(million, max_bytes=len(million), max_elements=1000, want=("start",)):
            seen["n"] += 1
    except SX.XmlRefused as e:
        return e.reason
    return None


r, secs = timed(count_until_refused)
check(r == "elements" and seen["n"] <= 1000 and secs < 1, f"#6422 a million elements: left at the limit ({r}, {seen['n']} seen, {secs:.2f} s)")
check(reason(b"<a>" * 5000 + b"</a>" * 5000, max_depth=40) == "depth", "#6422 nested too deep: refused")
check(reason(b"<a>" * 40 + b"</a>" * 40, max_depth=40) == 40, "#6422 nested just as deep as allowed: read")
check(reason(million, max_bytes=100_000) == "size", "#6422 more bytes than allowed: refused")
check(reason(b"<a><b></a>") == "broken" and reason(b"") == "broken" and reason(b"   ") == "broken" and reason(b"<a>\x00</a>") == "nul",
      "#6422 broken and empty documents are ET.ParseError, a NUL in the content is refused")

# what stays readable
umlaut = '<?xml version="1.0" encoding="ISO-8859-1"?><a t="Grüße">Müller</a>'
root = SX.sx_tree(umlaut.encode("latin-1"), max_bytes=1000, max_elements=10)
check(root.text == "Müller" and root.get("t") == "Grüße", "#6422 a declared ISO-8859-1 is read as bytes")
root = SX.sx_tree(umlaut.replace("ISO-8859-1", "windows-1252").encode("cp1252"), max_bytes=1000, max_elements=10)
check(root.text == "Müller", "#6422 a declared windows-1252 is read as bytes")
root = SX.sx_tree("\ufeff" + umlaut, max_bytes=1000, max_elements=10)  # decoded already: the declaration no longer holds
check(root.text == "Müller" and root.get("t") == "Grüße", "#6422 decoded text with a stale declaration (and a mark) is read")
root = SX.sx_tree(b"\xef\xbb\xbf<a>\xc3\xa4</a>", max_bytes=1000, max_elements=10)
check(root.text == "ä", "#6422 UTF-8 with a byte order mark is read")
big = "<r>" + "".join(f"<i n='{i}'>ä€𝄞 {i}</i>" for i in range(20000)) + "</r>"  # multi-byte characters over the piece borders
root = SX.sx_tree(big, max_bytes=10_000_000, max_elements=30000)
check(len(root) == 20000 and root[19999].text == "ä€𝄞 19999", "#6422 a long text with multi-byte characters is read whole")
root = SX.sx_tree(big.encode(), max_bytes=10_000_000, max_elements=30000)
check(len(root) == 20000 and root[12345].text == "ä€𝄞 12345", "#6422 ... and the same as bytes")
got = [el.get("n") for ev, el in SX.sx_events(iter([big.encode()[:70001], big.encode()[70001:]]), max_bytes=10_000_000, want=("end",))
       if el.tag == "i"]
check(len(got) == 20000 and got[-1] == "19999", "#6422 a stream of pieces gives every element once")
check(SX.sx_check(big.encode(), max_bytes=10_000_000, max_elements=30000) is None, "#6422 sx_check reads an ordinary document to its end")

# ---------------------------------------------------------------- B. inside the app container: every place that reads XML
PROBE = GEN + r'''
import io, json, time, zipfile
from xml.etree import ElementTree as ET
from kalmido.core.config import app
from kalmido.core.errors import BadInput, BadKey
from kalmido.core import csvimport, safexml
from kalmido.office import einvoice_in as E, bookarch, cfbank, legacyimport as li
from kalmido.sheets import io as sio
from kalmido.wiki import outline, wikiatt
from kalmido.calendars import caldav, subscriptions as subs
from kalmido.life import rss
from kalmido.admin import offsite

out = {}
def run(key, fn):
    """[what happened, seconds]: "ok:<repr of the result>" or "<exception class>:<text>"."""
    t0 = time.monotonic()
    try:
        r = "ok:" + repr(fn())[:300]
    except BaseException as e:  # the test wants to see a RecursionError / MemoryError too
        r = type(e).__name__ + ":" + (e.text() if hasattr(e, "text") else str(e))[:300]
    out[key] = [r, round(time.monotonic() - t0, 3)]

UBL = """<?xml version="1.0" encoding="UTF-8"?>
<ubl:Invoice xmlns:ubl="urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"
  xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"
  xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2">
  <cbc:ID>UBL-2026-0042</cbc:ID><cbc:IssueDate>2026-10-05</cbc:IssueDate><cbc:InvoiceTypeCode>380</cbc:InvoiceTypeCode>
  <cbc:Note>Grüße aus Musterstadt</cbc:Note><cbc:DocumentCurrencyCode>EUR</cbc:DocumentCurrencyCode>
  <cac:AccountingSupplierParty><cac:Party><cac:PartyName><cbc:Name>Beispiel Druckerei</cbc:Name></cac:PartyName></cac:Party></cac:AccountingSupplierParty>
  <cac:LegalMonetaryTotal><cbc:TaxExclusiveAmount currencyID="EUR">100.00</cbc:TaxExclusiveAmount>
    <cbc:TaxInclusiveAmount currencyID="EUR">119.00</cbc:TaxInclusiveAmount><cbc:PayableAmount currencyID="EUR">119.00</cbc:PayableAmount></cac:LegalMonetaryTotal>
</ubl:Invoice>"""
UBL_OPEN = UBL.split("<cbc:ID>")[0].split("?>", 1)[1].strip()
CAMT = """<?xml version="1.0" encoding="ISO-8859-1"?><Document xmlns="urn:iso:std:iso:20022:tech:xsd:camt.053.001.02"><BkToCstmrStmt><Stmt>
<Acct><Id><IBAN>DE02120300000000202051</IBAN></Id></Acct>
<Bal><Tp><CdOrPrtry><Cd>CLBD</Cd></CdOrPrtry></Tp><Amt Ccy="EUR">250.00</Amt><CdtDbtInd>CRDT</CdtDbtInd><Dt><Dt>2026-10-05</Dt></Dt></Bal>
<Ntry><Amt Ccy="EUR">12.50</Amt><CdtDbtInd>DBIT</CdtDbtInd><BookgDt><Dt>2026-10-05</Dt></BookgDt>
<NtryDtls><TxDtls><RltdPties><Cdtr><Nm>Bäckerei Müller</Nm></Cdtr></RltdPties><RmtInf><Ustrd>Brötchen</Ustrd></RmtInf></TxDtls></NtryDtls></Ntry>
</Stmt></BkToCstmrStmt></Document>"""
CAMT_OPEN = '<Document xmlns="urn:iso:std:iso:20022:tech:xsd:camt.053.001.02">'

def as_nul_text(doc):
    """What a caller that decodes itself gets of UTF-16 without a mark: UTF-8 text with NUL bytes."""
    return doc.encode("utf-16-le").decode("utf-8")

with app.test_request_context("/", headers={"Accept-Language": "en"}):
    # ---- e-invoice
    hostile = laughs(UBL_OPEN, "</ubl:Invoice>").encode("utf-16-le")  # 100 000 elements when unfolded
    out["ei_old_blind"] = OLD.search(E._decode(hostile)) is None
    run("ei_parse_u16", lambda: E.ei_parse(hostile))
    run("ei_checked_u16", lambda: E.ei_checked(hostile))
    run("ei_file_u16", lambda: E.ei_of_file("rechnung.xml", "application/xml", hostile))
    run("ei_checked_dtd", lambda: E.ei_checked(laughs(UBL_OPEN, "</ubl:Invoice>").encode()))
    many = (UBL_OPEN + "<x/>" * (E.ELEMENTS_MAX + 10) + "</ubl:Invoice>").encode()
    run("ei_parse_many", lambda: E.ei_parse(many))
    run("ei_checked_many", lambda: E.ei_checked(many))
    run("ei_checked_deep", lambda: E.ei_checked((UBL_OPEN + "<x>" * 60 + "</x>" * 60 + "</ubl:Invoice>").encode()))
    run("ei_checked_broken", lambda: E.ei_checked(UBL[:400].encode()))
    run("ei_checked_ok", lambda: E.ei_checked(UBL.encode()))
    run("ei_file_ok", lambda: (E.ei_of_file("rechnung.xml", "application/xml", UBL.encode()) or {}).get("number"))
    run("ei_parse_u16_bom", lambda: E.ei_parse(UBL.replace('encoding="UTF-8"', 'encoding="UTF-16"').encode("utf-16"))["note"])
    run("ei_checked_u16_bom", lambda: E.ei_checked(UBL.replace('encoding="UTF-8"', 'encoding="UTF-16"').encode("utf-16")))
    run("ei_parse_latin", lambda: E.ei_parse(UBL.replace("UTF-8", "ISO-8859-1").encode("latin-1"))["note"])
    # the worker's memory limit holds: the limits taken away, a document far larger than the worker may hold
    keep = (E.ELEMENTS_MAX, E.XML_MAX, E.PDF_MEM)
    E.ELEMENTS_MAX, E.XML_MAX, E.PDF_MEM = 10 ** 9, 200 * 1024 * 1024, 160 * 1024 * 1024
    try:
        run("ei_checked_memory", lambda: E.ei_checked((UBL_OPEN + "<x><y>" * 30 + "</y></x>" * 30 + "<z a='1' b='2'/>" * 2_000_000 + "</ubl:Invoice>").encode()))
    finally:
        E.ELEMENTS_MAX, E.XML_MAX, E.PDF_MEM = keep
    # ---- CAMT: rows and balances
    hostile = as_nul_text(laughs(CAMT_OPEN, "</Document>"))
    out["camt_old_blind"] = OLD.search(hostile) is None
    run("camt_rows_u16", lambda: csvimport.camt_rows(hostile))
    run("camt_bal_u16", lambda: cfbank.cfb_camt_balances(hostile, "EUR"))
    run("camt_rows_dtd", lambda: csvimport.camt_rows(laughs(CAMT_OPEN, "</Document>")))
    run("camt_rows_ok", lambda: [(r["amount"], r["counterpart"], r["purpose"]) for r in csvimport.camt_rows(CAMT)])
    run("camt_bal_ok", lambda: [(b["kind"], str(b["amount"])) for b in cfbank.cfb_camt_balances(CAMT, "EUR")])
    # ---- DATEV archive: document.xml
    DOCS = ('<?xml version="1.0" encoding="windows-1252"?><archive xmlns="http://xml.datev.de/bedi/tps/document/v05.0"><content>'
            '<document guid="0f3c2a10-1111-4222-8333-444455556666"><extension xsi:type="File" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" name="Beleg Müller.pdf"/></document>'
            '</content></archive>')
    hostile = laughs("<archive>", "</archive>").encode("utf-16-le")
    out["datev_old_blind"] = OLD.search(bookarch.di_decode(hostile)) is None
    run("datev_u16", lambda: bookarch._docs_xml(hostile))
    run("datev_dtd", lambda: bookarch._docs_xml(laughs("<archive>", "</archive>").encode()))
    keep = bookarch.BA_DOCS_ELEMENTS
    bookarch.BA_DOCS_ELEMENTS = 1000
    try:
        run("datev_many", lambda: bookarch._docs_xml(b"<archive>" + b"<document/>" * 200_000 + b"</archive>"))
    finally:
        bookarch.BA_DOCS_ELEMENTS = keep
    run("datev_ok", lambda: bookarch._docs_xml(DOCS.encode("cp1252")))
    # ---- mind map
    hostile = as_nul_text(laughs("<opml><body>", "</body></opml>"))
    run("mm_opml_u16", lambda: outline.mm_parse_opml(hostile))
    run("mm_freemind_u16", lambda: outline.mm_parse_freemind(as_nul_text(laughs("<map>", "</map>"))))
    run("mm_opml_dtd", lambda: outline.mm_parse_opml(laughs("<opml><body>", "</body></opml>")))
    run("mm_many", lambda: outline.mm_xml("<opml>" + "<outline/>" * (outline.MM_XML_ELEMENTS + 10) + "</opml>"))
    run("mm_opml_ok", lambda: [k["title"] for k in outline.mm_parse_opml('<?xml version="1.0" encoding="UTF-8"?><opml><body><outline text="Äpfel"><outline text="Birnen"/></outline></body></opml>')["children"]])
    # ---- .xlsx: a DOCTYPE behind the first 4 KB, an ATTLIST default on every cell (no ENTITY)
    NS = 'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'
    RNS = 'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"'
    def xlsx(sheet, strings=None, name="Contacts"):
        p = {"[Content_Types].xml": b'<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>',
             "xl/workbook.xml": f'<?xml version="1.0"?><workbook {NS} {RNS}><sheets><sheet name="{name}" sheetId="1" r:id="rId1"/></sheets></workbook>'.encode(),
             "xl/_rels/workbook.xml.rels": b'<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/></Relationships>',
             "xl/worksheets/sheet1.xml": sheet}
        if strings is not None:
            p["xl/sharedStrings.xml"] = strings
        b = io.BytesIO()
        with zipfile.ZipFile(b, "w", zipfile.ZIP_DEFLATED) as z:
            for n, d in p.items():
                z.writestr(n, d)
        return b.getvalue()
    rows = "".join(f'<row r="{r}">' + "".join(f'<c r="{c}{r}"><v>{r}</v></c>' for c in "ABCDE") + "</row>" for r in range(1, 401))
    sheet = attlist(f"<worksheet {NS}><sheetData>" + rows, "</sheetData></worksheet>", n=0, size=100_000, pad=6000, name="worksheet")
    raw = xlsx(sheet.encode())
    out["xlsx_bytes"] = len(raw)
    out["xlsx_doctype_at"] = sheet.index("<!DOCTYPE")
    run("xlsx_sheet_attlist", lambda: sio.shx_read_xlsx(raw))
    run("xlsx_legacy_attlist", lambda: li.fi_xlsx_read(raw))
    sst = attlist(f"<sst {NS}>" + "<si><t>x</t></si>" * 2000, "</sst>", el="si", n=0, size=100_000, pad=6000, name="sst")
    raw2 = xlsx(f'<?xml version="1.0"?><worksheet {NS}><sheetData><row r="1"><c r="A1" t="s"><v>0</v></c></row></sheetData></worksheet>'.encode(), sst.encode())
    run("xlsx_sheet_sst", lambda: sio.shx_read_xlsx(raw2))
    run("xlsx_legacy_sst", lambda: li.fi_xlsx_read(raw2))
    u16 = f'<?xml version="1.0" encoding="UTF-16"?><worksheet {NS}><sheetData/></worksheet>'.encode("utf-16-le")
    run("xlsx_sheet_u16", lambda: sio.shx_read_xlsx(xlsx(u16)))
    plain = xlsx(f'<?xml version="1.0"?><worksheet {NS}><sheetData>{rows}</sheetData></worksheet>'.encode())
    run("xlsx_sheet_ok", lambda: len(sio.shx_read_xlsx(plain).rows))
    run("xlsx_legacy_ok", lambda: len(li.fi_xlsx_read(plain)["contacts"]))
    # ---- DAV request body, CalDAV answer, feed, OPML: refused at the DOCTYPE, not after the whole document
    big_ent = '<?xml version="1.0"?><!DOCTYPE a [<!ENTITY e "' + "B" * 50_000 + '">]>'
    slow = big_ent + '<D:multistatus xmlns:D="DAV:">' + "<D:response>&e;</D:response>" * 4000 + "</D:multistatus>"  # 200 MB of text when unfolded
    out["dav_bytes"] = len(slow)
    run("dav_body", lambda: caldav.dav_xml(slow.replace("multistatus", "propfind").encode()))
    run("dav_answer", lambda: subs._dav_xml(slow.encode()))
    run("dav_answer_u16", lambda: subs._dav_xml(laughs('<D:multistatus xmlns:D="DAV:">', "</D:multistatus>").encode("utf-16-le")))
    feed_slow = big_ent + "<rss><channel>" + "<item><title>&e;</title></item>" * 4000 + "</channel></rss>"
    run("rss_dtd", lambda: rss.rss_parse(feed_slow.encode(), "https://example.test/feed"))
    run("rss_u16", lambda: rss.rss_parse(laughs("<rss><channel>", "</channel></rss>").encode("utf-16-le"), "https://example.test/feed"))
    FEED = '<?xml version="1.0" encoding="UTF-16"?><rss version="2.0"><channel><title>Grüße</title><link>https://example.test/</link><item><title>Erster Beitrag</title><link>https://example.test/1</link><guid>g1</guid></item></channel></rss>'
    run("rss_ok", lambda: [rss.rss_parse(FEED.replace("UTF-16", "UTF-8").encode(), "https://example.test/feed")[0]["title"], len(rss.rss_parse(FEED.replace("UTF-16", "UTF-8").encode(), "https://example.test/feed")[1])])
    run("rss_ok_u16_bom", lambda: rss.rss_parse(FEED.encode("utf-16"), "https://example.test/feed")[1][0]["title"])
    run("xml_no_dtd_deep", lambda: caldav.xml_no_dtd(b"<a>" * 5000 + b"</a>" * 5000))
    run("dav_body_ok", lambda: caldav.dav_xml(b'<?xml version="1.0" encoding="utf-8"?><D:propfind xmlns:D="DAV:"><D:prop><D:getetag/></D:prop></D:propfind>').tag)
    run("dav_answer_ok", lambda: len(subs._dav_responses(subs._dav_xml(b'<?xml version="1.0"?><D:multistatus xmlns:D="DAV:"><D:response><D:href>/cal/1.ics</D:href><D:propstat><D:prop><D:getetag>"1"</D:getetag></D:prop><D:status>HTTP/1.1 200 OK</D:status></D:propstat></D:response></D:multistatus>'), "https://example.test/cal/")))
    # ---- the listing of an off-site store (it had no guard at all)
    run("offsite_dtd", lambda: offsite._listing((big_ent + "<ListBucketResult>" + "<Contents><Key>&e;</Key></Contents>" * 4000 + "</ListBucketResult>").encode()))
    run("offsite_u16", lambda: offsite._listing(laughs("<ListBucketResult>", "</ListBucketResult>").encode("utf-16-le")))
    run("offsite_ok", lambda: [el.text for el in offsite._listing(b'<?xml version="1.0" encoding="UTF-8"?><ListBucketResult xmlns="http://s3.amazonaws.com/doc/2006-03-01/"><Contents><Key>kalmido/a.bin</Key></Contents></ListBucketResult>').iter() if el.tag.endswith("}Key")])
    # ---- SVG
    SVG = '<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10"><g><rect width="10" height="10" onclick="x()"/></g><script>alert(1)</script></svg>'
    run("svg_ok", lambda: wikiatt.wka_svg_clean(SVG.encode()).decode())
    run("svg_deep", lambda: len(wikiatt.wka_svg_clean(('<svg xmlns="http://www.w3.org/2000/svg">' + "<g>" * 20000 + "</g>" * 20000 + "</svg>").encode())))
    run("svg_deep_ok", lambda: wikiatt.wka_svg_clean(('<svg xmlns="http://www.w3.org/2000/svg">' + "<g>" * 150 + "</g>" * 150 + "</svg>").encode()).count(b"<g"))
    run("svg_dtd_late", lambda: wikiatt.wka_svg_clean(("<!--" + "c" * 100_000 + "-->" + laughs('<svg xmlns="http://www.w3.org/2000/svg">', "</svg>").split("?>", 1)[1]).encode()))
    run("svg_u16", lambda: wikiatt.wka_svg_clean(b" " * 80 + laughs('<svg xmlns="http://www.w3.org/2000/svg">', "</svg>").split("?>", 1)[1].encode("utf-16-le")))
    keep = wikiatt.SVG_ELEMENTS_MAX
    wikiatt.SVG_ELEMENTS_MAX = 1000
    try:
        run("svg_many", lambda: wikiatt.wka_svg_clean(('<svg xmlns="http://www.w3.org/2000/svg">' + "<g/>" * 500_000 + "</svg>").encode()))
    finally:
        wikiatt.SVG_ELEMENTS_MAX = keep
print(json.dumps(out))
'''

kt.fresh(prefix="P21272A")
kt.setup()

r = subprocess.run(["docker", "exec", "-i", CT, "python", "-"], input=PROBE, capture_output=True, text=True, encoding="utf-8", timeout=900)
check(r.returncode == 0, "#6422 the probe runs in the app container " + r.stderr[-1500:])
P = json.loads(r.stdout.strip().splitlines()[-1]) if r.returncode == 0 else {}
print("measured:", json.dumps(P, ensure_ascii=False)[:6000])
FAST = 3.0  # seconds: every refusal comes long before the document is worked through (the audit measured 7.6 s and 23 s)


def got(key, want, fast=True):
    """The probe's line key starts with want (and came within FAST seconds)."""
    res, secs = P.get(key) or ["missing", 0]
    ok = res.startswith(want) and (not fast or secs < FAST)
    check(ok, f"#6422 {key}: {want!r} {'within ' + str(FAST) + ' s ' if fast else ''}(got {res[:160]!r}, {secs} s)")
    return res


# e-invoice
check(P.get("ei_old_blind") is True, "#6422 reference: the e-invoice's old text search saw no DOCTYPE in that file")
check("DOCTYPE" in got("ei_parse_u16", "EinvoiceError:"), "#6422 e-invoice in UTF-16 without a mark: refused with the DOCTYPE text")
got("ei_checked_u16", "ok:'nul'")
got("ei_file_u16", "ok:None")
got("ei_checked_dtd", "ok:'dtd'")
check("too large" in got("ei_parse_many", "EinvoiceError:"), "#6422 e-invoice with too many elements: refused")
got("ei_checked_many", "ok:'elements'")
got("ei_checked_deep", "ok:'depth'")
got("ei_checked_broken", "ok:'broken'")
got("ei_checked_ok", "ok:None")
got("ei_file_ok", "ok:'UBL-2026-0042'")
got("ei_parse_u16_bom", "ok:'Grüße aus Musterstadt'")
got("ei_checked_u16_bom", "ok:None")
got("ei_parse_latin", "ok:'Grüße aus Musterstadt'")
mem = (P.get("ei_checked_memory") or ["missing"])[0]  # the process hit its memory limit (said so, or died); the app goes on
check(mem in ("ok:'memory'", "ok:'worker'"), f"#6422 the check process holds its memory limit ({mem})")
# CAMT
check(P.get("camt_old_blind") is True, "#6422 reference: the CAMT reader's old text search saw no DOCTYPE in that text")
check("DOCTYPE" in got("camt_rows_u16", "BadInput:"), "#6422 CAMT text with NUL bytes: refused with the DOCTYPE text")
got("camt_bal_u16", "ok:[]")
check("DOCTYPE" in got("camt_rows_dtd", "BadInput:"), "#6422 CAMT with a DOCTYPE: refused as before")
check("Bäckerei Müller" in got("camt_rows_ok", "ok:[") and "Brötchen" in P["camt_rows_ok"][0], "#6422 an ordinary CAMT statement (stale declaration) is read")
check("250" in got("camt_bal_ok", "ok:[("), "#6422 ... and its balance")
# DATEV
check(P.get("datev_old_blind") is True, "#6422 reference: the DATEV reader's old text search saw no DOCTYPE in that file")
check("DOCTYPE" in got("datev_u16", "BadInput:"), "#6422 document.xml in UTF-16 without a mark: refused")
check("DOCTYPE" in got("datev_dtd", "BadInput:"), "#6422 document.xml with a DOCTYPE: refused as before")
check("too large" in got("datev_many", "BadInput:"), "#6422 document.xml over its element limit: refused while reading")
check("Beleg Müller.pdf" in got("datev_ok", "ok:[("), "#6422 an ordinary document.xml (windows-1252) is read")
# mind map
for k in ("mm_opml_u16", "mm_freemind_u16", "mm_opml_dtd"):
    check("DOCTYPE" in got(k, "BadInput:"), f"#6422 {k}: refused with the DOCTYPE text")
got("mm_many", "BadInput:")
got("mm_opml_ok", "ok:['Äpfel']")
# .xlsx
check(P.get("xlsx_doctype_at", 0) > 4096 and P.get("xlsx_bytes", 10 ** 9) < 200_000,
      f"#6422 the .xlsx carries its DOCTYPE behind the first 4 KB and is small ({P.get('xlsx_doctype_at')}, {P.get('xlsx_bytes')} bytes)")
for k in ("xlsx_sheet_attlist", "xlsx_legacy_attlist", "xlsx_sheet_sst", "xlsx_legacy_sst", "xlsx_sheet_u16"):
    check("not a spreadsheet" in got(k, "BadInput:"), f"#6422 {k}: refused as no spreadsheet")
got("xlsx_sheet_ok", "ok:400")
got("xlsx_legacy_ok", "ok:")
# DAV, feeds
check(P.get("dav_bytes", 10 ** 9) < 400_000, f"#6422 the DAV document is small ({P.get('dav_bytes')} bytes)")
check("DTD" in got("dav_body", "DavError:"), "#6422 DAV body with a DTD: refused at the DOCTYPE")
got("dav_answer", "CalError:parse")
got("dav_answer_u16", "CalError:parse")
got("rss_dtd", "CalError:dtd")
got("rss_u16", "CalError:dtd")
got("rss_ok", "ok:['Grüße', 1]")
got("rss_ok_u16_bom", "ok:'Erster Beitrag'")
got("xml_no_dtd_deep", "ParseError:")
got("dav_body_ok", "ok:'{DAV:}propfind'")
got("dav_answer_ok", "ok:1")
# off-site listing
got("offsite_dtd", "ParseError:")
got("offsite_u16", "ParseError:")
got("offsite_ok", "ok:['kalmido/a.bin']")
# SVG
svg = got("svg_ok", "ok:")
check("<rect" in svg and "onclick" not in svg and "script" not in svg, "#6422 an ordinary SVG is cleaned as before")
got("svg_deep", "BadKey:")  # before: RecursionError out of the writer
got("svg_deep_ok", "ok:150")
got("svg_dtd_late", "BadKey:")
got("svg_u16", "BadKey:")
got("svg_many", "BadKey:")

sys.exit(kt.done("p21272_a_xml"))
