"""(#6408): ONE budget of web threads of this process for every request that holds a thread for long: an agent's
long-poll (agents/api.py), a hosted MCP call (agents/mcpremote.py) and an assistant call (assistant/web.py). Before, the three had
caps of their own (16 + 16 + none) that together passed the 24 threads and filled waitress' queue for people ("Task queue
depth", live 17.-19.11.2026); now they share LONG_SLOTS, so the reserve of threads stays free for people in the browser.
LONG_SLOTS = the web threads less LONG_RESERVE (at least LONG_MIN, but never more than half of the threads: a small
KALMIDO_THREADS keeps room for normal requests); KALMIDO_AGENT_WAITERS overrides (2.391.0 A, #3360: the name it had for the
long-polls alone).
No kind takes the whole budget: each kind holds at most LONG_SLOTS - KIND_RESERVE places, so waiting agents never lock the hosted
MCP and the assistant out of the server (and MCP calls never all agents) - the others always find KIND_RESERVE places."""
import threading

from .env import env_int
from .pg import WEB_THREADS

LONG_RESERVE, LONG_MIN = 8, 6
LONG_SLOTS = max(1, env_int("KALMIDO_AGENT_WAITERS", max(min(LONG_MIN, WEB_THREADS // 2), WEB_THREADS - LONG_RESERVE)))
LONG_KINDS = ("poll", "mcp", "assistant")
KIND_RESERVE = max(1, LONG_SLOTS // 4) if LONG_SLOTS > 1 else 0  # places one kind always leaves to the others
_LOCK = threading.Lock()
_TAKEN = {}  # kind -> places taken


def long_slot_take(kind):
    """Take one place for a long request (kind of LONG_KINDS). False = all taken (the caller answers busy at once). Every True
    needs one long_slot_give(kind)."""
    with _LOCK:
        if sum(_TAKEN.values()) >= LONG_SLOTS or _TAKEN.get(kind, 0) >= LONG_SLOTS - KIND_RESERVE:
            return False
        _TAKEN[kind] = _TAKEN.get(kind, 0) + 1
        return True


def long_slot_give(kind):
    with _LOCK:
        n = _TAKEN.get(kind, 0) - 1
        if n > 0:
            _TAKEN[kind] = n
        else:
            _TAKEN.pop(kind, None)


def long_slots():
    """{kind: places taken} of this process (Administration's health view, tests)."""
    with _LOCK:
        return dict(_TAKEN)
