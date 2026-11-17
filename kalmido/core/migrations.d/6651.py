"""2.1337.0 (#6651): file_text.anon = 1 when the file came from a source a stranger can fill (a public form, a file request, a
mail to a task address): its recognition gets the shorter clock (docs/ocr.py OCR_ANON_S, files/textscan.py ts_mark_anon).
New column with a DEFAULT: an older version ignores it."""
MIGRATIONS = [
    ("file_text", "anon", "ALTER TABLE file_text ADD COLUMN IF NOT EXISTS anon BIGINT NOT NULL DEFAULT 0"),
]
