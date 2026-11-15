#!/usr/bin/env python3
# kalmido-suite: after=p2296_a_pdfa nodata
"""2.1179.0 A (#6174): the layout of quotation and invoice PDFs (kalmido/office/pdf.py of the source tree), no server, no
container. Invented companies, figures and the test IBAN only. freelancer-matrix: office (the writer has no organisation in
it; the print model of a person without organisation is covered by the API suites)
 - 1 a quotation whose rights carry only the note (no right entered) prints no appendix "Transfer of rights" and no
   reference line: the note stands small beside the totals; with a right entered the appendix stays
 - 2 with sections the discount on the whole quotation is no row of the last section: the totals read "Summe Positionen",
   "Rabatt 5 %", "Summe netto"; the overview has no part "Rabatt"
 - 3 the totals move down at most PDF_SUM_FILL_MAX (25 mm) beyond the wished gap (was: to the page bottom)
 - 4 an invoice with a due text and a bank line prints ONE block "Zahlung" (due text, bank line, reference = the invoice
   number) above the footer, after the closing; no due text below the totals any more
 - 5 the standard invoice closing thanks (pack de / en and the translation of every app language)
 - 6 when the totals need a new page, they take at least the last three positions along (never a single one)
 - 7 the overview's amounts in the size of the part names
 - 8 the intro -> table air is 10 mm (PDF_INTRO_GAP)
 - 9 the order confirmation of a quotation sits at the bottom, right above the footer
usage: p21179_a_pdf_test.py            (KALMIDO_SRC = the source tree, default ../ next to tests/)"""
import importlib.util
import json
import os
import sys

N = os.path.dirname(os.path.abspath(__file__))
SRC = os.environ.get("KALMIDO_SRC") or os.path.join(N, "..")
spec = importlib.util.spec_from_file_location("office_pdf", os.path.join(SRC, "kalmido", "office", "pdf.py"))
pdf = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pdf)
sys.path.insert(0, N)
import pdfcheck  # noqa: E402
from kt import check, done  # noqa: E402

MM = pdf.MM
IBAN = "DE02120300000000202051"
CO = {"name": "Beispielstudio GmbH", "lines": ["Musterweg 1", "12345 Musterstadt"], "contact_lines": ["E-Mail: kontakt@example.com"],
      "register_lines": ["Amtsgericht Musterstadt HRB 1"], "bank_lines": ["Beispielbank", "IBAN DE02 1203 0000 0000 2020 51"], "color": "#2f5d8a"}
NOTE = "Im Übrigen gelten unsere AGB."
DUE = "Zahlbar bis 28.11.2026 ohne Abzug."


def money(v):
    return f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".") + " €"


def item(i, title=None, total=100):
    return {"kind": "item", "pos": i, "title": title or f"Leistung {i}", "qty": 1, "qty_text": "1", "unit_text": "Tag", "rate": total,
            "rate_text": money(total), "tax_pct": 19, "total": total, "total_text": money(total)}


def model(kind="offer", n=2, rights=None, lines=None, net=None, **kw):
    lines = lines if lines is not None else [item(i) for i in range(1, n + 1)]
    net = net if net is not None else 100 * n
    no = "KVA-2026-117" if kind == "offer" else "RE-2026-117"
    title = "Angebot" if kind == "offer" else "Rechnung"
    m = {"kind": kind, "lang": "de", "currency": "EUR", "number": no, "date": "2026-11-14", "date_text": "14.11.2026",
         "title": title, "project_title": "Imagefilm Hafenlichter", "company": CO,
         "recipient": {"name": "Beispielkunde AG", "lines": ["Beispielkunde AG", "Marktplatz 2", "54321 Beispielort"]},
         "meta": [[title + " Nr.", no], ["Datum", "14.11.2026"]], "lines": lines,
         "intro": "Sehr geehrte Damen und Herren,\nvielen Dank für Ihre Anfrage.",
         "totals": {"net": net, "rows": [["Summe netto", money(net)]], "show_tax_lines": False, "vat_note": "Alle Preise zuzüglich 19 % MwSt."},
         "rights": rights if rights is not None else {"title": "Rechteübertragung", "rows": [], "exceptions": "", "exclusive": 0, "note": NOTE},
         "closing": "Wir freuen uns auf die Zusammenarbeit.", "signature": "Mit freundlichen Grüßen", "signature_name": "Erika Beispiel",
         "accept_on": 1 if kind == "offer" else 0,
         "labels": {"pos": "Pos.", "title": "Leistung", "qty": "Menge", "unit_price": "Preis", "total": "Gesamt", "vat": "MwSt."}}
    m.update(kw)
    return m


def find(pages, s, start=False):
    return [(n, t) for n, p in enumerate(pages, 1) for t in p["texts"] if (t["s"].startswith(s) if start else s == t["s"])]


def all_text(pages):
    return " | ".join(t["s"] for p in pages for t in p["texts"])


def lay(m):
    data = pdf.office_pdf(m)
    return data, pdfcheck.layout(data)


# ---------------------------------------------------------------- 1. rights with only the note: no appendix
data, pg = lay(model())
txt = all_text(pg)
check("RECHTEÜBERTRAGUNG" not in txt and "Rechteübertragung siehe" not in txt, f"#6174 1: no appendix 'Rechteübertragung' with only the note ({txt[-300:]})")
nt, tot = find(pg, NOTE), find(pg, "Summe netto")
check(len(nt) == 1 and tot and nt[0][0] == tot[0][0] and abs(nt[0][1]["y"] - tot[0][1]["y"]) < 20 * MM and nt[0][1]["x"] < tot[0][1]["x"],
      f"#6174 1: the note stands small beside the totals {nt[:1]} {tot[:1]}")
check(nt and nt[0][1]["size"] < find(pg, "Leistung 1")[0][1]["size"], "#6174 1: the note is small")
check(not pdfcheck.problems(data), f"#6174 1: clean {pdfcheck.problems(data)[:3]}")
_, pr = lay(model(rights={"title": "Rechteübertragung", "rows": [["Zeitliche Auswertung", "unbegrenzt"]], "note": NOTE}))
check("RECHTEÜBERTRAGUNG" in all_text(pr) and find(pr, "Zeitliche Auswertung"), "#6174 1: with a right entered the appendix stays")

# ---------------------------------------------------------------- 2. the discount on the whole quotation in the totals
SECS = (("Konzeption", 3, 400), ("Dreh", 4, 1000), ("Schnitt", 3, 600))
ln, k, items_sum = [], 0, 0
for name, cnt, price in SECS:
    ln.append({"kind": "heading", "title": name})
    for _ in range(cnt):
        k += 1
        ln.append(item(k, f"{name} Teil {k}", price))
        items_sum += price
    ln.append({"kind": "subtotal", "label": f"Zwischensumme {name}", "title": name, "total": cnt * price, "total_text": money(cnt * price)})
disc = round(items_sum * 0.05, 2)
ln.append({"kind": "discount", "title": "Rabatt", "pct": 5, "total": -disc, "total_text": money(-disc), "detail": "5 % auf die markierten Positionen"})
data, pg = lay(model(lines=ln, net=items_sum - disc, rights={}))
# the totals stand twice (below the overview on page 1 and after the positions, #3622): every block reads the three rows
pos_t, rab, net_t = find(pg, "Summe Positionen"), find(pg, "Rabatt 5 %"), find(pg, "Summe netto")
check(len(rab) == len(pos_t) == len(net_t) == 2, f"#6174 2: the discount only in the two totals blocks (not in the overview / table) {rab}")
check(all(a[0] == r[0] == t[0] and a[1]["y"] < r[1]["y"] < t[1]["y"] and abs(r[1]["x"] - t[1]["x"]) < 0.5 for a, r, t in zip(pos_t, rab, net_t)),
      f"#6174 2: totals read 'Summe Positionen' / 'Rabatt 5 %' / 'Summe netto' in the totals column {pos_t} {rab} {net_t}")
check(find(pg, money(items_sum)) and find(pg, money(-disc)) and find(pg, money(items_sum - disc)), "#6174 2: the three amounts")
last_pos = find(pg, "Schnitt Teil 10")
check(last_pos and rab and (rab[-1][0], rab[-1][1]["y"]) > (last_pos[0][0], last_pos[0][1]["y"] + 10 * MM),
      "#6174 2: the discount below the table, not as its last row")
ov = find(pg, "Übersicht", True) or find(pg, "ÜBERSICHT", True)
check(ov, "#6174 2: the quotation has its overview")
# ---------------------------------------------------------------- 7. the overview's amounts in the size of the names
name_ov = [t for n, t in find(pg, "Konzeption") if n == 1]
amt_ov = [t for n, t in find(pg, money(1200)) if n == 1 and name_ov and abs(t["y"] - name_ov[0]["y"]) < 1]
check(name_ov and amt_ov and abs(amt_ov[0]["size"] - name_ov[0]["size"]) < 0.01,
      f"#6174 7: overview amount size = name size ({amt_ov[0]['size'] if amt_ov else None} / {name_ov[0]['size'] if name_ov else None})")
check(not pdfcheck.problems(data), f"#6174 2: clean {pdfcheck.problems(data)[:3]}")

# ---------------------------------------------------------------- 3. the totals move down at most 25 mm beyond the wish
check(abs(getattr(pdf, "PDF_SUM_FILL_MAX", 0) - 25 * MM) < 0.01, "#6174 3: PDF_SUM_FILL_MAX = 25 mm")
_, pg = lay(model(n=2, rights={}))
lp, tot = find(pg, "Leistung 2"), find(pg, "Summe netto")
gap = tot[0][1]["y"] - lp[0][1]["y"] if lp and tot and lp[0][0] == tot[0][0] else None
check(gap is not None and gap < pdf.PDF_SUM_GAP + 25 * MM + 15 * MM,
      f"#6174 3: a short quotation has no hole between table and totals ({gap and round(gap / MM)} mm)")

# ---------------------------------------------------------------- 9. the order confirmation at the bottom
acc = find(pg, "AUFTRAGSERTEILUNG")
foot = pg[-1]["foot"]
check(acc and foot and acc[0][0] == len(pg) and foot - acc[0][1]["y"] < 30 * MM and acc[0][1]["y"] - tot[0][1]["y"] > 30 * MM,
      f"#6174 9: the order confirmation right above the footer ({acc and foot and round((foot - acc[0][1]['y']) / MM)} mm)")

# ---------------------------------------------------------------- 8. intro -> table 10 mm
check(abs(getattr(pdf, "PDF_INTRO_GAP", 0) - 10 * MM) < 0.01, "#6174 8: PDF_INTRO_GAP = 10 mm")
it, th = find(pg, "vielen Dank für Ihre Anfrage."), find(pg, "LEISTUNG")
d = th[0][1]["y"] - it[0][1]["y"] if it and th else None
check(d is not None and 8 * MM < d < 14 * MM, f"#6174 8: intro -> table head about 10 mm ({d and round(d / MM, 1)} mm, was about 18)")

# ---------------------------------------------------------------- 4. the invoice: one payment block
inv = model("invoice", 3, rights={}, closing="Vielen Dank für Ihren Auftrag und die angenehme Zusammenarbeit.",
            totals={"rows": [["Summe netto", money(300)], ["MwSt. 19 % auf 300,00 €", money(57)], ["Rechnungsbetrag", money(357)]], "show_tax_lines": True},
            payment={"text": DUE, "iban": IBAN, "bic": "BYLADEM1001", "bank_name": "Beispielbank"})
data, pg = lay(inv)
hd, due, bank, ref = find(pg, "ZAHLUNG"), find(pg, DUE), find(pg, "Beispielbank · IBAN", True), find(pg, "Verwendungszweck: RE-2026-117")
check(len(hd) == 1 and len(due) == 1 and len(bank) == 1 and len(ref) == 1, f"#6174 4: one block: heading, due text, bank line, reference ({len(hd)}, {len(due)}, {len(bank)}, {len(ref)})")
if hd and due and bank and ref:
    check(hd[0][1]["y"] < due[0][1]["y"] < bank[0][1]["y"] < ref[0][1]["y"] and ref[0][1]["y"] - hd[0][1]["y"] < 25 * MM,
          "#6174 4: heading, due text, bank, reference in this order, close together")
    cl = find(pg, "Vielen Dank für Ihren Auftrag und die angenehme Zusammenarbeit.")
    gr = find(pg, "Rechnungsbetrag")
    check(cl and (cl[0][0], cl[0][1]["y"]) < (due[0][0], due[0][1]["y"]), "#6174 4: the due text comes after the closing (not below the totals)")
    check(gr and due[0][1]["y"] - gr[-1][1]["y"] > 25 * MM, "#6174 4: no due text right below the totals")
    f = pg[ref[0][0] - 1]["foot"]
    check(f and 0 < f - ref[0][1]["y"] < 15 * MM, "#6174 4: the payment block right above the footer")
check("Bitte überweisen" not in all_text(pg), "#6174 4: no transfer request in the text")
check(not pdfcheck.problems(data), f"#6174 4: clean {pdfcheck.problems(data)[:3]}")
# a reminder-like model (no due text): the bank line alone, as before
_, pg = lay(dict(inv, payment={"text": "", "iban": IBAN, "bic": "BYLADEM1001", "bank_name": "Beispielbank"}))
check(not find(pg, "ZAHLUNG") and len(find(pg, "Beispielbank · IBAN", True)) == 1, "#6174 4: without a due text no payment heading, the bank line stays")
# a credit note (no payment): nothing of it
_, pg = lay(dict(inv, kind="credit", payment=None))
check(not find(pg, "ZAHLUNG") and not find(pg, "Verwendungszweck", True), "#6174 4: a credit note has no payment block")

# ---------------------------------------------------------------- 5. the standard invoice closing
NEW = {"de": "Vielen Dank für Ihren Auftrag und die angenehme Zusammenarbeit.", "en": "Thank you for your order and the pleasant cooperation."}
for pk in ("de.json", "xx.json"):
    with open(os.path.join(SRC, "kalmido", "office", "packs", pk), encoding="utf-8") as fh:
        ic = json.load(fh)["texts"]["invoice_closing"]
    check(ic.get("de") == NEW["de"] and ic.get("en") == NEW["en"], f"#6174 5: pack {pk}: the new standard closing {ic}")
for lg in ("de", "fr", "es", "it", "nl"):
    with open(os.path.join(SRC, "static", "i18n", lg + ".json"), encoding="utf-8") as fh:
        tv = json.load(fh).get(NEW["en"] + "|pack") or ""
    check(tv and "Zusammenarbeit" in tv if lg == "de" else bool(tv), f"#6174 5: {lg}: the closing translated ({tv!r})")

# ---------------------------------------------------------------- 6. the totals never take a single position along
lone = []
for n in range(8, 70):
    _, pg = lay(model(n=n, rights={}))
    t = find(pg, "Summe netto")
    if not t or t[0][0] == 1:
        continue
    on_page = [x for x in find(pg, "Leistung ", True) if x[0] == t[0][0]]
    if len(on_page) < 3:
        lone.append((n, len(on_page)))
check(not lone, f"#6174 6: the totals take at least 3 positions to a new page ({lone[:5]})")

sys.exit(done("p21179_a_pdf"))
