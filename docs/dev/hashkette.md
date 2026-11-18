# The daily check of the office hash chain

*Since 2.1309.0 (#6467), marks and savepoints since 2.1333.0 (#6770). For developers of Kalmido.*

`office/chain.py hch_watch_tick` runs in the watchdog (notify/push.py), once after the start and then daily. It recomputes
every office's chains (`hch_check`) and remembers what it already reported in two global settings:

- `office_chain_watch` = `{office id: "chain:seq:id:reason"}`: the break reported last. The same break the next day says
  nothing again; a chain intact again forgets it.
- `office_chain_unreadable` = `{office id: {id, since, last, told}}`: an office with a link its key cannot open now
  (`reason: unreadable`, e.g. a key restored from another backup). Found on `HCH_UNREAD_DAYS` (3) days in a row, it gets one
  admin alert of its own; a day without a check, or the office readable again, starts the count anew. The check goes on
  behind such a link with the stored hash, so a real break further on is still found.

**What the marks protect against.** They lie in the same database as the chains. They catch a mistake: a script, a broken
migration, a restore, a hand edit of a document. They do not catch someone with write access to the database: whoever can
change a finalised document there can recompute its chain or set the mark to the break, and no alert comes. Proof against
that needs the chain heads outside the database (the GoBD export's `chain_heads.csv`, `hch_heads`), compared later.

**Savepoints.** Each office runs in its own savepoint (`c.savepoint()`): an office whose check fails rolls back only its own
statements, never the `chain_broken` log lines of the offices checked before it in the same run (a plain `c.rollback()` did,
and dropped the system context with them). A new statement in the loop belongs inside that block.
