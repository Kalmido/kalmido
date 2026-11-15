#!/usr/bin/env python3
# kalmido-suite: after=p2296_a_pdfa nodata
"""2.1201.0 (#6175): three small points of the quotation PDF (kalmido/office/pdf.py + calc.py of the source tree), no server, no
container. Invented companies and figures only. freelancer-matrix: office (the writer has no organisation in it; the print
model of a person without organisation is covered by the API suites)
 - 10 the discount note reads "auf die rabattfähigen Positionen" / "on the discountable positions" (was "markierten" /
      "marked": the PDF marks nothing), every app language without "marked"
 - 11 an optional / alternative position below a section heading that names it already ("Optionen", "Alternativen",
      "Options") prints without the prefix "Optional:" / "Alternativ:"; below any other heading the prefix stays
      ("Optik" is no option)
 - 12 the section headings of the table in the step of section titles (FS_SUM, as strong as the subtotals at least, was
      FS_SMALL) and with more air above them than before (6 pt)
usage: p21201_a_offer_pdf_test.py            (KALMIDO_SRC = the source tree, default ../ next to tests/)"""
import importlib.util
import os
import sys

N = os.path.dirname(os.path.abspath(__file__))
SRC = os.environ.get("KALMIDO_SRC") or os.path.join(N, "..")


def load(name):
    spec = importlib.util.spec_from_file_location("office_" + name, os.path.join(SRC, "kalmido", "office", name + ".py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


pdf, calc = load("pdf"), load("calc")
sys.path.insert(0, N)
import pdfcheck  # noqa: E402
from kt import check, done  # noqa: E402

# ---------------------------------------------------------------- 10. the discount note
check(calc.label(None, "de", "discount_detail", pct="5") == "5 % auf die rabattfähigen Positionen",
      f"#6175 10: de discount note ({calc.label(None, 'de', 'discount_detail', pct='5')!r})")
check(calc.label(None, "en", "discount_detail", pct="5") == "5 % on the discountable positions", "#6175 10: en discount note")
check(calc.label(None, "de", "discount_detail_amount") == "Fester Betrag auf die rabattfähigen Positionen", "#6175 10: de fixed amount note")
for lg in ("fr", "nl", "es", "it"):
    s = calc.label(None, lg, "discount_detail", pct="5") + " / " + calc.label(None, lg, "discount_detail_amount")
    check("discountable" not in s and not any(w in s for w in ("marqu", "gemarkeerd", "marcad", "contrassegn")), f"#6175 10: {lg} translated, nothing 'marked' ({s})")

# ---------------------------------------------------------------- 11. no doubled "Optional:" below "Optionen"
ou = calc.opt_label_under
check(ou("Optional:", "Optionen") == "" and ou("Optional:", "Optionale Leistungen") == "" and ou("Alternativ:", "Alternativen") == "",
      "#6175 11: de: no prefix below a heading that names it")
check(ou("Optional:", "Options") == "" and ou("Alternative:", "Alternatives") == "" and ou("En option :", "Options") == "",
      "#6175 11: en / fr likewise")
check(ou("Optional:", "Dreh") == "Optional:" and ou("Optional:", "Optik und Objektive") == "Optional:" and ou("Optional:", "") == "Optional:"
      and ou("Alternativ:", "Optionen") == "Alternativ:", "#6175 11: the prefix stays below any other heading (also 'Optik')")

# ---------------------------------------------------------------- 12. stronger section headings with more air
CO = {"name": "Beispielstudio GmbH", "lines": ["Musterweg 1", "12345 Musterstadt"], "color": "#2f5d8a"}


def money(v):
    return f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".") + " €"


def item(i, title, total=100):
    return {"kind": "item", "pos": i, "title": title, "qty": 1, "qty_text": "1", "unit_text": "Tag", "rate": total,
            "rate_text": money(total), "tax_pct": 19, "total": total, "total_text": money(total)}


ln, k = [], 0
for name in ("Konzeption", "Dreh"):
    ln.append({"kind": "heading", "title": name})
    for _ in range(3):
        k += 1
        ln.append(item(k, f"{name} Teil {k}"))
    ln.append({"kind": "subtotal", "label": f"Zwischensumme {name}", "title": name, "total": 300, "total_text": money(300)})
m = {"kind": "offer", "lang": "de", "currency": "EUR", "number": "KVA-2026-201", "date": "2026-11-15", "date_text": "15.11.2026",
     "title": "Angebot", "project_title": "Imagefilm Hafenlichter", "company": CO,
     "recipient": {"name": "Beispielkunde AG", "lines": ["Beispielkunde AG", "Marktplatz 2", "54321 Beispielort"]},
     "meta": [["Angebot Nr.", "KVA-2026-201"], ["Datum", "15.11.2026"]], "lines": ln, "intro": "Sehr geehrte Damen und Herren,",
     "totals": {"net": 600, "rows": [["Summe netto", money(600)]], "show_tax_lines": False}, "rights": {},
     "labels": {"pos": "Pos.", "title": "Leistung", "qty": "Menge", "unit_price": "Preis", "total": "Gesamt", "vat": "MwSt."}}
data = pdf.office_pdf(m)
pg = pdfcheck.layout(data)


def find(s):
    return [t for p in pg for t in p["texts"] if t["s"] == s]


hd, sub, it4, it5 = find("DREH"), find("Zwischensumme Konzeption"), find("Dreh Teil 4"), find("Dreh Teil 5")
check(hd and sub and it4 and it5, f"#6175 12: heading, subtotal and rows printed ({len(hd)} {len(sub)} {len(it4)} {len(it5)})")
if hd and sub and it4 and it5:
    h, s, a, b = hd[-1], sub[-1], it4[-1], it5[-1]
    check(h["size"] >= s["size"] and h["bold"], f"#6175 12: the heading at least as strong as the subtotal ({h['size']} / {s['size']})")
    check(abs(h["size"] - max(pdf.PDF_FS_MIN, pdf.FS_SUM + pdf.PDF_FS_DELTA)) < 0.01,  # look A of a quotation
          f"#6175 12: the heading in the step FS_SUM ({h['size']})")
    pitch = b["y"] - a["y"]  # one table row
    # the subtotal's text sits 4 pt into its row (a row high): was a row - 4 + 11 pt down to the heading text (25.8 pt), now 6 pt more
    check(h["y"] - s["y"] >= pitch + 10, f"#6175 12: more air above the heading ({h['y'] - s['y']:.1f} pt after the subtotal, a row is {pitch:.1f})")
check(not pdfcheck.problems(data), f"#6175 12: clean {pdfcheck.problems(data)[:3]}")
sys.exit(done("p21201_a_offer_pdf"))
