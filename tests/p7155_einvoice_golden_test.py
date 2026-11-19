#!/usr/bin/env python3
# kalmido-suite: after=office_einvoice nodata
"""2.1407 (#7155): one EN 16931 value model for CII and UBL -- the XML stays the same byte for byte.
The cases below (all tax categories, mixed rates with exempt and zero rated lines, a position's own discount and a fixed
discount line (#5815), a surcharge, a sub-cent foreign currency price with its rounding charge, USD with BT-111, credit
note, flat rate, final invoice with progress invoices, cash discount, no IBAN, free address lines, text notes) are built
as ZUGFeRD, XRechnung CII and UBL (Peppol, XRechnung, EN 16931) and compared with the files the builders wrote before the
merge (tests/fixtures/einvoice_7155.json.gz: {case.form: XML}, written by the code of 2.1406 with --write). A difference names the case and the
first differing line.
usage: p7155_einvoice_golden_test.py [--write]   (KALMIDO_SRC = the source tree, default ../ next to tests/)"""
import copy
import difflib
import gzip
import json
import importlib.util
import os
import sys

N = os.path.dirname(os.path.abspath(__file__))
SRC = os.environ.get("KALMIDO_SRC") or os.path.join(N, "..")
GOLD = os.path.join(N, "fixtures", "einvoice_7155.json.gz")
spec = importlib.util.spec_from_file_location("einvoice", os.path.join(SRC, "kalmido", "office", "einvoice.py"))
ein = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ein)
sys.path.insert(0, N)
from kt import FAILS, OKS, check  # noqa: E402

SENDER = {"name": "Studio  Nordlicht GmbH", "street": "Hafenstraße 12", "zip": "20457", "city": "Hamburg", "country": "DE",
          "address_extra": "Hinterhaus", "email": "post@beispiel-studio.example", "phone": "+49 40 000000", "tax_number": "12/345/67890",
          "vat_id": "DE123456789", "iban": "DE02 1203 0000 0000 2020 51", "bic": "BYLADEM1001", "bank_name": "Beispielbank",
          "register_no": "HRB 00000", "managing_directors": "Jana Muster"}
RECIPIENT = {"name": "Beispielkunde AG", "name_extra": "Abteilung Film", "street": "Marktstraße 5", "zip": "50667", "city": "Köln",
             "country": "DE", "vat_id": "DE987654321", "customer_no": "K-0042", "buyer_reference": "04011000-12345-03",
             "email_invoice": "rechnung@beispielkunde.example", "extra": "Postfach 7",
             "contact": {"name": "Max Beispiel", "phone": "+49 221 000", "email": "max@beispielkunde.example"}}


def item(pos, title, rate, qty="1", net=None, unit="flat", pct=19, tax="standard", **kw):
    from decimal import Decimal
    net = net if net is not None else str((Decimal(str(qty)) * Decimal(str(rate))).quantize(Decimal("0.01")))
    return {"kind": "item", "pos": pos, "title": title, "qty": qty, "unit": unit, "rate": rate, "tax": tax, "tax_pct": pct,
            "net": net, "total": net, **kw}


def base(**kw):
    m = {"kind": "invoice", "lang": "de", "currency": "EUR", "locked": True, "number": "RE-2026-0100", "date": "2026-05-08",
         "project_title": "Imagefilm  Frühjahr\n2026", "order_ref": "PO-7", "service_from": "2026-04-01", "service_to": "2026-04-30",
         "due_date": "2026-05-22", "vat_mode": "vat", "vat_note_key": "", "vat_note_text": "",
         "company": {"name": "Studio Nordlicht GmbH"}, "sender_fields": dict(SENDER), "recipient": copy.deepcopy(RECIPIENT),
         "intro": "Sehr geehrte Damen und Herren,", "closing": "Vielen Dank.",
         "rights": {"title": "Rechteübertragung", "rows": [["Zeit", "unbegrenzt"], ["", "weltweit"]], "note": "Im Übrigen gilt der RV."},
         "lines": [{"kind": "heading", "title": "Dreh  und Schnitt"}, item(1, "Drehtag", "1200.00", "2", unit="day", detail="Kamera + Ton"),
                   {"kind": "text", "text": "Nach Absprache."}, item(2, "Schnitt", "85.00", "7.5", unit="hour"),
                   {"kind": "text", "text": "Am Ende."}],
         "totals": {"net": "3037.50", "tax_lines": [{"pct": "19", "amount": "577.13"}], "tax": "577.13", "gross": "3614.63"},
         "payment": {"iban": SENDER["iban"], "bic": SENDER["bic"], "text": "Zahlbar bis 22.05.2026 ohne Abzug."}}
    m.update(kw)
    return m


def novat(key, **kw):
    m = base(vat_mode="novat", vat_note_key=key, **kw)
    for ln in m["lines"]:
        if ln["kind"] == "item":
            ln["tax_pct"] = 0
    m["totals"] = {"net": "3037.50", "tax_lines": [], "tax": "0.00", "gross": "3037.50"}
    return m


def cases():
    out = {}
    out["standard"] = base()
    mixed = base(exempt_reason="Heilbehandlung nach § 4 Nr. 14 UStG")  # 19 %, 7 %, exempt 0 % (E), zero rated (Z)
    mixed["lines"] = [item(1, "Film", "1000.00"), item(2, "Buch", "50.00", "3", pct=7, tax="reduced"),
                      item(3, "Beratung", "200.00", pct=0, tax="exempt"), item(4, "Export UK", "300.00", pct=0, tax="standard")]
    mixed["totals"] = {"net": "1650.00", "tax_lines": [{"pct": "19", "amount": "190.00"}, {"pct": "7", "amount": "10.50"}], "gross": "1850.50"}
    out["mixed_rates"] = mixed
    out["reverse_AE"] = novat("reverse")
    out["abroad_O"] = novat("abroad")
    sf = dict(SENDER, register_no="")
    out["abroad_O_taxno"] = novat("abroad", sender_fields=sf)
    out["abroad_G_fallback"] = novat("abroad", sender_fields=dict(sf, tax_number=""))
    out["eu_goods_K"] = novat("eu_goods")
    out["export_G"] = novat("export")
    out["small_E"] = novat("small", vat_note_text="Kleinunternehmer nach § 19 UStG.")
    out["unknown_note_E"] = novat("")
    disc = base()  # 2.1042.0 (#5815): a position's own discount, a fixed amount discount line, a surcharge line
    disc["lines"] = [item(1, "Regie", "1000.00", "2", net="1800.00", unit="day", allowance="200.00", list_net="2000.00", discount_pct="10"),
                     item(2, "Licht", "333.335", "3", net="900.00", unit="day", allowance="100.00", list_net="1000.01", discount_pct="10"),
                     {"kind": "surcharge", "title": "Wochenendzuschlag", "rate": "150.00", "qty": "1", "tax_pct": 19, "tax": "standard", "net": "150.00"},
                     {"kind": "producing", "title": "Handling", "net": "45.50", "tax_pct": 19, "tax": "standard"},
                     {"kind": "raw", "title": "Rohdaten (optional)", "net": "99.00", "optional": True, "tax_pct": 19},
                     {"kind": "raw", "title": "Rohdaten", "net": "120.00", "rate": "120.00", "tax_pct": 19, "tax": "standard"},
                     {"kind": "discount", "title": "Rabatt fest", "rate": "-500.00", "qty": "1", "net": "-500.00", "tax_pct": 19, "tax": "standard"},
                     {"kind": "discount", "title": "Rabatt 5 %", "net": "-120.78", "tax_pct": 19, "tax": "standard"}]
    disc["totals"] = {"net": "2394.72", "tax_lines": [{"pct": "19", "amount": "455.00"}], "gross": "2849.72"}
    out["discounts"] = disc
    usd = base(currency="USD")  # a sub-cent price that fits with no places (rounding charge) and BT-111
    usd["lines"] = [item(1, "Minuten", "0.135625", "1000", net="135.63", unit="minute"), item(2, "Odd", "0.1234567", "3", net="0.37"),
                    item(3, "Zeit", "0.1", "7", net="0.71", unit="hour"), item(4, "Zero qty", "10.00", "0", net="10.00"),
                    item(5, "Bits", "0.0000003", "3000000", net="1.00", unit="piece"), item(6, "Neg", "-0.0000003", "3000000", net="-1.00")]
    usd["totals"] = {"net": "146.71", "tax_lines": [{"pct": "19", "amount": "27.87"}], "gross": "174.58", "tax_eur": "25.57", "home": "EUR"}
    out["usd_subcent"] = usd
    chf = base(currency="EUR")
    chf["totals"] = dict(chf["totals"], home="CHF")
    out["eur_in_chf_office"] = chf
    cr = base(kind="credit", number="GS-2026-001", cancels={"number": "RE-2026-0100", "date": "2026-05-08"})
    out["credit"] = cr
    out["credit_no_due_no_text"] = base(kind="credit", number="GS-2026-002", due_date="", payment={}, cancels={"number": "RE-2026-0099"})
    flat = base()
    flat["lines"] = [item(1, "Pauschale Imagefilm", "4500.00", unit="flat"), item(2, "Stück", "12.50", "4", unit="piece"),
                     item(3, "Ohne Einheit", "10.00", unit="")]
    flat["totals"] = {"net": "4560.00", "tax_lines": [{"pct": "19", "amount": "866.40"}], "gross": "5426.40"}
    out["flat"] = flat
    fin = base()  # 2.408.0 (#3520): a final invoice with progress invoices
    fin["abs_prepaid"] = [{"gross": "1190.00"}]
    fin["abs_full"] = {"gross": "3614.63", "prepaid": "1190.00", "tax_lines": [{"pct": "19", "amount": "577.13"}],
                       "note": "Abschlagsrechnung AR-1 vom 01.04.2026: 1.190,00 EUR"}
    fin["totals"] = {"net": "2037.50", "tax_lines": [{"pct": "19", "amount": "387.13"}], "gross": "2424.63"}
    out["final_after_progress"] = fin
    out["progress_326"] = base(type_code="326")
    out["skonto"] = base(payment={"iban": SENDER["iban"], "text": "Zahlbar bis 22.05.2026.\n2 % Skonto bis 15.05.2026.",
                                  "skonto_bt20": "#SKONTO#TAGE=7#PROZENT=2.00#"})
    out["skonto_no_text_no_due"] = base(due_date="", payment={"skonto_bt20": "#SKONTO#TAGE=7#PROZENT=2.00#"})
    out["no_iban_no_due"] = base(due_date="", payment={}, sender_fields=dict(SENDER, iban="", bic="", bank_name=""))
    rc = {"name": "Kunde Ltd", "lines": ["Kunde Ltd", "c/o Office", "Unit 4", "1 High Street", "London", "United Kingdom"],
          "email_invoice": "", "buyer_reference": "", "customer_no": "C-9"}
    out["free_address_uk"] = base(recipient=rc, order_ref="", lang="en", intro="", closing="", rights=None)
    rc2 = {"name": "Kunde GmbH", "lines": ["Kunde GmbH", "Weg 1", "A-1010 Wien"], "country": "AT", "buyer_reference": "X"}
    out["free_address_at"] = base(recipient=rc2, sender_fields=dict(SENDER, phone="", email=""))
    out["vat_note_text_taxed"] = base(vat_note_text="Leistung im Inland.", project_title="")
    return out


FORMS = [("cii-zugferd", lambda m: ein.ein_build(m, "zugferd")), ("cii-xrechnung", lambda m: ein.ein_build(m, "xrechnung")),
         ("ubl-peppol", lambda m: ein.ein_ubl_build(m, "peppol")), ("ubl-xrechnung", lambda m: ein.ein_ubl_build(m, "xrechnung")),
         ("ubl-en16931", lambda m: ein.ein_ubl_build(m, "en16931", "0204:991-1-2", "9930:DE987654321"))]


def build(m, fn):
    try:
        return fn(copy.deepcopy(m))
    except Exception as e:  # noqa: BLE001 -- the refusal is part of the output (XRechnung without buyer reference)
        return f"{type(e).__name__}: {e}\n".encode()


write = "--write" in sys.argv[1:]
got_all = {f"{name}.{form}": build(m, fn).decode() for name, m in cases().items() for form, fn in FORMS}
if write:
    with gzip.open(GOLD, "wt", encoding="utf-8") as fh:
        json.dump(got_all, fh, ensure_ascii=False, indent=0, sort_keys=True)
    print(f"wrote {len(got_all)} reference files to {GOLD}")
    sys.exit(0)
with gzip.open(GOLD, "rt", encoding="utf-8") as fh:
    gold = json.load(fh)
check(sorted(gold) == sorted(got_all), f"the same {len(gold)} cases as the reference: {sorted(set(gold) ^ set(got_all))}")
for key, got in got_all.items():
    want = gold.get(key)
    if want is None:
        continue
    diff = "" if got == want else "\n".join(list(difflib.unified_diff(want.splitlines(), got.splitlines(), "before", "after", lineterm="", n=1))[:12])
    check(got == want, f"{key}: the same XML as before" + (f"\n{diff}" if diff else ""))
print(f"p7155_einvoice_golden: {OKS[0]} ok, {len(FAILS)} failed")
sys.exit(1 if FAILS else 0)
