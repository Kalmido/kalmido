#!/usr/bin/env python3
# kalmido-suite: fresh
"""2.1381.0 (#6428, audit #4780; the rest of #4379 F2): every call to an outside server has a total limit, also before the
body. Own container (start.sh); a server inside it answers drop by drop (a byte every 0.3 s, far below every socket timeout).
Invented addresses (.test) only.
freelancer-matrix: own
 - cal_http without `until` (calendar subscriptions, feeds, bookmarks, CardDAV, CalDAV writes, contact photos, OIDC):
   headers dripping end at deadline / CAL_DEADLINE ("timeout"), before only the body was bounded
 - a connection that comes up only AFTER the watchdog of cal_until fired (a slow connect) is shut at once: cal_http(until)
   and a webhook delivery (_wh_post, the deliveries' shared path) end near their limit instead of dripping on
 - _cal_connector: one connect deadline (CAL_CONNECT) over at most CAL_ADDRS checked addresses (a name with many silent
   addresses); accounts/servers.py _msv_connector is the same connector with its own numbers
 - the Paperless-ngx request, a page of the Linear import and a Karakeep request run under cal_until: headers dripping
   end at their limit
 - the SSRF guard is unchanged: an internal address without the allow-list stays "blocked"
usage: p21381_6428_fetch_deadline_test.py <datadir>      (KMT_NOSTART=1 / P21381F_NOSTART=1: a running server)"""
import json
import subprocess
import sys

import kt
from kt import CT, check, done

kt.fresh(prefix="P21381F")
kt.docker_logs_on_first_fail()


def py(code):
    """Runs code inside the test container (the app's modules importable); -> the last JSON line it printed."""
    r = subprocess.run(["docker", "exec", "-i", CT, "python", "-c", code], capture_output=True, text=True, timeout=900)
    if r.returncode:
        print("PY FAILED:", r.stdout[-2000:], r.stderr[-3000:], flush=True)
    for ln in reversed((r.stdout or "").splitlines()):
        if ln.startswith("{"):
            return json.loads(ln)
    return {}


CODE = r"""
import http.server, json, socket, threading, time, app
from kalmido.calendars import subscriptions as S
from kalmido.integrations import webhooks as WH
from kalmido.integrations import imp_linear as LIN
from kalmido.paperless import ngx as P
from kalmido.life import karakeep as K
from kalmido.accounts import servers as MSV
class Drip(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    def log_message(self, *a):
        pass
    def answer(self):
        n = int(self.headers.get("Content-Length") or 0)
        if n:
            self.rfile.read(n)
        try:
            self.wfile.write(b"HTTP/1.1 200 OK\r\nX-Slow: ")  # the status line, then a header drop by drop
            self.wfile.flush()
            for _ in range(100):  # 30 s
                self.wfile.write(b"x")
                self.wfile.flush()
                time.sleep(0.3)
        except OSError:
            pass
    do_GET = do_POST = do_PATCH = answer
srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Drip)
srv.daemon_threads = True
PORT = srv.server_address[1]
threading.Thread(target=srv.serve_forever, daemon=True).start()
U = f"http://127.0.0.1:{PORT}"
AL = frozenset({("127.0.0.1", PORT)})
out = {}
def run(k, fn):
    t0 = time.monotonic()
    try:
        out[k] = fn()
    except S.CalError as e:
        out[k] = e.code
    except (P.PlError, K.KkError) as e:
        out[k] = getattr(e, "code", None) or str(e.args[0] if e.args else e)
    except Exception as e:  # noqa: BLE001  (the Linear import: BadInput with its text)
        out[k] = type(e).__name__
    out[k + "_s"] = round(time.monotonic() - t0, 1)

# 1. cal_http without until: the deadline bounds the header phase too
S.CAL_DEADLINE = 2
run("cal_nountil", lambda: S.cal_http(U + "/head", allow=AL)[0])
run("cal_deadline", lambda: S.cal_http(U + "/head", allow=AL, timeout=10, deadline=2)[0])
S.CAL_DEADLINE = 60

# 2. a connection that comes up after the watchdog fired (a connect taking 1.5 s, the limit 0.5 s)
Real = socket.socket
class LateSock(Real):
    def connect(self, sa):
        if sa[1] == PORT:
            time.sleep(1.5)  # the watchdog fires meanwhile; no socket of this call is registered yet
        return super().connect(sa)
socket.socket = LateSock
WH.CAL_SEND_S = 0.5
run("cal_late", lambda: S.cal_http(U + "/head", allow=AL, until=time.monotonic() + 0.5)[0])
run("wh_late", lambda: WH._wh_post(U + "/head", "s3cret", "ping", "d1", 1, b"{}", AL)[3])
socket.socket = Real

# 3. one connect deadline over at most CAL_ADDRS addresses: a name with six silent addresses
tries = []
class SilentSock(Real):
    def connect(self, sa):
        if sa[1] == 9:
            tries.append(sa)
            time.sleep(min(self.gettimeout() or 5, 0.8))
            raise socket.timeout("silent")
        return super().connect(sa)
real_gai = socket.getaddrinfo
socket.getaddrinfo = lambda host, port, *a, **k: ([(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.%d" % i, 9)) for i in range(1, 7)]
                                                   if host == "many.test" else real_gai(host, port, *a, **k))
socket.socket = SilentSock
MANY = frozenset({("many.test", 9)})
run("addrs", lambda: S._cal_connector(MANY)(("many.test", 9), 20) and "connected")
out["addrs_tries"] = len(tries)
tries.clear()
S.CAL_CONNECT = 2
run("connect", lambda: S._cal_connector(MANY)(("many.test", 9), 20) and "connected")
out["connect_tries"] = len(tries)
S.CAL_CONNECT = 10
tries.clear()
MSV.MSV_CONNECT = 1
run("msv", lambda: MSV._msv_connector(MANY)(("many.test", 9), 20) and "connected")
out["msv_tries"] = len(tries)
socket.socket = Real
socket.getaddrinfo = real_gai

# 4. Paperless, Linear, Karakeep: headers dripping end at their limit
P.PL_DEADLINE = 2
P.plh_allow = lambda c, url=None: AL
run("pl", lambda: P._pl_get1(None, U, "tok", "/api/", 10, False, 1000))
run("lin", lambda: LIN.lin_post(U + "/graphql", AL, "lin_api_k", None, time.monotonic() + 2))
K.KK_TIMEOUT = 2
K.unseal = lambda *a: "key"
S.cal_allow = lambda c, purpose=None: AL
run("kk", lambda: K.kk_req(None, {"user_id": 1, "token": "x", "url": U}, "/bookmarks"))

# 5. the SSRF guard holds: an internal address without the allow-list
run("ssrf", lambda: S.cal_http("http://127.0.0.1:%d/head" % PORT)[0])
out["stack"] = len(getattr(S._CAL_WATCH, "stack", None) or [])
print(json.dumps(out))
"""
j = py(CODE)
print(json.dumps(j), flush=True)
for k, lim, what in (("cal_nountil", 5, "cal_http without until: headers dripping end at CAL_DEADLINE"),
                     ("cal_deadline", 5, "cal_http(deadline=2): the deadline bounds the header phase, too"),
                     ("cal_late", 4, "cal_http(until): a connection made after the watchdog fired is shut"),
                     ("wh_late", 4, "webhook: a connection made after the watchdog fired is shut")):
    check(j.get(k) == "timeout" and j.get(k + "_s", 99) < lim, f"#6428: {what} ({j.get(k)}, {j.get(k + '_s')} s)")
check(j.get("addrs_tries") == 3 and j.get("addrs_s", 99) < 4, f"#6428: at most CAL_ADDRS (3) of six addresses are tried "
      f"({j.get('addrs_tries')}, {j.get('addrs_s')} s, {j.get('addrs')})")
check(j.get("connect_tries", 9) <= 3 and j.get("connect_s", 99) < 3.5 and j.get("connect") in ("timeout", "TimeoutError"),
      f"#6428: one connect deadline over all addresses ({j.get('connect_tries')}, {j.get('connect_s')} s, {j.get('connect')})")
check(j.get("msv_tries", 9) <= 2 and j.get("msv_s", 99) < 2.5, f"#6428: _msv_connector keeps its own deadline ({j.get('msv_tries')}, {j.get('msv_s')} s)")
check(j.get("pl") == "timeout" and j.get("pl_s", 99) < 5, f"#6428: Paperless: headers dripping end at PL_DEADLINE ({j.get('pl')}, {j.get('pl_s')} s)")
check(j.get("lin") == "BadInput" and j.get("lin_s", 99) < 5, f"#6428: Linear: a page ends at the fetch's deadline ({j.get('lin')}, {j.get('lin_s')} s)")
check(j.get("kk") == "network" and j.get("kk_s", 99) < 5, f"#6428: Karakeep: one request ends at KK_TIMEOUT ({j.get('kk')}, {j.get('kk_s')} s)")
check(j.get("ssrf") == "blocked", f"#6428: the SSRF guard is unchanged ({j.get('ssrf')})")
check(j.get("stack") == 0, f"#6428: no watchdog stays registered ({j.get('stack')})")
sys.exit(done("p21381_6428_fetch_deadline"))
