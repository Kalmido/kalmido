"""2.1401.0 (#7056, Fable re-check of 2.1368 F1-F3, F7): for which shares with pictures a picture embedded in a knowledge page
is confirmed -- wiki_embeds.shares, the keys of those shares (wiki/wkshare.py wsh_ikey: "w<id>" a link of wiki_shares, "p<id>"
a person share by its card). A share shows a picture only when its row names that share (wkshare.wsh_img_nodes, the one check
at the output); its embedder's own save under the share (wkembed.wem_confirm) or the share's pictures switched on over the
page (wem_share_confirm) add the key -- a rename, a move, a merge of folders, the trash, a round trip through another
workspace add nothing.
  shares NULL / empty = confirmed for no share: no picture through any share until one of the two above.
The rows of before are confirmed once for the live shares with pictures that cover their pages (wkembed.wem_ok_start).
New nullable column: an older version ignores it (its rows then lack the keys of what it embedded: no picture, never more)."""
AFTER = [
    "ALTER TABLE wiki_embeds ADD COLUMN IF NOT EXISTS shares TEXT[]",
]
