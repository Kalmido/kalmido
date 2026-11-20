"""(#6500): the sessions of before get sessions.remember (migrations.d/6500.py) once: a sign-in with "Stay signed in" lived
longer than one day (start_session: one day without it, SESSION_DAYS with it), a support session never counts. From here on
start_session writes the column and accounts/session.py session_remember reads only it (no rule from the length any more)."""
from .pg import system_ctx


def migr_remember6500(c):
    with system_ctx(c):  # every account's sessions
        c.execute("UPDATE sessions SET remember = (expires_at - created_at > INTERVAL '36 hours' AND COALESCE(via, '') <> 'support' "
                  "AND grant_id IS NULL) WHERE remember IS NULL")


STEPS = [("cdn_backfill", "migr_remember6500", True, migr_remember6500)]  # (phase, key, once, f)
