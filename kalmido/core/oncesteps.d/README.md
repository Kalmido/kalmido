# oncesteps.d - one-shot data steps of the start, one file per task (#7445)

A new one-shot of the start (settings flag `migr_*`) is a file `<task id>[_a-z0-9].py` here, never a line at the end of
`kalmido/core/oncesteps.py` `STEPS`:

```python
"""(#1234): what the step does and why once."""
from .db import gset  # the fragment runs as a module of kalmido.core (relative imports like oncesteps.py)
from .pg import system_ctx


def migr_thing1234(c):
    with system_ctx(c):  # every organisation's rows (row-level security)
        c.execute("UPDATE ...")
    gset(c, "migr_thing1234", "1")  # optional: the runner writes the flag after a once step that did not


STEPS = [("cdn_backfill", "migr_thing1234", True, migr_thing1234)]  # (phase, key, once, f)
```

- Files load in name order (`once_frag_load`); `run_phase` runs a phase's fragment steps right behind its fixed `STEPS`.
- `tools/check_migrations.py` checks: the file name, `STEPS` a list of (phase, key, once, function of this file), the phase one
  of `oncesteps.STEPS`, the key unique over `STEPS` and all fragments and not in `RETIRED`, a `migr_*` flag only in the
  fragment whose `STEPS` has that key.
- Retiring it later (core/db.py `MIN_FROM`): delete the file and put its key into `oncesteps.RETIRED`.
