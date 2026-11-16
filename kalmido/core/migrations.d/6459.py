"""2.1259.0 (#6459): the amount a reminder's "fee paid" counts (office_docs.reminder_fee_paid_amount, home: the reminder's
currency): fee + default interest + flat fee, stored when a person marks it paid (office/invoices.py fd_fee_post,
inv_reminder_paid_claim), emptied when it leaves "paid". NULL on a reminder marked paid before 2.1259 = its fee alone
(office/books.py bk_fees_paid), so old and locked years stay as they were. A free column of a finalised document
(migrations.d/4598.py). New column only: an older version ignores it."""
MIGRATIONS = [
    ("office_docs", "reminder_fee_paid_amount", "ALTER TABLE office_docs ADD COLUMN IF NOT EXISTS reminder_fee_paid_amount NUMERIC(14,4)"),
]
