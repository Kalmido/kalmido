"""2.581.0 (#4803): the background part of the document flows (docs/flows.py): the scheduled flows' tick and the flows' webhook
calls. The webhook of a flow follows the rules of every other webhook (integrations/webhooks.py): the address is checked when
the flow is saved (wh_url_check: https only, no internal address unless an admin allowed the host) and again before each call;
the call itself goes through the same guarded opener (every address the host resolves to must be public, no redirects), signed
with the flow's own secret (X-Kalmido-Signature), retried after the same waits (WH_BACKOFF), then given up ('failed').
2.1321.0 (#6555): like the organisation's webhooks a call goes out only while the flow's author is an admin of the workspace
(else the flow pauses), failed calls are counted at the flow, and a call given up switches the flow's webhook off -- each
told to the admins (docs/flows.py fl_hook_off). The body
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
                            if p and p != "blocked" and not dfh_author_ok(c, r):  # 2.1321.0 (#6555): webhook off / author no admin
                                p = "off"
                    except Exception as e:  # noqa: BLE001
                        print(f"docflows: webhook of run {r['id']} could not be prepared:", type(e).__name__, flush=True)
                        aa_count("watchdog", f"docflows|hook|{type(e).__name__}", "docflows")
                        dfh_retry(c, r["id"], int(r["hook_attempt"] or 0) + 1, type(e).__name__, 0)
                        continue
                    if p is None or p == "blocked":
                        c.execute("UPDATE doc_flow_runs SET hook=? WHERE id=?", ("blocked" if p else "gone", r["id"]))
                        continue
                    if p == "off":
                        c.execute("UPDATE doc_flow_runs SET hook='off' WHERE id=? AND hook='wait'", (r["id"],))
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
                    FL.fl_hook_result(c, r["rule_id"], ok, f"{errc} {status or ''}".strip())  # 2.1321.0 (#6555): counted at the flow
                    if ok:
                        c.execute("UPDATE doc_flow_runs SET hook='done', hook_attempt=? WHERE id=? AND hook='wait'", (att, r["id"]))
                    elif dfh_retry(c, r["id"], att, errc, status):  # the last retry failed: the flow's webhook switches off
                        FL.fl_hook_off(c, r["rule_id"], r["ws"], "failures", f"{errc} {status or ''}".strip())
                c.commit()
            finally:
                c.close()
    return len(todo)


def dfh_author_ok(c, r):
    """2.1321.0 (#6555): may run r's webhook call go out -- its flow's webhook is not off, and the flow's author is still an
    admin of the workspace (docs/flows.py fl_hook_author_ok); a flow whose author is not pauses here (the admins hear it)."""
    f = c.execute("SELECT id, ws, created_by, hook_state FROM doc_rules WHERE id=?", (r["rule_id"],)).fetchone()
    if not f or f["hook_state"]:
        return False
    if FL.fl_hook_author_ok(c, f["ws"], f["created_by"]):
        return True
    FL.fl_hook_off(c, f["id"], f["ws"], "admin")
    return False


def dfh_retry(c, rid, att, errc, status):
    """A failed attempt `att` of run rid's webhook: the next one after WH_BACKOFF, or given up ('failed') after the last. 2.1265.0
    (#6389): a given-up call is counted for the admin alerts (aa_count) too, not only a log line. -> True when given up."""
    if att > len(WH_BACKOFF):
        c.execute("UPDATE doc_flow_runs SET hook='failed', hook_attempt=? WHERE id=? AND hook='wait'", (att, rid))
        print(f"docflows: webhook of run {rid} given up after {att} attempts ({errc} {status or ''})", flush=True)
        aa_count("watchdog", "docflows|webhook_failed", rid)
        return True
    c.execute("UPDATE doc_flow_runs SET hook_attempt=?, hook_next=? WHERE id=? AND hook='wait'",
              (att, time.time() + WH_BACKOFF[att - 1], rid))
    return False


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
