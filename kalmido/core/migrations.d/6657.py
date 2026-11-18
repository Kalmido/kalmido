"""2.1368.0 (#6657, Fable re-check N2 of #6321): a stamp per knowledge page -- wiki_pages.wem_at = the page's updated_at when
this version last wrote the page (and so kept its rows of wiki_embeds, wiki/wkembed.py). The trigger kalmido_wem_at sets it at
every write of updated_at, but only on a connection of this version (the session setting app.wem6657 that core/pg.py
SESSION_OPTIONS gives every connection of the app): a version without it (a rollback), a hand-written UPDATE or a script
leaves the stamp behind. The start (wkembed.wem_embeds_start) sets every picture row of a page whose stamp does not match
its updated_at to nobody (user_id NULL: no picture through a share until someone puts it in again), then stamps the pages.
  wem_at NULL = not known yet (the pages of before, a page an older version made): the start looks at it as before #6657
  (the pages changed since the start before) and stamps it.
New nullable column, a function and a trigger that only writes that column: an older version ignores all three."""
SCHEMA = """
CREATE OR REPLACE FUNCTION kalmido_wem_at() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF current_setting('app.wem6657', true) = 'on' THEN
    NEW.wem_at := NEW.updated_at;
  END IF;
  RETURN NEW;
END $$;
CREATE OR REPLACE TRIGGER kalmido_wem_at BEFORE INSERT OR UPDATE OF updated_at ON wiki_pages FOR EACH ROW EXECUTE FUNCTION kalmido_wem_at();
"""
MIGRATIONS = [
    ("wiki_pages", "wem_at", "ALTER TABLE wiki_pages ADD COLUMN IF NOT EXISTS wem_at TIMESTAMPTZ"),
]
