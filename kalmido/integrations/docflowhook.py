"""2.581.0 (#4803): the background part of the document flows (docs/flows.py): the scheduled flows' tick and the flows' webhook
calls. The webhook of a flow follows the rules of every other webhook (integrations/webhooks.py): the address is checked when
the flow is saved (wh_url_check: https only, no internal address unless an admin allowed the host) and again before each call;
the call itself goes through the same guarded opener (every address the host resolves to must be public, no redirects), signed
with the flow's own secret (X-Kalmido-Signature), retried after the same waits (WH_BACKOFF), then given up ('failed'). The body
carries the document's name, labels, dates and link -- never its text, amount or file. KALMIDO_WEBHOOKS=0: no webhook in a flow.
One loop per instance (startup.py wrk_start "docflows")."""
import time

from ..core.db import connect, iso, now_utc
from ..core.env import env_int
from ..core.errors import BadInput
from ..core.pg import system_ctx
from ..accounts.session import GATE
from ..api.v1 import WH_ON
from ..docs import flows as FL
from ..notify.alerts import aa_count
from .webhooks import WH_BACKOFF, wh_allow, wh_send, wh_url_check

DFH_TICK = 5                                         # s between two looks at the waiting webhook calls
DFH_SCHED = env_int("KALMIDO_DOCFLOW_TICK_S", 300, lo=1)  # s between two looks at the scheduled flows
DFH_BATCH = 20


def dfh_check(c, url):
    return wh_url_check(c, url)


if WH_ON and dfh_check not in FL.FL_URL_CHECK:
    FL.FL_URL_CHECK.append(dfh_check)


def dfh_hooks():
    """Send the waiting webhook calls (the network part outside the maintenance gate). -> how many were tried."""
    todo = []
    with GATE.bg():
        c = connect()
        try:
            with system_ctx(c):  # document flows: server-side delivery of every workspace's flow webhooks, nothing handed to a person
                rows = c.execute("SELECT * FROM doc_flow_runs WHERE hook='wait' AND hook_next<=? ORDER BY hook_next, id LIMIT ?",
                                 (time.time(), DFH_BATCH)).fetchall()
                allow = wh_allow(c)
                for r in rows:
                    try:  # 2.1265.0 (#6389): a run whose payload raises waits like a failed call; the others of the batch go out
                        with c.savepoint():
                            p = FL.fl_hook_payload(c, r) if WH_ON else None
                            if p:
                                try:
                                    dfh_check(c, p[0])
                                except BadInput:
                                    p = "blocked"
                    except Exception as e:  # noqa: BLE001
                        print(f"docflows: webhook of run {r['id']} could not be prepared:", type(e).__name__, flush=True)
                        aa_count("watchdog", f"docflows|hook|{type(e).__name__}", "docflows")
                        dfh_retry(c, r["id"], int(r["hook_attempt"] or 0) + 1, type(e).__name__, 0)
                        continue
                    if p is None or p == "blocked":
                        c.execute("UPDATE doc_flow_runs SET hook=? WHERE id=?", ("blocked" if p else "gone", r["id"]))
                        continue
                    todo.append((dict(r), p))
            c.commit()
        finally:
            c.close()
    for r, (url, secret, body) in todo:
        att = int(r["hook_attempt"] or 0) + 1
        ok, status, _ms, errc = wh_send(url, secret, "document.flow", f"dfl-{r['id']}", att, body, allow)
        with GATE.bg():
            c = connect()
            try:
                with system_ctx(c):  # document flows: the result of one call
                    if ok:
                        c.execute("UPDATE doc_flow_runs SET hook='done', hook_attempt=? WHERE id=? AND hook='wait'", (att, r["id"]))
                    else:
                        dfh_retry(c, r["id"], att, errc, status)
                c.commit()
            finally:
                c.close()
    return len(todo)


def dfh_retry(c, rid, att, errc, status):
    """A failed attempt `att` of run rid's webhook: the next one after WH_BACKOFF, or given up ('failed') after the last. 2.1265.0
    (#6389): a given-up call is counted for the admin alerts (aa_count) too, not only a log line."""
    if att > len(WH_BACKOFF):
        c.execute("UPDATE doc_flow_runs SET hook='failed', hook_attempt=? WHERE id=? AND hook='wait'", (att, rid))
        print(f"docflows: webhook of run {rid} given up after {att} attempts ({errc} {status or ''})", flush=True)
        aa_count("watchdog", "docflows|webhook_failed", rid)
    else:
        c.execute("UPDATE doc_flow_runs SET hook_attempt=?, hook_next=? WHERE id=? AND hook='wait'",
                  (att, time.time() + WH_BACKOFF[att - 1], rid))


def dfh_sched():
    with GATE.bg():
        c = connect()
        try:
            with system_ctx(c):  # document flows: server-side scheduled runs of every workspace's flows
                n = FL.fl_tick(c)
            c.commit()
            return n
        finally:
            c.close()


def dfh_loop():
    last = 0.0
    while True:
        time.sleep(min(DFH_TICK, DFH_SCHED))
        try:
            if time.monotonic() - last >= DFH_SCHED:
                last = time.monotonic()
                dfh_sched()
            dfh_hooks()
        except Exception as e:  # noqa: BLE001 -- the loop never dies
            print("docflows:", type(e).__name__, e, iso(now_utc()), flush=True)
            aa_count("watchdog", f"docflows|{type(e).__name__}", "docflows")  # 2.1265.0 (#6389): not only a log line
