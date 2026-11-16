"""2.1284.0 (#6321, Fable review of #6295, finding 1): who brought a file store picture into a knowledge page's text, per page
and file (wiki/wkembed.py wem_embeds_set, called by wiki/pages.py wiki_set_links at every write of a page's text). A share with
"show pictures" hands a picture out only when the share's maker AND this person see the file (wiki/wkshare.py wsh_img_nodes);
before, the page's last editor (wiki_pages.updated_by) stood in, which a rename, a move or a relink also set.
  page_id = the page (the rows go with it);
  node_id = the file store node as written in the text (no FK: a text may name any number; the rights are asked when a
            picture is handed out; a file deleted for good takes its rows along, wkembed.py wem_purged);
  user_id = who embedded it; NULL = nobody: the account is gone, or the embed appeared without a person writing it (a
            relink, a restored version, a text out of a space's lock, an import nobody here stands for) -- no picture
            until someone takes the embed out and puts it in again (nobody else stands in);
  created_at = when the row was made.
No organisation column: a row hangs on its page like wiki_links (derived from the text, read only next to the page's row).
The pages of before get their rows at the first start (wem_embeds_start: the last editor of then, the rule of #6295;
no editor = nobody); every later start looks at the pages changed since the start before (after a rollback).
An embed without a row is never handed out and never becomes "the next writer's".
New table only: an older version ignores it."""
SCHEMA = """
CREATE TABLE IF NOT EXISTS wiki_embeds (  -- 2.1284.0 (#6321): who embedded which file store picture into which page
  page_id BIGINT NOT NULL REFERENCES wiki_pages(id) ON DELETE CASCADE,
  node_id BIGINT NOT NULL, -- no FK: the number written in the text, checked when a picture is handed out
  user_id BIGINT REFERENCES users(id) ON DELETE SET NULL,
  created_at TIMESTAMPTZ NOT NULL,
  PRIMARY KEY (page_id, node_id));
CREATE INDEX IF NOT EXISTS ix6321_wiki_embeds_node ON wiki_embeds(node_id);
CREATE INDEX IF NOT EXISTS ix6321_wiki_embeds_user ON wiki_embeds(user_id) WHERE user_id IS NOT NULL;
"""
