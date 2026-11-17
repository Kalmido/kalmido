"""2.1337.0 (#6600): an organisation that is moving ("Umzug") is read only - ONE lock in the write path, in the database.

An admin of the organisation switches the move on (accounts/orgmove.py: orgs.moving_at, moving_by, moving_by_name, moving_why).
From then on no request writes a row of the organisation any more, whoever sends it (members, agents, API tokens, public forms,
booking pages, file requests, incoming hooks and mails, DAV): the trigger kalmido_zz_moving (function kalmido_moving_guard) sits on every table with an org_id
(the same set as the row-level security policies, core/rls.py org_tables, no hand list) and refuses an INSERT / UPDATE / DELETE
of such a row with SQLSTATE MV_STATE; core/db.py db_error answers it with 423 and MV_MSG. The organisation's own row (orgs, no
org_id) has the trigger kalmido_zz_moving_org: no change while it is moving except the end of the move.

What passes (the transaction-local switch app.move_ok = '1', set by core/pg.py with every context from mv_ok_now()):
- reading requests (GET / HEAD / OPTIONS): their bookkeeping (a read mark, the office log of an opened PDF) goes on;
- work without a request (the watchdog, the queue, the export's own run): it skips a moving organisation itself where it acts
  for it (mv_skip: invoice series, dunning, offers, subscriptions, bank and card hints, bank / mail / calendar / feed fetching,
  webhooks, schedules and rules of agents and lists, newsletter, portal mails) - a housekeeping statement over every
  organisation must never fail for all of them because of one;
- the few writes of a request a move allows (mv_allow): starting / downloading the export, ending the move, deleting the
  organisation (instance admin), the retention export;
- a session that never set app.move_ok (psql, the test suites' own access, pg_dump / pg_restore) and the database's own
  reference actions (pg_trigger_depth() > 1: deleting the organisation takes its rows along).
Tables in MV_FREE never get the trigger: the queue (bg_jobs: the export is a row there), the office log (office_doc_log: who
downloaded the export, the GoBD log of reads), the portal's sign-in rows (portal_logins: signing in stays possible).

Additive: a version before 2.1337 ignores the columns; the triggers it would find let everything through while no organisation
is moving (its way back: DROP TRIGGER kalmido_zz_moving ON <every table>, DROP TRIGGER kalmido_zz_moving_org ON orgs, DROP FUNCTION
kalmido_moving_guard(), kalmido_moving_org())."""
import contextlib
import threading
import time

from flask import g, has_request_context, request

from .i18n import N_
from .db import iso
from .pg import set_move_hook, system_ctx
from .rls import _lock_all, org_tables

MV_STATE = "KM423"  # the SQLSTATE of the triggers (class KM: Kalmido's own)
MV_MSG = N_("The organisation is moving: it is read-only.")  # translated by core/db.py mv_answer
MV_TRIGGER = "kalmido_zz_moving"  # the last BEFORE trigger of a table (by name): it sees org_id after kalmido_orw_fill (core/orgrows.py)
MV_ORG_TRIGGER = "kalmido_zz_moving_org"
MV_FREE = frozenset({"bg_jobs", "office_doc_log", "portal_logins"})
MV_SAFE = frozenset({"GET", "HEAD", "OPTIONS"})

GUARD_SRC = """
DECLARE
  ok TEXT := current_setting('app.move_ok', true);
  o BIGINT;
BEGIN
  IF ok IS NULL OR ok = '1' OR pg_trigger_depth() > 1 THEN
    IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
    RETURN NEW;
  END IF;
  IF TG_OP = 'INSERT' THEN o := NEW.org_id; ELSE o := OLD.org_id; END IF;
  IF o IS NOT NULL AND EXISTS (SELECT 1 FROM orgs WHERE id = o AND moving_at IS NOT NULL) THEN
    RAISE EXCEPTION 'organisation % is moving: read only', o USING ERRCODE = 'KM423', HINT = 'kalmido #6600';
  END IF;
  IF TG_OP = 'UPDATE' AND NEW.org_id IS DISTINCT FROM OLD.org_id AND NEW.org_id IS NOT NULL
     AND EXISTS (SELECT 1 FROM orgs WHERE id = NEW.org_id AND moving_at IS NOT NULL) THEN
    RAISE EXCEPTION 'organisation % is moving: read only', NEW.org_id USING ERRCODE = 'KM423', HINT = 'kalmido #6600';
  END IF;
  IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
  RETURN NEW;
END
"""
ORG_SRC = """
DECLARE
  ok TEXT := current_setting('app.move_ok', true);
BEGIN
  IF ok IS NULL OR ok = '1' OR pg_trigger_depth() > 1 OR OLD.moving_at IS NULL THEN
    IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
    RETURN NEW;
  END IF;
  RAISE EXCEPTION 'organisation % is moving: read only', OLD.id USING ERRCODE = 'KM423', HINT = 'kalmido #6600';
END
"""


_TL = threading.local()


def mv_ok_now():
    """'1' for the running transaction? (core/pg.py Conn._apply_ctx). Outside a request: yes (background work skips by itself),
    except inside mv_strict (the mail import: the lock refuses the mail of a moving organisation, it waits on the mail server)."""
    if getattr(_TL, "strict", 0):
        return False
    if not has_request_context():
        return True
    return request.method in MV_SAFE or bool(g.get("mv_ok"))


@contextlib.contextmanager
def mv_strict(c):
    """Background work on connection c that must not write into a moving organisation (the incoming mail, whose target only the
    importers know): inside the block the lock holds as for a writing request, also in the request contexts the importers open."""
    _TL.strict = getattr(_TL, "strict", 0) + 1
    c._db_ctx = None  # the running transaction takes it with its next statement
    try:
        yield c
    finally:
        _TL.strict -= 1
        c._db_ctx = None


def mv_refused(e):
    """True when database error e is the lock of a moving organisation."""
    return getattr(e, "sqlstate", None) == MV_STATE


set_move_hook(mv_ok_now)


def mv_allow(c=None):
    """This request may write into a moving organisation from now on (the export, ending the move, deleting it). c: the
    request's connection - its running transaction takes the switch with its next statement."""
    g.mv_ok = True
    if c is not None:
        c._db_ctx = None  # core/pg.py Conn._begin applies the context (with app.move_ok) again before the next statement


def _fn(c, name, src):
    if not c.execute("SELECT 1 FROM pg_proc WHERE proname=? AND pronamespace=current_schema()::regnamespace AND prosrc=?",
                     (name, src)).fetchone():
        c.execute(f"CREATE OR REPLACE FUNCTION {name}() RETURNS trigger LANGUAGE plpgsql AS $mv$" + src + "$mv$")


def mv_apply(c):
    """init_db, after core/rls.py apply (same transaction): the functions when their text changed, the trigger on every table
    with an org_id that lacks it (none on MV_FREE), the trigger of orgs. Only what is missing: a start next to the running
    server takes no table lock when nothing changed. Returns the number of triggers made / dropped."""
    _fn(c, "kalmido_moving_guard", GUARD_SRC)
    _fn(c, "kalmido_moving_org", ORG_SRC)
    want = {t for t in org_tables(c) if t not in MV_FREE}
    have = {r[0] for r in c.execute("SELECT r.relname FROM pg_trigger t JOIN pg_class r ON r.oid=t.tgrelid "
                                    "WHERE t.tgname=? AND NOT t.tgisinternal AND r.relnamespace=current_schema()::regnamespace",
                                    (MV_TRIGGER,)).fetchall()}
    org_on = c.execute("SELECT 1 FROM pg_trigger t JOIN pg_class r ON r.oid=t.tgrelid WHERE t.tgname=? AND r.relname='orgs' "
                       "AND r.relnamespace=current_schema()::regnamespace", (MV_ORG_TRIGGER,)).fetchone()
    add, drop = sorted(want - have), sorted(have - want)
    if add or drop:
        _lock_all(c, set(add) | set(drop))  # giving way to a running server, as the policies do
    for t in add:
        c.execute(f"CREATE OR REPLACE TRIGGER {MV_TRIGGER} BEFORE INSERT OR UPDATE OR DELETE ON {t} FOR EACH ROW "
                  "EXECUTE FUNCTION kalmido_moving_guard()")
    for t in drop:
        c.execute(f"DROP TRIGGER IF EXISTS {MV_TRIGGER} ON {t}")
    if not org_on:
        c.execute(f"CREATE OR REPLACE TRIGGER {MV_ORG_TRIGGER} BEFORE UPDATE OR DELETE ON orgs FOR EACH ROW "
                  "EXECUTE FUNCTION kalmido_moving_org()")
    return len(add) + len(drop) + (0 if org_on else 1)


# ---------------------------------------------------------------- the background's one check
MV_TTL_S = 15
_MV = {"at": -1e9, "ids": frozenset()}
_MV_LOCK = threading.Lock()


def mv_orgs(c, fresh=False):
    """The ids of the organisations moving now (read as "system", kept MV_TTL_S seconds for the watchdog's many loops)."""
    with _MV_LOCK:
        if not fresh and time.monotonic() - _MV["at"] < MV_TTL_S:
            return _MV["ids"]
    with system_ctx(c):  # instance structure: which organisations are moving (no content)
        ids = frozenset(r[0] for r in c.execute("SELECT id FROM orgs WHERE moving_at IS NOT NULL").fetchall())
    with _MV_LOCK:
        _MV["at"], _MV["ids"] = time.monotonic(), ids
    return ids


def mv_forget():
    """After a move began / ended in this process: the next mv_orgs reads again."""
    with _MV_LOCK:
        _MV["at"] = -1e9


def mv_skip(c, oid):
    """True when background work for organisation oid rests now (it is moving). None / 0 (private, no organisation): never."""
    return bool(oid) and int(oid) in mv_orgs(c)


def mv_sql(col="org_id"):
    """SQL condition for the background's own SELECTs: the row's organisation is not moving (a NULL one never is)."""
    return f"({col} IS NULL OR {col} NOT IN (SELECT id FROM orgs WHERE moving_at IS NOT NULL))"


def mv_info(r):
    """The move of org row r for the app (None when it is not moving): since, who switched it on, why."""
    try:
        at = r["moving_at"]
    except (KeyError, IndexError):
        return None
    if not at:
        return None
    return {"since": at if isinstance(at, str) else iso(at), "by": r["moving_by"], "by_name": r["moving_by_name"] or "",
            "why": r["moving_why"] or ""}
