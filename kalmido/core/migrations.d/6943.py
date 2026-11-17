"""2.1345.0 (#6943): the markup ("Zuschlag") of a quotation as a fixed amount, like the discount since #5815.
office_docs.markup_amount = a fixed net amount in the home currency (NULL = none: the percent markup_pct counts as before);
set, it counts instead of the percent (markup_pct then 0, so the markup stays on). New nullable column only: an older
version ignores it and computes the percent as before."""
MIGRATIONS = [
    ("office_docs", "markup_amount", "ALTER TABLE office_docs ADD COLUMN IF NOT EXISTS markup_amount NUMERIC(14,2)"),
]
