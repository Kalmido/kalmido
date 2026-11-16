"""2.1254.0 (#6299): office_doc_items.rate keeps 12 places (was NUMERIC(14,4)). Rates are stored in the home currency; a line in
a foreign currency is money(qty x rate x fx). An invoice from a quotation in USD / HUF / JPY takes the quotation's automatic
lines as amount / qty / fx (office/calc.py calc_home_rate), and 4 places x qty x fx missed the cent from qty x fx > ~100
(49,984.02 HUF -> rate 126.3818 -> 49,984.00); the same for the deductions of a final invoice (#4082) and a progress invoice
of a foreign amount. Only wider: the same 10 places before the point, every stored value stays exactly what it was (an older
version reads and writes the column as before), core/db.py col_present skips it once the column has the type."""
AFTER = [
    # widen-ok office_doc_items.rate: NUMERIC(14,4) -> NUMERIC(22,12), the same 10 digits before the point; no value changes
    "ALTER TABLE office_doc_items ALTER COLUMN rate TYPE NUMERIC(22,12)",
]
