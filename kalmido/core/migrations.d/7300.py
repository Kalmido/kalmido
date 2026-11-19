"""(#7300): "Created by" of a quotation (office_docs.author_id, kalmido/office/docauthor.py): the member named on
it and on its PDF as "Your contact"; NULL = nobody (older documents: the number's {initials} fall back to created_by). No FK,
like contact_id. New nullable column: an older version ignores it."""
MIGRATIONS = [
    ("office_docs", "author_id", "ALTER TABLE office_docs ADD COLUMN IF NOT EXISTS author_id BIGINT"),  # no FK: a finalised document never changes (a deleted account leaves the id, its name then prints as none), like contact_id
]
