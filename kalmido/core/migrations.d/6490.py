"""2.1309.0 (#6490): an invoice position made from a quotation's markup remembers how the quotation showed it:
office_doc_items.sur_pct = the percentage, sur_base = the base it is computed on (home currency, like rate). The invoice then
prints "15 %" | base | amount instead of "1 flat" | amount | amount (office/calc.py inv_sur_display); the position itself stays
1 x amount (sums, e-invoice). New nullable columns only: older versions ignore them, old rows keep NULL (printed as before)."""
MIGRATIONS = [
    ("office_doc_items", "sur_pct", "ALTER TABLE office_doc_items ADD COLUMN IF NOT EXISTS sur_pct NUMERIC(14,4)"),
    ("office_doc_items", "sur_base", "ALTER TABLE office_doc_items ADD COLUMN IF NOT EXISTS sur_base NUMERIC(22,12)"),
]
