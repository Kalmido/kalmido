"""(#6533): offices that exist keep the VAT basis and small business switch they counted with, once."""
from .db import gset  # the fragment runs as a module of kalmido.core (relative imports like oncesteps.py)
from .pg import system_ctx


def migr_tax6533(c):  # (#6533): the office's small business switch and VAT basis have no default any more (a new office
    # chooses both once); the offices that exist keep what they counted with: vat_basis "ist" (the old default) and
    # small_business 0 where the settings hold no value -- a saved row, and an office in use without one (documents or their
    # log, as office/web.py of_pack_choice tells an office in use). Plain keys of the JSON, never the encrypted company lines;
    # a value already there wins. A new database runs it on empty tables.
    with system_ctx(c):  # every organisation's office (row-level security)
        c.execute("""UPDATE office_settings SET data = CAST('{"vat_basis": "ist", "small_business": 0}' AS JSONB) || data
                     WHERE jsonb_typeof(data) = 'object' AND (data->'vat_basis' IS NULL OR data->'small_business' IS NULL)""")
        c.execute("""INSERT INTO office_settings(org_id, data, updated_at)
                     SELECT o.id, CAST('{"vat_basis": "ist", "small_business": 0}' AS JSONB), now() FROM orgs o
                     WHERE NOT EXISTS (SELECT 1 FROM office_settings s WHERE s.org_id = o.id)
                       AND (EXISTS (SELECT 1 FROM office_docs d WHERE d.org_id = o.id) OR EXISTS (SELECT 1 FROM office_doc_log l WHERE l.org_id = o.id))
                     ON CONFLICT (org_id) DO NOTHING""")
    gset(c, "migr_tax6533", "1")


STEPS = [("cdn_backfill", "migr_tax6533", True, migr_tax6533)]  # (phase, key, once, f)
