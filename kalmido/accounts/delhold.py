"""2.1298.0 (#6395): an admin's lock holds the final deletion an account asked for (admin/selfdelete.py) until an admin
releases it (it runs at once, or on its old day when that is still ahead) or rejects it (the deletion is off, the account
stays locked) -- at most SDL_HOLD after the lock: then it runs without a decision (the right to erasure is not put off for
ever). The plan of users.delete_plan notes it: "admin" (when the lock came, users.sdl_admin_locked), "release" (when an admin
released it), "told" (the stages the admins heard of in the bell). No routes, no imports from the app: the sign-in
(accounts/login.py), the user management (accounts/users.py) and the deletion (admin/selfdelete.py) read it."""
import json
from datetime import timedelta

from ..core.db import iso, parse_iso
from ..core.i18n import N_

SDL_HOLD = timedelta(days=30)  # decided 16.11.2026: at most 30 days from the lock
SDL_HELD = N_("The deletion of your account is on hold for a review. It happens by {0} at the latest.")  # tr() by the caller


def dh_plan(u):
    try:
        p = json.loads(u["delete_plan"] or "{}")
    except (TypeError, ValueError, KeyError, IndexError):
        p = {}
    return p if isinstance(p, dict) else {}


def sdl_hold_until(plan):
    """The end of the hold (datetime): the admin's lock + SDL_HOLD, or None (no admin's lock in the plan)."""
    try:
        return parse_iso(plan["admin"]) + SDL_HOLD if plan.get("admin") else None
    except (TypeError, ValueError):
        return None


def sdl_held(u):
    """The final deletion of the users row u waits for an admin's decision: an admin locked it while it waited, nobody
    released it yet, it is still locked. -> the end of the hold (datetime) or None."""
    if not u["delete_at"] or not u["disabled"]:
        return None
    p = dh_plan(u)
    return None if p.get("release") else sdl_hold_until(p)


def sdl_hold_dict(u):
    """For the admins (user management, the hoster's console): {until, at, release} of an account whose deletion an admin's
    lock holds or held (released: it runs on "at" or at once), else None. States and days only."""
    if not u["delete_at"] or not u["disabled"]:
        return None
    p = dh_plan(u)
    until = sdl_hold_until(p)
    if not until:
        return None
    return {"until": iso(until), "at": str(u["delete_at"]), "release": bool(p.get("release"))}
